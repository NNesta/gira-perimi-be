from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExamAnswer, ExamAttempt, PracticeAnswer, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.content import OptionOut, QuestionWithAnswerOut
from app.schemas.practice import PracticeMode
from app.services.content import ContentStore, Question


def to_question_out(q: Question) -> QuestionWithAnswerOut:
    return QuestionWithAnswerOut(
        id=q.id,
        ref=q.ref,
        text=q.text,
        image=q.image,
        options=[OptionOut(text=o.text, image=o.image) for o in q.options],
        topic=q.topic,
        answer=q.answer,
    )


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
    return len(pool), [to_question_out(content.questions[qid]) for qid in picked]


async def record_answer(
    db: AsyncSession, user: User, content: ContentStore, question_id: int, selected: int
) -> tuple[Question, bool]:
    question = content.questions.get(question_id)
    if question is None or not question.active:
        raise KeyError(question_id)
    correct = selected == question.answer
    db.add(PracticeAnswer(user_id=user.id, question_id=question_id, selected=selected, is_correct=correct))
    await db.commit()
    return question, correct
