import base64
import json
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pywebpush import WebPushException
from sqlalchemy import select

from app.core.config import settings
from app.models import PushSubscription, User
from app.services import push, reminders
from tests.conftest import login

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "B" + "x" * 86, "auth": "a" * 22}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


@pytest.fixture
def sent(monkeypatch):
    """Phone notifications switched on, with deliveries captured; endpoints containing "gone" answer 410."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", b64url(public))
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", b64url(key.private_numbers().private_value.to_bytes(32, "big")))
    deliveries = []

    def fake_webpush(subscription, data, **kwargs):
        if "gone" in subscription["endpoint"]:
            raise WebPushException("Push failed: 410 Gone", response=FakeResponse(410))
        deliveries.append((subscription["endpoint"], json.loads(data), kwargs["vapid_claims"]["sub"]))

    monkeypatch.setattr(push, "webpush", fake_webpush)
    return deliveries


async def test_push_is_off_until_the_keys_are_set(client):
    await login(client)
    assert (await client.get("/api/v1/auth/config")).json()["push_public_key"] is None
    body = {"endpoint": ENDPOINT, "keys": KEYS}
    assert (await client.put("/api/v1/push/subscription", json=body)).status_code == 409


async def test_devices_subscribe_move_with_the_learner_and_unsubscribe(client, db, sent):
    keza = await login(client)
    assert (await client.get("/api/v1/auth/config")).json()["push_public_key"] == settings.VAPID_PUBLIC_KEY

    elsewhere = {"endpoint": "https://evil.example/push", "keys": KEYS}
    assert (await client.put("/api/v1/push/subscription", json=elsewhere)).status_code == 422
    body = {"endpoint": ENDPOINT, "keys": KEYS}
    assert (await client.put("/api/v1/push/subscription", json=body)).status_code == 204
    assert (await client.put("/api/v1/push/subscription", json=body)).status_code == 204  # idempotent

    test = (await client.post("/api/v1/push/test")).json()
    assert test == {"sent": 1} and sent[0][0] == ENDPOINT and sent[0][1]["title"] == "Tsinda Neza"

    mugisha = await login(client, email="mugisha@gmail.com", name="Mugisha Eric")  # same phone, another learner
    await client.put("/api/v1/push/subscription", json=body)
    rows = list(await db.scalars(select(PushSubscription)))
    assert len(rows) == 1 and rows[0].user_id == uuid.UUID(mugisha["id"]) != uuid.UUID(keza["id"])

    assert (await client.post("/api/v1/push/unsubscribe", json={"endpoint": ENDPOINT})).status_code == 204
    assert list(await db.scalars(select(PushSubscription))) == []


async def test_daily_reminder_reaches_phones_and_forgets_dead_ones(client, db, sent):
    keza = await login(client)  # email reminders off, SMTP not set up: the phone is the only channel
    for endpoint in (ENDPOINT, "https://fcm.googleapis.com/fcm/send/gone"):
        await client.put("/api/v1/push/subscription", json={"endpoint": endpoint, "keys": KEYS})

    assert await reminders.send_reminders(db) == [keza["email"]]
    endpoint, message, subject = sent[-1]
    assert endpoint == ENDPOINT and message["url"] == "/ikibaho" and message["tag"] == "reminder"
    assert "ibibazo 0 kuri 20" in message["body"] and message["title"]
    assert subject == settings.SITE_URL  # no VAPID_SUBJECT: the site address is the contact

    remaining = list(await db.scalars(select(PushSubscription.endpoint)))
    assert remaining == [ENDPOINT]  # the 410 one is forgotten
    user = await db.get(User, uuid.UUID(keza["id"]))
    assert user.last_reminded_on is not None
    assert await reminders.send_reminders(db) == []  # once a day
