import uuid
from datetime import timedelta
from typing import Literal

import bcrypt
import jwt
from fastapi import Response

from app.core.config import settings
from app.db.base import utcnow

USER_COOKIE = "gp_session"
ADMIN_COOKIE = "gp_admin"
# "unsubscribe" tokens ride in reminder emails and can only switch reminders off.
TokenKind = Literal["user", "admin", "unsubscribe"]
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# A fixed hash used to keep login timing constant when the email does not exist.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")


def create_token(subject: uuid.UUID, kind: TokenKind, lifetime: timedelta) -> str:
    now = utcnow()
    payload = {"sub": str(subject), "typ": kind, "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, kind: TokenKind) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != kind:
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def set_session_cookie(response: Response, name: str, token: str, max_age: int) -> None:
    response.set_cookie(
        name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/", httponly=True, secure=settings.COOKIE_SECURE, samesite="lax")
