import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.content import OptionOut


class ExamItemOut(BaseModel):
    position: int
    question_id: int
    ref: str
    text: str
    image: str | None
    options: list[OptionOut]
    topic: str
    selected: int | None
    # Only revealed once the exam is completed.
    answer: int | None = None
    is_correct: bool | None = None
    explanation: str | None = None
    law_ref: str | None = None
    # The question read aloud (also while the exam runs); the explanation's clip once it is over.
    audio: str | None = None
    explanation_audio: str | None = None


class ExamOut(BaseModel):
    id: uuid.UUID
    status: str
    started_at: datetime
    deadline_at: datetime
    submitted_at: datetime | None
    server_time: datetime
    auto_submitted: bool
    total: int
    score: int | None
    pass_mark: int
    passed: bool | None
    answered: int
    items: list[ExamItemOut]
    # Set when this exam is a friend's challenge: its code, for the comparison on the result page.
    challenge_code: str | None = None


class ShareCodeOut(BaseModel):
    code: str


class SharedResultOut(BaseModel):
    """What anyone with the link sees: the learner's first name and score, nothing else."""

    name: str
    score: int
    total: int
    passed: bool
    day: date


class ExamSummaryOut(BaseModel):
    id: uuid.UUID
    status: str
    started_at: datetime
    submitted_at: datetime | None
    total: int
    score: int | None
    passed: bool | None
    duration_seconds: int | None


class AnswerIn(BaseModel):
    selected: int | None = Field(default=None, ge=0, le=3)


class AnswerSavedOut(BaseModel):
    position: int
    selected: int | None
    answered: int


class SheetAnswerIn(BaseModel):
    position: int = Field(ge=1, le=100)
    selected: int = Field(ge=0, le=3)


class SubmitIn(BaseModel):
    """The learner's answer sheet as their device last saw it, so choices whose own save failed are counted too."""

    answers: list[SheetAnswerIn] = Field(default_factory=list, max_length=100)
