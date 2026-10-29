import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import Float, case, cast, desc, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.base import utcnow
from app.models import Admin, ExamAnswer, ExamAttempt, ExamOutcome, PracticeAnswer, QuestionExplanation, User
from app.models.exam import ABANDONED, STATUS_COMPLETED
from app.schemas.admin import (
    AdminQuestionOut,
    AdminQuestionsOut,
    AdminUserDetailOut,
    AdminUserRowOut,
    AdminUserUpdate,
    DailyPointOut,
    ExplanationCountsOut,
    ExplanationUpdate,
    PlatformStatsOut,
    QuestionFilter,
    QuestionSort,
    ScoreBucketOut,
    TopicDifficultyOut,
    UserSort,
)
from app.schemas.common import Page
from app.schemas.content import OptionOut
from app.schemas.outcome import AdminTestimonialOut
from app.services import explanations, outcomes, progress
from app.services.content import TOPICS, ContentStore, Question
from app.services.dates import KIGALI

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


def _readiness_aggregates():
    """Per learner, what readiness looks at (see progress.readiness): the exams that count, and the average of the most
    recent READINESS_RECENT_EXAMS of them."""
    ranked = (
        select(
            ExamAttempt.user_id,
            ExamAttempt.score,
            func.row_number()
            .over(partition_by=ExamAttempt.user_id, order_by=ExamAttempt.submitted_at.desc())
            .label("rank"),
        )
        .where(ExamAttempt.status == STATUS_COMPLETED, not_(ABANDONED))
        .subquery()
    )
    recent_score = case((ranked.c.rank <= settings.READINESS_RECENT_EXAMS, cast(ranked.c.score, Float)))
    return (
        select(
            ranked.c.user_id.label("user_id"),
            func.count().label("exams"),
            func.avg(recent_score).label("average"),
        )
        .group_by(ranked.c.user_id)
        .subquery()
    )


def _readiness(exams: int | None, average: float | None) -> tuple[bool, str]:
    return progress.readiness_status(exams or 0, round(average, 2) if average is not None else None)


async def _per_question(db: AsyncSession) -> dict[int, list[int]]:
    """question_id -> [answers, correct answers], across practice and finished exams."""
    per_question: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    practice_rows = await db.execute(
        select(
            PracticeAnswer.question_id, func.count(), func.sum(case((PracticeAnswer.is_correct, 1), else_=0))
        ).group_by(PracticeAnswer.question_id)
    )
    exam_rows = await db.execute(
        select(ExamAnswer.question_id, func.count(), func.sum(case((ExamAnswer.is_correct, 1), else_=0)))
        .join(ExamAttempt, ExamAnswer.attempt_id == ExamAttempt.id)
        .where(ExamAttempt.status == STATUS_COMPLETED)
        .group_by(ExamAnswer.question_id)
    )
    for qid, n, ok in [*practice_rows.all(), *exam_rows.all()]:
        per_question[qid][0] += n
        per_question[qid][1] += ok or 0
    return per_question


async def _count(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where)) or 0


async def platform_stats(db: AsyncSession, content: ContentStore) -> PlatformStatsOut:
    now = utcnow()
    week_ago = now - timedelta(days=7)
    completed = ExamAttempt.status == STATUS_COMPLETED

    ready = _readiness_aggregates()
    per_user = (await db.execute(select(ready.c.exams, ready.c.average))).all()
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
    since = (now - timedelta(days=DAILY_WINDOW - 1)).astimezone(KIGALI).date()
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

    per_question = await _per_question(db)
    topic_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for qid, (n, ok) in per_question.items():
        topic = content.topic_of(qid)
        if topic:
            topic_totals[topic][0] += n
            topic_totals[topic][1] += ok

    outcome_counts = await outcomes.pass_counts(db)
    return PlatformStatsOut(
        users_total=await _count(db, User),
        users_new_7d=await _count(db, User, User.created_at >= week_ago),
        users_active_7d=await _count(db, User, User.last_active_at >= week_ago),
        users_ready=sum(_readiness(n, avg)[0] for n, avg in per_user),
        exams_total=total_exams or 0,
        exams_7d=await _count(db, ExamAttempt, completed, ExamAttempt.submitted_at >= week_ago),
        average_score=round(average, 2) if average is not None else None,
        pass_rate=round((passed or 0) / total_exams, 4) if total_exams else None,
        practice_answers=await _count(db, PracticeAnswer),
        outcomes_answered=outcome_counts[0],
        outcomes_passed=outcome_counts[1],
        testimonials_pending=await _count(
            db, ExamOutcome, ExamOutcome.testimonial.is_not(None), ExamOutcome.testimonial_status == "pending"
        ),
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
    ready = _readiness_aggregates()
    exams_col = func.coalesce(agg.c.exams, 0)
    query = (
        select(User, exams_col, agg.c.average, agg.c.best, ready.c.exams, ready.c.average)
        .outerjoin(agg, agg.c.user_id == User.id)
        .outerjoin(ready, ready.c.user_id == User.id)
    )
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
    for user, exams, average, best, counted, recent_average in rows:
        is_ready, status = _readiness(counted, recent_average)
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
                ready=is_ready,
                readiness_status=status,
            )
        )
    return Page[AdminUserRowOut](items=items, total=total, page=page, page_size=page_size)


