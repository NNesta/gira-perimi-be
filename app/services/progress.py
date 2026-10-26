import math
import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.models import ExamAnswer, ExamAttempt, LessonProgress, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.progress import (
    ActivityDayOut,
    DashboardOut,
    ExamStatsOut,
    LessonProgressOut,
    PlanOut,
    ReadinessOut,
    ScorePointOut,
    TodayOut,
    TopicMasteryOut,
)
from app.schemas.user import UserOut
from app.services import exams as exam_service
from app.services import review
from app.services.content import TOPICS, ContentStore
from app.services.dates import day_start, local_day
from app.services.practice import answer_history

TREND_LENGTH = 20
ACTIVITY_DAYS = 14
# Without an exam date, suggest a mock exam when the last one is at least this many days old.
DEFAULT_EXAM_EVERY_DAYS = 2


def readiness_status(count: int, average: float | None) -> tuple[bool, str]:
    """Recommended for the real exam after MORE than N exams with an average strictly ABOVE the bar."""
    ready = count > settings.READINESS_MIN_EXAMS and average is not None and average > settings.READINESS_MIN_AVERAGE
    if count == 0:
        return False, "new"
    if ready:
        return True, "ready"
    if average is not None and average > settings.READINESS_MIN_AVERAGE - 2:
        return False, "almost"
    return False, "learning"


def readiness(scores: list[int]) -> ReadinessOut:
    count = len(scores)
    average = round(sum(scores) / count, 2) if count else None
    required = settings.READINESS_MIN_EXAMS + 1
    ready, status = readiness_status(count, average)
    return ReadinessOut(
        status=status,
        ready=ready,
        exams_completed=count,
        exams_required=required,
        exams_remaining=max(0, required - count),
        average=average,
        average_required=settings.READINESS_MIN_AVERAGE,
    )


def exam_stats(scores: list[int]) -> ExamStatsOut:
    count = len(scores)
    passed = sum(s >= settings.EXAM_PASS_MARK for s in scores)
    return ExamStatsOut(
        completed=count,
        passed=passed,
        average=round(sum(scores) / count, 2) if count else None,
        best=max(scores) if scores else None,
        last=scores[-1] if scores else None,
        pass_rate=round(passed / count, 4) if count else None,
    )


def topic_mastery(history: list[tuple[int, bool, datetime]], content: ContentStore) -> list[TopicMasteryOut]:
    answered: dict[str, int] = defaultdict(int)
    correct: dict[str, int] = defaultdict(int)
    seen: dict[str, set[int]] = defaultdict(set)
    for qid, ok, _ in history:
        topic = content.topic_of(qid)
        if topic is None:
            continue
        answered[topic] += 1
        correct[topic] += ok
        seen[topic].add(qid)
    return [
        TopicMasteryOut(
            topic=t["id"],
            name=t["name"],
            answered=answered[t["id"]],
            correct=correct[t["id"]],
            accuracy=round(correct[t["id"]] / answered[t["id"]], 4) if answered[t["id"]] else None,
            question_count=len(content.ids_by_topic[t["id"]]),
            seen=len(seen[t["id"]] & set(content.ids_by_topic[t["id"]])),
        )
        for t in TOPICS
    ]


def streak(days: set[date], today: date) -> int:
    """Consecutive active days ending today (or yesterday, so an evening learner keeps their streak)."""
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


