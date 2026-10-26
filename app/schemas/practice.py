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
