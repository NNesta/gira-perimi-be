import uuid

from sqlalchemy import func, select

from app.core.config import settings
from app.models import PracticeAnswer, ReviewItem, User
from app.services.content import TOPICS
from tests.conftest import login


async def test_new_learners_start_with_the_welcome_until_they_finish_or_skip_it(client, db):
    keza = await login(client)
    assert keza["onboarded"] is False

    done = (await client.patch("/api/v1/me", json={"onboarded": True})).json()
    assert done["onboarded"] is True and done["daily_goal"] == 20  # other settings untouched
    user = await db.get(User, uuid.UUID(keza["id"]))
    first = user.onboarded_at

    await client.patch("/api/v1/me", json={"onboarded": True})
    await db.refresh(user)
    assert user.onboarded_at == first  # finishing twice keeps the first date
    assert (await login(client))["onboarded"] is True  # and the next sign-in skips the welcome


async def test_placement_quiz_asks_one_question_per_topic_and_names_weak_topics(client, db, content):
    keza = await login(client)
    quiz = (await client.get("/api/v1/practice/placement")).json()["questions"]
    assert [q["topic"] for q in quiz] == [t["id"] for t in TOPICS]

    # Right on the first three topics, wrong on the rest; a repeated answer is ignored.
    answers = [
        {"question_id": q["id"], "selected": q["answer"] if i < 3 else (q["answer"] + 1) % 2}
        for i, q in enumerate(quiz)
    ]
    response = await client.post("/api/v1/practice/placement", json={"answers": answers + answers[:1]})
    assert response.status_code == 201
    result = response.json()
    assert result["correct"] == 3 and result["total"] == len(TOPICS)
    assert result["weak_topics"] == [t["id"] for t in TOPICS[3:]]

    user_id = uuid.UUID(keza["id"])
    saved = await db.scalar(select(func.count()).select_from(PracticeAnswer).where(PracticeAnswer.user_id == user_id))
    assert saved == len(TOPICS)
    missed = await db.scalar(select(func.count()).select_from(ReviewItem).where(ReviewItem.user_id == user_id))
    assert missed == len(TOPICS) - 3  # wrong answers come back in review

    stray = {"answers": [{"question_id": 999999, "selected": 0}]}
    unknown = await client.post("/api/v1/practice/placement", json=stray)
    assert unknown.status_code == 404


async def test_placement_quiz_is_free_behind_the_paywall(client, monkeypatch):
    await login(client)
    monkeypatch.setattr(settings, "PAYWALL_ENABLED", True)
    assert (await client.get("/api/v1/practice/questions")).status_code == 402
    quiz = (await client.get("/api/v1/practice/placement")).json()["questions"]
    answers = [{"question_id": q["id"], "selected": q["answer"]} for q in quiz]
    assert (await client.post("/api/v1/practice/placement", json={"answers": answers})).status_code == 201


async def test_placement_quiz_needs_a_session(client):
    assert (await client.get("/api/v1/practice/placement")).status_code == 401
