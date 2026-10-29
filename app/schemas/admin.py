import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.content import OptionOut
from app.schemas.progress import LearnerReportOut


class AdminLoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class AdminOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str
    last_login_at: datetime | None


class DailyPointOut(BaseModel):
    day: date
    signups: int
    exams: int


class ScoreBucketOut(BaseModel):
    score: int
    count: int


class TopicDifficultyOut(BaseModel):
    topic: str
    name: str
    answered: int
    accuracy: float | None


class PlatformStatsOut(BaseModel):
    users_total: int
    users_new_7d: int
    users_active_7d: int
    users_ready: int
    exams_total: int
    exams_7d: int
    average_score: float | None
    pass_rate: float | None
    practice_answers: int
    # Real exam, as learners reported it ("Watsinze ikizamini?"), and testimonials waiting to be read.
    outcomes_answered: int = 0
    outcomes_passed: int = 0
    testimonials_pending: int = 0
    daily: list[DailyPointOut]
    score_distribution: list[ScoreBucketOut]
    topics: list[TopicDifficultyOut]


class AdminUserRowOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    picture_url: str | None
    plan: str
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    exams_completed: int
    average: float | None
    best: int | None
    ready: bool
    readiness_status: str


class AdminUserDetailOut(LearnerReportOut):
    phone: str | None
    plan: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    plan: Literal["free", "premium"] | None = None


UserSort = Literal["joined", "name", "exams", "average", "last_active"]

QuestionFilter = Literal["all", "missing", "unreviewed", "reviewed", "edited"]
QuestionSort = Literal["number", "hardest", "most_answered"]


class AdminQuestionOut(BaseModel):
    id: int
    ref: str
    text: str
    image: str | None
    options: list[OptionOut]
    answer: int
    topic: str
    explanation: str | None
    law_ref: str | None
    reviewed: bool
    edited: bool
    updated_at: datetime | None
    updated_by: str | None
    # How learners did on this question, across practice and finished exams.
    answered: int
    accuracy: float | None


class ExplanationCountsOut(BaseModel):
    total: int
    with_explanation: int
    reviewed: int
    edited: int


class AdminQuestionsOut(BaseModel):
    items: list[AdminQuestionOut]
    total: int
    page: int
    page_size: int
    counts: ExplanationCountsOut


class ExplanationUpdate(BaseModel):
    explanation: str = Field(max_length=2000)
    law_ref: str | None = Field(default=None, max_length=200)
    reviewed: bool = False
