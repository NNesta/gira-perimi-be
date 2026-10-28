import uuid
from datetime import timedelta

import pytest

from app.db.base import utcnow
from app.models import LessonProgress, PracticeAnswer
from app.services.content import ContentStore
from app.services.lesson_parser import parse_blocks
from app.services.progress import longest_streak
from tests.conftest import login
from tests.test_exams import answer_all, seed_completed_exams


def test_longest_streak_finds_the_best_run():
    day = utcnow().date()
    days = {day - timedelta(days=n) for n in (0, 1, 5, 6, 7, 8, 20)}
    assert longest_streak(days) == 4 and longest_streak(set()) == 0


async def test_badges_follow_what_the_learner_did(client, db, content):
    keza = await login(client)
    user_id = uuid.UUID(keza["id"])
    fresh = (await client.get("/api/v1/me/badges")).json()
    assert fresh["earned"] == 0 and fresh["total"] == len(fresh["items"]) == 12
    by_id = {b["id"]: b for b in fresh["items"]}
    assert by_id["ibyapa-byose"]["target"] == len(content.ids_by_topic["ibyapa"])
    assert by_id["amasomo-yose"]["target"] == len(content.lessons)

    await seed_completed_exams(db, user_id, [11, 13, 20])  # one per day, three days in a row
    now = utcnow()
    for qid in content.ids_by_topic["ibyapa"][:5]:
        q = content.questions[qid]
        db.add(PracticeAnswer(user_id=user_id, question_id=qid, selected=q.answer, is_correct=True, answered_at=now))
    db.add(LessonProgress(user_id=user_id, lesson_slug=content.lessons[0]["slug"]))
    await db.commit()

    by_id = {b["id"]: b for b in (await client.get("/api/v1/me/badges")).json()["items"]}
    assert by_id["ikizamini-cya-mbere"]["earned"] and by_id["natsinze"]["earned"] and by_id["amanota-yose"]["earned"]
    assert by_id["ibizamini-10"] == {**by_id["ibizamini-10"], "earned": False, "current": 3, "target": 10}
    assert by_id["iminsi-3"]["earned"] and not by_id["iminsi-7"]["earned"] and by_id["iminsi-7"]["current"] >= 3
    assert by_id["ibyapa-byose"]["current"] == 5 and by_id["amasomo-yose"]["current"] == 1
    assert not by_id["witeguye"]["earned"]


async def test_passed_exams_get_a_public_result_card(client, content):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    await answer_all(client, content, exam, correct=19)
    await client.post(f"/api/v1/exams/{exam['id']}/submit")

    code = (await client.post(f"/api/v1/exams/{exam['id']}/share")).json()["code"]
    assert (await client.post(f"/api/v1/exams/{exam['id']}/share")).json()["code"] == code  # same link every time

    client.cookies.clear()  # anyone with the link
    card = (await client.get(f"/api/v1/share/{code}")).json()
    assert card["name"] == "Keza" and card["score"] == 19 and card["total"] == 20 and card["passed"] is True
    assert set(card) == {"name", "score", "total", "passed", "day"}  # nothing else about the learner
    assert (await client.get("/api/v1/share/nope")).status_code == 404


async def test_failed_or_running_exams_cannot_be_shared(client, content):
    await login(client)
    exam = (await client.post("/api/v1/exams")).json()
    assert (await client.post(f"/api/v1/exams/{exam['id']}/share")).status_code == 409  # still running
    await answer_all(client, content, exam, correct=5)
    await client.post(f"/api/v1/exams/{exam['id']}/submit")
    assert (await client.post(f"/api/v1/exams/{exam['id']}/share")).status_code == 409  # not passed
    await login(client, email="mugisha@gmail.com", name="Mugisha Eric")
    assert (await client.post(f"/api/v1/exams/{exam['id']}/share")).status_code == 404  # someone else's


def test_lessons_can_hold_known_diagrams(tmp_path, content):
    assert parse_blocks(["::diagram kunyuranaho"]) == [{"type": "diagram", "name": "kunyuranaho"}]
    drawn = [
        b["name"]
        for lesson in content.lessons
        for section in lesson["sections"]
        for b in section["blocks"]
        if b["type"] == "diagram"
    ]
    assert sorted(drawn) == ["aho-guhagarara", "imirongo", "intera-yo-guhagarara", "kunyuranaho"]

    lessons = tmp_path / "lessons"
    lessons.mkdir()
    (lessons / "01.md").write_text(
        "---\nslug: x\norder: 1\ntitle: X\nsummary: s\nicon: book\ntopics: ibyapa\nminutes: 1\nfree: true\n---\n\n"
        "## A\n\n::diagram nta-gishushanyo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown diagram"):
        ContentStore(lessons_dir=lessons)
