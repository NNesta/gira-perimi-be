from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import DB, Content, CurrentUser, PaidUser
from app.schemas.practice import (
    MistakesOut,
    MistakeStatus,
    OfflineAnswersIn,
    OfflineSyncOut,
    PlacementIn,
    PlacementOut,
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


@router.get("/mistakes")
async def mistakes(
    db: DB,
    user: PaidUser,
    content: Content,
    topic: str | None = None,
    status_filter: MistakeStatus = Query("all", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> MistakesOut:
    """ "Ibyo nibeshyeho": questions answered wrongly, with the learner's choice and the explanation."""
    if topic is not None and topic not in TOPIC_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iyo nsanganyamatsiko ntibaho.")
    return await practice_service.mistakes(db, user, content, topic, status_filter, page, page_size)


@router.get("/placement")
async def placement_questions(db: DB, _user: CurrentUser, content: Content) -> PracticeSetOut:
    """The first-time welcome quiz: one question per topic. Free for every learner, even behind the paywall."""
    questions = await practice_service.placement_set(db, content)
    return PracticeSetOut(topic=None, mode="random", available=len(questions), questions=questions)


@router.post("/placement", status_code=status.HTTP_201_CREATED)
async def placement_answers(body: PlacementIn, db: DB, user: CurrentUser, content: Content) -> PlacementOut:
    """Saves the welcome quiz and names the topics answered wrongly, in the order they are taught."""
    try:
        return await practice_service.record_placement(db, user, content, body.answers)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Icyo kibazo ntikibonetse.") from exc


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
