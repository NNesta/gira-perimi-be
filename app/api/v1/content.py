from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import DB, Content, OptionalUser, PaidUser, has_access
from app.models import LessonProgress
from app.schemas.content import (
    ExamRulesOut,
    LessonNavOut,
    LessonOut,
    LessonSummaryOut,
    OverviewOut,
    QuestionSearchOut,
    QuestionWithAnswerOut,
    SignCategoryOut,
    SignOut,
    SignsOut,
    TopicOut,
)
from app.services.content import TOPIC_IDS
from app.services.practice import questions_out

router = APIRouter(tags=["content"])

SEARCH_LIMIT = 30


async def _completed_slugs(db: DB, user: OptionalUser) -> set[str]:
    if user is None:
        return set()
    return set(await db.scalars(select(LessonProgress.lesson_slug).where(LessonProgress.user_id == user.id)))


@router.get("/overview")
async def overview(content: Content) -> OverviewOut:
    return OverviewOut(
        questions=len(content.active_ids),
        lessons=len(content.lessons),
        signs=len(content.signs),
        topics=len(content.topic_list()),
        exam=ExamRulesOut(
            question_count=settings.EXAM_QUESTION_COUNT,
            duration_minutes=settings.EXAM_DURATION_MINUTES,
            pass_mark=settings.EXAM_PASS_MARK,
            readiness_min_exams=settings.READINESS_MIN_EXAMS,
            readiness_min_average=settings.READINESS_MIN_AVERAGE,
        ),
    )


@router.get("/questions/search")
async def search_questions(
    db: DB,
    _user: PaidUser,
    content: Content,
    q: str = Query(min_length=1, max_length=100),
    topic: str | None = None,
) -> QuestionSearchOut:
    """Searches the whole bank: question, answers and explanation. Signed-in learners only, as results show answers."""
    if topic is not None and topic not in TOPIC_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iyo nsanganyamatsiko ntibaho.")
    ids = content.search(q, topic)
    return QuestionSearchOut(total=len(ids), items=await questions_out(db, content, ids[:SEARCH_LIMIT]))


@router.get("/topics")
async def topics(content: Content) -> list[TopicOut]:
    return [TopicOut(**t) for t in content.topic_list()]


@router.get("/lessons")
async def lessons(content: Content, db: DB, user: OptionalUser) -> list[LessonSummaryOut]:
    done = await _completed_slugs(db, user)
    unlocked = has_access(user)
    return [
        LessonSummaryOut(
            **{
                k: lesson[k]
                for k in ("slug", "order", "title", "summary", "icon", "topics", "minutes", "free", "question_count")
            },
            sections=[s["title"] for s in lesson["sections"]],
            completed=lesson["slug"] in done,
            locked=not (lesson["free"] or unlocked),
        )
        for lesson in content.lessons
    ]


@router.get("/lessons/{slug}")
async def lesson(slug: str, content: Content, db: DB, user: OptionalUser) -> LessonOut:
    data = content.lessons_by_slug.get(slug)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Iri somo ntiribonetse.")
    if not (data["free"] or has_access(user)):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Iri somo risaba ifatabuguzi rikiri ku gihe.")
    index = content.lessons.index(data)
    prev_lesson = content.lessons[index - 1] if index > 0 else None
    next_lesson = content.lessons[index + 1] if index + 1 < len(content.lessons) else None
    return LessonOut(
        **{k: v for k, v in data.items() if k in LessonOut.model_fields and k not in ("completed", "previous", "next")},
        completed=slug in await _completed_slugs(db, user),
        previous=LessonNavOut(slug=prev_lesson["slug"], title=prev_lesson["title"]) if prev_lesson else None,
        next=LessonNavOut(slug=next_lesson["slug"], title=next_lesson["title"]) if next_lesson else None,
    )


@router.get("/signs")
async def signs(content: Content) -> SignsOut:
    counts: dict[str, int] = {}
    for sign in content.signs:
        counts[sign["category"]] = counts.get(sign["category"], 0) + 1
    return SignsOut(
        categories=[SignCategoryOut(**c, count=counts.get(c["id"], 0)) for c in content.sign_categories],
        signs=[SignOut(**s) for s in content.signs],
    )


@router.get("/questions/sample")
async def sample_questions(content: Content, db: DB, count: int = Query(5, ge=1, le=10)) -> list[QuestionWithAnswerOut]:
    """A small public quiz for visitors (landing page demo). Answers are included: feedback is instant."""
    return await questions_out(db, content, content.draw_exam(count))
