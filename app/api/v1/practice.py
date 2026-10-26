from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import DB, Content, PaidUser
from app.schemas.practice import (
    OfflineAnswersIn,
    OfflineSyncOut,
    PracticeAnswerIn,
    PracticeAnswerOut,
    PracticeMode,
    PracticeSetOut,
)
from app.services import practice as practice_service
from app.services.content import TOPIC_IDS

router = APIRouter(prefix="/practice", tags=["practice"])


@router.get("/questions")
async def practice_questions(
    db: DB,
    user: PaidUser,
    content: Content,
    topic: str | None = None,
    mode: PracticeMode = "random",
    count: int = Query(10, ge=1, le=50),
) -> PracticeSetOut:
    """Untimed practice with instant feedback, by topic; `new` = never answered, `mistakes` = last answer wrong."""
    if topic is not None and topic not in TOPIC_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iyo nsanganyamatsiko ntibaho.")
    available, questions = await practice_service.build_set(db, user, content, topic, mode, count)
    return PracticeSetOut(topic=topic, mode=mode, available=available, questions=questions)


@router.post("/answers", status_code=status.HTTP_201_CREATED)
async def answer(body: PracticeAnswerIn, db: DB, user: PaidUser, content: Content) -> PracticeAnswerOut:
    try:
        question, correct, note = await practice_service.record_answer(
            db, user, content, body.question_id, body.selected
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Icyo kibazo ntikibonetse.") from exc
    return PracticeAnswerOut(
        question_id=question.id,
        selected=body.selected,
        answer=question.answer,
        correct=correct,
        explanation=note.text,
        law_ref=note.law_ref,
    )


@router.post("/answers/offline")
async def sync_offline_answers(body: OfflineAnswersIn, db: DB, user: PaidUser, content: Content) -> OfflineSyncOut:
    """Saves answers given while offline (sent again until acknowledged; duplicates are ignored)."""
    return await practice_service.sync_offline(db, user, content, body.answers)
