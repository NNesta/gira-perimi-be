"""Error alerts with Sentry. Off unless SENTRY_DSN is set.

No personal data is sent: no cookies or user details (send_default_pii), no request bodies (the admin sign-in form,
Google credentials) and no local variables from the stack, where e-mail addresses could appear.
"""

import sentry_sdk

from app.core.config import settings


def init_sentry(component: str) -> bool:
    """Starts Sentry for the API or a CLI command. Unexpected errors (HTTP 500s, crashes) then reach the inbox."""
    if not settings.SENTRY_DSN:
        return False
    proxy = settings.OUTBOUND_PROXY or None  # PythonAnywhere free accounts reach the internet through a proxy
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.0,  # errors only: stays inside the free plan
        http_proxy=proxy,
        https_proxy=proxy,
    )
    sentry_sdk.set_tag("component", component)
    return True
