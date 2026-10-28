from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.models import PushSubscription
from app.schemas.push import PushEndpointIn, PushSubscriptionIn, PushTestOut
from app.services import push as push_service

router = APIRouter(prefix="/push", tags=["push"])

NOT_SET_UP = "Imenyesha kuri telefoni ntiriratunganywa kuri uru rubuga."


def _require_push() -> None:
    if not settings.push_available:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_SET_UP)


@router.put("/subscription", status_code=status.HTTP_204_NO_CONTENT)
async def save_subscription(body: PushSubscriptionIn, db: DB, user: CurrentUser) -> None:
    """Remembers this browser for the daily reminder. Sent again whenever the profile page loads (idempotent)."""
    _require_push()
    record = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if record is None:
        db.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth))
    else:
        record.user_id, record.p256dh, record.auth = user.id, body.keys.p256dh, body.keys.auth
    await db.commit()


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def forget_subscription(body: PushEndpointIn, db: DB, user: CurrentUser) -> None:
    await db.execute(
        delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id)
    )
    await db.commit()


@router.post("/test")
async def send_test(db: DB, user: CurrentUser) -> PushTestOut:
    """Sends a sample notification to each of the learner's devices, so they can see it works."""
    _require_push()
    sent = await push_service.notify(
        db,
        user.id,
        {
            "title": "Tsinda Neza",
            "body": "Imenyesha rirakora! Tuzakwibutsa kwiga buri mugoroba utarageza ku ntego yawe.",
            "url": "/umwirondoro",
            "tag": "test",
        },
    )
    return PushTestOut(sent=sent)
