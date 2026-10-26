from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class QuestionExplanation(Base):
    """An admin's edit of a question's explanation; wins over the default in app/data/explanations.json."""

    __tablename__ = "question_explanations"

    question_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Empty text hides the explanation for that question.
    text: Mapped[str] = mapped_column(Text, default="")
    law_ref: Mapped[str | None] = mapped_column(String(200))
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(320))
