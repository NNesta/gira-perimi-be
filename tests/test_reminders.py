import uuid
from datetime import timedelta

import pytest

from app.core.config import settings
from app.db.base import utcnow
from app.models import PracticeAnswer, User
from app.services import reminders
from app.services.dates import local_day
from tests.conftest import login


@pytest.fixture
def smtp(monkeypatch):
    """Reminders switched on, with deliveries captured instead of sent."""
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_FROM", "Tsinda Neza <noreply@example.com>")
    monkeypatch.setattr(settings, "SITE_URL", "https://tsindaneza.example")
    outbox = []

    def deliver(messages):
        outbox.extend(messages)
        return [True] * len(messages)

    monkeypatch.setattr(reminders, "_deliver", deliver)
    return outbox


async def test_reminders_reach_opted_in_learners_below_their_goal_once_a_day(client, content, db, smtp):
    config = (await client.get("/api/v1/auth/config")).json()
    assert config["reminders_available"] is True

    keza = await login(client)
    assert (await client.patch("/api/v1/me", json={"reminders": True, "daily_goal": 10})).status_code == 200
    exam_day = local_day(utcnow()) + timedelta(days=5)
    await client.patch("/api/v1/me", json={"exam_date": exam_day.isoformat()})
    await login(client, email="mugisha@gmail.com", name="Mugisha Eric")  # reminders off: never emailed

    sent = await reminders.send_reminders(db)
    assert sent == [keza["email"]]
    message = smtp[0]
    assert message["To"] == keza["email"] and "Iminota 10" in message["Subject"]
    body = message.get_body(("plain",)).get_content()
    assert "ibibazo 0 kuri 10" in body and "Hasigaye iminsi 5" in body
    assert "https://tsindaneza.example/ikibaho" in body and "https://tsindaneza.example/reka-kwibutswa?token=" in body
    assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert message.get_body(("html",)) is not None

    assert await reminders.send_reminders(db) == []  # once a day

    user = await db.get(User, uuid.UUID(keza["id"]))
    user.last_reminded_on = None
    for _ in range(10):
        db.add(PracticeAnswer(user_id=user.id, question_id=content.active_ids[0], selected=0, is_correct=False))
    await db.commit()
    assert await reminders.send_reminders(db) == []  # goal reached: no reminder


async def test_one_click_unsubscribe(client, db, smtp):
    keza = await login(client)
    await client.patch("/api/v1/me", json={"reminders": True})
    user = await db.get(User, uuid.UUID(keza["id"]))
    token = reminders.unsubscribe_token(user)

    assert (await client.post("/api/v1/reminders/unsubscribe", params={"token": "x" * 40})).status_code == 400
    login_token = client.cookies.get("gp_session")
    assert (await client.post("/api/v1/reminders/unsubscribe", params={"token": login_token})).status_code == 400

    # Mail providers POST form data without an Origin header (RFC 8058).
    response = await client.post(
        "/api/v1/reminders/unsubscribe", params={"token": token}, data={"List-Unsubscribe": "One-Click"}
    )
    assert response.status_code == 204
    await db.refresh(user)
    assert user.reminders is False


async def test_send_reminders_refuses_without_smtp(db):
    with pytest.raises(RuntimeError):
        await reminders.send_reminders(db)
