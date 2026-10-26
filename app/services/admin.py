import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import Float, case, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.models import ExamAnswer, ExamAttempt, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.admin import (
    AdminUserDetailOut,
    AdminUserRowOut,
    AdminUserUpdate,
    DailyPointOut,
    PlatformStatsOut,
    ScoreBucketOut,
    TopicDifficultyOut,
    UserSort,
)
from app.schemas.common import Page
from app.services import exams as exam_service
from app.services import progress
from app.services.content import TOPICS, ContentStore
from app.services.practice import answer_history

DAILY_WINDOW = 30


def _exam_aggregates():
    """Per-learner completed-exam count, average and best score."""
    return (
        select(
            ExamAttempt.user_id.label("user_id"),
            func.count(ExamAttempt.id).label("exams"),
            func.avg(cast(ExamAttempt.score, Float)).label("average"),
            func.max(ExamAttempt.score).label("best"),
        )
        .where(ExamAttempt.status == STATUS_COMPLETED)
        .group_by(ExamAttempt.user_id)
        .subquery()
    )


async def _count(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where)) or 0


async def platform_stats(db: AsyncSession, content: ContentStore) -> PlatformStatsOut:
    now = utcnow()
    week_ago = now - timedelta(days=7)
    completed = ExamAttempt.status == STATUS_COMPLETED

    agg = _exam_aggregates()
    per_user = (await db.execute(select(agg.c.exams, agg.c.average))).all()
    score_row = (
        await db.execute(
            select(
                func.avg(cast(ExamAttempt.score, Float)),
                func.sum(case((ExamAttempt.score >= settings.EXAM_PASS_MARK, 1), else_=0)),
                func.count(ExamAttempt.id),
            ).where(completed)
        )
    ).one()
    average, passed, total_exams = score_row

    # Day buckets in Kigali time (UTC+2); timestamps are stored as naive UTC.
    since = (now - timedelta(days=DAILY_WINDOW - 1)).astimezone(progress.KIGALI).date()
    signup_day = func.date(User.created_at, "+2 hours")
    exam_day = func.date(ExamAttempt.submitted_at, "+2 hours")
    signups = dict((await db.execute(select(signup_day, func.count()).group_by(signup_day))).all())
    exams_daily = dict((await db.execute(select(exam_day, func.count()).where(completed).group_by(exam_day))).all())
    daily = []
    for i in range(DAILY_WINDOW):
        day = since + timedelta(days=i)
        key = day.isoformat()
        daily.append(DailyPointOut(day=day, signups=signups.get(key, 0), exams=exams_daily.get(key, 0)))

    buckets = dict(
        (await db.execute(select(ExamAttempt.score, func.count()).where(completed).group_by(ExamAttempt.score))).all()
    )
    distribution = [ScoreBucketOut(score=s, count=buckets.get(s, 0)) for s in range(settings.EXAM_QUESTION_COUNT + 1)]

    per_question: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    practice_rows = await db.execute(
        select(
            PracticeAnswer.question_id, func.count(), func.sum(case((PracticeAnswer.is_correct, 1), else_=0))
        ).group_by(PracticeAnswer.question_id)
    )
    exam_rows = await db.execute(
        select(ExamAnswer.question_id, func.count(), func.sum(case((ExamAnswer.is_correct, 1), else_=0)))
        .join(ExamAttempt, ExamAnswer.attempt_id == ExamAttempt.id)
        .where(completed)
        .group_by(ExamAnswer.question_id)
    )
    for qid, n, ok in [*practice_rows.all(), *exam_rows.all()]:
        per_question[qid][0] += n
        per_question[qid][1] += ok or 0
    topic_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for qid, (n, ok) in per_question.items():
        topic = content.topic_of(qid)
        if topic:
            topic_totals[topic][0] += n
            topic_totals[topic][1] += ok

    return PlatformStatsOut(
        users_total=await _count(db, User),
        users_new_7d=await _count(db, User, User.created_at >= week_ago),
        users_active_7d=await _count(db, User, User.last_active_at >= week_ago),
        users_ready=sum(progress.readiness_status(n, avg)[0] for n, avg in per_user),
        exams_total=total_exams or 0,
        exams_7d=await _count(db, ExamAttempt, completed, ExamAttempt.submitted_at >= week_ago),
        average_score=round(average, 2) if average is not None else None,
        pass_rate=round((passed or 0) / total_exams, 4) if total_exams else None,
        practice_answers=await _count(db, PracticeAnswer),
        daily=daily,
        score_distribution=distribution,
        topics=[
            TopicDifficultyOut(
                topic=t["id"],
                name=t["name"],
                answered=topic_totals[t["id"]][0],
                accuracy=round(topic_totals[t["id"]][1] / topic_totals[t["id"]][0], 4)
                if topic_totals[t["id"]][0]
                else None,
            )
            for t in TOPICS
        ],
    )


