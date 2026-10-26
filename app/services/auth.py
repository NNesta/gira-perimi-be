import anyio
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import DUMMY_PASSWORD_HASH, verify_password
from app.db.base import utcnow
from app.models import Admin, User


class AuthError(Exception):
    pass


class AccountSuspended(Exception):
    pass


class GoogleUnavailable(Exception):
    """Sign-in with Google cannot run right now (not configured, or Google's keys could not be fetched)."""


# Tolerates a server clock that runs slightly behind Google's ("Token used too early").
GOOGLE_CLOCK_SKEW_SECONDS = 10


async def verify_google_credential(credential: str) -> dict:
    """Validates a Google Identity Services ID token (signature, audience, expiry, issuer)."""
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleUnavailable("Kwinjira ukoresheje Google ntibirashyirwaho kuri seriveri.")

    def _verify() -> dict:
        return id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=GOOGLE_CLOCK_SKEW_SECONDS,
        )

    try:
        info = await anyio.to_thread.run_sync(_verify)
    except google_exceptions.TransportError as exc:
        raise GoogleUnavailable("Ntitwashoboye kuvugana na Google. Ongera ugerageze mu kanya gato.") from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        raise AuthError("Google ntiyemeje uwo uri we. Ongera ugerageze.") from exc
    if not info.get("email") or info.get("email_verified") not in (True, "true"):
        raise AuthError("Imeyili yawe ya Google ntiremezwa.")
    return info


async def upsert_user(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    google_sub: str | None = None,
    given_name: str | None = None,
    picture_url: str | None = None,
) -> User:
    """Registers the learner on first sign-in, otherwise refreshes their Google profile.

    The Google account id (`sub`) wins over the email, which a Google account can change; an account found by
    email alone is linked to the Google account on that sign-in.
    """
    email = email.strip().lower()
    user = None
    if google_sub:
        user = (await db.scalars(select(User).where(User.google_sub == google_sub))).first()
    if user is None:
        user = (await db.scalars(select(User).where(User.email == email))).first()
    now = utcnow()
    if user is None:
        user = User(email=email, name=name, google_sub=google_sub, given_name=given_name, picture_url=picture_url)
        db.add(user)
    else:
        if not user.is_active:
            raise AccountSuspended
        user.name = name or user.name
        user.given_name = given_name or user.given_name
        user.picture_url = picture_url or user.picture_url
        user.google_sub = user.google_sub or google_sub
    user.last_login_at = now
    user.last_active_at = now
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_admin(db: AsyncSession, email: str, password: str) -> Admin | None:
    admin = (await db.scalars(select(Admin).where(Admin.email == email.strip().lower()))).first()
    # bcrypt is CPU-bound: keep it off the event loop. The dummy hash keeps timing constant for unknown emails.
    password_hash = admin.password_hash if admin else DUMMY_PASSWORD_HASH
    valid = await anyio.to_thread.run_sync(verify_password, password, password_hash)
    if admin is None or not valid:
        return None
    admin.last_login_at = utcnow()
    await db.commit()
    return admin
