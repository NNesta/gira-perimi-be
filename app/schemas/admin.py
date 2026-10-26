import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.exam import ExamSummaryOut
from app.schemas.progress import ExamStatsOut, ReadinessOut, TopicMasteryOut


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


class AdminUserDetailOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    picture_url: str | None
    phone: str | None
    plan: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    last_active_at: datetime | None
    readiness: ReadinessOut
    exams: ExamStatsOut
    topics: list[TopicMasteryOut]
    lessons_completed: int
    lessons_total: int
    practice_answers: int
    recent_exams: list[ExamSummaryOut]


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    plan: Literal["free", "premium"] | None = None


UserSort = Literal["joined", "name", "exams", "average", "last_active"]
