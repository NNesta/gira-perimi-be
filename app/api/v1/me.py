from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select

from app.core.deps import DB, Content, CurrentUser
from app.core.security import USER_COOKIE, clear_session_cookie
from app.models import LessonProgress, User
from app.schemas.progress import DashboardOut
from app.schemas.user import UserOut, UserUpdate
from app.services import progress as progress_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/dashboard")
async def dashboard(db: DB, user: CurrentUser, content: Content) -> DashboardOut:
    """Everything the learner dashboard shows: readiness, averages, trend, topic mastery, lessons."""
    return await progress_service.dashboard(db, user, content)


@router.patch("", response_model=UserOut)
async def update_profile(body: UserUpdate, db: DB, user: CurrentUser) -> User:
    user.phone = body.phone.strip() if body.phone else None
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
