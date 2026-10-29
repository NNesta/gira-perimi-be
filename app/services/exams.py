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
from app.services import review
from app.services.content import ContentStore, explanation_audio
from app.services.explanations import Explanation


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
    attempt.answered = sum(a.selected is not None for a in attempt.answers)
    attempt.status = STATUS_COMPLETED
    attempt.auto_submitted = auto
    attempt.submitted_at = min(now, attempt.deadline_at)


async def _schedule_review(db: AsyncSession, attempt: ExamAttempt) -> None:
    """Answered questions feed the spaced review: mistakes come back tomorrow, due items move on."""
    await review.record_questions(
        db,
        attempt.user_id,
        [(a.question_id, bool(a.is_correct), attempt.submitted_at) for a in attempt.answers if a.selected is not None],
    )


async def finalize_expired(db: AsyncSession, attempt: ExamAttempt, content: ContentStore) -> bool:
    """Grades an abandoned exam with the answers saved before the clock ran out."""
    if attempt.status == STATUS_IN_PROGRESS and is_expired(attempt):
        grade(attempt, content, auto=True)
        await _schedule_review(db, attempt)
        await db.commit()
        return True
    return False


async def current_attempt(db: AsyncSession, user: User, content: ContentStore) -> ExamAttempt | None:
    """The learner's running exam (the earliest, should there be several). Expired ones are graded on the way."""
    running = await db.scalars(
        _with_answers()
        .where(ExamAttempt.user_id == user.id, ExamAttempt.status == STATUS_IN_PROGRESS)
        .order_by(ExamAttempt.started_at, ExamAttempt.id)
    )
    for attempt in running.all():
        if not await finalize_expired(db, attempt, content):
            return attempt
    return None


async def start_exam(db: AsyncSession, user: User, content: ContentStore) -> ExamAttempt:
    """Resumes the running exam if there is one, otherwise draws a fresh 20-question paper."""
    running = await current_attempt(db, user, content)
    if running is not None:
        return running
    return await new_attempt(db, user, content, content.draw_exam(settings.EXAM_QUESTION_COUNT))


async def new_attempt(
    db: AsyncSession, user: User, content: ContentStore, question_ids: list[int], challenge_id: uuid.UUID | None = None
) -> ExamAttempt:
    """Starts the clock on a paper: a fresh draw, or a friend's (`challenge_id`)."""
    now = utcnow()
    attempt = ExamAttempt(
        user_id=user.id,
        started_at=now,
        deadline_at=now + timedelta(minutes=settings.EXAM_DURATION_MINUTES),
        total=len(question_ids),
        challenge_id=challenge_id,
        answers=[ExamAnswer(position=i + 1, question_id=qid) for i, qid in enumerate(question_ids)],
    )
    db.add(attempt)
    await db.commit()
    # Two requests at once (a double tap, two tabs) can both get this far. Each then resumes the earliest running exam
    # and the later one drops its own paper, so no forgotten twin is left to be graded 0/20 when its time runs out.
    first = await current_attempt(db, user, content)
    if first is not None and first.id != attempt.id:
        await db.delete(attempt)
        await db.commit()
        return first
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


async def submit(
    db: AsyncSession, attempt: ExamAttempt, content: ContentStore, sheet: dict[int, int] | None = None
) -> ExamAttempt:
    """Grades the exam. `sheet` (position -> choice) is the answer sheet as the learner's device last saw it: choices
    whose own save failed on a poor connection still count, as long as the clock has not run out."""
    if attempt.status == STATUS_IN_PROGRESS:
        expired = is_expired(attempt)
        if sheet and not expired:
            now = utcnow()
            for answer in attempt.answers:
                choice = sheet.get(answer.position)
                if choice is not None and choice != answer.selected:
                    answer.selected = choice
                    answer.answered_at = now
        grade(attempt, content, auto=expired)
        await _schedule_review(db, attempt)
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


def to_out(
    attempt: ExamAttempt,
    content: ContentStore,
    notes: dict[int, Explanation] | None = None,
    challenge_code: str | None = None,
) -> ExamOut:
    """`notes` (explanations) are only shown once the exam is completed."""
    completed = attempt.status == STATUS_COMPLETED
    notes = notes if completed and notes else {}
    items = []
    for answer in attempt.answers:
        q = content.questions[answer.question_id]
        note = notes.get(q.id)
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
                explanation=note.text if note else None,
                law_ref=note.law_ref if note else None,
                audio=q.audio,
                explanation_audio=explanation_audio(q, note.text) if note else None,
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
        challenge_code=challenge_code,
    )
