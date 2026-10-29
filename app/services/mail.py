"""Outgoing email (reminders, sign-in links): the shared look and one SMTP connection per batch."""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from app.core.config import settings

logger = logging.getLogger(__name__)

# Email palette, matching the website. Mail clients ignore stylesheets, so every element is styled inline.
BRAND = "#129b68"
INK = "#0b1324"
INK_SOFT = "#273248"
MUTED = "#5d6779"
LINE = "#e2e8f0"
CANVAS = "#f4f7fb"
TRACK = "#dde5ee"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def font(size: int, weight: int = 400, color: str = INK, line: float = 1.5) -> str:
    return f"font-family:{FONT};font-size:{size}px;font-weight:{weight};line-height:{line};color:{color};"


def new_message(to: str, subject: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    # Mail servers and spam filters expect both; smtplib adds neither.
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=parseaddr(settings.SMTP_FROM)[1].rpartition("@")[2] or None)
    return message


def deliver(messages: list[EmailMessage]) -> list[bool]:
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
                logger.warning("Email to %s failed: %s", message["To"], exc)
                results.append(False)
    return results
