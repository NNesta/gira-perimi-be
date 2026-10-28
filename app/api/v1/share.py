from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import DB
from app.models import ExamAttempt
from app.schemas.exam import SharedResultOut
from app.services import exams as exam_service
from app.services.dates import local_day

router = APIRouter(prefix="/share", tags=["share"])


@router.get("/{code}")
async def shared_result(code: str, db: DB) -> SharedResultOut:
    """Public: the result card behind a shared link (first name and score only)."""
    attempt = await db.scalar(
        select(ExamAttempt).options(selectinload(ExamAttempt.user)).where(ExamAttempt.share_code == code)
    )
    if attempt is None or attempt.score is None or attempt.submitted_at is None or not attempt.user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iyi link ntikiriho.")
    user = attempt.user
    return SharedResultOut(
        name=user.given_name or user.name.split()[0],
        score=attempt.score,
        total=attempt.total,
        passed=bool(exam_service.passed(attempt)),
        day=local_day(attempt.submitted_at),
    )
