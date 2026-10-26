from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.content import QuestionWithAnswerOut, SignOut


class ReviewSummaryOut(BaseModel):
    due: int
    due_questions: int
    due_signs: int
    learning: int
    mastered: int
    next_due_at: datetime | None
    # Items still being learned, per Leitner box 1–5.
    boxes: list[int]


class ReviewQuestionOut(BaseModel):
    kind: Literal["question"] = "question"
    box: int
    question: QuestionWithAnswerOut


class ReviewSignOut(BaseModel):
    kind: Literal["sign"] = "sign"
    box: int
    sign: SignOut


class ReviewSessionOut(BaseModel):
    summary: ReviewSummaryOut
    items: list[ReviewQuestionOut | ReviewSignOut]


class SignRecallIn(BaseModel):
    sign_id: str = Field(min_length=1, max_length=32)
    known: bool
