"""Sign-in links by email: the second way in, for learners who cannot use Google (often a phone set up by its seller,
whose Gmail opens on the phone but whose password nobody knows), or who have no Gmail at all.

A link works once, for EMAIL_LOGIN_MINUTES. Opening it shows a button; only pressing it signs in, because mail
scanners open links on their own and would otherwise use them up.
"""

import hashlib
import html
import secrets
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlencode

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.models import EmailLogin, User
from app.services.mail import BRAND, CANVAS, INK, INK_SOFT, LINE, MUTED, font, new_message


class LinkInvalid(Exception):
    """Unknown, used or expired link."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def safe_next(path: str | None) -> str | None:
    """Only a path on this site may follow the sign-in (no open redirect)."""
    return path if path and path.startswith("/") and not path.startswith(("//", "/\\")) else None


async def issue(db: AsyncSession, email: str, name: str | None) -> str:
    """Records a new link for `email` and returns its token (sent by email, never stored)."""
    now = utcnow()
    # Old links are of no use to anyone: tidy up while we are here.
    await db.execute(delete(EmailLogin).where(EmailLogin.expires_at < now - timedelta(days=1)))
    token = secrets.token_urlsafe(32)
    db.add(
        EmailLogin(
            email=email,
            token_hash=_hash(token),
            name=name,
            created_at=now,
            expires_at=now + timedelta(minutes=settings.EMAIL_LOGIN_MINUTES),
        )
    )
    await db.commit()
    return token


async def redeem(db: AsyncSession, token: str) -> EmailLogin:
    """Uses up the link and returns it. One atomic update, so a link pressed twice at once still signs in once."""
    now = utcnow()
    token_hash = _hash(token)
    used = await db.execute(
        update(EmailLogin)
        .where(EmailLogin.token_hash == token_hash, EmailLogin.used_at.is_(None), EmailLogin.expires_at > now)
        .values(used_at=now)
    )
    if used.rowcount != 1:
        raise LinkInvalid
    await db.commit()
    return await db.scalar(select(EmailLogin).where(EmailLogin.token_hash == token_hash))


def link_url(token: str, next_path: str | None) -> str:
    query = {"token": token} | ({"next": next_path} if next_path else {})
    return f"{settings.SITE_URL.rstrip('/')}/injira/imeyili?{urlencode(query)}"


def compose(email: str, url: str, user: User | None) -> EmailMessage:
    minutes = settings.EMAIL_LOGIN_MINUTES
    site = settings.SITE_URL.rstrip("/")
    greeting = f"Muraho {user.given_name or user.name.split()[0]}," if user else "Muraho,"
    lead = f"Kanda kuri buto ikurikira kugira ngo winjire kuri Tsinda Neza. Ikora rimwe gusa, mu minota {minutes}."
    ignore = "Niba atari wowe wasabye iyi link, irengagize iyi meyili: nta wundi ushobora kwinjira atayifite."

    message = new_message(email, "Link yo kwinjira kuri Tsinda Neza")
    message.set_content("\n\n".join([greeting, lead, f"Injira: {url}", ignore, "Itsinda rya Tsinda Neza"]))
    e = html.escape
    message.add_alternative(
        f"""<!doctype html>
<html lang="rw">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>Tsinda Neza</title></head>
<body style="margin:0;padding:0;background:{CANVAS}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{CANVAS}">
<tr><td align="center" style="padding:36px 16px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px">
    <tr><td style="padding:0 4px 20px">
      <img src="{e(site)}/icons/icon-192.png" width="36" height="36" alt=""
        style="display:inline-block;vertical-align:middle;border:0;border-radius:10px">
      <span style="vertical-align:middle;margin-left:8px;letter-spacing:-0.3px;{font(20, 800, INK, 1)}"
        >Tsinda<span style="color:{BRAND}">Neza</span></span>
    </td></tr>
    <tr><td style="background:#ffffff;border:1px solid {LINE};border-radius:20px;padding:34px 30px">
      <h1 style="margin:0 0 10px;{font(22, 800, INK, 1.3)}">{e(greeting)}</h1>
      <p style="margin:0;{font(16, 400, INK_SOFT, 1.6)}">{e(lead)}</p>
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:26px"><tr>
        <td style="background:{BRAND};border-radius:12px">
          <a href="{e(url)}" style="display:inline-block;padding:14px 30px;text-decoration:none;border-radius:12px;
            {font(16, 700, "#ffffff", 1)}">Injira kuri Tsinda Neza</a>
        </td>
      </tr></table>
      <p style="margin:26px 0 0;word-break:break-all;{font(12, 400, MUTED, 1.6)}">
        Buto idakora? Fungura iyi link: <a href="{e(url)}" style="color:{BRAND}">{e(url)}</a></p>
      <p style="margin:22px 0 0;padding-top:18px;border-top:1px solid {LINE};{font(13, 400, MUTED, 1.6)}"
        >{e(ignore)}</p>
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>""",
        subtype="html",
    )
    return message
