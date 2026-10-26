import uuid
from datetime import datetime

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


class UserUpdate(BaseModel):
    phone: str | None = Field(default=None, max_length=32, pattern=r"^\+?[0-9 ]{9,20}$")


class GoogleLoginIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class AuthConfigOut(BaseModel):
    google_client_id: str | None
    paywall_enabled: bool
