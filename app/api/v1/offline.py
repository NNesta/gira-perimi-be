from fastapi import APIRouter

from app.core.deps import DB, Content, PaidUser
from app.schemas.content import TopicOut
from app.schemas.offline import OfflinePackOut
from app.services import explanations
from app.services.practice import questions_out

router = APIRouter(prefix="/offline", tags=["offline"])


@router.get("/pack")
async def offline_pack(db: DB, _: PaidUser, content: Content) -> OfflinePackOut:
    """Every active question with its answer and explanation, so the app can run practice without a connection."""
    edited = await explanations.last_edit(db)
    version = content.version + (f"-{int(edited.timestamp())}" if edited else "")
    return OfflinePackOut(
        version=version,
        topics=[TopicOut(**t) for t in content.topic_list()],
        questions=await questions_out(db, content, content.active_ids),
    )
