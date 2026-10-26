from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.exam import ExamSummaryOut
from app.schemas.review import ReviewSummaryOut
from app.schemas.user import UserOut

ReadinessStatus = Literal["new", "learning", "almost", "ready"]
# none: no exam date yet · on_track · tight: more work than days left · today: exam day · passed: the date is behind us
PlanPace = Literal["none", "on_track", "tight", "today", "passed"]


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


class TodayOut(BaseModel):
    """Today's study checklist (Kigali day)."""

    answered: int
    goal: int
    lesson_done: bool
    exam_done: bool
    exam_suggested: bool


class PlanOut(BaseModel):
    exam_date: date | None
    days_left: int | None
    lessons_left: int
    exams_left: int
    pace: PlanPace
    # Suggested rhythm of mock exams to be ready in time: one every N days (1 = daily), or None.
    exam_every_days: int | None
    exams_per_day: int | None


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
    today: TodayOut
    plan: PlanOut
    review: ReviewSummaryOut
