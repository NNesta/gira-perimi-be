from typing import Any

from pydantic import BaseModel


class OptionOut(BaseModel):
    text: str
    image: str | None


class QuestionOut(BaseModel):
    id: int
    ref: str
    text: str
    image: str | None
    options: list[OptionOut]
    topic: str
    # "Umva": the question and its answers read aloud (MP3), when there is a clip.
    audio: str | None = None


class QuestionWithAnswerOut(QuestionOut):
    answer: int
    # Why the answer is right, and the article of law behind it (when known).
    explanation: str | None = None
    law_ref: str | None = None
    explanation_audio: str | None = None


class TopicOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    question_count: int
    lessons: list[str]


class LessonSummaryOut(BaseModel):
    slug: str
    order: int
    title: str
    summary: str
    icon: str
    topics: list[str]
    minutes: int
    free: bool
    question_count: int
    sections: list[str]
    # For after the theory exam (the practical test): listed apart, not counted in study plans.
    after_theory: bool = False
    completed: bool = False
    locked: bool = False


class LessonSectionOut(BaseModel):
    id: str
    title: str
    blocks: list[dict[str, Any]]


class LessonNavOut(BaseModel):
    slug: str
    title: str


class LessonOut(BaseModel):
    slug: str
    order: int
    title: str
    summary: str
    icon: str
    topics: list[str]
    minutes: int
    free: bool
    question_count: int
    after_theory: bool = False
    sources: list[str]
    sections: list[LessonSectionOut]
    completed: bool = False
    previous: LessonNavOut | None = None
    next: LessonNavOut | None = None


class SignOut(BaseModel):
    id: str
    code: str
    category: str
    name: str
    description: str
    image: str


class SignCategoryOut(BaseModel):
    id: str
    name: str
    description: str
    letter: str
    count: int


class SignsOut(BaseModel):
    categories: list[SignCategoryOut]
    signs: list[SignOut]


class ExamRulesOut(BaseModel):
    question_count: int
    duration_minutes: int
    pass_mark: int
    readiness_min_exams: int
    readiness_min_average: float
    readiness_recent_exams: int


class QuestionSearchOut(BaseModel):
    total: int
    items: list[QuestionWithAnswerOut]


class OverviewOut(BaseModel):
    questions: int
    lessons: int
    signs: int
    topics: int
    exam: ExamRulesOut
    # Credit owed for the voice of the audio clips (its licence asks for it), when there are clips.
    audio_credit: str | None = None
