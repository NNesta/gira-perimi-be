"""Opt-in daily reminders for learners who have not reached today's goal: email, phone notifications, or both.

Run once a day (e.g. 18:00 Kigali) by a scheduler: `python -m app.cli send-reminders`. A learner gets at most one
reminder per day: by email while `reminders` is on (every email carries a one-click unsubscribe link), and on each
device where they switched phone notifications on.
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
from app.models import PushSubscription, User
from app.services import progress, push, review
from app.services.dates import day_start, local_day
from app.services.mail import BRAND, CANVAS, INK, INK_SOFT, LINE, MUTED, TRACK, new_message
from app.services.mail import deliver as _deliver
from app.services.mail import font as _font

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
    """Learners with a reminder channel on, not yet reminded today, and below their daily goal."""
    today = local_day(now)
    channels = []
    if settings.reminders_available:
        channels.append(User.reminders)
    if settings.push_available:
        channels.append(User.id.in_(select(PushSubscription.user_id)))
    if not channels:
        return []
    users = list(
        await db.scalars(
            select(User).where(
                User.is_active,
                or_(*channels),
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


def _days(n: int) -> str:
    return f"umunsi {n}" if n == 1 else f"iminsi {n}"


def _lead(reminder: Reminder) -> str:
    """The one sentence that fits the learner's day best."""
    if reminder.days_to_exam == 0:
        return (
            "Uyu munsi ni umunsi w’ikizamini cyawe. Subiramo ibibazo bike mbere yo kugenda, kandi ugire amahirwe masa!"
        )
    if reminder.answered == 0:
        return "Nturakora imyitozo y’uyu munsi. Iminota icumi irahagije ngo ukomeze kwitegura neza ikizamini."
    left = reminder.user.daily_goal - reminder.answered
    questions = "ikibazo 1" if left == 1 else f"ibibazo {left}"
    return f"Uri mu nzira nziza! Hasigaye {questions} ngo ugere ku ntego wihaye uyu munsi."


