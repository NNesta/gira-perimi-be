"""Phone notifications (Web Push), delivered by each browser's own push service: free, no SMS.

Android browsers show them like any app notification; on an iPhone (iOS 16.4+) only once the site is installed on the
home screen. Requests go through OUTBOUND_PROXY when one is set (PythonAnywhere free accounts).
"""

import json
import logging
from functools import lru_cache
from typing import Literal

import anyio
import requests
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utcnow
from app.models import PushSubscription

logger = logging.getLogger(__name__)

# A reminder that has waited this long on the push service (phone off, no network) is no longer worth showing.
TTL_SECONDS = 6 * 60 * 60
# The push service answers 404/410 once the browser has dropped the subscription (site data cleared, app removed).
GONE = {404, 410}

Result = Literal["sent", "gone", "failed"]


@lru_cache
def _vapid(private_key: str) -> Vapid01:
    return Vapid01.from_string(private_key)


def _session() -> requests.Session:
    session = requests.Session()
    if settings.OUTBOUND_PROXY:
        session.proxies.update({"http": settings.OUTBOUND_PROXY, "https": settings.OUTBOUND_PROXY})
    return session


def _send(subscription: dict, payload: str, session: requests.Session) -> Result:
    """Blocking: run it in a thread."""
    try:
        webpush(
            subscription,
            data=payload,
            vapid_private_key=_vapid(settings.VAPID_PRIVATE_KEY),
            vapid_claims={"sub": settings.vapid_subject},
            ttl=TTL_SECONDS,
            timeout=20,
            requests_session=session,
        )
    except WebPushException as exc:
        if getattr(exc.response, "status_code", None) in GONE:
            return "gone"
        logger.warning("Push to %s failed: %s", subscription["endpoint"][:60], exc)
        return "failed"
    except requests.RequestException as exc:
        logger.warning("Push to %s failed: %s", subscription["endpoint"][:60], exc)
        return "failed"
    return "sent"


async def notify(db: AsyncSession, user_id, message: dict) -> int:
    """Sends `message` ({title, body, url, tag}) to each of the learner's devices and returns how many got it.

    Devices the push service reports as gone are forgotten.
    """
    subscriptions = list(await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)))
    if not subscriptions:
        return 0
    payload = json.dumps(message, ensure_ascii=False)
    session = _session()
    results = await anyio.to_thread.run_sync(lambda: [_send(s.info, payload, session) for s in subscriptions])
    now = utcnow()
    for subscription, result in zip(subscriptions, results, strict=True):
        if result == "gone":
            await db.delete(subscription)
        elif result == "sent":
            subscription.last_sent_at = now
    await db.commit()
    return results.count("sent")
