"""Driving schools. An admin opens a school and lists its instructors' email addresses; whoever signs in with one of
them (Google or an email link) teaches there. Instructors make classes, each with a join code; a learner who joins with
the code agrees that the school's instructors see their progress, and can leave at any time."""

import logging
import secrets
import smtplib
import uuid
from collections import defaultdict

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import ClassMember, School, SchoolClass, SchoolInstructor, User
from app.schemas.school import (
    ClassDetailOut,
    ClassLearnerOut,
    ClassSummaryOut,
    ClassTopicOut,
    InstructorOut,
    MyClassOut,
    SchoolAdminOut,
    TeachingSchoolOut,
)
from app.services import mail, progress
from app.services.content import TOPICS, ContentStore
from app.services.practice import answer_history

logger = logging.getLogger(__name__)

# No 0/O or 1/I: codes are read out loud and typed on phones.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
WEAK_ACCURACY = 0.75
WEAK_MIN_ANSWERS = 5


class NotFound(Exception):
    pass


def normalize_code(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


async def new_code(db: AsyncSession) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if await db.scalar(select(SchoolClass.id).where(SchoolClass.join_code == code)) is None:
            return code


# ---------------------------------------------------------------------- admin
async def admin_list(db: AsyncSession) -> list[SchoolAdminOut]:
    schools = list(
        await db.scalars(select(School).options(selectinload(School.instructors)).order_by(School.created_at.desc()))
    )
    emails = {i.email for s in schools for i in s.instructors}
    names = dict((await db.execute(select(User.email, User.name).where(User.email.in_(emails)))).all())
    classes = dict(
        (await db.execute(select(SchoolClass.school_id, func.count()).group_by(SchoolClass.school_id))).all()
    )
    learners = dict(
        (
            await db.execute(
                select(SchoolClass.school_id, func.count(func.distinct(ClassMember.user_id)))
                .join(ClassMember, ClassMember.class_id == SchoolClass.id)
                .group_by(SchoolClass.school_id)
            )
        ).all()
    )
    return [
        SchoolAdminOut(
            id=s.id,
            name=s.name,
            active=s.active,
            created_at=s.created_at,
            instructors=[InstructorOut(id=i.id, email=i.email, name=names.get(i.email)) for i in s.instructors],
            classes=classes.get(s.id, 0),
            learners=learners.get(s.id, 0),
        )
        for s in schools
    ]


async def get_school(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.scalar(select(School).options(selectinload(School.instructors)).where(School.id == school_id))
    if school is None:
        raise NotFound
    return school


def _invitation(email: str, school: str) -> mail.EmailMessage:
    site = settings.SITE_URL.rstrip("/")
    message = mail.new_message(email, f"Ubu uri umwarimu wa {school} kuri Tsinda Neza")
    message.set_content(
        "\n\n".join(
            [
                "Muraho,",
                f"{school} yagushyize ku rutonde rw’abarimu bayo kuri Tsinda Neza. Ushobora gukora amatsinda "
                "y’abanyeshuri, ukabaha kode yo kwinjiramo, maze ukabona aho buri wese ageze yitegura ikizamini.",
                f"Injira ukoresheje iyi meyili ({email}), hanyuma ujye kuri: {site}/umwarimu",
                "Itsinda rya Tsinda Neza",
            ]
        )
    )
    return message


async def invite(db: AsyncSession, school: School, email: str) -> None:
    """Adds an instructor (by email) and, when email is set up, tells them how to start."""
    email = email.strip().lower()
    if any(i.email == email for i in school.instructors):
        return
    school.instructors.append(SchoolInstructor(email=email))
    await db.commit()
    if not settings.email_login_available:
        return
    try:
        await anyio.to_thread.run_sync(mail.deliver, [_invitation(email, school.name)])
    except (OSError, smtplib.SMTPException) as exc:  # the invitation is a courtesy: the instructor is added anyway
        logger.warning("Instructor invitation not sent: %s", exc)


# ---------------------------------------------------------------------- instructors
async def teaching_school_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    """Open schools where this account teaches (its email is on the school's list)."""
    return set(
        await db.scalars(
            select(SchoolInstructor.school_id)
            .join(School, School.id == SchoolInstructor.school_id)
            .where(SchoolInstructor.email == user.email.lower(), School.active)
        )
    )


async def is_instructor(db: AsyncSession, user: User) -> bool:
    return bool(await teaching_school_ids(db, user))


async def teaching(db: AsyncSession, user: User) -> list[TeachingSchoolOut]:
    ids = await teaching_school_ids(db, user)
    if not ids:
        return []
    schools = await db.scalars(
        select(School).options(selectinload(School.classes)).where(School.id.in_(ids)).order_by(School.name)
    )
    counts = dict(
        (
            await db.execute(
                select(ClassMember.class_id, func.count())
                .join(SchoolClass, SchoolClass.id == ClassMember.class_id)
                .where(SchoolClass.school_id.in_(ids))
                .group_by(ClassMember.class_id)
            )
        ).all()
    )
    return [
        TeachingSchoolOut(
            id=s.id,
            name=s.name,
            classes=[
                ClassSummaryOut(
                    id=c.id,
                    name=c.name,
                    join_code=c.join_code,
                    archived=c.archived,
                    learners=counts.get(c.id, 0),
                    created_at=c.created_at,
                )
                for c in s.classes
            ],
        )
        for s in schools
    ]


async def class_for(db: AsyncSession, user: User, class_id: uuid.UUID) -> SchoolClass:
    """A class this instructor may see: one of a school they teach at."""
    klass = await db.scalar(
        select(SchoolClass).options(selectinload(SchoolClass.school)).where(SchoolClass.id == class_id)
    )
    if klass is None or klass.school_id not in await teaching_school_ids(db, user):
        raise NotFound
    return klass


async def class_detail(db: AsyncSession, klass: SchoolClass, content: ContentStore) -> ClassDetailOut:
    rows = (
        await db.execute(
            select(User, ClassMember.joined_at)
            .join(ClassMember, ClassMember.user_id == User.id)
            .where(ClassMember.class_id == klass.id, User.is_active)
            .order_by(User.name)
        )
    ).all()
    names = {t["id"]: t["name"] for t in TOPICS}
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    learners = []
    for user, joined_at in rows:
        exams = await progress.completed_exams(db, user.id)
        topics = progress.topic_mastery(await answer_history(db, user), content)
        for t in topics:
            totals[t.topic][0] += t.answered
            totals[t.topic][1] += t.correct
        weak = sorted(
            (t for t in topics if t.answered >= WEAK_MIN_ANSWERS and (t.accuracy or 0) < WEAK_ACCURACY),
            key=lambda t: t.accuracy or 0,
        )
        learners.append(
            ClassLearnerOut(
                id=user.id,
                name=user.name,
                email=user.email,
                picture_url=user.picture_url,
                joined_at=joined_at,
                last_active_at=user.last_active_at,
                exam_date=user.exam_date,
                readiness=progress.readiness(progress.readiness_scores(exams)),
                exams_completed=len(exams),
                weak_topics=[names[t.topic] for t in weak[:3]],
            )
        )
    class_topics = [
        ClassTopicOut(
            topic=t["id"],
            name=t["name"],
            answered=totals[t["id"]][0],
            accuracy=round(totals[t["id"]][1] / totals[t["id"]][0], 4) if totals[t["id"]][0] else None,
        )
        for t in TOPICS
    ]
    class_topics.sort(key=lambda t: (t.accuracy is None, t.accuracy or 0))
    return ClassDetailOut(
        id=klass.id,
        name=klass.name,
        join_code=klass.join_code,
        archived=klass.archived,
        school_id=klass.school_id,
        school_name=klass.school.name,
        learners=learners,
        topics=class_topics,
    )


async def member(db: AsyncSession, klass: SchoolClass, user_id: uuid.UUID) -> User:
    user = await db.scalar(
        select(User)
        .join(ClassMember, ClassMember.user_id == User.id)
        .where(ClassMember.class_id == klass.id, User.id == user_id, User.is_active)
    )
    if user is None:
        raise NotFound
    return user


# ---------------------------------------------------------------------- learners
async def joinable(db: AsyncSession, code: str) -> SchoolClass:
    klass = await db.scalar(
        select(SchoolClass)
        .options(selectinload(SchoolClass.school))
        .join(School, School.id == SchoolClass.school_id)
        .where(SchoolClass.join_code == normalize_code(code), SchoolClass.archived.is_(False), School.active)
    )
    if klass is None:
        raise NotFound
    return klass


async def join(db: AsyncSession, user: User, klass: SchoolClass) -> MyClassOut:
    record = await db.scalar(
        select(ClassMember).where(ClassMember.class_id == klass.id, ClassMember.user_id == user.id)
    )
    if record is None:
        record = ClassMember(class_id=klass.id, user_id=user.id)
        db.add(record)
        await db.commit()
    return MyClassOut(id=klass.id, name=klass.name, school=klass.school.name, joined_at=record.joined_at)


async def my_classes(db: AsyncSession, user: User) -> list[MyClassOut]:
    rows = await db.execute(
        select(SchoolClass, School.name, ClassMember.joined_at)
        .join(ClassMember, ClassMember.class_id == SchoolClass.id)
        .join(School, School.id == SchoolClass.school_id)
        .where(ClassMember.user_id == user.id)
        .order_by(ClassMember.joined_at)
    )
    return [MyClassOut(id=c.id, name=c.name, school=school, joined_at=at) for c, school, at in rows.all()]
