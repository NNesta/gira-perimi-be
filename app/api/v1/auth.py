from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.security import USER_COOKIE, clear_session_cookie, create_token, set_session_cookie
from app.models import User
from app.schemas.user import AuthConfigOut, GoogleLoginIn, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SUSPENDED = "Konti yawe yahagaritswe. Vugana n’ubuyobozi bwa Gira Perimi."


def _start_session(response: Response, user: User) -> None:
    lifetime = timedelta(days=settings.USER_SESSION_DAYS)
    token = create_token(user.id, "user", lifetime)
    set_session_cookie(response, USER_COOKIE, token, int(lifetime.total_seconds()))


@router.get("/config")
async def auth_config() -> AuthConfigOut:
    return AuthConfigOut(
        google_client_id=settings.GOOGLE_CLIENT_ID or None,
        paywall_enabled=settings.PAYWALL_ENABLED,
        reminders_available=settings.reminders_available,
    )


@router.post("/google", response_model=UserOut)
async def google_login(body: GoogleLoginIn, response: Response, db: DB) -> User:
    """Registers (first visit) or signs in a learner with a Google ID token from Google Identity Services.

    Google is the only way learners sign in; email + password is reserved for admins (`/admin/auth/login`).
    """
    try:
        info = await auth_service.verify_google_credential(body.credential)
    except auth_service.GoogleUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    try:
        user = await auth_service.upsert_user(
            db,
            email=info["email"],
            name=info.get("name") or info["email"].split("@")[0],
            google_sub=info["sub"],
            given_name=info.get("given_name"),
            picture_url=info.get("picture"),
        )
    except auth_service.AccountSuspended as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SUSPENDED) from exc
    _start_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    clear_session_cookie(response, USER_COOKIE)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
