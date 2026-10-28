"""Management commands.

    uv run python -m app.cli create-admin --email you@example.com --name "Your Name"
    uv run python -m app.cli list-admins
    uv run python -m app.cli daily                         # THE scheduled task: backup, then reminders (16:00 UTC)
    uv run python -m app.cli backup                        # backup only (e.g. before a deploy)
    uv run python -m app.cli send-reminders [--dry-run]    # reminders only
    uv run python -m app.cli vapid-keys                    # key pair for phone notifications (once)
    uv run python -m app.cli sentry-test                   # check that error alerts arrive

The password is read from the GP_ADMIN_PASSWORD environment variable when set, otherwise prompted twice.
"""

import argparse
import asyncio
import base64
import getpass
import os
import sqlite3
import sys

import sentry_sdk
from sqlalchemy import select

from app.core.config import settings
from app.core.monitoring import init_sentry
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.session import SessionLocal, engine
from app.models import Admin
from app.services import backups, reminders
from app.services.dates import local_day

MIN_PASSWORD_LENGTH = 10


def read_password() -> str:
    password = os.environ.get("GP_ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return password


async def create_admin(email: str, name: str) -> None:
    email = email.strip().lower()
    password_hash = hash_password(read_password())
    async with SessionLocal() as db:
        admin = (await db.scalars(select(Admin).where(Admin.email == email))).first()
        if admin is None:
            db.add(Admin(email=email, name=name, password_hash=password_hash))
            action = "created"
        else:
            admin.name = name
            admin.password_hash = password_hash
            action = "updated (password reset)"
        await db.commit()
    await engine.dispose()
    print(f"Admin {email} {action}.")


async def list_admins() -> None:
    async with SessionLocal() as db:
        for admin in await db.scalars(select(Admin).order_by(Admin.created_at)):
            print(f"{admin.email}\t{admin.name}\tlast login: {admin.last_login_at or '-'}")
    await engine.dispose()


async def send_reminders(dry_run: bool) -> None:
    async with SessionLocal() as db:
        try:
            emails = await reminders.send_reminders(db, dry_run=dry_run)
        except RuntimeError as exc:
            sys.exit(str(exc))
    await engine.dispose()
    verb = "Would remind" if dry_run else "Reminded"
    print(f"{verb} {len(emails)} learner(s).")
    for email in emails:
        print(f"  {email}")


def run_backup() -> bool:
    """Makes today's copy and drops the old ones. On failure: alert, say so in the task log, return False."""
    today = local_day(utcnow())
    try:
        made = backups.backup(today)
        removed = backups.prune(today)
    except (backups.BackupError, OSError, sqlite3.Error) as exc:
        sentry_sdk.capture_exception(exc)
        print(f"Backup FAILED: {exc}", file=sys.stderr)
        return False
    kept = len(backups.list_backups())
    print(f"Backup: {made.path} ({made.size / 1024:.0f} KB). {kept} kept, {len(removed)} old removed.")
    return True


async def daily() -> None:
    """The one scheduled task (free accounts get one): back up the database first, then send today's reminders."""
    ok = run_backup()
    if settings.reminders_available or settings.push_available:
        try:
            async with SessionLocal() as db:
                emails = await reminders.send_reminders(db)
            print(f"Reminded {len(emails)} learner(s).")
        except Exception as exc:  # reported, and the backup result above still stands
            sentry_sdk.capture_exception(exc)
            print(f"Reminders FAILED: {exc}", file=sys.stderr)
            ok = False
    else:
        print("Reminders are off (set SMTP or the VAPID keys to switch them on).")
    await engine.dispose()
    sentry_sdk.flush(10)
    if not ok:
        sys.exit(1)


def sentry_test() -> None:
    if not init_sentry("cli"):
        sys.exit("SENTRY_DSN is not set in .env.")
    event = sentry_sdk.capture_message("Tsinda Neza: test alert from the server")
    sentry_sdk.flush(10)
    print(f"Test alert sent ({event}). It should appear in Sentry within a minute.")


def vapid_keys() -> None:
    """Prints a new key pair for phone notifications, ready to paste into .env."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    key = ec.generate_private_key(ec.SECP256R1())
    print(f"VAPID_PUBLIC_KEY={b64url(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))}")
    print(f"VAPID_PRIVATE_KEY={b64url(key.private_numbers().private_value.to_bytes(32, 'big'))}")
    print("# Keep the private key secret. Changing the pair later switches off notifications on every device.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="create an admin, or reset an existing admin's password")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Umuyobozi")
    sub.add_parser("list-admins")
    sub.add_parser("vapid-keys", help="print a new key pair for phone notifications")
    sub.add_parser("daily", help="the scheduled task: back up the database, then send today's reminders")
    sub.add_parser("backup", help="back up the database now and drop old copies")
    sub.add_parser("sentry-test", help="send a test error alert to Sentry")
    remind = sub.add_parser(
        "send-reminders", help="remind learners who have not reached today's goal (email and phone, opt-in)"
    )
    remind.add_argument("--dry-run", action="store_true", help="list who would be reminded, send nothing")
    args = parser.parse_args()
    if args.command != "sentry-test":
        init_sentry("cli")
    if args.command == "daily":
        asyncio.run(daily())
    elif args.command == "backup":
        sys.exit(0 if run_backup() else 1)
    elif args.command == "sentry-test":
        sentry_test()
    elif args.command == "create-admin":
        asyncio.run(create_admin(args.email, args.name))
    elif args.command == "send-reminders":
        asyncio.run(send_reminders(args.dry_run))
    elif args.command == "vapid-keys":
        vapid_keys()
    else:
        asyncio.run(list_admins())


if __name__ == "__main__":
    main()
