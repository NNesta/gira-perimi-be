"""A throwaway database with one demo learner, for the product screenshots on the website's home page.

    uv run python -m scripts.demo_screens /tmp/tsinda-demo.db     # prints the learner's session token

Then serve the API from it (DATABASE_URL=sqlite+aiosqlite:////tmp/tsinda-demo.db) and follow
gira-perimi-fe/scripts/screenshots.mjs. The script only ever creates a new file: it refuses an existing database.

Keza, the demo learner, has studied for three weeks: 11 lessons, daily practice with a 9-day streak, and 12 mock
exams that climb from 11/20 to 18/20, so the dashboard shows a learner who is ready, with a few weak topics left.
"""

import asyncio
import random
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import create_token
from app.db.base import Base, utcnow
from app.db.session import create_engine
from app.models import ExamAnswer, ExamAttempt, LessonProgress, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.services import review
from app.services.content import get_content
from app.services.dates import day_start, local_day

EXAM_SCORES = [11, 13, 12, 14, 15, 16, 15, 17, 16, 18, 17, 18]
# How often Keza gets each topic right in practice: strong on signs, still unsure about priorities.
ACCURACY = {
    "ibyapa": 0.88,
    "ibimenyetso": 0.84,
    "gutambuka-mbere": 0.58,
    "kunyuranaho": 0.74,
    "umuvuduko": 0.66,
    "guhagarara": 0.8,
    "amatara": 0.77,
    "ibinyabiziga": 0.7,
    "abagenzi": 0.82,
    "imyitwarire": 0.79,
}
# Answers per day for the last 14 days, oldest first; today is not over (14 of a goal of 20).
DAILY_ANSWERS = [22, 0, 31, 18, 0, 26, 35, 20, 24, 41, 28, 33, 25, 14]


async def seed(path: Path) -> str:
    rng = random.Random(2026)
    content = get_content()
    engine = create_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = utcnow()
    today = local_day(now)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        user = User(
            email="keza@example.com",
            name="Keza Uwase",
            given_name="Keza",
            created_at=now - timedelta(days=24),
            last_login_at=now,
            last_active_at=now,
            exam_date=today + timedelta(days=12),
            daily_goal=20,
            onboarded_at=now - timedelta(days=24),
        )
        db.add(user)
        await db.flush()

        for i, lesson in enumerate(content.lessons[:11]):
            db.add(
                LessonProgress(
                    user_id=user.id, lesson_slug=lesson["slug"], completed_at=now - timedelta(days=22 - 2 * i)
                )
            )

        results = []
        for days_ago, count in zip(range(13, -1, -1), DAILY_ANSWERS, strict=True):
            start = day_start(today - timedelta(days=days_ago)) + timedelta(hours=17)
            for n in range(count):
                qid = rng.choice(content.active_ids)
                question = content.questions[qid]
                correct = rng.random() < ACCURACY[question.topic]
                selected = question.answer if correct else rng.choice([o for o in range(4) if o != question.answer])
                at = min(start + timedelta(minutes=n), now - timedelta(minutes=count - n))
                db.add(
                    PracticeAnswer(
                        user_id=user.id, question_id=qid, selected=selected, is_correct=correct, answered_at=at
                    )
                )
                results.append((qid, correct, at))

        for i, score in enumerate(EXAM_SCORES):
            started = day_start(today - timedelta(days=20 - i * 5 // 3)) + timedelta(hours=18, minutes=i)
            paper = content.draw_exam(20, rng)
            right = set(rng.sample(range(20), score))
            answers = []
            for position, qid in enumerate(paper):
                answer = content.questions[qid].answer
                selected = answer if position in right else (answer + 1 + rng.randrange(3)) % 4
                answers.append(
                    ExamAnswer(
                        position=position + 1,
                        question_id=qid,
                        selected=selected,
                        is_correct=position in right,
                        answered_at=started + timedelta(seconds=40 * (position + 1)),
                    )
                )
                results.append((qid, position in right, started + timedelta(minutes=15)))
            db.add(
                ExamAttempt(
                    user_id=user.id,
                    status=STATUS_COMPLETED,
                    started_at=started,
                    deadline_at=started + timedelta(minutes=20),
                    submitted_at=started + timedelta(minutes=14, seconds=30 + 7 * i),
                    total=20,
                    score=score,
                    answered=20,
                    answers=answers,
                )
            )

        # She keeps up with her reviews: only the last few days' mistakes are still waiting.
        await review.record_questions(db, user.id, [r for r in results if r[2] >= now - timedelta(days=3)])
        await db.commit()
        token = create_token(user.id, "user", timedelta(days=1), user.session_version)
    await engine.dispose()
    return token


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.demo_screens <new database file>")
    path = Path(sys.argv[1]).resolve()
    if path.exists():
        sys.exit(f"{path} already exists: give the path of a new, throwaway file.")
    print(asyncio.run(seed(path)))


if __name__ == "__main__":
    main()
