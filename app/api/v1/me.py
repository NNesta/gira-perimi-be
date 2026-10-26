from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.deps import DB, Content, CurrentUser
from app.core.security import USER_COOKIE, clear_session_cookie
from app.db.base import utcnow
from app.models import LessonProgress, User
from app.schemas.progress import DashboardOut
from app.schemas.user import UserOut, UserUpdate
from app.services import progress as progress_service
from app.services.dates import local_day

# An exam date further away than this is almost certainly a typo.
EXAM_DATE_HORIZON = timedelta(days=730)

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/dashboard")
async def dashboard(db: DB, user: CurrentUser, content: Content) -> DashboardOut:
    """Everything the learner dashboard shows: readiness, averages, trend, topic mastery, lessons."""
    return await progress_service.dashboard(db, user, content)


@router.patch("", response_model=UserOut)
async def update_profile(body: UserUpdate, db: DB, user: CurrentUser) -> User:
    """Phone, exam date, daily goal and reminders. Only the fields present in the request change."""
    fields = body.model_fields_set
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
