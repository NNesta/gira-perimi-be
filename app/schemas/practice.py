import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.content import QuestionWithAnswerOut

PracticeMode = Literal["random", "new", "mistakes"]


class PracticeSetOut(BaseModel):
    topic: str | None
    mode: PracticeMode
    available: int
    questions: list[QuestionWithAnswerOut]


class PracticeAnswerIn(BaseModel):
    question_id: int = Field(ge=1)
    selected: int = Field(ge=0, le=3)


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
