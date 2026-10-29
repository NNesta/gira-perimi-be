from google.auth import exceptions as google_exceptions
from google.oauth2 import id_token

from app.core.config import settings
from app.models import User
from tests.conftest import GOOGLE_CLIENT_ID, google_claims, google_credential, login


async def google_sign_in(client, **claims):
    return await client.post("/api/v1/auth/google", json={"credential": google_credential(**claims)})


async def test_google_registers_then_signs_in(client):
    first = await login(client)
    assert first["email"] == "keza@gmail.com"
    assert first["given_name"] == "Keza" and first["picture_url"].startswith("https://lh3.googleusercontent.com/")
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["id"] == first["id"]

    # Same Google account later, with a new display name and a changed email: same learner, refreshed profile.
    again = await login(client, email="keza.uwase@gmail.com", name="Keza U.", sub="google-keza@gmail.com")
    assert again["id"] == first["id"] and again["name"] == "Keza U."

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_google_links_an_existing_account_by_email(client, db):
    existing = User(email="mugisha@gmail.com", name="Mugisha")
    db.add(existing)
    await db.commit()
    user = await login(client, email="Mugisha@gmail.com", name="Mugisha Eric")
    assert user["id"] == str(existing.id) and user["name"] == "Mugisha Eric"
    await db.refresh(existing)
    assert existing.google_sub == "google-mugisha@gmail.com"


async def test_google_rejects_bad_tokens(client):
    assert (await client.post("/api/v1/auth/google", json={"credential": "x" * 40})).status_code == 401
    unverified = await google_sign_in(client, **(google_claims() | {"email_verified": False}))
    assert unverified.status_code == 401 and "ntiremezwa" in unverified.json()["detail"]
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_google_verification_uses_client_id_clock_skew_and_proxy(client, monkeypatch):
    seen = {}

    def verify(credential, request, audience=None, clock_skew_in_seconds=0):
        seen.update(audience=audience, skew=clock_skew_in_seconds, proxies=dict(request.session.proxies))
        return google_claims()

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    assert (await google_sign_in(client, **google_claims())).status_code == 200
    assert seen == {"audience": GOOGLE_CLIENT_ID, "skew": 10, "proxies": {}}

    proxy = "http://proxy.server:3128"
    monkeypatch.setattr(settings, "OUTBOUND_PROXY", proxy)
    assert (await google_sign_in(client, **google_claims())).status_code == 200
    assert seen["proxies"] == {"http": proxy, "https": proxy}


async def test_google_unreachable_is_a_temporary_error(client, monkeypatch):
    def verify(*_args, **_kwargs):
        raise google_exceptions.TransportError("certs unreachable")

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    response = await google_sign_in(client, **google_claims())
    assert response.status_code == 503


async def test_protected_routes_require_login(client):
    for method, url in [
        ("get", "/api/v1/me/dashboard"),
        ("post", "/api/v1/exams"),
        ("get", "/api/v1/practice/questions"),
    ]:
        assert (await client.request(method.upper(), url)).status_code == 401


async def test_learners_cannot_sign_in_with_email_only(client):
    # Email + password is for admins; learners use Google or a one-time link sent by email, never a bare address.
    response = await client.post("/api/v1/auth/dev-login", json={"email": "a@b.rw", "name": "Aba"})
    assert response.status_code == 404


async def test_google_login_without_client_id_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    response = await google_sign_in(client, **google_claims())
    assert response.status_code == 503
    config = (await client.get("/api/v1/auth/config")).json()
    assert config == {
        "google_client_id": None,
        "email_login": False,
        "paywall_enabled": False,
        "reminders_available": False,
        "push_public_key": None,
    }


async def test_config_exposes_the_client_id(client):
    config = (await client.get("/api/v1/auth/config")).json()
    assert config["google_client_id"] == GOOGLE_CLIENT_ID


async def test_foreign_origin_cannot_post(client):
    response = await client.post(
        "/api/v1/auth/google",
        json={"credential": google_credential(**google_claims())},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


async def test_profile_update_and_account_deletion(client):
    await login(client)
    updated = await client.patch("/api/v1/me", json={"phone": "+250 788 123 456"})
    assert updated.status_code == 200 and updated.json()["phone"] == "+250 788 123 456"
    assert (await client.patch("/api/v1/me", json={"phone": "abc"})).status_code == 422
    assert (await client.delete("/api/v1/me")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_paywall_hook(client, monkeypatch):
    await login(client)
    monkeypatch.setattr(settings, "PAYWALL_ENABLED", True)
    assert (await client.post("/api/v1/exams")).status_code == 402
    assert (await client.get("/api/v1/lessons/ibyapa")).status_code == 402
    assert (await client.get("/api/v1/lessons/intangiriro")).status_code == 200  # free lesson stays open
    lessons = (await client.get("/api/v1/lessons")).json()
    assert {lesson["slug"]: lesson["locked"] for lesson in lessons}["ibyapa"] is True
