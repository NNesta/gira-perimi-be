from fastapi import APIRouter

from app.core.deps import DB
from app.schemas.outcome import OutcomeStatsOut
from app.services import outcomes as outcome_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/outcomes")
async def outcome_stats(db: DB) -> OutcomeStatsOut:
    """Public: the real-exam pass rate learners reported, and the testimonials they agreed to share."""
    return await outcome_service.public_stats(db)