async def list_users(
    db: AsyncSession, *, search: str | None, sort: UserSort, descending: bool, page: int, page_size: int
) -> Page[AdminUserRowOut]:
    agg = _exam_aggregates()
    exams_col = func.coalesce(agg.c.exams, 0)
    query = select(User, exams_col, agg.c.average, agg.c.best).outerjoin(agg, agg.c.user_id == User.id)
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.where(or_(func.lower(User.name).like(term), func.lower(User.email).like(term)))
    sort_columns = {
        "joined": User.created_at,
        "name": func.lower(User.name),
        "exams": exams_col,
        "average": func.coalesce(agg.c.average, -1),
        "last_active": func.coalesce(User.last_active_at, User.created_at),
    }
    column = sort_columns[sort]
    query = query.order_by(desc(column) if descending else column, User.created_at.desc())

    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = (await db.execute(query.limit(page_size).offset((page - 1) * page_size))).all()
    items = []
    for user, exams, average, best in rows:
        ready, status = progress.readiness_status(exams, average)
        items.append(
            AdminUserRowOut(
                id=user.id,
                email=user.email,
                name=user.name,
                picture_url=user.picture_url,
                plan=user.plan,
                is_active=user.is_active,
                created_at=user.created_at,
                last_active_at=user.last_active_at,
                exams_completed=exams,
                average=round(average, 2) if average is not None else None,
                best=best,
                ready=ready,
                readiness_status=status,
            )
        )
    return Page[AdminUserRowOut](items=items, total=total, page=page, page_size=page_size)


async def user_detail(db: AsyncSession, user: User, content: ContentStore) -> AdminUserDetailOut:
    exams = await progress.completed_exams(db, user.id)
    scores = [e.score or 0 for e in exams]
    history = await answer_history(db, user)
    lessons = await progress.lesson_slugs(db, user.id)
    recent = (
        await db.scalars(
            select(ExamAttempt).where(ExamAttempt.user_id == user.id).order_by(ExamAttempt.started_at.desc()).limit(20)
        )
    ).all()
    return AdminUserDetailOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
        phone=user.phone,
        plan=user.plan,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        last_active_at=user.last_active_at,
        readiness=progress.readiness(scores),
        exams=progress.exam_stats(scores),
        topics=progress.topic_mastery(history, content),
        lessons_completed=len([s for s in lessons if s in content.lessons_by_slug]),
        lessons_total=len(content.lessons),
        practice_answers=await _count(db, PracticeAnswer, PracticeAnswer.user_id == user.id),
        recent_exams=[exam_service.to_summary(e) for e in recent],
    )


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def update_user(db: AsyncSession, user: User, data: AdminUserUpdate) -> User:
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.plan is not None:
        user.plan = data.plan
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user: User) -> None:
    """Removes the learner and, through ON DELETE CASCADE, all of their exams, answers and progress."""
    await db.delete(user)
    await db.commit()
