import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.base import utcnow
from app.models import ExamAnswer, ExamAttempt, User
from app.models.exam import STATUS_COMPLETED, STATUS_IN_PROGRESS
from app.schemas.content import OptionOut
from app.schemas.exam import ExamItemOut, ExamOut, ExamSummaryOut
from app.services.content import ContentStore


class ExamNotFound(Exception):
    pass


class ExamClosed(Exception):
    pass


def _with_answers():
    return select(ExamAttempt).options(selectinload(ExamAttempt.answers))


async def get_attempt(db: AsyncSession, user: User, attempt_id: uuid.UUID) -> ExamAttempt:
    attempt = (
        await db.scalars(_with_answers().where(ExamAttempt.id == attempt_id, ExamAttempt.user_id == user.id))
    ).first()
    if attempt is None:
        raise ExamNotFound
    return attempt


def is_expired(attempt: ExamAttempt) -> bool:
    return utcnow() > attempt.deadline_at + timedelta(seconds=settings.EXAM_GRACE_SECONDS)


def grade(attempt: ExamAttempt, content: ContentStore, *, auto: bool) -> None:
    score = 0
    for answer in attempt.answers:
        correct = answer.selected is not None and answer.selected == content.questions[answer.question_id].answer
        answer.is_correct = correct
        score += correct
    now = utcnow()
    attempt.score = score
    attempt.status = STATUS_COMPLETED
    attempt.auto_submitted = auto
    attempt.submitted_at = min(now, attempt.deadline_at)


async def finalize_expired(db: AsyncSession, attempt: ExamAttempt, content: ContentStore) -> bool:
    """Grades an abandoned exam with the answers saved before the clock ran out."""
    if attempt.status == STATUS_IN_PROGRESS and is_expired(attempt):
        grade(attempt, content, auto=True)
        await db.commit()
        return True
    return False


async def current_attempt(db: AsyncSession, user: User, content: ContentStore) -> ExamAttempt | None:
    attempt = (
        await db.scalars(
            _with_answers()
            .where(ExamAttempt.user_id == user.id, ExamAttempt.status == STATUS_IN_PROGRESS)
            .order_by(ExamAttempt.started_at.desc())
        )
    ).first()
    if attempt is None or await finalize_expired(db, attempt, content):
        return None
    return attempt


async def start_exam(db: AsyncSession, user: User, content: ContentStore) -> ExamAttempt:
    """Resumes the running exam if there is one, otherwise draws a fresh 20-question paper."""
    running = await current_attempt(db, user, content)
    if running is not None:
        return running
    question_ids = content.draw_exam(settings.EXAM_QUESTION_COUNT)
    now = utcnow()
    attempt = ExamAttempt(
        user_id=user.id,
        started_at=now,
        deadline_at=now + timedelta(minutes=settings.EXAM_DURATION_MINUTES),
        total=len(question_ids),
        answers=[ExamAnswer(position=i + 1, question_id=qid) for i, qid in enumerate(question_ids)],
    )
    db.add(attempt)
    await db.commit()
    return await get_attempt(db, user, attempt.id)


async def save_answer(
    db: AsyncSession, attempt: ExamAttempt, content: ContentStore, position: int, selected: int | None
) -> ExamAnswer:
    if attempt.status != STATUS_IN_PROGRESS or await finalize_expired(db, attempt, content):
        raise ExamClosed
    answer = next((a for a in attempt.answers if a.position == position), None)
    if answer is None:
        raise ExamNotFound
    answer.selected = selected
    answer.answered_at = utcnow() if selected is not None else None
    await db.commit()
    return answer


async def submit(db: AsyncSession, attempt: ExamAttempt, content: ContentStore) -> ExamAttempt:
    if attempt.status == STATUS_IN_PROGRESS:
        grade(attempt, content, auto=is_expired(attempt))
        await db.commit()
    return attempt


async def list_attempts(
    db: AsyncSession, user: User, content: ContentStore, limit: int = 50, offset: int = 0
) -> list[ExamAttempt]:
    await current_attempt(db, user, content)  # settles an expired exam so history is accurate
    result = await db.scalars(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user.id)
        .order_by(ExamAttempt.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)


# ---------------------------------------------------------------------- serializers
def passed(attempt: ExamAttempt) -> bool | None:
    return None if attempt.score is None else attempt.score >= settings.EXAM_PASS_MARK


def to_summary(attempt: ExamAttempt) -> ExamSummaryOut:
    duration = None
    if attempt.submitted_at is not None:
        duration = int((attempt.submitted_at - attempt.started_at).total_seconds())
    return ExamSummaryOut(
        id=attempt.id,
        status=attempt.status,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        total=attempt.total,
        score=attempt.score,
        passed=passed(attempt),
        duration_seconds=duration,
    )


def to_out(attempt: ExamAttempt, content: ContentStore) -> ExamOut:
    completed = attempt.status == STATUS_COMPLETED
    items = []
    for answer in attempt.answers:
        q = content.questions[answer.question_id]
        items.append(
            ExamItemOut(
                position=answer.position,
                question_id=q.id,
                ref=q.ref,
                text=q.text,
                image=q.image,
                options=[OptionOut(text=o.text, image=o.image) for o in q.options],
                topic=q.topic,
                selected=answer.selected,
                answer=q.answer if completed else None,
                is_correct=answer.is_correct if completed else None,
            )
        )
    return ExamOut(
        id=attempt.id,
        status=attempt.status,
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        submitted_at=attempt.submitted_at,
        server_time=utcnow(),
        auto_submitted=attempt.auto_submitted,
        total=attempt.total,
        score=attempt.score,
        pass_mark=settings.EXAM_PASS_MARK,
        passed=passed(attempt),
        answered=sum(a.selected is not None for a in attempt.answers),
        items=items,
    )
