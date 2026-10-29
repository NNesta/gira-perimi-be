import uuid
from datetime import date

from pydantic import BaseModel


class ChallengePlayerOut(BaseModel):
    name: str
    score: int
    total: int
    creator: bool
    you: bool


class ChallengeOut(BaseModel):
    """A friend's challenge ("Hangana nanjye"): the author's first name and score, and who has taken it."""

    code: str
    creator_name: str
    creator_score: int
    total: int
    day: date
    # Friends who have finished it (the author not counted).
    players: int
    is_creator: bool
    # The viewer's own exam on this paper, if they have started it.
    exam_id: uuid.UUID | None
    exam_status: str | None
    # Everyone's result, best first: only for the author and for those who have finished it, otherwise null.
    standings: list[ChallengePlayerOut] | None
