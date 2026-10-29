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


def create_token(subject: uuid.UUID, kind: TokenKind, lifetime: timedelta, version: int = 0) -> str:
    """`version`: the account's session_version for session tokens; raising it cancels every token issued before."""
    now = utcnow()
    payload = {"sub": str(subject), "typ": kind, "ver": version, "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _claims(token: str, kind: TokenKind) -> tuple[uuid.UUID, int] | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != kind:
            return None
        # Tokens issued before session versions existed carry none: they belong to version 0.
        return uuid.UUID(payload["sub"]), int(payload.get("ver", 0))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def decode_token(token: str, kind: TokenKind) -> uuid.UUID | None:
    claims = _claims(token, kind)
    return claims[0] if claims else None


def decode_session(token: str, kind: Literal["user", "admin"]) -> tuple[uuid.UUID, int] | None:
    """(account id, session version) of a session cookie; the caller compares the version with the account's."""
    return _claims(token, kind)


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
