import secrets
import uuid

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select

from app.core.deps import DB, Content, PaidUser
from app.models import ExamAttempt
from app.schemas.exam import AnswerIn, AnswerSavedOut, ExamOut, ExamSummaryOut, ShareCodeOut, SubmitIn
from app.services import exams as exam_service
from app.services import explanations

router = APIRouter(prefix="/exams", tags=["exams"])

NOT_FOUND = "Iki kizamini ntikibonetse."
CLOSED = "Igihe cy’iki kizamini cyararangiye. Ibisubizo wari umaze gutanga byabaruwe."


async def _load(db: DB, user: PaidUser, exam_id: uuid.UUID):
    try:
        return await exam_service.get_attempt(db, user, exam_id)
    except exam_service.ExamNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def start_exam(db: DB, user: PaidUser, content: Content) -> ExamOut:
    """Starts a timed 20-question mock exam, or resumes the one still running."""
    attempt = await exam_service.start_exam(db, user, content)
    return exam_service.to_out(attempt, content)


@router.get("")
async def list_exams(
    db: DB, user: PaidUser, content: Content, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> list[ExamSummaryOut]:
    attempts = await exam_service.list_attempts(db, user, content, limit=limit, offset=offset)
    return [exam_service.to_summary(a) for a in attempts]


async def _out(db: DB, attempt, content: Content) -> ExamOut:
    notes = None
    if attempt.is_completed:
        notes = await explanations.for_questions(db, content, [a.question_id for a in attempt.answers])
    return exam_service.to_out(attempt, content, notes)


@router.get("/{exam_id}")
async def get_exam(exam_id: uuid.UUID, db: DB, user: PaidUser, content: Content) -> ExamOut:
    attempt = await _load(db, user, exam_id)
    await exam_service.finalize_expired(db, attempt, content)
    return await _out(db, attempt, content)


@router.put("/{exam_id}/answers/{position}")
async def save_answer(
    exam_id: uuid.UUID,
    body: AnswerIn,
    db: DB,
    user: PaidUser,
    content: Content,
    position: int = Path(ge=1, le=100),
) -> AnswerSavedOut:
    attempt = await _load(db, user, exam_id)
    try:
        answer = await exam_service.save_answer(db, attempt, content, position, body.selected)
    except exam_service.ExamClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, CLOSED) from exc
    except exam_service.ExamNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from exc
    return AnswerSavedOut(
        position=answer.position,
        selected=answer.selected,
        answered=sum(a.selected is not None for a in attempt.answers),
    )


@router.post("/{exam_id}/submit")
async def submit_exam(
    exam_id: uuid.UUID, db: DB, user: PaidUser, content: Content, body: SubmitIn | None = None
) -> ExamOut:
    """Grades the exam. The optional answer sheet carries choices whose own save failed (ignored once time is up)."""
    attempt = await _load(db, user, exam_id)
    sheet = {a.position: a.selected for a in body.answers} if body else None
    await exam_service.submit(db, attempt, content, sheet)
    return await _out(db, attempt, content)


@router.post("/{exam_id}/share")
async def share_exam(exam_id: uuid.UUID, db: DB, user: PaidUser) -> ShareCodeOut:
    """Creates (once) the public code of a passed exam's result card, for sharing on WhatsApp and elsewhere."""
    attempt = await _load(db, user, exam_id)
    if not attempt.is_completed or not exam_service.passed(attempt):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ushobora gusangiza ikizamini watsinze gusa.")
    while attempt.share_code is None:
        code = secrets.token_urlsafe(6)
        if await db.scalar(select(ExamAttempt.id).where(ExamAttempt.share_code == code)) is None:
            attempt.share_code = code
    await db.commit()
    return ShareCodeOut(code=attempt.share_code)
