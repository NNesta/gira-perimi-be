import uuid
from datetime import datetime

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class EmailLogin(Base):
    """A sign-in link sent by email, for learners who cannot use Google. Works once, for EMAIL_LOGIN_MINUTES.

    Only a hash of the link's token is stored, so a copy of the database does not open anyone's account.
    """

    __tablename__ = "email_logins"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # The name given with the request, used only if the link creates the account.
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
