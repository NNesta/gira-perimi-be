import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.exam import ExamAttempt
    from app.models.practice import PracticeAnswer
    from app.models.progress import LessonProgress


class User(Base):
    """A learner. Accounts are created on first Google sign-in."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    given_name: Mapped[str | None] = mapped_column(String(100))
    picture_url: Mapped[str | None] = mapped_column(String(1024))
    phone: Mapped[str | None] = mapped_column(String(32))
    # Subscription hook for the future paywall: "free" | "premium".
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_active_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    exams: Mapped[list["ExamAttempt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    practice_answers: Mapped[list["PracticeAnswer"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    lessons: Mapped[list["LessonProgress"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)

    @property
    def has_premium(self) -> bool:
        if self.plan != "premium":
            return False
        return self.plan_expires_at is None or self.plan_expires_at > utcnow()
