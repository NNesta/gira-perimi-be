import random
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import ExamAnswer, ExamAttempt, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.content import OptionOut, QuestionWithAnswerOut
from app.schemas.practice import (
    MistakeCounts,
    MistakeOut,
    MistakesOut,
    MistakeStatus,
    OfflineAnswerIn,
    OfflineSyncOut,
    PlacementOut,
    PracticeAnswerIn,
    PracticeMode,
)
from app.services import explanations, review
from app.services.content import TOPICS, ContentStore, Question, explanation_audio
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
        audio=q.audio,
        answer=q.answer,
        explanation=note.text,
        law_ref=note.law_ref,
        explanation_audio=explanation_audio(q, note.text),
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


async def mistakes(
    db: AsyncSession,
    user: User,
    content: ContentStore,
    topic: str | None,
    status: MistakeStatus,
    page: int,
    page_size: int,
) -> MistakesOut:
    """Every question the learner has got wrong, in practice or a finished exam, the most recent mistake first."""
    practice = await db.execute(
        select(
            PracticeAnswer.question_id, PracticeAnswer.selected, PracticeAnswer.is_correct, PracticeAnswer.answered_at
        ).where(PracticeAnswer.user_id == user.id)
    )
    exams = await db.execute(
        select(ExamAnswer.question_id, ExamAnswer.selected, ExamAnswer.is_correct, ExamAttempt.submitted_at)
        .join(ExamAttempt, ExamAnswer.attempt_id == ExamAttempt.id)
        .where(ExamAttempt.user_id == user.id, ExamAttempt.status == STATUS_COMPLETED)
    )
    rows = sorted((r for r in [*practice.all(), *exams.all()] if r[3] is not None), key=lambda r: r[3])

    stats: dict[int, dict] = {}
    for qid, selected, correct, at in rows:
        question = content.questions.get(qid)
        if question is None or not question.active:
            continue
        if not correct:
            record = stats.setdefault(qid, {"wrong": 0})
            record.update(wrong=record["wrong"] + 1, at=at, selected=selected, fixed=False)
        elif qid in stats:
            stats[qid]["fixed"] = True

    chosen = {qid: s for qid, s in stats.items() if status == "all" or s["fixed"] == (status == "fixed")}
    topics = Counter(content.questions[qid].topic for qid in chosen)
    ids = sorted(
        (qid for qid in chosen if topic is None or content.questions[qid].topic == topic),
        key=lambda qid: chosen[qid]["at"],
        reverse=True,
    )
    page_ids = ids[(page - 1) * page_size : page * page_size]
    questions = {q.id: q for q in await questions_out(db, content, page_ids)}
    fixed = sum(s["fixed"] for s in stats.values())
    return MistakesOut(
        total=len(ids),
        page=page,
        page_size=page_size,
        counts=MistakeCounts(all=len(stats), open=len(stats) - fixed, fixed=fixed),
        topics=dict(topics),
        items=[
            MistakeOut(
                question=questions[qid],
                wrong_count=chosen[qid]["wrong"],
                last_wrong_at=chosen[qid]["at"],
                last_selected=chosen[qid]["selected"],
                fixed=chosen[qid]["fixed"],
            )
            for qid in page_ids
        ],
    )


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


async def placement_set(
    db: AsyncSession, content: ContentStore, rng: random.Random | None = None
) -> list[QuestionWithAnswerOut]:
    """The welcome quiz: one random question from each topic, in the order the topics are taught."""
    rng = rng or random.SystemRandom()
    picked = [rng.choice(ids) for t in TOPICS if (ids := content.ids_by_topic[t["id"]])]
    return await questions_out(db, content, picked)


async def record_placement(
    db: AsyncSession, user: User, content: ContentStore, answers: list[PracticeAnswerIn]
) -> PlacementOut:
    """Saves the welcome quiz in one go, as practice answers: they count towards topic mastery and review."""
    now = utcnow()
    graded: dict[int, bool] = {}
    for item in answers:
        question = content.questions.get(item.question_id)
        if question is None or not question.active:
            raise KeyError(item.question_id)
        if item.question_id in graded:
            continue
        graded[item.question_id] = correct = item.selected == question.answer
        db.add(
            PracticeAnswer(
                user_id=user.id,
                question_id=item.question_id,
                selected=item.selected,
                is_correct=correct,
                answered_at=now,
            )
        )
    await review.record_questions(db, user.id, [(qid, ok, now) for qid, ok in graded.items()])
    await db.commit()
    weak = {content.questions[qid].topic for qid, ok in graded.items() if not ok}
    return PlacementOut(
        correct=sum(graded.values()), total=len(graded), weak_topics=[t["id"] for t in TOPICS if t["id"] in weak]
    )


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
