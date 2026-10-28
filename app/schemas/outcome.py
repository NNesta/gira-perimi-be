import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

OutcomeResult = Literal["passed", "failed", "not_taken"]
TestimonialStatus = Literal["pending", "approved", "hidden"]


class OutcomeIn(BaseModel):
    exam_date: date
    result: OutcomeResult
    testimonial: str | None = Field(default=None, max_length=400)
    public: bool = False

    @field_validator("testimonial")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        value = " ".join(value.split()) if value else None
        return value or None


class OutcomeOut(BaseModel):
    exam_date: date
    result: OutcomeResult
    testimonial: str | None
    public: bool
    testimonial_status: TestimonialStatus


class TestimonialOut(BaseModel):
    name: str
    text: str
    exam_date: date


class OutcomeStatsOut(BaseModel):
    """Public: how learners did in the real exam, by their own account."""

    answered: int
    passed: int
    # Null until enough learners have answered (OUTCOME_MIN_ANSWERS): a rate from 3 people would mislead.
    pass_rate: float | None
    testimonials: list[TestimonialOut]


class AdminTestimonialOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    exam_date: date
    result: OutcomeResult
    text: str
    public: bool
    status: TestimonialStatus
    created_at: datetime


class TestimonialUpdate(BaseModel):
    status: Literal["approved", "hidden"]
