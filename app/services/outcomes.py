"""Real-exam outcomes ("Watsinze ikizamini?"): the question, the answers, the public pass rate and testimonials."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import ExamOutcome, User
from app.models.outcome import RESULT_FAILED, RESULT_PASSED
from app.schemas.outcome import OutcomeIn, OutcomeStatsOut, TestimonialOut
from app.schemas.progress import PredictionOut, ReadinessOut

PUBLIC_TESTIMONIALS = 6
# Levels for "learners at your level passed X%": the average of the recent mock exams, out of 20.
LEVEL_BANDS = [(0.0, 12.0), (12.0, 15.0), (15.0, 17.0), (17.0, 20.0)]


class OutcomeMismatch(ValueError):
    pass


def first_name(user: User) -> str:
    return user.given_name or user.name.split()[0]


async def for_date(db: AsyncSession, user_id: uuid.UUID, exam_date: date) -> ExamOutcome | None:
    return await db.scalar(
        select(ExamOutcome).where(ExamOutcome.user_id == user_id, ExamOutcome.exam_date == exam_date)
    )


async def question_due(db: AsyncSession, user: User, today: date) -> date | None:
    """The exam date to ask about: it has passed and the learner has not answered for it yet."""
    if user.exam_date is None or user.exam_date >= today:
        return None
    return None if await for_date(db, user.id, user.exam_date) else user.exam_date


async def record(
    db: AsyncSession, user: User, body: OutcomeIn, today: date, level: ReadinessOut | None = None
) -> ExamOutcome:
    """Saves (or corrects) the answer for the learner's current exam date. `level`: where the learner stands now,
    kept from the first answer for the pass rates by level (see prediction)."""
    if body.exam_date != user.exam_date or body.exam_date > today:
        raise OutcomeMismatch(body.exam_date)
    outcome = await for_date(db, user.id, body.exam_date)
    if outcome is None:
        outcome = ExamOutcome(user_id=user.id, exam_date=body.exam_date)
        if level is not None:
            outcome.recent_average, outcome.mock_exams = level.average, level.exams_completed
        db.add(outcome)
    text = body.testimonial if body.result == RESULT_PASSED else None
    if text != outcome.testimonial:
        outcome.testimonial_status = "pending"  # new words are read by an admin before they are shown
    outcome.result, outcome.testimonial, outcome.testimonial_public = body.result, text, bool(text and body.public)
    await db.commit()
    await db.refresh(outcome)
    return outcome


async def pass_counts(db: AsyncSession) -> tuple[int, int]:
    """(learners who said they sat the exam, those who passed it at least once). "Not taken" answers do not count."""
    rows = await db.execute(
        select(ExamOutcome.user_id, ExamOutcome.result)
        .join(User, User.id == ExamOutcome.user_id)
        .where(User.is_active, ExamOutcome.result.in_((RESULT_PASSED, RESULT_FAILED)))
    )
    passed: dict[uuid.UUID, bool] = {}
    for user_id, result in rows.all():
        passed[user_id] = passed.get(user_id, False) or result == RESULT_PASSED
    return len(passed), sum(passed.values())


async def public_stats(db: AsyncSession) -> OutcomeStatsOut:
    answered, passed = await pass_counts(db)
    shown = await db.scalars(
        select(ExamOutcome)
        .options(selectinload(ExamOutcome.user))
        .join(User, User.id == ExamOutcome.user_id)
        .where(
            User.is_active,
            ExamOutcome.testimonial_public,
            ExamOutcome.testimonial_status == "approved",
            ExamOutcome.testimonial.is_not(None),
        )
        .order_by(ExamOutcome.updated_at.desc())
        .limit(PUBLIC_TESTIMONIALS)
    )
    return OutcomeStatsOut(
        answered=answered,
        passed=passed,
        pass_rate=round(passed / answered, 4) if answered and answered >= settings.OUTCOME_MIN_ANSWERS else None,
        testimonials=[
            TestimonialOut(name=first_name(o.user), text=o.testimonial or "", exam_date=o.exam_date) for o in shown
        ],
    )


def level_band(average: float) -> tuple[float, float]:
    for low, high in LEVEL_BANDS:
        if average < high:
            return low, high
    return LEVEL_BANDS[-1]


async def prediction(db: AsyncSession, average: float | None) -> PredictionOut | None:
    """How learners with a recent average like this one did in the real exam, by their own account.

    Each sitting counts once ("passed" or "failed"; "not taken" is left out). Nothing is said until the band holds
    OUTCOME_MIN_ANSWERS answers: a rate drawn from a handful of people would mislead.
    """
    if average is None:
        return None
    low, high = level_band(average)
    in_band = ExamOutcome.recent_average >= low
    if high < LEVEL_BANDS[-1][1]:
        in_band = in_band & (ExamOutcome.recent_average < high)
    results = list(
        await db.scalars(
            select(ExamOutcome.result)
            .join(User, User.id == ExamOutcome.user_id)
            .where(User.is_active, in_band, ExamOutcome.result.in_((RESULT_PASSED, RESULT_FAILED)))
        )
    )
    if len(results) < settings.OUTCOME_MIN_ANSWERS:
        return None
    passed = results.count(RESULT_PASSED)
    return PredictionOut(
        band_low=low, band_high=high, reports=len(results), passed=passed, pass_rate=round(passed / len(results), 4)
    )
