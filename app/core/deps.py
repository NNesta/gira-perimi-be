from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import ADMIN_COOKIE, USER_COOKIE, decode_session
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Admin, User
from app.services.content import ContentStore, get_content

DB = Annotated[AsyncSession, Depends(get_db)]
Content = Annotated[ContentStore, Depends(get_content)]

ACTIVITY_TOUCH_INTERVAL = timedelta(minutes=5)


async def _session_user(request: Request, db: AsyncSession) -> User | None:
    token = request.cookies.get(USER_COOKIE)
    claims = decode_session(token, "user") if token else None
    if claims is None:
        return None
    user_id, version = claims
    user = await db.get(User, user_id)
    # A session from before "sign out everywhere" or a suspension has an older version: it no longer counts.
    if user is None or version != user.session_version:
        return None
    now = utcnow()
    if user.is_active and (user.last_active_at is None or now - user.last_active_at > ACTIVITY_TOUCH_INTERVAL):
        user.last_active_at = now
        await db.commit()
    return user


async def get_optional_user(request: Request, db: DB) -> User | None:
    user = await _session_user(request, db)
    return user if user is not None and user.is_active else None


async def get_current_user(request: Request, db: DB) -> User:
    user = await _session_user(request, db)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Banza winjire kugira ngo ukomeze.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Konti yawe yahagaritswe. Vugana n’ubuyobozi bwa Tsinda Neza.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def has_access(user: User | None) -> bool:
    """Paywall hook: today everything is free; flip PAYWALL_ENABLED once subscriptions launch."""
    if not settings.PAYWALL_ENABLED:
        return True
    return user is not None and user.has_premium


async def require_access(user: CurrentUser) -> User:
    if not has_access(user):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Iyi serivisi isaba ifatabuguzi rikiri ku gihe.")
    return user


PaidUser = Annotated[User, Depends(require_access)]


async def get_current_admin(request: Request, db: DB) -> Admin:
    token = request.cookies.get(ADMIN_COOKIE)
    claims = decode_session(token, "admin") if token else None
    admin = await db.get(Admin, claims[0]) if claims else None
    # A password reset raises the version: sessions opened with the old password end at once.
    if admin is None or claims[1] != admin.session_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Injira nk’umuyobozi kugira ngo ukomeze.")
    return admin


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]
