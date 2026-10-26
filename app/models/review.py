import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow

KIND_QUESTION = "question"
KIND_SIGN = "sign"


class ReviewItem(Base):
    """Something a learner got wrong, scheduled for spaced review (Leitner boxes 1–5)."""

    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "item_id", name="uq_review_items_user_item"),
        Index("ix_review_items_user_due", "user_id", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    # Question id (as text) or sign id.
    item_id: Mapped[str] = mapped_column(String(32))
    box: Mapped[int] = mapped_column(SmallInteger, default=1)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set once the item has been recalled correctly in the last box; it then leaves the review queue.
    mastered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
