import uuid

from sqlalchemy import func, select

from app.models import ExamAttempt, PracticeAnswer
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login
from tests.test_exams import seed_completed_exams


async def admin_login(client, password: str = ADMIN_PASSWORD):
    return await client.post("/api/v1/admin/auth/login", json={"email": ADMIN_EMAIL, "password": password})


async def test_admin_endpoints_require_admin_session(client, admin):
    assert (await client.get("/api/v1/admin/stats")).status_code == 401
    await login(client)  # a learner session is not an admin session
    assert (await client.get("/api/v1/admin/users")).status_code == 401


async def test_admin_login_is_rate_limited(client, admin):
    for _ in range(5):
        assert (await admin_login(client, "wrong-password")).status_code == 401
    blocked = await admin_login(client)
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


async def test_admin_login_limit_is_per_visitor_behind_the_proxy(client, admin):
    """Behind the site's proxy every request comes from one address: X-Forwarded-For tells visitors apart."""

    async def attempt(email: str, password: str, forwarded_for: str):
        return await client.post(
            "/api/v1/admin/auth/login",
            json={"email": email, "password": password},
            headers={"X-Forwarded-For": forwarded_for},
        )

    for i in range(5):
        assert (await attempt(f"umushyitsi{i}@example.com", "wrong-password", "203.0.113.7")).status_code == 401
    assert (await attempt("undi@example.com", "wrong-password", "203.0.113.7")).status_code == 429
    # A forged entry in front of the one the site added changes nothing.
    assert (await attempt("undi@example.com", "wrong-password", "10.9.9.9, 203.0.113.7")).status_code == 429
    # Another visitor can still sign in.
    assert (await attempt(ADMIN_EMAIL, ADMIN_PASSWORD, "198.51.100.4")).status_code == 200


async def test_admin_dashboard_and_user_management(client, admin, db):
    learner = await login(client)
    learner_id = uuid.UUID(learner["id"])
    await seed_completed_exams(db, learner_id, [17] * 11)
    await client.get("/api/v1/practice/questions")
    db.add(PracticeAnswer(user_id=learner_id, question_id=1, selected=0, is_correct=True))
    await db.commit()

    response = await admin_login(client)
    assert response.status_code == 200 and response.json()["email"] == ADMIN_EMAIL

    stats = (await client.get("/api/v1/admin/stats")).json()
    assert stats["users_total"] == 1 and stats["users_ready"] == 1
    assert stats["exams_total"] == 11 and stats["average_score"] == 17.0 and stats["pass_rate"] == 1.0
    assert len(stats["daily"]) == 30 and sum(d["exams"] for d in stats["daily"]) == 11
    assert next(b for b in stats["score_distribution"] if b["score"] == 17)["count"] == 11

    page = (await client.get("/api/v1/admin/users", params={"search": "keza", "sort": "average"})).json()
    assert page["total"] == 1
    row = page["items"][0]
    assert row["exams_completed"] == 11 and row["average"] == 17.0 and row["ready"] is True
    assert (await client.get("/api/v1/admin/users", params={"search": "ntawe"})).json()["total"] == 0

    detail = (await client.get(f"/api/v1/admin/users/{learner_id}")).json()
    assert detail["readiness"]["ready"] is True and detail["practice_answers"] == 1

    suspended = (await client.patch(f"/api/v1/admin/users/{learner_id}", json={"is_active": False})).json()
    assert suspended["is_active"] is False

    assert (await client.delete(f"/api/v1/admin/users/{learner_id}")).status_code == 204
    assert (await client.get(f"/api/v1/admin/users/{learner_id}")).status_code == 404
    remaining = await db.scalar(select(func.count()).select_from(ExamAttempt).where(ExamAttempt.user_id == learner_id))
    assert remaining == 0  # cascade removed the learner's exams

    assert (await client.post("/api/v1/admin/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/admin/auth/me")).status_code == 401
