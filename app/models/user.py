import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, SmallInteger, String, Uuid, false, text
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

    # Study plan: the day of the real exam, the daily question goal and opt-in reminder emails.
    exam_date: Mapped[date | None] = mapped_column(Date)
    daily_goal: Mapped[int] = mapped_column(SmallInteger, default=20, server_default=text("20"))
    reminders: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_reminded_on: Mapped[date | None] = mapped_column(Date)

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
