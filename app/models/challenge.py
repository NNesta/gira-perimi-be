import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow
from app.models.user import User


class Challenge(Base):
    """ "Hangana nanjye": the 20 questions of a finished mock exam, offered to friends to sit under the same rules."""

    __tablename__ = "challenges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The exam the paper comes from: one challenge per exam. Not a foreign key, as exams point back at challenges.
    source_exam_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    # Question ids in the paper's order, comma-separated.
    question_ids: Mapped[str] = mapped_column(String(400))
    creator_score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    creator: Mapped[User] = relationship()

    @property
    def paper(self) -> list[int]:
        return [int(qid) for qid in self.question_ids.split(",") if qid]
