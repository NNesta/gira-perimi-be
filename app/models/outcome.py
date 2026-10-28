import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, String, Text, UniqueConstraint, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow
from app.models.user import User

RESULT_PASSED = "passed"
RESULT_FAILED = "failed"
RESULT_NOT_TAKEN = "not_taken"


class ExamOutcome(Base):
    """What a learner told us about the real exam ("Watsinze ikizamini?"), asked once their exam date has passed."""

    __tablename__ = "exam_outcomes"
    __table_args__ = (UniqueConstraint("user_id", "exam_date", name="uq_exam_outcomes_user_date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exam_date: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(12))  # passed | failed | not_taken
    # Optional words for other learners. Shown on the site only if the learner agreed and an admin approved them.
    testimonial: Mapped[str | None] = mapped_column(Text)
    testimonial_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    testimonial_status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | approved | hidden
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()
