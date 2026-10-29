import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.config import settings
from app.core.deps import DB, Content, CurrentAdmin
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.core.security import ADMIN_COOKIE, clear_session_cookie, create_token, set_session_cookie
from app.models import Admin, ExamOutcome, School, User
from app.schemas.admin import (
    AdminLoginIn,
    AdminOut,
    AdminQuestionOut,
    AdminQuestionsOut,
    AdminUserDetailOut,
    AdminUserRowOut,
    AdminUserUpdate,
    ExplanationUpdate,
    PlatformStatsOut,
    QuestionFilter,
    QuestionSort,
    UserSort,
)
from app.schemas.common import Page
from app.schemas.outcome import AdminTestimonialOut, TestimonialStatus, TestimonialUpdate
from app.schemas.school import InstructorIn, SchoolAdminOut, SchoolCreate, SchoolUpdate
from app.services import admin as admin_service
from app.services import auth as auth_service
from app.services import schools as school_service
from app.services.content import TOPIC_IDS, Question

router = APIRouter(prefix="/admin", tags=["admin"])
login_limiter = SlidingWindowLimiter(settings.ADMIN_LOGIN_MAX_ATTEMPTS, settings.ADMIN_LOGIN_WINDOW_SECONDS)
USER_NOT_FOUND = "Uwo munyeshuri ntabonetse."
QUESTION_NOT_FOUND = "Icyo kibazo ntikibonetse."


