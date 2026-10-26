from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import ExamAnswer, ExamAttempt, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.content import OptionOut, QuestionWithAnswerOut
from app.schemas.practice import OfflineAnswerIn, OfflineSyncOut, PracticeMode
from app.services import explanations, review
from app.services.content import ContentStore, Question
from app.services.explanations import Explanation

# Offline answers older than this are not accepted (they would distort streaks and daily goals).
OFFLINE_MAX_AGE = timedelta(days=60)


def to_question_out(q: Question, note: Explanation | None = None) -> QuestionWithAnswerOut:
    note = note or Explanation(q.explanation, q.law_ref)
    return QuestionWithAnswerOut(
        id=q.id,
        ref=q.ref,
        text=q.text,
        image=q.image,
        options=[OptionOut(text=o.text, image=o.image) for o in q.options],
        topic=q.topic,
        answer=q.answer,
        explanation=note.text,
        law_ref=note.law_ref,
    )


async def questions_out(db: AsyncSession, content: ContentStore, ids: list[int]) -> list[QuestionWithAnswerOut]:
    notes = await explanations.for_questions(db, content, ids)
    return [to_question_out(content.questions[qid], notes.get(qid)) for qid in ids]


async def answer_history(db: AsyncSession, user: User) -> list[tuple[int, bool, object]]:
    """(question_id, is_correct, answered_at) for practice answers and graded exam answers, oldest first."""
    practice = await db.execute(
        select(PracticeAnswer.question_id, PracticeAnswer.is_correct, PracticeAnswer.answered_at).where(
            PracticeAnswer.user_id == user.id
        )
    )
    exams = await db.execute(
        select(ExamAnswer.question_id, ExamAnswer.is_correct, ExamAttempt.submitted_at)
        .join(ExamAttempt, ExamAnswer.attempt_id == ExamAttempt.id)
        .where(ExamAttempt.user_id == user.id, ExamAttempt.status == STATUS_COMPLETED)
    )
    rows = [(qid, bool(ok), at) for qid, ok, at in practice.all()]
    rows += [(qid, bool(ok), at) for qid, ok, at in exams.all()]
    rows.sort(key=lambda r: r[2])
    return rows


async def build_set(
    db: AsyncSession, user: User, content: ContentStore, topic: str | None, mode: PracticeMode, count: int
) -> tuple[int, list[QuestionWithAnswerOut]]:
    pool = content.ids_by_topic[topic] if topic else content.active_ids
    if mode != "random":
        history = await answer_history(db, user)
        if mode == "new":
            seen = {qid for qid, _, _ in history}
            pool = [qid for qid in pool if qid not in seen]
        else:  # mistakes: the most recent answer to the question was wrong
            last: dict[int, bool] = {}
            for qid, ok, _ in history:
                last[qid] = ok
            wrong = {qid for qid, ok in last.items() if not ok}
            pool = [qid for qid in pool if qid in wrong]
    picked = content.sample(pool, count)
    return len(pool), await questions_out(db, content, picked)


async def record_answer(
    db: AsyncSession, user: User, content: ContentStore, question_id: int, selected: int
) -> tuple[Question, bool, Explanation]:
    question = content.questions.get(question_id)
    if question is None or not question.active:
        raise KeyError(question_id)
    correct = selected == question.answer
    now = utcnow()
    db.add(
        PracticeAnswer(user_id=user.id, question_id=question_id, selected=selected, is_correct=correct, answered_at=now)
    )
    await review.record_questions(db, user.id, [(question_id, correct, now)])
    await db.commit()
    notes = await explanations.for_questions(db, content, [question_id])
    return question, correct, notes[question_id]


async def sync_offline(
    db: AsyncSession, user: User, content: ContentStore, answers: list[OfflineAnswerIn]
) -> OfflineSyncOut:
    """Saves answers given offline. Answers already saved (same client_id) are counted, not duplicated."""
    now = utcnow()
    client_ids = {str(a.client_id) for a in answers}
    known = set(
        await db.scalars(
            select(PracticeAnswer.client_id).where(
                PracticeAnswer.user_id == user.id, PracticeAnswer.client_id.in_(client_ids)
            )
        )
    )
    saved = duplicates = skipped = 0
    results = []
    for answer in answers:
        client_id = str(answer.client_id)
        if client_id in known:
            duplicates += 1
            continue
        question = content.questions.get(answer.question_id)
        answered_at = min(answer.answered_at, now) if answer.answered_at.tzinfo else None
        if question is None or not question.active or answered_at is None or now - answered_at > OFFLINE_MAX_AGE:
            skipped += 1
            continue
        known.add(client_id)
        correct = answer.selected == question.answer
        db.add(
            PracticeAnswer(
                user_id=user.id,
                question_id=question.id,
                selected=answer.selected,
                is_correct=correct,
                answered_at=answered_at,
                client_id=client_id,
            )
        )
        results.append((question.id, correct, answered_at))
        saved += 1
    await review.record_questions(db, user.id, results)
    await db.commit()
    return OfflineSyncOut(saved=saved, duplicates=duplicates, skipped=skipped)
