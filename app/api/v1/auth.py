import logging
import smtplib
from datetime import timedelta

import anyio
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.core.security import USER_COOKIE, clear_session_cookie, create_token, set_session_cookie
from app.models import User
from app.schemas.user import AuthConfigOut, EmailLinkIn, EmailLoginIn, GoogleLoginIn, UserOut
from app.services import auth as auth_service
from app.services import email_login, mail, schools

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

SUSPENDED = "Konti yawe yahagaritswe. Vugana n’ubuyobozi bwa Tsinda Neza."
# Each request for a link counts, sent or not: these stop the form being used to flood someone's inbox.
link_limiter_address = SlidingWindowLimiter(settings.EMAIL_LOGIN_PER_ADDRESS, settings.EMAIL_LOGIN_MINUTES * 60)
link_limiter_visitor = SlidingWindowLimiter(settings.EMAIL_LOGIN_PER_VISITOR, 60 * 60)


def _start_session(response: Response, user: User) -> None:
    lifetime = timedelta(days=settings.USER_SESSION_DAYS)
    token = create_token(user.id, "user", lifetime, user.session_version)
    set_session_cookie(response, USER_COOKIE, token, int(lifetime.total_seconds()))


@router.get("/config")
async def auth_config() -> AuthConfigOut:
    return AuthConfigOut(
        google_client_id=settings.GOOGLE_CLIENT_ID or None,
        email_login=settings.email_login_available,
        paywall_enabled=settings.PAYWALL_ENABLED,
        reminders_available=settings.reminders_available,
        push_public_key=settings.VAPID_PUBLIC_KEY if settings.push_available else None,
    )


@router.post("/google", response_model=UserOut)
async def google_login(body: GoogleLoginIn, response: Response, db: DB) -> User:
    """Registers (first visit) or signs in a learner with a Google ID token from Google Identity Services.

    Learners can also sign in with a link sent by email (`/auth/email`); email + password is reserved for admins.
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


@router.post("/email", status_code=status.HTTP_202_ACCEPTED)
async def email_link(body: EmailLoginIn, request: Request, db: DB) -> None:
    """Emails a one-time sign-in link (registers on first use): for learners who cannot use Google.

    The answer is the same whether or not the address has an account, so the form cannot be used to find out who
    studies here.
    """
    if not settings.email_login_available:
        raise HTTPException(status.HTTP_409_CONFLICT, "Kwinjira ukoresheje imeyili ntibirashyirwaho kuri uru rubuga.")
    email = body.email.strip().lower()
    keys = ((link_limiter_visitor, f"ip:{client_ip(request)}"), (link_limiter_address, f"email:{email}"))
    wait = max(limiter.retry_after(key) for limiter, key in keys)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Mwasabye link nyinshi. Ongera ugerageze nyuma y’iminota {max(1, wait // 60)}.",
            headers={"Retry-After": str(wait)},
        )
    for limiter, key in keys:
        limiter.hit(key)

    user = (await db.scalars(select(User).where(User.email == email))).first()
    if user is not None and not user.is_active:
        logger.info("Sign-in link not sent: account suspended")
        return
    token = await email_login.issue(db, email, body.name)
    message = email_login.compose(email, email_login.link_url(token, email_login.safe_next(body.next)), user)
    try:
        sent = await anyio.to_thread.run_sync(mail.deliver, [message])
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("Sign-in link not sent: %s", exc)
        sent = [False]
    if not sent[0]:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Ntitwashoboye kohereza imeyili. Ongera ugerageze mu kanya gato."
        )


@router.post("/email/verify", response_model=UserOut)
async def email_link_verify(body: EmailLinkIn, response: Response, db: DB) -> User:
    """Signs in with the token from a sign-in link (once)."""
    try:
        link = await email_login.redeem(db, body.token)
        user = await auth_service.sign_in_by_email(db, email=link.email, name=link.name)
    except email_login.LinkInvalid as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Iyi link ntigikora: yarakoreshejwe cyangwa igihe cyayo cyarashize."
        ) from exc
    except auth_service.AccountSuspended as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, SUSPENDED) from exc
    _start_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    clear_session_cookie(response, USER_COOKIE)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_everywhere(response: Response, db: DB, user: CurrentUser) -> None:
    """Signs the learner out on every device at once (a phone left behind, a shared computer)."""
    user.session_version += 1
    await db.commit()
    clear_session_cookie(response, USER_COOKIE)


@router.get("/me")
async def me(db: DB, user: CurrentUser) -> UserOut:
    """The signed-in learner, and whether they teach at a driving school (the site then links to /umwarimu)."""
    out = UserOut.model_validate(user)
    out.instructor = await schools.is_instructor(db, user)
    return out
