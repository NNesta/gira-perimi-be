import base64
import json
from collections.abc import AsyncIterator

import pytest
from google.oauth2 import id_token
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.admin import login_limiter
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import create_engine, get_db
from app.main import app
from app.models import Admin
from app.services.content import ContentStore, get_content

ADMIN_EMAIL = "admin@tsindaneza.rw"
ADMIN_PASSWORD = "Ijambobanga-ryiza-2026"
GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com"


def google_credential(**claims) -> str:
    """A stand-in for a Google ID token: the stubbed verifier below returns these claims."""
    return "test." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()


def fake_verify_oauth2_token(credential, _request, audience=None, clock_skew_in_seconds=0):
    # Same contract as google.oauth2.id_token.verify_oauth2_token: claims on success, ValueError otherwise.
    if audience != GOOGLE_CLIENT_ID or not credential.startswith("test."):
        raise ValueError("Could not verify token")
    return json.loads(base64.urlsafe_b64decode(credential.removeprefix("test.")))


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Ignore outbound-network settings from a developer's .env: no real proxy, SMTP, push keys or Sentry in tests."""
    monkeypatch.setattr(settings, "OUTBOUND_PROXY", "")
    for name in (
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
        "SENTRY_DSN",
    ):
        monkeypatch.setattr(settings, name, "")  # reminders and alerts off unless a test switches them on


@pytest.fixture
async def session_factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def content() -> ContentStore:
    return get_content()


@pytest.fixture
async def client(session_factory, monkeypatch) -> AsyncIterator[AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    monkeypatch.setattr(id_token, "verify_oauth2_token", fake_verify_oauth2_token)
    app.dependency_overrides[get_db] = override_db
    login_limiter._hits.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


def google_claims(email: str = "keza@gmail.com", name: str = "Keza Uwase", sub: str | None = None) -> dict:
    return {
        "sub": sub or f"google-{email.lower()}",
        "email": email,
        "email_verified": True,
        "name": name,
        "given_name": name.split()[0],
        "picture": "https://lh3.googleusercontent.com/a/test-photo",
    }


async def login(
    http: AsyncClient, email: str = "keza@gmail.com", name: str = "Keza Uwase", sub: str | None = None
) -> dict:
    """Signs a learner in the only way learners can: POST /auth/google with a Google ID token."""
    credential = google_credential(**google_claims(email, name, sub))
    response = await http.post("/api/v1/auth/google", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def admin(db) -> Admin:
    record = Admin(email=ADMIN_EMAIL, name="Umuyobozi", password_hash=hash_password(ADMIN_PASSWORD))
    db.add(record)
    await db.commit()
    return record
