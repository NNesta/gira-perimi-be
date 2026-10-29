"""Hangana nanjye ("challenge me"): a learner offers the 20 questions of a finished mock exam to friends, who sit the
same paper under the same rules. Everyone who took it, and its author, sees how the others did."""

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Challenge, ExamAttempt, User
from app.models.exam import STATUS_COMPLETED
from app.schemas.challenge import ChallengeOut, ChallengePlayerOut
from app.services import exams
from app.services.content import ContentStore
from app.services.dates import local_day
from app.services.outcomes import first_name


class OwnChallenge(Exception):
    """The author cannot sit their own paper again as a challenge."""


class OtherExamRunning(Exception):
    def __init__(self, attempt_id) -> None:
        super().__init__(attempt_id)
        self.attempt_id = attempt_id


async def for_exam(db: AsyncSession, attempt: ExamAttempt) -> Challenge:
    """The challenge made from a finished exam (created once; later calls return the same code)."""
    existing = await db.scalar(select(Challenge).where(Challenge.source_exam_id == attempt.id))
    if existing is not None:
        return existing
    code = secrets.token_urlsafe(6)
    while await db.scalar(select(Challenge.id).where(Challenge.code == code)) is not None:
        code = secrets.token_urlsafe(6)
    challenge = Challenge(
        code=code,
        creator_id=attempt.user_id,
        source_exam_id=attempt.id,
        question_ids=",".join(str(answer.question_id) for answer in attempt.answers),
        creator_score=attempt.score or 0,
        total=attempt.total,
    )
    db.add(challenge)
    await db.commit()
    return challenge


async def by_code(db: AsyncSession, code: str) -> Challenge | None:
    return await db.scalar(select(Challenge).options(selectinload(Challenge.creator)).where(Challenge.code == code))


async def mine(db: AsyncSession, user: User, challenge: Challenge) -> ExamAttempt | None:
    return await db.scalar(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user.id, ExamAttempt.challenge_id == challenge.id)
        .order_by(ExamAttempt.started_at.desc())
    )


async def take(db: AsyncSession, user: User, challenge: Challenge, content: ContentStore) -> ExamAttempt:
    """The learner's exam on this paper: the one they already have (running or finished), or a new one."""
    if challenge.creator_id == user.id:
        raise OwnChallenge
    existing = await mine(db, user, challenge)
    if existing is not None:
        attempt = await exams.get_attempt(db, user, existing.id)
        await exams.finalize_expired(db, attempt, content)
        return attempt
    running = await exams.current_attempt(db, user, content)
    if running is not None:
        raise OtherExamRunning(running.id)
    paper = [qid for qid in challenge.paper if qid in content.questions]
    return await exams.new_attempt(db, user, content, paper, challenge_id=challenge.id)


async def view(db: AsyncSession, challenge: Challenge, user: User | None) -> ChallengeOut:
    """What the challenge page shows. The others' results only to its author and to those who have taken it."""
    finished = (
        await db.execute(
            select(ExamAttempt, User)
            .join(User, User.id == ExamAttempt.user_id)
            .where(ExamAttempt.challenge_id == challenge.id, ExamAttempt.status == STATUS_COMPLETED, User.is_active)
            .order_by(ExamAttempt.score.desc(), ExamAttempt.submitted_at)
        )
    ).all()
    attempt = await mine(db, user, challenge) if user else None
    is_creator = user is not None and user.id == challenge.creator_id
    took_it = attempt is not None and attempt.status == STATUS_COMPLETED
    standings = None
    if is_creator or took_it:
        players = [
            ChallengePlayerOut(
                name=first_name(challenge.creator),
                score=challenge.creator_score,
                total=challenge.total,
                creator=True,
                you=is_creator,
            ),
            *(
                ChallengePlayerOut(
                    name=first_name(player),
                    score=exam.score or 0,
                    total=exam.total,
                    creator=False,
                    you=player.id == user.id,
                )
                for exam, player in finished
            ),
        ]
        standings = sorted(players, key=lambda p: -p.score)
    return ChallengeOut(
        code=challenge.code,
        creator_name=first_name(challenge.creator),
        creator_score=challenge.creator_score,
        total=challenge.total,
        day=local_day(challenge.created_at),
        players=len(finished),
        is_creator=is_creator,
        exam_id=attempt.id if attempt else None,
        exam_status=attempt.status if attempt else None,
        standings=standings,
    )
