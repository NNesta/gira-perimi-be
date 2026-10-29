import uuid

from app.models import ExamAttempt
from tests.conftest import login
from tests.test_exams import answer_all


async def finished_exam(client, content, correct: int) -> dict:
    exam = (await client.post("/api/v1/exams")).json()
    await answer_all(client, content, exam, correct=correct)
    return (await client.post(f"/api/v1/exams/{exam['id']}/submit")).json()


async def test_friends_sit_the_same_paper_and_compare(client, content):
    await login(client)  # Keza
    keza_exam = await finished_exam(client, content, correct=16)
    code = (await client.post(f"/api/v1/exams/{keza_exam['id']}/challenge")).json()["code"]
    assert (await client.post(f"/api/v1/exams/{keza_exam['id']}/challenge")).json()["code"] == code  # made once
    assert (await client.post(f"/api/v1/challenges/{code}/start")).status_code == 409  # not your own paper

    client.cookies.clear()
    public = (await client.get(f"/api/v1/challenges/{code}")).json()
    assert public["creator_name"] == "Keza" and public["creator_score"] == 16 and public["players"] == 0
    assert public["standings"] is None  # strangers do not see the results
    assert (await client.post(f"/api/v1/challenges/{code}/start")).status_code == 401  # sign-in required

    await login(client, email="mugisha@gmail.com", name="Mugisha Eric")
    started = await client.post(f"/api/v1/challenges/{code}/start")
    assert started.status_code == 201
    exam = started.json()
    assert [i["question_id"] for i in exam["items"]] == [i["question_id"] for i in keza_exam["items"]]
    assert (await client.post(f"/api/v1/challenges/{code}/start")).json()["id"] == exam["id"]  # resumes
    assert (await client.get(f"/api/v1/challenges/{code}")).json()["standings"] is None  # not until finished

    await answer_all(client, content, exam, correct=18)
    result = (await client.post(f"/api/v1/exams/{exam['id']}/submit")).json()
    assert result["challenge_code"] == code and result["score"] == 18

    seen = (await client.get(f"/api/v1/challenges/{code}")).json()
    assert seen["players"] == 1 and seen["exam_id"] == exam["id"] and seen["exam_status"] == "completed"
    assert [(p["name"], p["score"], p["you"], p["creator"]) for p in seen["standings"]] == [
        ("Mugisha", 18, True, False),
        ("Keza", 16, False, True),
    ]
    again = (await client.post(f"/api/v1/challenges/{code}/start")).json()
    assert again["id"] == exam["id"] and again["status"] == "completed"  # one go per friend


async def test_challenges_need_a_finished_exam_and_no_other_running(client, content, db):
    await login(client)
    keza_exam = await finished_exam(client, content, correct=12)
    code = (await client.post(f"/api/v1/exams/{keza_exam['id']}/challenge")).json()["code"]
    running = (await client.post("/api/v1/exams")).json()
    assert (await client.post(f"/api/v1/exams/{running['id']}/challenge")).status_code == 409

    await login(client, email="mugisha@gmail.com", name="Mugisha Eric")
    own = (await client.post("/api/v1/exams")).json()
    blocked = await client.post(f"/api/v1/challenges/{code}/start")
    assert blocked.status_code == 409 and "kitarangiye" in blocked.json()["detail"]
    attempt = await db.get(ExamAttempt, uuid.UUID(own["id"]))
    assert attempt.challenge_id is None
    assert (await client.get("/api/v1/challenges/nta-mukino")).status_code == 404
