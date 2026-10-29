import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.progress import ReadinessOut


# ---------------------------------------------------------------------- admin
class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class SchoolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    active: bool | None = None


class InstructorIn(BaseModel):
    email: EmailStr = Field(max_length=320)


class InstructorOut(BaseModel):
    id: uuid.UUID
    email: str
    # The instructor's name once they have an account (they sign in like learners, with this address).
    name: str | None


class SchoolAdminOut(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    created_at: datetime
    instructors: list[InstructorOut]
    classes: int
    learners: int


# ---------------------------------------------------------------------- instructors
class ClassCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    archived: bool | None = None


class ClassSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    join_code: str
    archived: bool
    learners: int
    created_at: datetime


class TeachingSchoolOut(BaseModel):
    id: uuid.UUID
    name: str
    classes: list[ClassSummaryOut]


class ClassLearnerOut(BaseModel):
    """One learner in the class table: enough to see at a glance who is ready and who needs help with what."""

    id: uuid.UUID
    name: str
    email: str
    picture_url: str | None
    joined_at: datetime
    last_active_at: datetime | None
    exam_date: date | None
    readiness: ReadinessOut
    exams_completed: int
    # Topic names, weakest first (accuracy below 75% over at least 5 answers).
    weak_topics: list[str]


class ClassTopicOut(BaseModel):
    topic: str
    name: str
    answered: int
    accuracy: float | None


class ClassDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    join_code: str
    archived: bool
    school_id: uuid.UUID
    school_name: str
    learners: list[ClassLearnerOut]
    # The whole class's accuracy per topic, weakest first: what to teach next.
    topics: list[ClassTopicOut]


# ---------------------------------------------------------------------- learners
class JoinIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class ClassPreviewOut(BaseModel):
    """What a learner sees before joining with a code."""

    name: str
    school: str


class MyClassOut(BaseModel):
    id: uuid.UUID
    name: str
    school: str
    joined_at: datetime