async def answered_since(db: AsyncSession, since: datetime, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Questions answered since `since` per learner: practice answers plus answered questions of finished exams."""
    user_ids = list(user_ids)
    counts: dict[uuid.UUID, int] = defaultdict(int)
    practice = await db.execute(
        select(PracticeAnswer.user_id, func.count())
        .where(PracticeAnswer.user_id.in_(user_ids), PracticeAnswer.answered_at >= since)
        .group_by(PracticeAnswer.user_id)
    )
    exams = await db.execute(
        select(ExamAttempt.user_id, func.count(ExamAnswer.id))
        .join(ExamAnswer, ExamAnswer.attempt_id == ExamAttempt.id)
        .where(
            ExamAttempt.user_id.in_(user_ids),
            ExamAttempt.status == STATUS_COMPLETED,
            ExamAttempt.submitted_at >= since,
            ExamAnswer.selected.is_not(None),
        )
        .group_by(ExamAttempt.user_id)
    )
    for user_id, n in [*practice.all(), *exams.all()]:
        counts[user_id] += n
    return dict(counts)


async def active_days(db: AsyncSession, user_id: uuid.UUID, since: date) -> set[date]:
    """Kigali days with any practice answer, finished exam or completed lesson since `since`."""
    start = day_start(since)
    moments = [
        *await db.scalars(
            select(PracticeAnswer.answered_at).where(
                PracticeAnswer.user_id == user_id, PracticeAnswer.answered_at >= start
            )
        ),
        *await db.scalars(
            select(ExamAttempt.submitted_at).where(
                ExamAttempt.user_id == user_id,
                ExamAttempt.status == STATUS_COMPLETED,
                ExamAttempt.submitted_at >= start,
            )
        ),
        *await db.scalars(
            select(LessonProgress.completed_at).where(
                LessonProgress.user_id == user_id, LessonProgress.completed_at >= start
            )
        ),
    ]
    return {local_day(at) for at in moments}


def study_plan(user: User, today: date, lessons_left: int, exams_left: int) -> PlanOut:
    """Turns the exam date into a pace: is there enough time, and how often to sit a mock exam."""
    if user.exam_date is None:
        return PlanOut(
            exam_date=None,
            days_left=None,
            lessons_left=lessons_left,
            exams_left=exams_left,
            pace="none",
            exam_every_days=None,
            exams_per_day=None,
        )
    days_left = (user.exam_date - today).days
    every = per_day = None
    if days_left < 0:
        pace = "passed"
    elif days_left == 0:
        pace = "today"
    else:
        pace = "tight" if exams_left > 2 * days_left or lessons_left > 3 * days_left else "on_track"
        if exams_left:
            if exams_left <= days_left:
                every = days_left // exams_left
            else:
                every, per_day = 1, math.ceil(exams_left / days_left)
    return PlanOut(
        exam_date=user.exam_date,
        days_left=days_left,
        lessons_left=lessons_left,
        exams_left=exams_left,
        pace=pace,
        exam_every_days=every,
        exams_per_day=per_day,
    )


def suggest_exam(plan: PlanOut, exams: list[ExamAttempt], today: date) -> bool:
    if plan.exams_left == 0 or plan.pace in ("today", "passed"):
        return False
    if not exams:
        return True
    last = local_day(exams[-1].submitted_at)
    if last == today:
        return False
    return (today - last).days >= (plan.exam_every_days or DEFAULT_EXAM_EVERY_DAYS)


async def completed_exams(db: AsyncSession, user_id) -> list[ExamAttempt]:
    result = await db.scalars(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user_id, ExamAttempt.status == STATUS_COMPLETED)
        .order_by(ExamAttempt.submitted_at)
    )
    return list(result)


async def lesson_slugs(db: AsyncSession, user_id) -> list[str]:
    result = await db.scalars(
        select(LessonProgress.lesson_slug)
        .where(LessonProgress.user_id == user_id)
        .order_by(LessonProgress.completed_at)
    )
    return list(result)


def lesson_progress(completed: list[str], content: ContentStore) -> LessonProgressOut:
    done = [slug for slug in completed if slug in content.lessons_by_slug]
    next_slug = next((lesson["slug"] for lesson in content.lessons if lesson["slug"] not in done), None)
    return LessonProgressOut(completed=len(done), total=len(content.lessons), completed_slugs=done, next_slug=next_slug)


async def dashboard(db: AsyncSession, user: User, content: ContentStore) -> DashboardOut:
    running = await exam_service.current_attempt(db, user, content)
    exams = await completed_exams(db, user.id)
    scores = [e.score or 0 for e in exams]
    history = await answer_history(db, user)
    lessons = await lesson_slugs(db, user.id)
    practice_count = (
        await db.scalar(select(func.count()).select_from(PracticeAnswer).where(PracticeAnswer.user_id == user.id)) or 0
    )

    today = local_day(utcnow())
    activity: dict[date, int] = defaultdict(int)
    for _, _, at in history:
        activity[local_day(at)] += 1
    days_active = set(activity)
    lesson_days = {
        local_day(at)
        for at in await db.scalars(select(LessonProgress.completed_at).where(LessonProgress.user_id == user.id))
    }
    days_active.update(lesson_days)

    lessons_out = lesson_progress(lessons, content)
    readiness_out = readiness(scores)
    plan = study_plan(user, today, lessons_out.total - lessons_out.completed, readiness_out.exams_remaining)
    answered_today = (await answered_since(db, day_start(today), [user.id])).get(user.id, 0)

    recent = sorted(exams, key=lambda e: e.submitted_at, reverse=True)[:5]
    return DashboardOut(
        user=UserOut.model_validate(user),
        readiness=readiness_out,
        exams=exam_stats(scores),
        trend=[
            ScorePointOut(
                exam_id=str(e.id),
                date=e.submitted_at,
                score=e.score or 0,
                passed=(e.score or 0) >= settings.EXAM_PASS_MARK,
            )
            for e in exams[-TREND_LENGTH:]
        ],
        topics=topic_mastery(history, content),
        lessons=lessons_out,
        practice_answers=practice_count,
        questions_seen=len(
            {qid for qid, _, _ in history if qid in content.questions and content.questions[qid].active}
        ),
        question_total=len(content.active_ids),
        streak_days=streak(days_active, today),
        activity=[
            ActivityDayOut(day=today - timedelta(days=i), answers=activity.get(today - timedelta(days=i), 0))
            for i in range(ACTIVITY_DAYS - 1, -1, -1)
        ],
        recent_exams=[exam_service.to_summary(e) for e in recent],
        in_progress_exam=str(running.id) if running else None,
        today=TodayOut(
            answered=answered_today,
            goal=user.daily_goal,
            lesson_done=today in lesson_days,
            exam_done=any(local_day(e.submitted_at) == today for e in exams),
            exam_suggested=suggest_exam(plan, exams, today),
        ),
        plan=plan,
        review=await review.summary(db, user.id),
    )
