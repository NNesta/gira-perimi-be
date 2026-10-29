"""Driving schools: an admin opens a school and invites its instructors by email; instructors make classes with a join
code; learners join a class with the code, agreeing that its instructors see their progress."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow


class School(Base):
    __tablename__ = "schools"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    # A closed school's instructors lose access and its classes take no new learners; nothing is deleted.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    instructors: Mapped[list["SchoolInstructor"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="SchoolInstructor.email"
    )
    classes: Mapped[list["SchoolClass"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="SchoolClass.created_at"
    )


class SchoolInstructor(Base):
    """An instructor, known by email: whoever signs in with that address (Google or email link) teaches here."""

    __tablename__ = "school_instructors"
    __table_args__ = (UniqueConstraint("school_id", "email", name="uq_school_instructors_school_email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SchoolClass(Base):
    __tablename__ = "school_classes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    # What learners type (or open as a link) to join, e.g. K7M2QX.
    join_code: Mapped[str] = mapped_column(String(12), unique=True)
    # An archived class keeps its learners' history for instructors but takes no new learners.
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    school: Mapped[School] = relationship(back_populates="classes")
    members: Mapped[list["ClassMember"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class ClassMember(Base):
    """A learner in a class. Joining is the learner's consent to the class's instructors seeing their progress."""

    __tablename__ = "class_members"
    __table_args__ = (UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("school_classes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
