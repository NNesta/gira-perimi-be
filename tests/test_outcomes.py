import uuid
from datetime import timedelta

import sentry_sdk

from app.core import monitoring
from app.core.config import settings
from app.db.base import utcnow
from app.models import User
from app.services.dates import local_day
from tests.conftest import login
from tests.test_admin import admin_login


async def exam_was(db, user_id: str, days_ago: int):
    user = await db.get(User, uuid.UUID(user_id))
    user.exam_date = local_day(utcnow()) - timedelta(days=days_ago)
    await db.commit()
    return user.exam_date.isoformat()


async def test_learners_are_asked_once_their_exam_date_has_passed(client, db):
    keza = await login(client)
    soon = (local_day(utcnow()) + timedelta(days=3)).isoformat()
    await client.patch("/api/v1/me", json={"exam_date": soon})
    assert (await client.get("/api/v1/me/dashboard")).json()["outcome_question"] is None  # not yet

    day = await exam_was(db, keza["id"], 2)
    dashboard = (await client.get("/api/v1/me/dashboard")).json()
    assert dashboard["outcome_question"] == day and dashboard["plan"]["pace"] == "passed"

    wrong = await client.post("/api/v1/me/outcome", json={"exam_date": soon, "result": "passed"})
    assert wrong.status_code == 422

    answer = {"exam_date": day, "result": "passed", "testimonial": "  Ibyapa  byanyoroheye! ", "public": True}
    saved = (await client.post("/api/v1/me/outcome", json=answer)).json()
    assert saved["testimonial"] == "Ibyapa byanyoroheye!" and saved["testimonial_status"] == "pending"
    dashboard = (await client.get("/api/v1/me/dashboard")).json()
    assert dashboard["outcome_question"] is None and dashboard["plan"]["pace"] == "succeeded"


async def test_pass_rate_and_testimonials_need_enough_answers_and_approval(client, db, admin, monkeypatch):
    for i, (result, words) in enumerate([("passed", "Murakoze cyane!"), ("failed", "Nzongera"), ("not_taken", None)]):
        learner = await login(client, email=f"l{i}@gmail.com", name=f"Learner{i} Uwase")
        day = await exam_was(db, learner["id"], 1)
        body = {"exam_date": day, "result": result, "testimonial": words, "public": True}
        assert (await client.post("/api/v1/me/outcome", json=body)).status_code == 200

    stats = (await client.get("/api/v1/stats/outcomes")).json()
    assert stats == {"answered": 2, "passed": 1, "pass_rate": None, "testimonials": []}  # too few, nothing approved
    monkeypatch.setattr(settings, "OUTCOME_MIN_ANSWERS", 2)
    assert (await client.get("/api/v1/stats/outcomes")).json()["pass_rate"] == 0.5

    await admin_login(client)
    waiting = (await client.get("/api/v1/admin/testimonials", params={"status": "pending"})).json()
    assert [t["text"] for t in waiting] == ["Murakoze cyane!"]  # a failed exam's words are not kept
    admin_stats = (await client.get("/api/v1/admin/stats")).json()
    assert (admin_stats["outcomes_answered"], admin_stats["outcomes_passed"], admin_stats["testimonials_pending"]) == (
        2,
        1,
        1,
    )

    assert (
        await client.patch(f"/api/v1/admin/testimonials/{waiting[0]['id']}", json={"status": "approved"})
    ).status_code == 204
    shown = (await client.get("/api/v1/stats/outcomes")).json()["testimonials"]
    assert shown == [{"name": "Learner0", "text": "Murakoze cyane!", "exam_date": shown[0]["exam_date"]}]


async def test_private_testimonials_stay_private(client, db, admin):
    keza = await login(client)
    day = await exam_was(db, keza["id"], 1)
    body = {"exam_date": day, "result": "passed", "testimonial": "Byari byoroshye.", "public": False}
    await client.post("/api/v1/me/outcome", json=body)
    await admin_login(client)
    outcome_id = (await client.get("/api/v1/admin/testimonials")).json()[0]["id"]
    await client.patch(f"/api/v1/admin/testimonials/{outcome_id}", json={"status": "approved"})
    assert (await client.get("/api/v1/stats/outcomes")).json()["testimonials"] == []


def test_sentry_only_starts_with_a_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    assert monitoring.init_sentry("api") is False and calls == []

    monkeypatch.setattr(settings, "SENTRY_DSN", "https://key@o1.ingest.sentry.io/1")
    monkeypatch.setattr(settings, "OUTBOUND_PROXY", "http://proxy.server:3128")
    assert monitoring.init_sentry("api") is True
    assert calls[0]["send_default_pii"] is False and calls[0]["max_request_body_size"] == "never"
    assert calls[0]["include_local_variables"] is False and calls[0]["https_proxy"] == "http://proxy.server:3128"
