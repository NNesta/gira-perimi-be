"""Opt-in daily reminder emails for learners who have not reached today's goal.

Run once a day (e.g. 18:00 Kigali) by a scheduler: `python -m app.cli send-reminders`. A learner gets at most one
reminder per day, only while `reminders` is on; every email carries a one-click unsubscribe link.
"""

import html
import logging
import smtplib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.message import EmailMessage

import anyio
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_token
from app.db.base import utcnow
from app.models import User
from app.services import progress, review
from app.services.dates import day_start, local_day

logger = logging.getLogger(__name__)

UNSUBSCRIBE_TOKEN_LIFETIME = timedelta(days=90)


@dataclass(frozen=True, slots=True)
class Reminder:
    user: User
    answered: int
    streak: int
    review_due: int
    days_to_exam: int | None


def unsubscribe_token(user: User) -> str:
    return create_token(user.id, "unsubscribe", UNSUBSCRIBE_TOKEN_LIFETIME)


async def pending(db: AsyncSession, now: datetime) -> list[Reminder]:
    """Learners with reminders on, not yet reminded today, and below their daily goal."""
    today = local_day(now)
    users = list(
        await db.scalars(
            select(User).where(
                User.is_active,
                User.reminders,
                or_(User.last_reminded_on.is_(None), User.last_reminded_on < today),
            )
        )
    )
    if not users:
        return []
    answered = await progress.answered_since(db, day_start(today), [u.id for u in users])
    reminders = []
    for user in users:
        done = answered.get(user.id, 0)
        if done >= user.daily_goal:
            continue
        days = await progress.active_days(db, user.id, since=today - timedelta(days=90))
        reminders.append(
            Reminder(
                user=user,
                answered=done,
                streak=progress.streak(days, today),
                review_due=(await review.summary(db, user.id)).due,
                days_to_exam=(user.exam_date - today).days if user.exam_date and user.exam_date >= today else None,
            )
        )
    return reminders


def _first_name(user: User) -> str:
    return user.given_name or user.name.split()[0]


def compose(reminder: Reminder) -> EmailMessage:
    user = reminder.user
    site = settings.SITE_URL.rstrip("/")
    token = unsubscribe_token(user)
    dashboard_url = f"{site}/ikibaho"
    unsubscribe_url = f"{site}/reka-kwibutswa?token={token}"

    lines = [f"Uyu munsi umaze gusubiza ibibazo {reminder.answered} kuri {user.daily_goal} wihaye."]
    if reminder.review_due:
        lines.append(f"Ufite ibintu {reminder.review_due} byo gusubiramo uyu munsi.")
    if reminder.streak:
        lines.append(f"Umaze iminsi {reminder.streak} wiga udasiba. Ntucikeho!")
    if reminder.days_to_exam is not None:
        lines.append(
            "Ikizamini cyawe ni uyu munsi. Amahirwe masa!"
            if reminder.days_to_exam == 0
            else f"Hasigaye iminsi {reminder.days_to_exam} ngo ukore ikizamini."
        )

    subject = (
        f"Ntucikeho! Umaze iminsi {reminder.streak} wiga 🔥"
        if reminder.streak
        else "Iminota 10 y’imyitozo uyu munsi? 🚦"
    )
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = user.email
    message["List-Unsubscribe"] = f"<{site}/api/v1/reminders/unsubscribe?token={token}>"
    message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    greeting = f"Mwiriwe {_first_name(user)},"
    message.set_content(
        "\n\n".join(
            [
                greeting,
                "\n".join(lines),
                f"Komeza wige: {dashboard_url}",
                f"— Gira Perimi\nNtushaka kongera kwibutswa? {unsubscribe_url}",
            ]
        )
    )
    paragraphs = "".join(f'<p style="margin:0 0 10px">{html.escape(line)}</p>' for line in lines)
    message.add_alternative(
        f"""<!doctype html><html lang="rw">
<body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#0d1628">
<div style="max-width:520px;margin:0 auto;padding:28px 18px">
  <p style="font-size:20px;font-weight:bold;margin:0 0 18px">Gira<span style="color:#129b68">Perimi</span></p>
  <div style="background:#ffffff;border-radius:18px;padding:26px;border:1px solid #e3e8f0">
    <p style="font-size:17px;font-weight:bold;margin:0 0 14px">{html.escape(greeting)}</p>
    {paragraphs}
    <a href="{html.escape(dashboard_url)}" style="display:inline-block;margin-top:14px;background:#129b68;color:#ffffff;
      text-decoration:none;font-weight:bold;padding:12px 22px;border-radius:12px">Komeza wige</a>
  </div>
  <p style="font-size:12px;color:#5b6576;margin:18px 4px 0">Wahisemo kwibutswa kuri Gira Perimi.
    <a href="{html.escape(unsubscribe_url)}" style="color:#5b6576">Hagarika kwibutswa</a></p>
</div></body></html>""",
        subtype="html",
    )
    return message


def _deliver(messages: list[EmailMessage]) -> list[bool]:
    """Sends over one SMTP connection (SSL on port 465, STARTTLS otherwise). Blocking: run it in a thread."""
    smtp_class = smtplib.SMTP_SSL if settings.SMTP_PORT == 465 else smtplib.SMTP
    results = []
    with smtp_class(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        if smtp_class is smtplib.SMTP:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        for message in messages:
            try:
                smtp.send_message(message)
                results.append(True)
            except smtplib.SMTPException as exc:
                logger.warning("Reminder to %s failed: %s", message["To"], exc)
                results.append(False)
    return results


async def send_reminders(db: AsyncSession, now: datetime | None = None, dry_run: bool = False) -> list[str]:
    """Sends today's reminders and returns the addresses reached (or that would be, with dry_run)."""
    if not settings.reminders_available:
        raise RuntimeError("Reminders are switched off: set SMTP_HOST and SMTP_FROM.")
    now = now or utcnow()
    reminders = await pending(db, now)
    if dry_run or not reminders:
        return [r.user.email for r in reminders]
    messages = [compose(r) for r in reminders]
    sent = await anyio.to_thread.run_sync(_deliver, messages)
    today: date = local_day(now)
    reached = []
    for reminder, ok in zip(reminders, sent, strict=True):
        if ok:
            reminder.user.last_reminded_on = today
            reached.append(reminder.user.email)
    await db.commit()
    return reached