async def user_detail(db: AsyncSession, user: User, content: ContentStore) -> AdminUserDetailOut:
    report = await progress.learner_report(db, user, content)
    return AdminUserDetailOut(
        **report.model_dump(),
        phone=user.phone,
        plan=user.plan,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def update_user(db: AsyncSession, user: User, data: AdminUserUpdate) -> User:
    if data.is_active is not None:
        if user.is_active and not data.is_active:
            user.session_version += 1  # a suspension also ends the sessions already open, even if lifted later
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


# ---------------------------------------------------------------------- explanations
def _search_key(text: str) -> str:
    return text.lower().replace("’", "'")


def _question_out(q: Question, note: explanations.Explanation, stats: list[int] | None) -> AdminQuestionOut:
    answered, correct = stats or (0, 0)
    return AdminQuestionOut(
        id=q.id,
        ref=q.ref,
        text=q.text,
        image=q.image,
        options=[OptionOut(text=o.text, image=o.image) for o in q.options],
        answer=q.answer,
        topic=q.topic,
        explanation=note.text,
        law_ref=note.law_ref,
        reviewed=note.reviewed,
        edited=note.edited,
        updated_at=note.updated_at,
        updated_by=note.updated_by,
        answered=answered,
        accuracy=round(correct / answered, 4) if answered else None,
    )


async def list_questions(
    db: AsyncSession,
    content: ContentStore,
    *,
    search: str | None,
    topic: str | None,
    status: QuestionFilter,
    sort: QuestionSort,
    page: int,
    page_size: int,
) -> AdminQuestionsOut:
    edits = await explanations.overrides(db)
    stats = await _per_question(db)
    rows = [
        _question_out(q, explanations.resolve(q, edits.get(q.id)), stats.get(q.id))
        for q in content.questions.values()
        if q.active
    ]
    counts = ExplanationCountsOut(
        total=len(rows),
        with_explanation=sum(r.explanation is not None for r in rows),
        reviewed=sum(r.reviewed for r in rows),
        edited=sum(r.edited for r in rows),
    )
    if topic:
        rows = [r for r in rows if r.topic == topic]
    keep = {
        "all": lambda r: True,
        "missing": lambda r: r.explanation is None,
        "unreviewed": lambda r: r.explanation is not None and not r.reviewed,
        "reviewed": lambda r: r.reviewed,
        "edited": lambda r: r.edited,
    }[status]
    rows = [r for r in rows if keep(r)]
    if search:
        term = _search_key(search.strip())
        rows = [
            r
            for r in rows
            if term == r.ref
            or term in _search_key(" ".join([r.text, r.explanation or "", *(o.text for o in r.options)]))
        ]
    if sort == "hardest":
        rows.sort(key=lambda r: (r.accuracy is None, r.accuracy or 0, -r.answered, r.id))
    elif sort == "most_answered":
        rows.sort(key=lambda r: (-r.answered, r.id))
    else:
        rows.sort(key=lambda r: r.id)
    start = (page - 1) * page_size
    return AdminQuestionsOut(
        items=rows[start : start + page_size], total=len(rows), page=page, page_size=page_size, counts=counts
    )


async def question_out(db: AsyncSession, content: ContentStore, question: Question) -> AdminQuestionOut:
    edits = await explanations.overrides(db, [question.id])
    stats = await _per_question(db)
    return _question_out(question, explanations.resolve(question, edits.get(question.id)), stats.get(question.id))


async def save_explanation(db: AsyncSession, question: Question, data: ExplanationUpdate, admin: Admin) -> None:
    row = await db.get(QuestionExplanation, question.id)
    if row is None:
        row = QuestionExplanation(question_id=question.id)
        db.add(row)
    row.text = data.explanation.strip()
    row.law_ref = (data.law_ref or "").strip() or None
    row.reviewed = data.reviewed
    row.updated_at = utcnow()
    row.updated_by = admin.email
    await db.commit()


async def reset_explanation(db: AsyncSession, question: Question) -> None:
    """Drops the admin's edit; the default explanation from app/data/explanations.json applies again."""
    row = await db.get(QuestionExplanation, question.id)
    if row is not None:
        await db.delete(row)
        await db.commit()


async def list_testimonials(db: AsyncSession, status: str | None) -> list[AdminTestimonialOut]:
    """Learners' words about the real exam, newest first; `status` filters pending / approved / hidden."""
    query = (
        select(ExamOutcome)
        .options(selectinload(ExamOutcome.user))
        .where(ExamOutcome.testimonial.is_not(None))
        .order_by(ExamOutcome.updated_at.desc())
    )
    if status:
        query = query.where(ExamOutcome.testimonial_status == status)
    return [
        AdminTestimonialOut(
            id=o.id,
            user_id=o.user_id,
            name=o.user.name,
            email=o.user.email,
            exam_date=o.exam_date,
            result=o.result,
            text=o.testimonial or "",
            public=o.testimonial_public,
            status=o.testimonial_status,
            created_at=o.updated_at,
        )
        for o in await db.scalars(query)
    ]
