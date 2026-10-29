import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.models import ExamAnswer, ExamAttempt, User
from app.models.exam import STATUS_COMPLETED, STATUS_IN_PROGRESS
from app.services import exams as exam_service
from tests.conftest import login


async def answer_all(client, content, exam: dict, correct: int) -> None:
    """Answers the first `correct` questions right and the rest wrong."""
    for item in exam["items"]:
        answer = content.questions[item["question_id"]].answer
        choice = answer if item["position"] <= correct else (answer + 1) % 4
        saved = await client.put(f"/api/v1/exams/{exam['id']}/answers/{item['position']}", json={"selected": choice})
        assert saved.status_code == 200, saved.text


async def test_exam_lifecycle(client, content):
    await login(client)
    started = await client.post("/api/v1/exams")
    assert started.status_code == 201
    exam = started.json()
    assert exam["status"] == "in_progress" and exam["total"] == 20 and len(exam["items"]) == 20
    assert all(item["answer"] is None for item in exam["items"])  # answers stay hidden while running

    resumed = (await client.post("/api/v1/exams")).json()
    assert resumed["id"] == exam["id"]

    await answer_all(client, content, exam, correct=13)
    cleared = await client.put(f"/api/v1/exams/{exam['id']}/answers/20", json={"selected": None})
    assert cleared.json()["answered"] == 19

    result = (await client.post(f"/api/v1/exams/{exam['id']}/submit")).json()
    assert result["status"] == "completed"
    assert result["score"] == 13 and result["passed"] is True
    assert all(item["answer"] is not None for item in result["items"])
    assert sum(item["is_correct"] for item in result["items"]) == 13

    late = await client.put(f"/api/v1/exams/{exam['id']}/answers/1", json={"selected": 0})
    assert late.status_code == 409

    history = (await client.get("/api/v1/exams")).json()
    assert len(history) == 1 and history[0]["score"] == 13


async def test_expired_exam_is_graded_with_saved_answers(client, content, db):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    await answer_all(client, content, exam, correct=5)
    attempt = await db.get(ExamAttempt, uuid.UUID(exam["id"]))
    attempt.deadline_at = utcnow() - timedelta(minutes=5)
    await db.commit()

    assert (await client.put(f"/api/v1/exams/{exam['id']}/answers/1", json={"selected": 1})).status_code == 409
    graded = (await client.get(f"/api/v1/exams/{exam['id']}")).json()
    assert graded["status"] == "completed" and graded["auto_submitted"] is True
    assert graded["score"] == 5 and graded["passed"] is False
    # Every question was answered: the clock ran out, but the exam was sat, so readiness counts it.
    assert (await client.get("/api/v1/me/dashboard")).json()["readiness"]["exams_completed"] == 1


async def test_submit_counts_the_answer_sheet(client, content):
    """Choices whose own save failed (poor connection) reach the server with the answer sheet."""
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    sheet = [
        {"position": item["position"], "selected": content.questions[item["question_id"]].answer}
        for item in exam["items"][:12]
    ]
    result = (await client.post(f"/api/v1/exams/{exam['id']}/submit", json={"answers": sheet})).json()
    assert result["score"] == 12 and result["passed"] is True and result["answered"] == 12


async def test_answer_sheet_is_ignored_once_time_is_up(client, content, db):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    attempt = await db.get(ExamAttempt, uuid.UUID(exam["id"]))
    attempt.deadline_at = utcnow() - timedelta(minutes=5)
    await db.commit()

    sheet = [{"position": i["position"], "selected": content.questions[i["question_id"]].answer} for i in exam["items"]]
    result = (await client.post(f"/api/v1/exams/{exam['id']}/submit", json={"answers": sheet})).json()
    assert result["score"] == 0 and result["auto_submitted"] is True


async def test_simultaneous_starts_leave_one_exam(client, content, db, session_factory, monkeypatch):
    """Another tab starts an exam between this request's check for a running one and its own new paper."""
    await login(client)
    check_running = exam_service.current_attempt
    rival_ids: list[uuid.UUID] = []

    async def other_tab_starts_meanwhile(session, user, store):
        running = await check_running(session, user, store)
        if not rival_ids:
            async with session_factory() as other:
                now = utcnow()
                rival = ExamAttempt(
                    user_id=user.id,
                    started_at=now,
                    deadline_at=now + timedelta(minutes=20),
                    total=20,
                    answers=[ExamAnswer(position=i + 1, question_id=qid) for i, qid in enumerate(store.draw_exam(20))],
                )
                other.add(rival)
                await other.commit()
                rival_ids.append(rival.id)
        return running

    monkeypatch.setattr(exam_service, "current_attempt", other_tab_starts_meanwhile)
    started = (await client.post("/api/v1/exams")).json()

    assert started["id"] == str(rival_ids[0])
    running = (await db.scalars(select(ExamAttempt.id).where(ExamAttempt.status == STATUS_IN_PROGRESS))).all()
    assert running == rival_ids


