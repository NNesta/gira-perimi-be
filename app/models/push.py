import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class PushSubscription(Base):
    """One browser or installed app that accepted phone notifications (Web Push). A learner can have several."""

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The push service's address for this browser; unique, so a device signed in by someone else moves with them.
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    @property
    def info(self) -> dict:
        """The shape pywebpush (and the browser's PushSubscription.toJSON()) use."""
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}
