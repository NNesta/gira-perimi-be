import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.content import QuestionWithAnswerOut

PracticeMode = Literal["random", "new", "mistakes"]
# open: the last answer to the question is still wrong; fixed: answered correctly since.
MistakeStatus = Literal["all", "open", "fixed"]


class PracticeSetOut(BaseModel):
    topic: str | None
    mode: PracticeMode
    available: int
    questions: list[QuestionWithAnswerOut]


class PracticeAnswerIn(BaseModel):
    question_id: int = Field(ge=1)
    selected: int = Field(ge=0, le=3)


class PlacementIn(BaseModel):
    answers: list[PracticeAnswerIn] = Field(min_length=1, max_length=20)


class PlacementOut(BaseModel):
    correct: int
    total: int
    weak_topics: list[str]


class PracticeAnswerOut(BaseModel):
    question_id: int
    selected: int
    answer: int
    correct: bool
    explanation: str | None = None
    law_ref: str | None = None


class OfflineAnswerIn(PracticeAnswerIn):
    """An answer given while offline, synced later. `client_id` makes retries safe."""

    client_id: uuid.UUID
    answered_at: datetime


class OfflineAnswersIn(BaseModel):
    answers: list[OfflineAnswerIn] = Field(max_length=500)


class OfflineSyncOut(BaseModel):
    saved: int
    duplicates: int
    skipped: int


class MistakeOut(BaseModel):
    question: QuestionWithAnswerOut
    wrong_count: int
    last_wrong_at: datetime
    # The option picked the last time the answer was wrong (null: left unanswered in an exam).
    last_selected: int | None
    fixed: bool


class MistakeCounts(BaseModel):
    all: int
    open: int
    fixed: int


class MistakesOut(BaseModel):
    total: int
    page: int
    page_size: int
    counts: MistakeCounts
    # Questions per topic for the chosen status, for the topic filter.
    topics: dict[str, int]
    items: list[MistakeOut]
