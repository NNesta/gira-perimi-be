import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.db.base import utcnow
from app.models import PracticeAnswer, ReviewItem
from tests.conftest import login


async def test_offline_pack_needs_a_learner_and_holds_every_question(client, content):
    assert (await client.get("/api/v1/offline/pack")).status_code == 401
    await login(client)
    pack = (await client.get("/api/v1/offline/pack")).json()
    assert pack["version"].startswith(content.version)
    assert len(pack["questions"]) == len(content.active_ids)
    assert {t["id"] for t in pack["topics"]} == set(content.ids_by_topic)
    sample = pack["questions"][0]
    assert {"answer", "explanation", "law_ref", "options"} <= set(sample)


async def test_offline_answers_sync_once(client, content, db):
    await login(client)
    qid, other = content.active_ids[:2]
    now = utcnow()
    batch = {
        "answers": [
            {
                "client_id": str(uuid.uuid4()),
                "question_id": qid,
                "selected": content.questions[qid].answer,
                "answered_at": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "client_id": str(uuid.uuid4()),
                "question_id": other,
                "selected": (content.questions[other].answer + 1) % 4,
                "answered_at": (now - timedelta(days=1)).isoformat(),
            },
            {"client_id": str(uuid.uuid4()), "question_id": 99999, "selected": 0, "answered_at": now.isoformat()},
            {
                "client_id": str(uuid.uuid4()),
                "question_id": qid,
                "selected": 0,
                "answered_at": (now - timedelta(days=90)).isoformat(),
            },
            {"client_id": str(uuid.uuid4()), "question_id": qid, "selected": 0, "answered_at": "2026-01-01T10:00:00"},
        ]
    }
    first = await client.post("/api/v1/practice/answers/offline", json=batch)
    assert first.status_code == 200 and first.json() == {"saved": 2, "duplicates": 0, "skipped": 3}

    retry = (await client.post("/api/v1/practice/answers/offline", json=batch)).json()
    assert retry == {"saved": 0, "duplicates": 2, "skipped": 3}
    assert await db.scalar(select(func.count()).select_from(PracticeAnswer)) == 2

    rows = {a.question_id: a for a in await db.scalars(select(PracticeAnswer))}
    assert abs(rows[qid].answered_at - (now - timedelta(hours=3))) < timedelta(seconds=1)  # keeps the real time
    assert [i.item_id for i in await db.scalars(select(ReviewItem))] == [str(other)]  # the offline mistake

    future = {
        "answers": [
            {
                "client_id": str(uuid.uuid4()),
                "question_id": qid,
                "selected": 0,
                "answered_at": (now + timedelta(days=2)).isoformat(),
            }
        ]
    }
    assert (await client.post("/api/v1/practice/answers/offline", json=future)).json()["saved"] == 1
    latest = await db.scalar(select(func.max(PracticeAnswer.answered_at)))
    assert latest <= utcnow()


async def test_offline_batch_is_capped(client):
    await login(client)
    answer = {"question_id": 1, "selected": 0, "answered_at": utcnow().isoformat()}
    too_many = {"answers": [{**answer, "client_id": str(uuid.uuid4())} for _ in range(501)]}
    assert (await client.post("/api/v1/practice/answers/offline", json=too_many)).status_code == 422
