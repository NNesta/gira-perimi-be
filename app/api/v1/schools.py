import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete

from app.core.deps import DB, Content, CurrentUser
from app.models import ClassMember, SchoolClass
from app.schemas.progress import LearnerReportOut
from app.schemas.school import (
    ClassCreate,
    ClassDetailOut,
    ClassPreviewOut,
    ClassSummaryOut,
    ClassUpdate,
    JoinIn,
    MyClassOut,
    TeachingSchoolOut,
)
from app.services import progress, schools

router = APIRouter(tags=["schools"])

CLASS_NOT_FOUND = "Iryo tsinda ntiribonetse."
CODE_NOT_FOUND = "Iyo kode ntibonetse. Reba ko wayanditse neza, cyangwa ubaze umwarimu wawe."


# ---------------------------------------------------------------------- learners
@router.get("/classes/join/{code}")
async def class_preview(code: str, db: DB) -> ClassPreviewOut:
    """Public: the class and school a join code opens, shown before the learner agrees to join."""
    try:
        klass = await schools.joinable(db, code)
    except schools.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CODE_NOT_FOUND) from exc
    return ClassPreviewOut(name=klass.name, school=klass.school.name)


@router.post("/classes/join")
async def join_class(body: JoinIn, db: DB, user: CurrentUser) -> MyClassOut:
    """Joins a class: the learner agrees that the school's instructors see their progress (they can leave any time)."""
    try:
        klass = await schools.joinable(db, body.code)
    except schools.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CODE_NOT_FOUND) from exc
    return await schools.join(db, user, klass)


@router.get("/me/classes")
async def my_classes(db: DB, user: CurrentUser) -> list[MyClassOut]:
    return await schools.my_classes(db, user)


@router.delete("/me/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave_class(class_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    """Leaves a class: its instructors stop seeing the learner's progress at once."""
    await db.execute(delete(ClassMember).where(ClassMember.class_id == class_id, ClassMember.user_id == user.id))
    await db.commit()


# ---------------------------------------------------------------------- instructors
async def _class(db: DB, user: CurrentUser, class_id: uuid.UUID) -> SchoolClass:
    try:
        return await schools.class_for(db, user, class_id)
    except schools.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CLASS_NOT_FOUND) from exc


@router.get("/teaching")
async def teaching(db: DB, user: CurrentUser) -> list[TeachingSchoolOut]:
    """The schools this account teaches at, with their classes; empty for everyone else."""
    return await schools.teaching(db, user)


@router.post("/teaching/schools/{school_id}/classes", status_code=status.HTTP_201_CREATED)
async def create_class(school_id: uuid.UUID, body: ClassCreate, db: DB, user: CurrentUser) -> ClassSummaryOut:
    if school_id not in await schools.teaching_school_ids(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iryo shuri ntiribonetse.")
    klass = SchoolClass(school_id=school_id, name=" ".join(body.name.split()), join_code=await schools.new_code(db))
    db.add(klass)
    await db.commit()
    return ClassSummaryOut(
        id=klass.id, name=klass.name, join_code=klass.join_code, archived=False, learners=0, created_at=klass.created_at
    )


@router.patch("/teaching/classes/{class_id}")
async def update_class(
    class_id: uuid.UUID, body: ClassUpdate, db: DB, user: CurrentUser, content: Content
) -> ClassDetailOut:
    klass = await _class(db, user, class_id)
    if body.name is not None:
        klass.name = " ".join(body.name.split())
    if body.archived is not None:
        klass.archived = body.archived
    await db.commit()
    return await schools.class_detail(db, klass, content)


@router.get("/teaching/classes/{class_id}")
async def class_detail(class_id: uuid.UUID, db: DB, user: CurrentUser, content: Content) -> ClassDetailOut:
    """The class table: every learner's readiness and weak topics, and the class's weakest topics."""
    return await schools.class_detail(db, await _class(db, user, class_id), content)


@router.get("/teaching/classes/{class_id}/learners/{user_id}")
async def class_learner(
    class_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: CurrentUser, content: Content
) -> LearnerReportOut:
    try:
        learner = await schools.member(db, await _class(db, user, class_id), user_id)
    except schools.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uwo munyeshuri ntari muri iri tsinda.") from exc
    return await progress.learner_report(db, learner, content)


@router.delete("/teaching/classes/{class_id}/learners/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_learner(class_id: uuid.UUID, user_id: uuid.UUID, db: DB, user: CurrentUser) -> None:
    klass = await _class(db, user, class_id)
    await db.execute(delete(ClassMember).where(ClassMember.class_id == klass.id, ClassMember.user_id == user_id))
    await db.commit()
