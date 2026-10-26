"""Spaced review ("Isubiramo"): what a learner gets wrong comes back after 1, 3, 7, 14 and 30 days.

Leitner boxes: a wrong answer puts the item in box 1, due the next day. Recalling a *due* item correctly moves it up
one box; recalling it in box 5 masters it and it leaves the queue. Answering correctly before an item is due changes
nothing, so cramming does not skip the spacing.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import ReviewItem
from app.models.review import KIND_QUESTION, KIND_SIGN
from app.schemas.review import ReviewSummaryOut
from app.services.content import ContentStore
from app.services.dates import day_start, local_day

INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}
LAST_BOX = max(INTERVAL_DAYS)


def due_date(box: int, now: datetime) -> datetime:
    """Midnight in Kigali, INTERVAL_DAYS[box] days after `now`: items come due at the start of a learner's day."""
    return day_start(local_day(now) + timedelta(days=INTERVAL_DAYS[box]))


async def record(db: AsyncSession, user_id, kind: str, results: Iterable[tuple[str, bool, datetime]]) -> None:
    """Applies (item_id, correct, answered_at) results to the learner's review queue. The caller commits."""
    results = list(results)
    if not results:
        return
    ids = {item_id for item_id, _, _ in results}
    existing = {
        item.item_id: item
        for item in await db.scalars(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id, ReviewItem.kind == kind, ReviewItem.item_id.in_(ids)
            )
        )
    }
    for item_id, correct, at in sorted(results, key=lambda r: r[2]):
        item = existing.get(item_id)
        if not correct:
            if item is None:
                item = ReviewItem(user_id=user_id, kind=kind, item_id=item_id, box=1, lapses=0, created_at=at)
                db.add(item)
                existing[item_id] = item
            else:
                item.box = 1
                item.lapses += 1
                item.mastered_at = None
            item.due_at = due_date(1, at)
            item.last_reviewed_at = at
        elif item is not None and item.mastered_at is None and item.due_at <= at:
            if item.box >= LAST_BOX:
                item.mastered_at = at
            else:
                item.box += 1
                item.due_at = due_date(item.box, at)
            item.last_reviewed_at = at


async def record_questions(db: AsyncSession, user_id, results: Iterable[tuple[int, bool, datetime]]) -> None:
    await record(db, user_id, KIND_QUESTION, ((str(qid), ok, at) for qid, ok, at in results))


async def due_items(db: AsyncSession, user_id, content: ContentStore, limit: int) -> list[ReviewItem]:
    """Due items, oldest first, skipping questions or signs that no longer exist."""
    now = utcnow()
    rows = await db.scalars(
        select(ReviewItem)
        .where(ReviewItem.user_id == user_id, ReviewItem.mastered_at.is_(None), ReviewItem.due_at <= now)
        .order_by(ReviewItem.due_at, ReviewItem.box)
    )
    items = []
    for item in rows:
        if item.kind == KIND_QUESTION:
            question = content.questions.get(int(item.item_id))
            if question is None or not question.active:
                continue
        elif item.kind != KIND_SIGN or item.item_id not in content.signs_by_id:
            continue
        items.append(item)
        if len(items) == limit:
            break
    return items


async def summary(db: AsyncSession, user_id) -> ReviewSummaryOut:
    now = utcnow()
    open_items = (ReviewItem.user_id == user_id, ReviewItem.mastered_at.is_(None))
    due_by_kind = dict(
        (
            await db.execute(
                select(ReviewItem.kind, func.count())
                .where(*open_items, ReviewItem.due_at <= now)
                .group_by(ReviewItem.kind)
            )
        ).all()
    )
    learning = await db.scalar(select(func.count()).select_from(ReviewItem).where(*open_items)) or 0
    mastered = (
        await db.scalar(
            select(func.count())
            .select_from(ReviewItem)
            .where(ReviewItem.user_id == user_id, ReviewItem.mastered_at.is_not(None))
        )
        or 0
    )
    next_due = await db.scalar(select(func.min(ReviewItem.due_at)).where(*open_items, ReviewItem.due_at > now))
    per_box = dict(
        (await db.execute(select(ReviewItem.box, func.count()).where(*open_items).group_by(ReviewItem.box))).all()
    )
    due_questions = due_by_kind.get(KIND_QUESTION, 0)
    due_signs = due_by_kind.get(KIND_SIGN, 0)
    return ReviewSummaryOut(
        due=due_questions + due_signs,
        due_questions=due_questions,
        due_signs=due_signs,
        learning=learning,
        mastered=mastered,
        next_due_at=next_due,
        boxes=[per_box.get(box, 0) for box in INTERVAL_DAYS],
    )