@router.post("/auth/login", response_model=AdminOut)
async def admin_login(body: AdminLoginIn, request: Request, response: Response, db: DB) -> Admin:
    keys = (f"ip:{client_ip(request)}", f"email:{body.email.strip().lower()}")
    wait = max(login_limiter.retry_after(k) for k in keys)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Mwagerageje inshuro nyinshi. Ongera ugerageze nyuma y’iminota {max(1, wait // 60)}.",
            headers={"Retry-After": str(wait)},
        )
    admin = await auth_service.authenticate_admin(db, body.email, body.password)
    if admin is None:
        for key in keys:
            login_limiter.hit(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Imeyili cyangwa ijambobanga si byo.")
    for key in keys:
        login_limiter.reset(key)
    lifetime = timedelta(hours=settings.ADMIN_SESSION_HOURS)
    token = create_token(admin.id, "admin", lifetime, admin.session_version)
    set_session_cookie(response, ADMIN_COOKIE, token, int(lifetime.total_seconds()))
    return admin


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def admin_logout(response: Response) -> None:
    clear_session_cookie(response, ADMIN_COOKIE)


@router.get("/auth/me", response_model=AdminOut)
async def admin_me(admin: CurrentAdmin) -> Admin:
    return admin


@router.get("/stats")
async def stats(_: CurrentAdmin, db: DB, content: Content) -> PlatformStatsOut:
    return await admin_service.platform_stats(db, content)


@router.get("/users")
async def users(
    _: CurrentAdmin,
    db: DB,
    search: str | None = Query(None, max_length=100),
    sort: UserSort = "joined",
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[AdminUserRowOut]:
    return await admin_service.list_users(
        db, search=search, sort=sort, descending=order == "desc", page=page, page_size=page_size
    )


async def _get_user(db: DB, user_id: uuid.UUID) -> User:
    user = await admin_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
    return user


@router.get("/users/{user_id}")
async def user_detail(user_id: uuid.UUID, _: CurrentAdmin, db: DB, content: Content) -> AdminUserDetailOut:
    return await admin_service.user_detail(db, await _get_user(db, user_id), content)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: AdminUserUpdate, _: CurrentAdmin, db: DB, content: Content
) -> AdminUserDetailOut:
    user = await admin_service.update_user(db, await _get_user(db, user_id), body)
    return await admin_service.user_detail(db, user, content)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: uuid.UUID, _: CurrentAdmin, db: DB) -> None:
    await admin_service.delete_user(db, await _get_user(db, user_id))


@router.get("/questions")
async def questions(
    _: CurrentAdmin,
    db: DB,
    content: Content,
    search: str | None = Query(None, max_length=100),
    topic: str | None = None,
    status_filter: QuestionFilter = Query("all", alias="status"),
    sort: QuestionSort = "number",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AdminQuestionsOut:
    """Question bank with explanations, their review status and how often learners get each question right."""
    return await admin_service.list_questions(
        db,
        content,
        search=search,
        topic=topic if topic in TOPIC_IDS else None,
        status=status_filter,
        sort=sort,
        page=page,
        page_size=page_size,
    )


def _question(content: Content, question_id: int) -> Question:
    question = content.questions.get(question_id)
    if question is None or not question.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUESTION_NOT_FOUND)
    return question


@router.put("/questions/{question_id}/explanation")
async def save_explanation(
    question_id: int, body: ExplanationUpdate, admin: CurrentAdmin, db: DB, content: Content
) -> AdminQuestionOut:
    question = _question(content, question_id)
    await admin_service.save_explanation(db, question, body, admin)
    return await admin_service.question_out(db, content, question)


@router.delete("/questions/{question_id}/explanation")
async def reset_explanation(question_id: int, _: CurrentAdmin, db: DB, content: Content) -> AdminQuestionOut:
    question = _question(content, question_id)
    await admin_service.reset_explanation(db, question)
    return await admin_service.question_out(db, content, question)


@router.get("/testimonials")
async def testimonials(
    _: CurrentAdmin, db: DB, status_filter: TestimonialStatus | None = Query(None, alias="status")
) -> list[AdminTestimonialOut]:
    """ "Ubuhamya": what learners wrote after passing the real exam. Only approved, consented ones reach the site."""
    return await admin_service.list_testimonials(db, status_filter)


@router.patch("/testimonials/{outcome_id}", status_code=status.HTTP_204_NO_CONTENT)
async def moderate_testimonial(outcome_id: uuid.UUID, body: TestimonialUpdate, _: CurrentAdmin, db: DB) -> None:
    outcome = await db.get(ExamOutcome, outcome_id)
    if outcome is None or not outcome.testimonial:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ubu buhamya ntibubonetse.")
    outcome.testimonial_status = body.status
    await db.commit()


# ---------------------------------------------------------------------- driving schools
async def _school(db: DB, school_id: uuid.UUID):
    try:
        return await school_service.get_school(db, school_id)
    except school_service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iryo shuri ntiribonetse.") from exc


async def _school_out(db: DB, school_id: uuid.UUID) -> SchoolAdminOut:
    return next(s for s in await school_service.admin_list(db) if s.id == school_id)


@router.get("/schools")
async def schools(_: CurrentAdmin, db: DB) -> list[SchoolAdminOut]:
    """Driving schools, their instructors (by email) and how many classes and learners they have."""
    return await school_service.admin_list(db)


@router.post("/schools", status_code=status.HTTP_201_CREATED)
async def create_school(body: SchoolCreate, _: CurrentAdmin, db: DB) -> SchoolAdminOut:
    school = School(name=" ".join(body.name.split()))
    db.add(school)
    await db.commit()
    return await _school_out(db, school.id)


@router.patch("/schools/{school_id}")
async def update_school(school_id: uuid.UUID, body: SchoolUpdate, _: CurrentAdmin, db: DB) -> SchoolAdminOut:
    """Renames a school, or closes it (its instructors lose access; nothing is deleted) and reopens it."""
    school = await _school(db, school_id)
    if body.name is not None:
        school.name = " ".join(body.name.split())
    if body.active is not None:
        school.active = body.active
    await db.commit()
    return await _school_out(db, school.id)


@router.post("/schools/{school_id}/instructors")
async def add_instructor(school_id: uuid.UUID, body: InstructorIn, _: CurrentAdmin, db: DB) -> SchoolAdminOut:
    """Whoever signs in with this address teaches at the school; they are told by email when email is set up."""
    await school_service.invite(db, await _school(db, school_id), body.email)
    return await _school_out(db, school_id)


@router.delete("/schools/{school_id}/instructors/{instructor_id}")
async def remove_instructor(school_id: uuid.UUID, instructor_id: uuid.UUID, _: CurrentAdmin, db: DB) -> SchoolAdminOut:
    school = await _school(db, school_id)
    school.instructors = [i for i in school.instructors if i.id != instructor_id]
    await db.commit()
    return await _school_out(db, school_id)
