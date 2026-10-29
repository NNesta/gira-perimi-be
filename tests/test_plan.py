import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.models import ExamAttempt, LessonProgress
from app.services.dates import local_day
from tests.conftest import login
from tests.test_exams import seed_completed_exams


async def test_profile_settings_are_partial_and_validated(client):
    await login(client)
    me = (await client.get("/api/v1/auth/me")).json()
    assert me["exam_date"] is None and me["daily_goal"] == 20 and me["reminders"] is False

    today = local_day(utcnow())
    exam_day = (today + timedelta(days=30)).isoformat()
    updated = await client.patch("/api/v1/me", json={"exam_date": exam_day, "daily_goal": 30})
    assert updated.status_code == 200
    assert updated.json()["exam_date"] == exam_day and updated.json()["daily_goal"] == 30

    phone = (await client.patch("/api/v1/me", json={"phone": "+250 788 000 111"})).json()
    assert phone["exam_date"] == exam_day and phone["daily_goal"] == 30  # untouched fields stay

    past = await client.patch("/api/v1/me", json={"exam_date": (today - timedelta(days=1)).isoformat()})
    assert past.status_code == 422 and "itariki" in past.json()["detail"]
    far = await client.patch("/api/v1/me", json={"exam_date": (today + timedelta(days=800)).isoformat()})
    assert far.status_code == 422
    assert (await client.patch("/api/v1/me", json={"daily_goal": 2})).status_code == 422
    assert (await client.patch("/api/v1/me", json={"reminders": True})).status_code == 409  # no SMTP configured

    cleared = (await client.patch("/api/v1/me", json={"exam_date": None})).json()
    assert cleared["exam_date"] is None


async def test_dashboard_today_and_plan(client, content, db):
    user = await login(client)
    user_id = uuid.UUID(user["id"])
    dash = (await client.get("/api/v1/me/dashboard")).json()
    assert dash["plan"]["pace"] == "none" and dash["plan"]["exam_date"] is None
    assert dash["today"] == {
        "answered": 0,
        "goal": 20,
        "lesson_done": False,
        "exam_done": False,
        "exam_suggested": True,
    }
    assert dash["review"]["due"] == 0

    qid = content.active_ids[0]
    await client.post(
        "/api/v1/practice/answers", json={"question_id": qid, "selected": (content.questions[qid].answer + 1) % 4}
    )
    db.add(LessonProgress(user_id=user_id, lesson_slug=content.lessons[0]["slug"]))
    await db.commit()

    today = local_day(utcnow())
    await client.patch("/api/v1/me", json={"exam_date": (today + timedelta(days=22)).isoformat()})
    dash = (await client.get("/api/v1/me/dashboard")).json()
    assert dash["today"]["answered"] == 1 and dash["today"]["lesson_done"] is True
    plan = dash["plan"]
    assert plan["days_left"] == 22 and plan["exams_left"] == 11 and plan["pace"] == "on_track"
    assert plan["exam_every_days"] == 2 and plan["exams_per_day"] is None
    assert plan["lessons_left"] == len(content.core_lessons) - 1
    assert dash["review"]["learning"] == 1

    await client.patch("/api/v1/me", json={"exam_date": (today + timedelta(days=4)).isoformat()})
    plan = (await client.get("/api/v1/me/dashboard")).json()["plan"]
    assert plan["pace"] == "tight" and plan["exams_per_day"] == 3 and plan["exam_every_days"] == 1

    await client.patch("/api/v1/me", json={"exam_date": today.isoformat()})
    dash = (await client.get("/api/v1/me/dashboard")).json()
    assert dash["plan"]["pace"] == "today" and dash["today"]["exam_suggested"] is False


async def test_exam_suggestion_follows_the_rhythm(client, db):
    user = await login(client)
    await seed_completed_exams(db, uuid.UUID(user["id"]), [14])
    exam = (await db.scalars(select(ExamAttempt))).one()

    exam.submitted_at = utcnow()  # finished today: nothing more to suggest
    await db.commit()
    today = (await client.get("/api/v1/me/dashboard")).json()["today"]
    assert today["exam_done"] is True and today["exam_suggested"] is False

    exam.submitted_at = utcnow() - timedelta(days=1)  # yesterday: without an exam date, one every 2 days
    await db.commit()
    assert (await client.get("/api/v1/me/dashboard")).json()["today"]["exam_suggested"] is False

    exam.submitted_at = utcnow() - timedelta(days=2)
    await db.commit()
    assert (await client.get("/api/v1/me/dashboard")).json()["today"]["exam_suggested"] is True
