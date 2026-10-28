from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DEV_SECRET = "dev-only-change-me-0123456789abcdef0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Tsinda Neza API"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'gira_perimi.db'}"
    MEDIA_DIR: Path = BASE_DIR / "media"

    # Auth
    SECRET_KEY: str = DEV_SECRET
    USER_SESSION_DAYS: int = 30
    ADMIN_SESSION_HOURS: int = 8
    GOOGLE_CLIENT_ID: str = ""
    # HTTP proxy for the API's own outbound calls (downloading Google's token-signing keys). Needed on hosts that only
    # allow the internet through a proxy, e.g. PythonAnywhere free accounts: http://proxy.server:3128
    OUTBOUND_PROXY: str = ""
    COOKIE_SECURE: bool = False
    FRONTEND_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    ADMIN_LOGIN_MAX_ATTEMPTS: int = 5
    ADMIN_LOGIN_WINDOW_SECONDS: int = 15 * 60

    # Exam rules (mirrors the Rwanda National Police provisional test)
    EXAM_QUESTION_COUNT: int = 20
    EXAM_DURATION_MINUTES: int = 20
    EXAM_PASS_MARK: int = 12
    EXAM_GRACE_SECONDS: int = 15

    # A learner is recommended for the real exam after MORE than READINESS_MIN_EXAMS
    # completed exams with an average strictly ABOVE READINESS_MIN_AVERAGE (out of 20).
    READINESS_MIN_EXAMS: int = 10
    READINESS_MIN_AVERAGE: float = 15.0

    # Future subscriptions: when enabled, practice/exams/premium lessons require an active plan.
    PAYWALL_ENABLED: bool = False

    # Study plan: questions a learner aims to answer each day unless they choose another goal.
    DEFAULT_DAILY_GOAL: int = 20

    # Daily reminder emails (opt-in). Sent by `python -m app.cli send-reminders`, run once a day by a scheduler.
    # Leave SMTP_HOST empty to switch reminders off; learners then never see the option.
    SITE_URL: str = "http://localhost:3000"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # Phone notifications (Web Push): free, sent through the browser's own push service. Generate the key pair once
    # with `python -m app.cli vapid-keys`; leave them empty to switch phone notifications off. VAPID_SUBJECT is a
    # contact for the push services ("mailto:you@example.com" or the site's https address).
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = ""

    # Daily backups of the SQLite database (`python -m app.cli daily`, or `backup` on its own): gzip copies kept in
    # BACKUP_DIR. Every copy from the last BACKUP_KEEP_DAYS days is kept, plus the first copy of each of the last
    # BACKUP_KEEP_MONTHS months.
    BACKUP_DIR: Path = BASE_DIR / "backups"
    BACKUP_KEEP_DAYS: int = 14
    BACKUP_KEEP_MONTHS: int = 6

    # Error alerts with Sentry (sentry.io, free plan): the project's DSN, or empty to switch alerts off.
    SENTRY_DSN: str = ""

    # "Watsinze ikizamini?": the real-exam pass rate is published once this many learners have answered.
    OUTCOME_MIN_ANSWERS: int = 10

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == DEV_SECRET or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters in production")
            self.COOKIE_SECURE = True
        return self

    @property
    def reminders_available(self) -> bool:
        """Reminder emails can be sent."""
        return bool(self.SMTP_HOST and self.SMTP_FROM)

    @property
    def push_available(self) -> bool:
        """Phone notifications can be sent."""
        return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)

    @property
    def vapid_subject(self) -> str:
        return self.VAPID_SUBJECT or self.SITE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
