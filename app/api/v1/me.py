from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.deps import DB, Content, CurrentUser
from app.core.security import USER_COOKIE, clear_session_cookie
from app.db.base import utcnow
from app.models import LessonProgress, User
from app.schemas.outcome import OutcomeIn, OutcomeOut
from app.schemas.progress import BadgesOut, DashboardOut
from app.schemas.user import UserOut, UserUpdate
from app.services import badges as badge_service
from app.services import outcomes as outcome_service
from app.services import progress as progress_service
from app.services.dates import local_day

# An exam date further away than this is almost certainly a typo.
EXAM_DATE_HORIZON = timedelta(days=730)

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/dashboard")
async def dashboard(db: DB, user: CurrentUser, content: Content) -> DashboardOut:
    """Everything the learner dashboard shows: readiness, averages, trend, topic mastery, lessons."""
    return await progress_service.dashboard(db, user, content)


@router.get("/badges")
async def badges(db: DB, user: CurrentUser, content: Content) -> BadgesOut:
    """Achievement badges: which are earned, and how far along the others are."""
    return await badge_service.badges(db, user, content)


@router.post("/outcome")
async def report_outcome(body: OutcomeIn, db: DB, user: CurrentUser) -> OutcomeOut:
    """ "Watsinze ikizamini?": the learner's answer for their (past) exam date, with optional words for others."""
    exams = await progress_service.completed_exams(db, user.id)
    level = progress_service.readiness(progress_service.readiness_scores(exams))
    try:
        outcome = await outcome_service.record(db, user, body, local_day(utcnow()), level)
    except outcome_service.OutcomeMismatch as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Iyi tariki si iy’ikizamini cyawe cyarangiye."
        ) from exc
    return OutcomeOut(
        exam_date=outcome.exam_date,
        result=outcome.result,
        testimonial=outcome.testimonial,
        public=outcome.testimonial_public,
        testimonial_status=outcome.testimonial_status,
    )


@router.patch("", response_model=UserOut)
async def update_profile(body: UserUpdate, db: DB, user: CurrentUser) -> User:
    """Phone, exam date, daily goal, reminders and the first-time welcome. Only the fields sent change."""
    fields = body.model_fields_set
    if "name" in fields and body.name and body.name.strip():
        user.name = " ".join(body.name.split())
        user.given_name = user.name.split()[0]
    if "phone" in fields:
        user.phone = body.phone.strip() if body.phone else None
    if "exam_date" in fields:
        today = local_day(utcnow())
        if body.exam_date is not None and not today <= body.exam_date <= today + EXAM_DATE_HORIZON:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Hitamo itariki y’ikizamini kiri imbere, mu myaka 2 iri imbere."
            )
        user.exam_date = body.exam_date
    if "daily_goal" in fields:
        user.daily_goal = body.daily_goal
    if "reminders" in fields:
        if body.reminders and not settings.reminders_available:
            raise HTTPException(status.HTTP_409_CONFLICT, "Kwibutswa kuri imeyili ntibirashyirwaho kuri uru rubuga.")
        user.reminders = body.reminders
    if "onboarded" in fields:
        user.onboarded_at = (user.onboarded_at or utcnow()) if body.onboarded else None
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(response: Response, db: DB, user: CurrentUser) -> None:
    """Lets a learner erase their account and all of their results."""
    await db.delete(user)
    await db.commit()
    clear_session_cookie(response, USER_COOKIE)


@router.put("/lessons/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def complete_lesson(slug: str, db: DB, user: CurrentUser, content: Content) -> None:
    if slug not in content.lessons_by_slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iri somo ntiribonetse.")
    exists = await db.scalar(
        select(LessonProgress.id).where(LessonProgress.user_id == user.id, LessonProgress.lesson_slug == slug)
    )
    if exists is None:
        db.add(LessonProgress(user_id=user.id, lesson_slug=slug))
        await db.commit()


@router.delete("/lessons/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def uncomplete_lesson(slug: str, db: DB, user: CurrentUser) -> None:
    await db.execute(
        delete(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_slug == slug)
    )
    await db.commit()
