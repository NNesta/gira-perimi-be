"""Achievement badges ("ibihembo"), worked out from what the learner has already done: nothing extra is stored."""

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import User
from app.schemas.progress import BadgeOut, BadgesOut
from app.services import progress
from app.services.content import ContentStore
from app.services.practice import answer_history

EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


async def badges(db: AsyncSession, user: User, content: ContentStore) -> BadgesOut:
    exams = await progress.completed_exams(db, user.id)
    scores = [e.score or 0 for e in exams]
    days = await progress.active_days(db, user.id, since=date(2000, 1, 1))
    longest = progress.longest_streak(days)
    answered = (await progress.answered_since(db, EPOCH, [user.id])).get(user.id, 0)
    core = [lesson["slug"] for lesson in content.core_lessons]
    lessons = len(set(await progress.lesson_slugs(db, user.id)) & set(core))
    sign_questions = set(content.ids_by_topic["ibyapa"])
    signs_right = len({qid for qid, ok, _ in await answer_history(db, user) if ok and qid in sign_questions})
    questions, pass_mark = settings.EXAM_QUESTION_COUNT, settings.EXAM_PASS_MARK

    rows = [
        ("ikizamini-cya-mbere", "Ikizamini cya mbere", "Kora ikizamini cy’igerageza cya mbere.", len(exams), 1),
        (
            "natsinze",
            "Natsinze",
            f"Tsinda ikizamini cy’igerageza (nibura {pass_mark}/{questions}).",
            int(any(s >= pass_mark for s in scores)),
            1,
        ),
        ("ibizamini-10", "Ibizamini 10", "Kora ibizamini 10 by’igerageza.", len(exams), 10),
        (
            "amanota-yose",
            "Amanota yose",
            f"Bona {questions}/{questions} mu kizamini cy’igerageza.",
            int(any(e.score == e.total for e in exams)),
            1,
        ),
        (
            "witeguye",
            "Witeguye",
            f"Kora ibizamini birenga {settings.READINESS_MIN_EXAMS}, impuzandengo y’ibizamini "
            f"{settings.READINESS_RECENT_EXAMS} biheruka irenga {settings.READINESS_MIN_AVERAGE:g}/{questions}.",
            int(progress.readiness(progress.readiness_scores(exams)).ready),
            1,
        ),
        ("iminsi-3", "Iminsi 3", "Iga iminsi 3 ikurikiranye.", longest, 3),
        ("iminsi-7", "Icyumweru cyose", "Iga iminsi 7 ikurikiranye.", longest, 7),
        ("iminsi-30", "Ukwezi kose", "Iga iminsi 30 ikurikiranye.", longest, 30),
        ("ibibazo-100", "Ibibazo 100", "Subiza ibibazo 100.", answered, 100),
        ("ibibazo-1000", "Ibibazo 1000", "Subiza ibibazo 1000.", answered, 1000),
        (
            "ibyapa-byose",
            "Ibyapa byose",
            f"Subiza neza, nibura rimwe, ibibazo {len(sign_questions)} byose by’ibyapa.",
            signs_right,
            len(sign_questions),
        ),
        ("amasomo-yose", "Amasomo yose", f"Soma amasomo {len(core)} yose.", lessons, len(core)),
    ]
    items = [
        BadgeOut(
            id=id_, title=title, description=text, earned=current >= target, current=min(current, target), target=target
        )
        for id_, title, text, current, target in rows
    ]
    return BadgesOut(earned=sum(b.earned for b in items), total=len(items), items=items)
