from tests.conftest import login
from tests.test_admin import admin_login
from tests.test_exams import answer_all


async def explain(client, question_id: int, text: str, law: str | None = "Iteka n° 85/01, ingingo ya 1", reviewed=True):
    response = await client.put(
        f"/api/v1/admin/questions/{question_id}/explanation",
        json={"explanation": text, "law_ref": law, "reviewed": reviewed},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_every_active_question_ships_with_an_explanation(content):
    missing = [q.id for q in content.questions.values() if q.active and not q.explanation]
    assert missing == []


async def test_explanations_follow_the_answer_everywhere(client, content, admin):
    await admin_login(client)
    learner = await login(client)
    assert learner

    exam = (await client.post("/api/v1/exams")).json()
    qid = exam["items"][0]["question_id"]
    await explain(client, qid, "  Kubera ko itegeko ribivuga.  ")

    practice = await client.post("/api/v1/practice/answers", json={"question_id": qid, "selected": 0})
    assert practice.json()["explanation"] == "Kubera ko itegeko ribivuga."
    assert practice.json()["law_ref"] == "Iteka n° 85/01, ingingo ya 1"

    running = (await client.get(f"/api/v1/exams/{exam['id']}")).json()
    assert all(item["explanation"] is None for item in running["items"])  # never while the exam runs
    await answer_all(client, content, exam, correct=20)
    done = (await client.post(f"/api/v1/exams/{exam['id']}/submit")).json()
    assert done["items"][0]["explanation"] == "Kubera ko itegeko ribivuga."

    hidden = await explain(client, qid, "   ", law=None)
    assert hidden["explanation"] is None and hidden["edited"] is True
    practice = await client.post("/api/v1/practice/answers", json={"question_id": qid, "selected": 0})
    assert practice.json()["explanation"] is None

    reset = (await client.delete(f"/api/v1/admin/questions/{qid}/explanation")).json()
    assert reset["edited"] is False and reset["reviewed"] is False
    assert reset["explanation"] == content.questions[qid].explanation


async def test_admin_question_list(client, content, admin):
    assert (await client.get("/api/v1/admin/questions")).status_code == 401
    await admin_login(client)
    page = (await client.get("/api/v1/admin/questions?page_size=5")).json()
    assert page["total"] == len(content.active_ids) == page["counts"]["total"]
    assert [q["id"] for q in page["items"]] == sorted(content.active_ids)[:5]

    first = page["items"][0]["id"]
    await explain(client, first, "Igisobanuro gishya.", reviewed=True)
    reviewed = (await client.get("/api/v1/admin/questions?status=reviewed")).json()
    assert [q["id"] for q in reviewed["items"]] == [first] and reviewed["items"][0]["updated_by"] == "admin@girape.rw"
    assert reviewed["counts"]["reviewed"] == 1 and reviewed["counts"]["edited"] == 1

    found = (await client.get("/api/v1/admin/questions", params={"search": "igisobanuro gishya"})).json()
    assert [q["id"] for q in found["items"]] == [first]
    by_topic = (await client.get("/api/v1/admin/questions?topic=ibyapa&page_size=100")).json()
    assert by_topic["total"] == len(content.ids_by_topic["ibyapa"])
    assert all(q["topic"] == "ibyapa" for q in by_topic["items"])

    assert (await client.put("/api/v1/admin/questions/99999/explanation", json={"explanation": "x"})).status_code == 404


async def test_hardest_questions_sort(client, content, admin):
    await login(client)
    easy, hard = content.active_ids[:2]
    await client.post(
        "/api/v1/practice/answers", json={"question_id": easy, "selected": content.questions[easy].answer}
    )
    wrong = (content.questions[hard].answer + 1) % 4
    await client.post("/api/v1/practice/answers", json={"question_id": hard, "selected": wrong})
    await admin_login(client)
    hardest = (await client.get("/api/v1/admin/questions?sort=hardest&page_size=2")).json()["items"]
    assert [q["id"] for q in hardest] == [hard, easy]
    assert hardest[0]["accuracy"] == 0 and hardest[1]["accuracy"] == 1
