"""Question explanations: defaults ship in app/data/explanations.json; admins can edit them (stored in the DB)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestionExplanation
from app.services.content import ContentStore, Question


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str | None
    law_ref: str | None
    reviewed: bool = False
    edited: bool = False
    updated_at: datetime | None = None
    updated_by: str | None = None


def resolve(question: Question, override: QuestionExplanation | None) -> Explanation:
    if override is None:
        return Explanation(question.explanation, question.law_ref)
    return Explanation(
        text=override.text.strip() or None,
        law_ref=(override.law_ref or "").strip() or None,
        reviewed=override.reviewed,
        edited=True,
        updated_at=override.updated_at,
        updated_by=override.updated_by,
    )


async def overrides(db: AsyncSession, ids: Iterable[int] | None = None) -> dict[int, QuestionExplanation]:
    query = select(QuestionExplanation)
    if ids is not None:
        query = query.where(QuestionExplanation.question_id.in_(list(ids)))
    return {row.question_id: row for row in await db.scalars(query)}


async def for_questions(db: AsyncSession, content: ContentStore, ids: Iterable[int]) -> dict[int, Explanation]:
    ids = list(ids)
    edits = await overrides(db, ids)
    return {qid: resolve(content.questions[qid], edits.get(qid)) for qid in ids if qid in content.questions}


async def last_edit(db: AsyncSession) -> datetime | None:
    return await db.scalar(select(func.max(QuestionExplanation.updated_at)))
