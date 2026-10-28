import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

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


class UserUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    phone: str | None = Field(default=None, max_length=32, pattern=r"^\+?[0-9 ]{9,20}$")
    exam_date: date | None = None
    daily_goal: int = Field(default=20, ge=5, le=100)
    reminders: bool = False
    onboarded: bool = False


class GoogleLoginIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class AuthConfigOut(BaseModel):
    google_client_id: str | None
    paywall_enabled: bool
    reminders_available: bool
    # VAPID public key for PushManager.subscribe(); null when phone notifications are switched off.
    push_public_key: str | None = None