async def test_other_users_cannot_see_an_exam(client):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    await login(client, email="mugisha@gmail.com", name="Mugisha")
    assert (await client.get(f"/api/v1/exams/{exam['id']}")).status_code == 404


async def seed_completed_exams(db, user_id: uuid.UUID, scores: list[int]) -> None:
    now = utcnow()
    for i, score in enumerate(scores):
        started = now - timedelta(days=len(scores) - i, minutes=20)
        db.add(
            ExamAttempt(
                user_id=user_id,
                status=STATUS_COMPLETED,
                started_at=started,
                deadline_at=started + timedelta(minutes=20),
                submitted_at=started + timedelta(minutes=15),
                total=20,
                score=score,
            )
        )
    await db.commit()


async def test_readiness_requires_more_than_ten_exams_above_fifteen(client, db):
    user = await login(client)
    user_id = uuid.UUID(user["id"])

    await seed_completed_exams(db, user_id, [16] * 10)
    readiness = (await client.get("/api/v1/me/dashboard")).json()["readiness"]
    assert readiness["ready"] is False and readiness["exams_remaining"] == 1 and readiness["status"] == "almost"

    await seed_completed_exams(db, user_id, [16])
    dashboard = (await client.get("/api/v1/me/dashboard")).json()
    assert dashboard["readiness"]["ready"] is True and dashboard["readiness"]["status"] == "ready"
    assert dashboard["exams"]["completed"] == 11 and dashboard["exams"]["average"] == 16.0
    assert len(dashboard["trend"]) == 11


async def test_average_of_exactly_fifteen_is_not_enough(client, db):
    user = await login(client)
    await seed_completed_exams(db, uuid.UUID(user["id"]), [15] * 12)
    readiness = (await client.get("/api/v1/me/dashboard")).json()["readiness"]
    assert readiness["ready"] is False and readiness["average"] == 15.0


async def test_readiness_follows_the_most_recent_exams(client, db):
    """Early low scores stop counting once the learner has improved."""
    user = await login(client)
    await seed_completed_exams(db, uuid.UUID(user["id"]), [9] * 5 + [18] * 10)
    dashboard = (await client.get("/api/v1/me/dashboard")).json()
    assert dashboard["exams"]["average"] == 15.0  # over every exam, it would not be enough
    readiness = dashboard["readiness"]
    assert readiness["ready"] is True and readiness["average"] == 18.0 and readiness["average_window"] == 10


async def test_abandoned_exam_does_not_count_for_readiness(client, db):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    for item in exam["items"][:3]:
        await client.put(f"/api/v1/exams/{exam['id']}/answers/{item['position']}", json={"selected": 0})
    attempt = await db.get(ExamAttempt, uuid.UUID(exam["id"]))
    attempt.deadline_at = utcnow() - timedelta(minutes=5)
    await db.commit()

    dashboard = (await client.get("/api/v1/me/dashboard")).json()
    assert dashboard["exams"]["completed"] == 1  # still in the history
    assert dashboard["readiness"]["exams_completed"] == 0 and dashboard["readiness"]["status"] == "new"


async def test_dashboard_tracks_lessons_and_practice(client, content, db):
    await login(client)
    assert (await client.put("/api/v1/me/lessons/ibyapa")).status_code == 204
    assert (await client.put("/api/v1/me/lessons/ibyapa")).status_code == 204  # idempotent
    assert (await client.put("/api/v1/me/lessons/ntaho")).status_code == 404

    practice = (await client.get("/api/v1/practice/questions", params={"topic": "ibyapa", "count": 3})).json()
    assert practice["available"] == len(content.ids_by_topic["ibyapa"]) and len(practice["questions"]) == 3
    q = practice["questions"][0]
    wrong = (q["answer"] + 1) % 4
    feedback = (await client.post("/api/v1/practice/answers", json={"question_id": q["id"], "selected": wrong})).json()
    assert feedback == {
        "question_id": q["id"],
        "selected": wrong,
        "answer": q["answer"],
        "correct": False,
        "explanation": q["explanation"],
        "law_ref": q["law_ref"],
    }

    mistakes = (await client.get("/api/v1/practice/questions", params={"mode": "mistakes"})).json()
    assert [m["id"] for m in mistakes["questions"]] == [q["id"]]
    fresh = (await client.get("/api/v1/practice/questions", params={"mode": "new", "count": 50})).json()
    assert fresh["available"] == len(content.active_ids) - 1

    dashboard = (await client.get("/api/v1/me/dashboard")).json()
    assert dashboard["lessons"]["completed"] == 1 and dashboard["lessons"]["next_slug"] == "intangiriro"
    assert dashboard["practice_answers"] == 1 and dashboard["questions_seen"] == 1
    assert dashboard["streak_days"] == 1
    ibyapa = next(t for t in dashboard["topics"] if t["topic"] == "ibyapa")
    assert ibyapa["answered"] == 1 and ibyapa["accuracy"] == 0.0

    stored = (await db.scalars(select(User))).one()
    assert stored.last_active_at is not None
