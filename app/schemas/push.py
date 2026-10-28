from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

# Browsers' push services. The API only ever sends to these, so a forged subscription cannot make it call
# another address.
PUSH_HOSTS = ("fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com", "push.apple.com")


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=255)
    auth: str = Field(min_length=8, max_length=64)


class PushEndpointIn(BaseModel):
    endpoint: str = Field(max_length=1024)


class PushSubscriptionIn(PushEndpointIn):
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def _known_push_service(cls, value: str) -> str:
        url = urlparse(value)
        host = url.hostname or ""
        if url.scheme != "https" or not any(host == h or host.endswith("." + h) for h in PUSH_HOSTS):
            raise ValueError("Iyi browser ntishobora kwakira imenyesha rya Tsinda Neza.")
        return value


class PushTestOut(BaseModel):
    sent: int
