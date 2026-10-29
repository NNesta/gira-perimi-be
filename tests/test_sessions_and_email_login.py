import re
import uuid
from datetime import timedelta

import jwt
import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import ALGORITHM, USER_COOKIE
from app.db.base import utcnow
from app.models import Admin, EmailLogin, User
from app.services import mail
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login


@pytest.fixture
def outbox(monkeypatch):
    """Email switched on, with deliveries captured instead of sent."""
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_FROM", "Tsinda Neza <noreply@example.com>")
    monkeypatch.setattr(settings, "SITE_URL", "https://tsindaneza.example")
    sent = []

    def deliver(messages):
        sent.extend(messages)
        return [True] * len(messages)

    monkeypatch.setattr(mail, "deliver", deliver)
    return sent


def link_in(message) -> str:
    body = message.get_body(("plain",)).get_content()
    return re.search(r"https://tsindaneza\.example/injira/imeyili\?\S+", body).group(0)


def token_in(message) -> str:
    return re.search(r"token=([\w-]+)", link_in(message)).group(1)


async def me_with(client, token: str):
    client.cookies.clear()
    return await client.get("/api/v1/auth/me", headers={"Cookie": f"{USER_COOKIE}={token}"})


# ---------------------------------------------------------------------- cancelling sessions
async def test_sign_out_everywhere_ends_every_session(client):
    await login(client)
    other_device = client.cookies.get(USER_COOKIE)
    assert (await client.post("/api/v1/auth/logout-all")).status_code == 204
    assert (await me_with(client, other_device)).status_code == 401

    await login(client)  # signing in again works
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_sessions_from_before_versions_still_work(client, db):
    """Upgrading must not sign anyone out: a token without a version counts as version 0."""
    user = await login(client)
    now = utcnow()
    legacy = jwt.encode(
        {"sub": user["id"], "typ": "user", "iat": now, "exp": now + timedelta(days=1)},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    assert (await me_with(client, legacy)).status_code == 200


async def test_suspension_ends_sessions_even_once_lifted(client, admin, db):
    learner = await login(client)
    session = client.cookies.get(USER_COOKIE)
    client.cookies.clear()
    admin_login = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    assert (await client.post("/api/v1/admin/auth/login", json=admin_login)).status_code == 200
    users = f"/api/v1/admin/users/{learner['id']}"
    assert (await client.patch(users, json={"is_active": False})).status_code == 200
    assert (await client.patch(users, json={"is_active": True})).status_code == 200

    assert (await me_with(client, session)).status_code == 401


async def test_admin_password_reset_ends_admin_sessions(client, admin, db):
    admin_login = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    assert (await client.post("/api/v1/admin/auth/login", json=admin_login)).status_code == 200
    assert (await client.get("/api/v1/admin/auth/me")).status_code == 200
    # What `python -m app.cli create-admin` does on a reset.
    await db.execute(update(Admin).where(Admin.email == ADMIN_EMAIL).values(session_version=Admin.session_version + 1))
    await db.commit()
    assert (await client.get("/api/v1/admin/auth/me")).status_code == 401


# ---------------------------------------------------------------------- sign-in links by email
async def test_email_link_registers_and_signs_in_once(client, db, outbox):
    assert (await client.get("/api/v1/auth/config")).json()["email_login"] is True
    asked = await client.post(
        "/api/v1/auth/email", json={"email": "Uwase.Aline@Yahoo.fr", "name": " Aline  Uwase ", "next": "/ikizamini"}
    )
    assert asked.status_code == 202

    [message] = outbox
    assert message["To"] == "uwase.aline@yahoo.fr" and "kwinjira" in message["Subject"]
    assert "&next=%2Fikizamini" in link_in(message)
    assert "Injira kuri Tsinda Neza" in message.get_body(("html",)).get_content()
    # Only a hash of the token is kept.
    assert token_in(message) not in {row.token_hash for row in await db.scalars(select(EmailLogin))}

    signed_in = await client.post("/api/v1/auth/email/verify", json={"token": token_in(message)})
    assert signed_in.status_code == 200
    user = signed_in.json()
    assert user["email"] == "uwase.aline@yahoo.fr" and user["name"] == "Aline Uwase"
    assert user["given_name"] == "Aline" and user["google_account"] is False and user["onboarded"] is False
    assert (await client.get("/api/v1/auth/me")).json()["id"] == user["id"]

    again = await client.post("/api/v1/auth/email/verify", json={"token": token_in(message)})
    assert again.status_code == 400


async def test_email_link_opens_an_existing_google_account_unchanged(client, outbox):
    keza = await login(client)  # Google: "Keza Uwase", with a photo
    client.cookies.clear()
    await client.post("/api/v1/auth/email", json={"email": "keza@gmail.com", "name": "Undi Izina"})
    user = (await client.post("/api/v1/auth/email/verify", json={"token": token_in(outbox[0])})).json()
    assert user["id"] == keza["id"] and user["name"] == "Keza Uwase" and user["google_account"] is True
    assert "Muraho Keza" in outbox[0].get_body(("plain",)).get_content()


async def test_expired_or_unknown_links_do_not_work(client, db, outbox):
    await client.post("/api/v1/auth/email", json={"email": "aline@example.com"})
    await db.execute(update(EmailLogin).values(expires_at=utcnow() - timedelta(minutes=1)))
    await db.commit()
    expired = await client.post("/api/v1/auth/email/verify", json={"token": token_in(outbox[0])})
    assert expired.status_code == 400
    assert (await client.post("/api/v1/auth/email/verify", json={"token": "x" * 43})).status_code == 400


async def test_email_links_are_rate_limited_and_never_sent_to_suspended_accounts(client, db, outbox):
    for _ in range(settings.EMAIL_LOGIN_PER_ADDRESS):
        assert (await client.post("/api/v1/auth/email", json={"email": "aline@example.com"})).status_code == 202
    blocked = await client.post("/api/v1/auth/email", json={"email": "aline@example.com"})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers

    db.add(User(email="hagaritswe@example.com", name="Hagaritswe", is_active=False))
    await db.commit()
    answer = await client.post("/api/v1/auth/email", json={"email": "hagaritswe@example.com"})
    assert answer.status_code == 202  # the same answer as for anyone else...
    assert [m["To"] for m in outbox].count("hagaritswe@example.com") == 0  # ...but nothing is sent


async def test_email_link_is_off_without_smtp_and_rejects_foreign_next(client, outbox, monkeypatch):
    await client.post("/api/v1/auth/email", json={"email": "aline@example.com", "next": "//evil.example"})
    assert "next=" not in link_in(outbox[0])

    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert (await client.post("/api/v1/auth/email", json={"email": "aline@example.com"})).status_code == 409
    assert (await client.post("/api/v1/auth/email", json={"email": "not-an-address"})).status_code == 422


async def test_learners_without_google_can_name_themselves(client, outbox, db):
    await client.post("/api/v1/auth/email", json={"email": "mugisha@example.com"})
    user = (await client.post("/api/v1/auth/email/verify", json={"token": token_in(outbox[0])})).json()
    assert user["name"] == "mugisha"  # nothing better was given

    renamed = (await client.patch("/api/v1/me", json={"name": "Mugisha  Eric"})).json()
    assert renamed["name"] == "Mugisha Eric" and renamed["given_name"] == "Mugisha"
    stored = await db.get(User, uuid.UUID(user["id"]))
    assert stored.name == "Mugisha Eric"
