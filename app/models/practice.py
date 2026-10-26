import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class PracticeAnswer(Base):
    """A single answer given in practice mode (instant feedback, untimed)."""

    __tablename__ = "practice_answers"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_practice_answers_user_client"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(Integer, index=True)
    selected: Mapped[int] = mapped_column(SmallInteger)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    answered_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Set by the browser for answers given offline, so a sync that is retried never saves an answer twice.
    client_id: Mapped[str | None] = mapped_column(String(36))
