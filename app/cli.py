"""Management commands.

    uv run python -m app.cli create-admin --email you@example.com --name "Your Name"
    uv run python -m app.cli list-admins

The password is read from the GP_ADMIN_PASSWORD environment variable when set, otherwise prompted twice.
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import Admin

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


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="create an admin, or reset an existing admin's password")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Umuyobozi")
    sub.add_parser("list-admins")
    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(create_admin(args.email, args.name))
    else:
        asyncio.run(list_admins())


if __name__ == "__main__":
    main()
