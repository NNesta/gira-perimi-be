import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.user import User

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"


class ExamAttempt(Base):
    """One mock exam: 20 questions answered within 20 minutes, like the real provisional test."""

    __tablename__ = "exam_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_IN_PROGRESS, index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime())
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    total: Mapped[int] = mapped_column(Integer)
    score: Mapped[int | None] = mapped_column(Integer)
    # Short public code for the result card a learner chose to share ("Nabonye 19/20"); null until they do.
    share_code: Mapped[str | None] = mapped_column(String(16), unique=True)

    user: Mapped["User"] = relationship(back_populates="exams")
    answers: Mapped[list["ExamAnswer"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExamAnswer.position",
    )

    @property
    def is_completed(self) -> bool:
        return self.status == STATUS_COMPLETED


class ExamAnswer(Base):
    __tablename__ = "exam_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("exam_attempts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    question_id: Mapped[int] = mapped_column(Integer, index=True)
    selected: Mapped[int | None] = mapped_column(SmallInteger)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    attempt: Mapped[ExamAttempt] = relationship(back_populates="answers")
