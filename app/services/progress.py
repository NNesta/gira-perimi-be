from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.models import ExamAttempt, LessonProgress, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.progress import (
    ActivityDayOut,
    DashboardOut,
    ExamStatsOut,
    LessonProgressOut,
    ReadinessOut,
    ScorePointOut,
    TopicMasteryOut,
)
from app.schemas.user import UserOut
from app.services import exams as exam_service
from app.services.content import TOPICS, ContentStore
from app.services.practice import answer_history

# Rwanda is UTC+2 all year (no daylight saving), so a fixed offset is exact.
KIGALI = timezone(timedelta(hours=2), "CAT")
TREND_LENGTH = 20
ACTIVITY_DAYS = 14


def local_day(moment: datetime) -> date:
    return moment.astimezone(KIGALI).date()


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
    active_days = set(activity)
    lesson_rows = await db.scalars(select(LessonProgress.completed_at).where(LessonProgress.user_id == user.id))
    active_days.update(local_day(at) for at in lesson_rows)

    recent = sorted(exams, key=lambda e: e.submitted_at, reverse=True)[:5]
    return DashboardOut(
        user=UserOut.model_validate(user),
        readiness=readiness(scores),
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
        lessons=lesson_progress(lessons, content),
        practice_answers=practice_count,
        questions_seen=len(
            {qid for qid, _, _ in history if qid in content.questions and content.questions[qid].active}
        ),
        question_total=len(content.active_ids),
        streak_days=streak(active_days, today),
        activity=[
            ActivityDayOut(day=today - timedelta(days=i), answers=activity.get(today - timedelta(days=i), 0))
            for i in range(ACTIVITY_DAYS - 1, -1, -1)
        ],
        recent_exams=[exam_service.to_summary(e) for e in recent],
        in_progress_exam=str(running.id) if running else None,
    )
