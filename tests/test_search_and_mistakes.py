import uuid
from datetime import timedelta

from app.core.config import settings
from app.db.base import utcnow
from app.models import PracticeAnswer
from app.services.content import normalize
from tests.conftest import login


def test_normalize_ignores_case_accents_and_apostrophes():
    assert normalize("Y’umuhanda, KW'IBURYO!") == "yumuhanda kwiburyo"
    assert normalize("  Café — moto  ") == "cafe moto"


async def test_search_finds_questions_by_words_and_by_number(client, content):
    await login(client)
    question = content.questions[29]  # "Ni ryari itegeko rigenga gutambuka mbere kw’iburyo ..."

    found = (await client.get("/api/v1/questions/search", params={"q": "gutambuka mbere kw'iburyo"})).json()
    assert found["total"] >= 1 and found["items"][0]["id"] == question.id
    assert found["items"][0]["answer"] == question.answer and found["items"][0]["explanation"]

    by_number = (await client.get("/api/v1/questions/search", params={"q": question.ref})).json()
    assert by_number["items"][0]["id"] == question.id

    in_topic = (await client.get("/api/v1/questions/search", params={"q": "umuvuduko", "topic": "umuvuduko"})).json()
    assert in_topic["total"] > 0 and all(q["topic"] == "umuvuduko" for q in in_topic["items"])
    assert len(in_topic["items"]) <= 30

    nothing = (await client.get("/api/v1/questions/search", params={"q": "zzzqqq"})).json()
    assert nothing == {"total": 0, "items": []}
    assert (await client.get("/api/v1/questions/search", params={"q": "moto", "topic": "nope"})).status_code == 404


async def test_search_needs_a_session_and_access(client, monkeypatch):
    assert (await client.get("/api/v1/questions/search", params={"q": "moto"})).status_code == 401
    await login(client)
    monkeypatch.setattr(settings, "PAYWALL_ENABLED", True)
    assert (await client.get("/api/v1/questions/search", params={"q": "moto"})).status_code == 402


async def test_mistakes_list_every_wrong_answer_and_whether_it_was_fixed(client, db, content):
    keza = await login(client)
    user_id = uuid.UUID(keza["id"])
    fixed_q, open_q, right_q = (content.questions[i] for i in content.ids_by_topic["umuvuduko"][:3])
    other_q = content.questions[content.ids_by_topic["ibyapa"][0]]
    wrong = lambda q: (q.answer + 1) % len(q.options)  # noqa: E731
    start = utcnow() - timedelta(hours=5)
    answers = [
        (fixed_q, wrong(fixed_q)),
        (open_q, wrong(open_q)),
        (fixed_q, fixed_q.answer),
        (right_q, right_q.answer),
        (open_q, wrong(open_q)),
        (other_q, wrong(other_q)),
    ]
    for i, (q, selected) in enumerate(answers):
        db.add(
            PracticeAnswer(
                user_id=user_id,
                question_id=q.id,
                selected=selected,
                is_correct=selected == q.answer,
                answered_at=start + timedelta(minutes=i),
            )
        )
    await db.commit()

    everything = (await client.get("/api/v1/practice/mistakes")).json()
    assert everything["counts"] == {"all": 3, "open": 2, "fixed": 1}
    assert [m["question"]["id"] for m in everything["items"]] == [other_q.id, open_q.id, fixed_q.id]  # latest first
    by_id = {m["question"]["id"]: m for m in everything["items"]}
    assert by_id[open_q.id]["wrong_count"] == 2 and by_id[open_q.id]["last_selected"] == wrong(open_q)
    assert by_id[fixed_q.id]["fixed"] is True and by_id[open_q.id]["fixed"] is False
    assert everything["topics"] == {"umuvuduko": 2, "ibyapa": 1}

    open_only = {"status": "open", "topic": "umuvuduko"}
    still_wrong = (await client.get("/api/v1/practice/mistakes", params=open_only)).json()
    assert [m["question"]["id"] for m in still_wrong["items"]] == [open_q.id] and still_wrong["total"] == 1
    paged = (await client.get("/api/v1/practice/mistakes", params={"page": 2, "page_size": 2})).json()
    assert [m["question"]["id"] for m in paged["items"]] == [fixed_q.id] and paged["total"] == 3
