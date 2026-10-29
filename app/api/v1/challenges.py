from fastapi import APIRouter, HTTPException, status

from app.core.deps import DB, Content, OptionalUser, PaidUser
from app.schemas.challenge import ChallengeOut
from app.schemas.exam import ExamOut
from app.services import challenges
from app.services import exams as exam_service

router = APIRouter(prefix="/challenges", tags=["challenges"])

NOT_FOUND = "Uyu mukino ntubonetse."


async def _challenge(db: DB, code: str):
    challenge = await challenges.by_code(db, code)
    if challenge is None or not challenge.creator.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return challenge


@router.get("/{code}")
async def challenge(code: str, db: DB, user: OptionalUser) -> ChallengeOut:
    """Public: a friend's challenge. Results of the others are shown to its author and to those who took it."""
    return await challenges.view(db, await _challenge(db, code), user)


@router.post("/{code}/start", status_code=status.HTTP_201_CREATED)
async def take_challenge(code: str, db: DB, user: PaidUser, content: Content) -> ExamOut:
    """Starts (or resumes, or shows) the learner's exam on the challenge's paper: same 20 questions, same rules."""
    try:
        attempt = await challenges.take(db, user, await _challenge(db, code), content)
    except challenges.OwnChallenge as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Uyu mukino ni wowe wawutanze: wohereze inshuti zawe.") from exc
    except challenges.OtherExamRunning as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ufite ikindi kizamini kitarangiye. Banza ugisoze, hanyuma uhangane."
        ) from exc
    return exam_service.to_out(attempt, content)
