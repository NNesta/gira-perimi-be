import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.exam import ExamSummaryOut
from app.schemas.review import ReviewSummaryOut
from app.schemas.user import UserOut

ReadinessStatus = Literal["new", "learning", "almost", "ready"]
# none: no exam date yet · on_track · tight: more work than days left · today: exam day · passed: the date is behind us
# passed: the exam date is behind us; succeeded: the learner told us they passed the real exam.
PlanPace = Literal["none", "on_track", "tight", "today", "passed", "succeeded"]


class ReadinessOut(BaseModel):
    status: ReadinessStatus
    ready: bool
    # Completed exams that count: abandoned ones (time ran out, under half answered) do not.
    exams_completed: int
    exams_required: int
    exams_remaining: int
    # Average of the `average_window` most recent exams that count.
    average: float | None
    average_required: float
    average_window: int


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


class PredictionOut(BaseModel):
    """How learners at the same level did in the real exam, by their own account: "at your level, X% passed".

    The level is the average of one's recent mock exams, in bands (e.g. 15–17/20). Only given once enough learners in
    the band have answered "Watsinze ikizamini?" (OUTCOME_MIN_ANSWERS).
    """

    band_low: float
    band_high: float
    reports: int
    passed: int
    pass_rate: float


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
    # "Watsinze ikizamini?": the past exam date to ask about, or null.
    outcome_question: date | None = None
    # How learners at this learner's level did in the real exam, once there are enough answers (see PredictionOut).
    prediction: PredictionOut | None = None


class BadgeOut(BaseModel):
    id: str
    title: str
    # What it takes, phrased as a goal ("Iga iminsi 7 ikurikiranye").
    description: str
    earned: bool
    current: int
    target: int


class BadgesOut(BaseModel):
    earned: int
    total: int
    items: list[BadgeOut]


class LearnerReportOut(BaseModel):
    """A learner's progress as staff see it: admins (who see more, see AdminUserDetailOut) and the instructors of the
    classes the learner joined."""

    id: uuid.UUID
    email: str
    name: str
    picture_url: str | None
    last_active_at: datetime | None
    exam_date: date | None
    daily_goal: int
    streak_days: int
    readiness: ReadinessOut
    exams: ExamStatsOut
    topics: list[TopicMasteryOut]
    lessons_completed: int
    lessons_total: int
    practice_answers: int
    recent_exams: list[ExamSummaryOut]
    review: ReviewSummaryOut