def _html(reminder: Reminder, *, greeting: str, lead: str, preheader: str, site: str, unsubscribe_url: str) -> str:
    """Table layout with inline styles: the form Gmail, Outlook and Apple Mail all render the same way."""
    e = html.escape
    goal = reminder.user.daily_goal
    percent = min(100, round(reminder.answered * 100 / goal)) if goal else 0
    bar = "font-size:0;line-height:8px;height:8px"
    filled = ""
    if percent:
        filled = f'<td width="{percent}%" style="background:{BRAND};border-radius:999px;{bar}">&nbsp;</td>'

    facts = []
    if (days := reminder.days_to_exam) is not None:
        facts.append(("Ikizamini cyawe", {0: "Uyu munsi", 1: "Ejo"}.get(days, f"Mu minsi {days}")))
    if reminder.review_due:
        facts.append(("Ibyo gusubiramo uyu munsi", str(reminder.review_due)))
    if reminder.streak:
        facts.append(("Iminsi wiga udasiba", str(reminder.streak)))
    rows = ""
    for i, (label, value) in enumerate(facts):
        cell = "padding:13px 0;" + (f"border-top:1px solid {LINE};" if i else "")
        rows += (
            f'<tr><td style="{cell}{_font(14, 400, INK_SOFT)}">{e(label)}</td>'
            f'<td align="right" style="{cell}{_font(14, 700)}">{e(value)}</td></tr>'
        )
    facts_table = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px">'
        f"{rows}</table>"
        if rows
        else ""
    )
    flag = "".join(
        f'<td width="{width}" height="4" style="background:{color};font-size:0;line-height:0">&nbsp;</td>'
        for width, color in ((28, "#00a1de"), (14, "#fad201"), (14, "#20603d"))
    )
    # Invisible filler keeps clients from pulling body text into the inbox preview after the preheader.
    filler = "&#847;&zwnj;&nbsp;" * 40

    return f"""<!doctype html>
<html lang="rw">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>Tsinda Neza</title>
<style>
  @media (max-width: 480px) {{ .card {{ padding: 28px 22px !important; }} .page {{ padding: 24px 12px !important; }} }}
</style>
</head>
<body style="margin:0;padding:0;background:{CANVAS}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all">{e(preheader)}{filler}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{CANVAS}">
<tr><td class="page" align="center" style="padding:36px 16px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px">
    <tr><td style="padding:0 4px 20px">
      <a href="{e(site)}" style="text-decoration:none">
        <img src="{e(site)}/icons/icon-192.png" width="36" height="36" alt=""
          style="display:inline-block;vertical-align:middle;border:0;border-radius:10px">
        <span style="vertical-align:middle;margin-left:8px;letter-spacing:-0.3px;{_font(20, 800, INK, 1)}"
          >Tsinda<span style="color:{BRAND}">Neza</span></span>
      </a>
    </td></tr>
    <tr><td class="card" style="background:#ffffff;border:1px solid {LINE};border-radius:20px;padding:36px 34px">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:22px">
        <tr>{flag}</tr></table>
      <h1 style="margin:0 0 10px;{_font(23, 800, INK, 1.3)}">{e(greeting)}</h1>
      <p style="margin:0;{_font(16, 400, INK_SOFT, 1.6)}">{e(lead)}</p>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
        style="margin-top:26px;background:{CANVAS};border-radius:14px">
      <tr><td style="padding:18px 20px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="text-transform:uppercase;letter-spacing:0.08em;{_font(12, 700, MUTED)}">Intego y’uyu munsi</td>
          <td align="right" style="{_font(15, 800, INK)}">{reminder.answered}<span
            style="color:{MUTED};font-weight:600"> / {goal}</span></td>
        </tr></table>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
          style="margin-top:12px;background:{TRACK};border-radius:999px">
          <tr>{filled}<td style="{bar}">&nbsp;</td></tr></table>
      </td></tr>
      </table>
      {facts_table}

      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:28px"><tr>
        <td style="background:{BRAND};border-radius:12px">
          <a href="{e(site)}/ikibaho"
            style="display:inline-block;padding:14px 28px;text-decoration:none;border-radius:12px;
              {_font(15, 700, "#ffffff", 1)}"
            >Komeza wige &rarr;</a>
        </td>
      </tr></table>

      <p style="margin:30px 0 0;{_font(14, 400, INK_SOFT, 1.6)}">Tukwifurije amasomo meza,<br>
        <strong style="color:{INK}">Itsinda rya Tsinda Neza</strong></p>
    </td></tr>
    <tr><td align="center" style="padding:24px 16px 0;{_font(12, 400, MUTED, 1.7)}">
      Wakiriye iyi meyili kuko wahisemo kwibutswa kwiga kuri Tsinda Neza.<br>
      <a href="{e(site)}/umwirondoro" style="color:{MUTED};text-decoration:underline">Hindura intego</a>
      &nbsp;&middot;&nbsp;
      <a href="{e(unsubscribe_url)}" style="color:{MUTED};text-decoration:underline">Hagarika kwibutswa</a>
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""


def _lines(reminder: Reminder) -> list[str]:
    lines = [f"Uyu munsi umaze gusubiza ibibazo {reminder.answered} kuri {reminder.user.daily_goal} wihaye."]
    if reminder.review_due:
        lines.append(f"Ufite ibintu {reminder.review_due} byo gusubiramo uyu munsi.")
    if reminder.streak:
        lines.append(f"Umaze {_days(reminder.streak)} wiga udasiba. Ntucikeho!")
    if reminder.days_to_exam is not None:
        lines.append(
            "Ikizamini cyawe ni uyu munsi. Amahirwe masa!"
            if reminder.days_to_exam == 0
            else f"Hasigaye {_days(reminder.days_to_exam)} ngo ukore ikizamini."
        )
    return lines


def _subject(reminder: Reminder) -> str:
    if reminder.days_to_exam == 0:
        return "Amahirwe masa ku kizamini cy’uyu munsi! 🍀"
    if reminder.streak >= 2:
        return f"Ntucikeho! Umaze {_days(reminder.streak)} wiga 🔥"
    return "Iminota 10 y’imyitozo uyu munsi? 🚦"


def notification(reminder: Reminder) -> dict:
    """The phone notification: the email's subject as the title and today's progress as the text."""
    lines = _lines(reminder)
    return {"title": _subject(reminder), "body": " ".join(lines[:2]), "url": "/ikibaho", "tag": "reminder"}


def compose(reminder: Reminder) -> EmailMessage:
    user = reminder.user
    site = settings.SITE_URL.rstrip("/")
    token = unsubscribe_token(user)
    dashboard_url = f"{site}/ikibaho"
    unsubscribe_url = f"{site}/reka-kwibutswa?token={token}"
    lines = _lines(reminder)
    subject = _subject(reminder)

    message = new_message(user.email, subject)
    message["List-Unsubscribe"] = f"<{site}/api/v1/reminders/unsubscribe?token={token}>"
    message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    greeting = f"Mwiriwe {_first_name(user)},"
    lead = _lead(reminder)
    message.set_content(
        "\n\n".join(
            [
                greeting,
                lead,
                "\n".join(lines),
                f"Komeza wige: {dashboard_url}",
                "Tukwifurije amasomo meza,\nItsinda rya Tsinda Neza",
                f"Hindura intego: {site}/umwirondoro\nHagarika kwibutswa: {unsubscribe_url}",
            ]
        )
    )
    message.add_alternative(
        _html(reminder, greeting=greeting, lead=lead, preheader=lines[0], site=site, unsubscribe_url=unsubscribe_url),
        subtype="html",
    )
    return message


async def send_reminders(db: AsyncSession, now: datetime | None = None, dry_run: bool = False) -> list[str]:
    """Sends today's reminders and returns the addresses of the learners reached (or that would be, with dry_run)."""
    if not (settings.reminders_available or settings.push_available):
        raise RuntimeError("Reminders are switched off: set SMTP_HOST and SMTP_FROM, or the VAPID keys.")
    now = now or utcnow()
    reminders = await pending(db, now)
    if dry_run or not reminders:
        return [r.user.email for r in reminders]

    reached: set = set()
    by_email = [r for r in reminders if settings.reminders_available and r.user.reminders]
    if by_email:
        try:
            sent = await anyio.to_thread.run_sync(_deliver, [compose(r) for r in by_email])
        except (OSError, smtplib.SMTPException) as exc:  # mail server unreachable: phones can still be reached
            logger.error("Reminder emails not sent: %s", exc)
            sent = [False] * len(by_email)
        reached |= {r.user.id for r, ok in zip(by_email, sent, strict=True) if ok}
    if settings.push_available:
        for reminder in reminders:
            if await push.notify(db, reminder.user.id, notification(reminder)):
                reached.add(reminder.user.id)

    today: date = local_day(now)
    for reminder in reminders:
        if reminder.user.id in reached:
            reminder.user.last_reminded_on = today
    await db.commit()
    return [r.user.email for r in reminders if r.user.id in reached]
