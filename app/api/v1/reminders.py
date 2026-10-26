from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import DB
from app.core.security import decode_token
from app.models import User

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(db: DB, token: str = Query(min_length=20, max_length=1024)) -> None:
    """One-click unsubscribe from reminder emails (RFC 8058). The signed token can only switch reminders off."""
    user_id = decode_token(token, "unsubscribe")
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Iyi link ntikiri ku gihe. Hagarika kwibutswa mu mwirondoro wawe."
        )
    user.reminders = False
    await db.commit()
