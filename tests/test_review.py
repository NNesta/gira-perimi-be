from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.models import ReviewItem
from app.services.dates import local_day
from tests.conftest import login
from tests.test_exams import answer_all


def wrong_choice(content, question_id: int) -> int:
    return (content.questions[question_id].answer + 1) % 4


async def make_due(db, user_id) -> None:
    """Time travel: every open review item becomes due now."""
    for item in await db.scalars(select(ReviewItem).where(ReviewItem.user_id == user_id)):
        item.due_at = utcnow() - timedelta(minutes=1)
    await db.commit()


async def answer(client, question_id: int, selected: int):
    response = await client.post("/api/v1/practice/answers", json={"question_id": question_id, "selected": selected})
    assert response.status_code == 201, response.text
    return response.json()


async def test_mistakes_come_back_the_next_day_and_climb_the_boxes(client, content, db):
    user = await login(client)
    qid = content.active_ids[0]
    await answer(client, qid, wrong_choice(content, qid))

    item = (await db.scalars(select(ReviewItem))).one()
    assert item.kind == "question" and item.item_id == str(qid) and item.box == 1
    assert local_day(item.due_at) == local_day(utcnow()) + timedelta(days=1)  # due at midnight tomorrow (Kigali)

    session = (await client.get("/api/v1/review")).json()
    assert session["items"] == [] and session["summary"]["due"] == 0 and session["summary"]["learning"] == 1
    assert session["summary"]["boxes"] == [1, 0, 0, 0, 0]
    assert session["summary"]["next_due_at"] is not None

    await answer(client, qid, content.questions[qid].answer)  # right, but not due yet: no promotion
    await db.refresh(item)
    assert item.box == 1

    for expected_box, interval in [(2, 3), (3, 7), (4, 14), (5, 30)]:
        await make_due(db, item.user_id)
        session = (await client.get("/api/v1/review")).json()
        assert [i["question"]["id"] for i in session["items"]] == [qid]
        assert session["items"][0]["question"]["answer"] == content.questions[qid].answer
        await answer(client, qid, content.questions[qid].answer)
        await db.refresh(item)
        assert item.box == expected_box
        assert local_day(item.due_at) == local_day(utcnow()) + timedelta(days=interval)

    await make_due(db, item.user_id)
    await answer(client, qid, content.questions[qid].answer)
    await db.refresh(item)
    assert item.mastered_at is not None
    summary = (await client.get("/api/v1/review")).json()["summary"]
    assert summary == {**summary, "due": 0, "learning": 0, "mastered": 1}
    assert user["id"] == str(item.user_id)


async def test_a_lapse_sends_an_item_back_to_box_one(client, content, db):
    await login(client)
    qid = content.active_ids[1]
    await answer(client, qid, wrong_choice(content, qid))
    item = (await db.scalars(select(ReviewItem))).one()
    await make_due(db, item.user_id)
    await answer(client, qid, content.questions[qid].answer)
    await db.refresh(item)
    assert item.box == 2
    await answer(client, qid, wrong_choice(content, qid))
    await db.refresh(item)
    assert item.box == 1 and item.lapses == 1


async def test_exam_mistakes_join_the_review(client, content, db):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    await answer_all(client, content, exam, correct=15)
    await client.post(f"/api/v1/exams/{exam['id']}/submit")
    wrong = {str(i["question_id"]) for i in exam["items"] if i["position"] > 15}
    assert {i.item_id for i in await db.scalars(select(ReviewItem))} == wrong


async def test_sign_flashcards(client, content, db):
    user = await login(client)
    sign = content.signs[0]
    assert (await client.post("/api/v1/review/signs", json={"sign_id": "nope", "known": False})).status_code == 404
    assert (await client.post("/api/v1/review/signs", json={"sign_id": sign["id"], "known": True})).status_code == 204
    assert (await db.scalars(select(ReviewItem))).first() is None  # knowing a new sign schedules nothing

    await client.post("/api/v1/review/signs", json={"sign_id": sign["id"], "known": False})
    item = (await db.scalars(select(ReviewItem))).one()
    assert item.kind == "sign" and str(item.user_id) == user["id"]
    await make_due(db, item.user_id)
    session = (await client.get("/api/v1/review")).json()
    assert session["summary"]["due_signs"] == 1
    assert session["items"][0]["kind"] == "sign" and session["items"][0]["sign"]["id"] == sign["id"]


async def test_review_requires_a_learner(client):
    assert (await client.get("/api/v1/review")).status_code == 401
    assert (await client.post("/api/v1/review/signs", json={"sign_id": "x", "known": True})).status_code == 401
