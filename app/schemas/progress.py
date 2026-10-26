from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.exam import ExamSummaryOut
from app.schemas.user import UserOut

ReadinessStatus = Literal["new", "learning", "almost", "ready"]


class ReadinessOut(BaseModel):
    status: ReadinessStatus
    ready: bool
    exams_completed: int
    exams_required: int
    exams_remaining: int
    average: float | None
    average_required: float


class ExamStatsOut(BaseModel):
    completed: int
    passed: int
    average: float | None
    best: int | None
    last: int | None
    pass_rate: float | None


class TopicMasteryOut(BaseModel):
    topic: str
    name: str
    answered: int
    correct: int
    accuracy: float | None
    question_count: int
    seen: int


class ScorePointOut(BaseModel):
    exam_id: str
    date: datetime
    score: int
    passed: bool


class LessonProgressOut(BaseModel):
    completed: int
    total: int
    completed_slugs: list[str]
    next_slug: str | None


class ActivityDayOut(BaseModel):
    day: date
    answers: int


class DashboardOut(BaseModel):
    user: UserOut
    readiness: ReadinessOut
    exams: ExamStatsOut
    trend: list[ScorePointOut]
    topics: list[TopicMasteryOut]
    lessons: LessonProgressOut
    practice_answers: int
    questions_seen: int
    question_total: int
    streak_days: int
    activity: list[ActivityDayOut]
    recent_exams: list[ExamSummaryOut]
    in_progress_exam: str | None
