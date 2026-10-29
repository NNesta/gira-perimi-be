import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str
    given_name: str | None
    picture_url: str | None
    phone: str | None
    plan: str
    created_at: datetime
    exam_date: date | None
    daily_goal: int
    reminders: bool
    onboarded: bool
    # Signed in with Google at least once: name and photo come from Google (and are not edited here).
    google_account: bool
    # Teaches at a driving school (filled by GET /auth/me only).
    instructor: bool = False


class UserUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    # For accounts opened with an email link; a Google sign-in replaces it with the name on the Google account.
    name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=32, pattern=r"^\+?[0-9 ]{9,20}$")
    exam_date: date | None = None
    daily_goal: int = Field(default=20, ge=5, le=100)
    reminders: bool = False
    onboarded: bool = False


class GoogleLoginIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class EmailLoginIn(BaseModel):
    """Asks for a sign-in link. `name` names the account if the link creates it; `next` is where to go afterwards."""

    email: EmailStr = Field(max_length=320)
    name: str | None = Field(default=None, max_length=100)
    next: str | None = Field(default=None, max_length=300)


class EmailLinkIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class AuthConfigOut(BaseModel):
    google_client_id: str | None
    # Sign-in links by email are offered (SMTP is set up).
    email_login: bool = False
    paywall_enabled: bool
    reminders_available: bool
    # VAPID public key for PushManager.subscribe(); null when phone notifications are switched off.
    push_public_key: str | None = None
