import logging
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)


def create_engine(url: str = settings.DATABASE_URL) -> AsyncEngine:
    engine = create_async_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


async def leave_wal(engine: AsyncEngine) -> None:
    """Moves an SQLite database out of WAL mode, which earlier versions turned on, to the classic rollback journal.

    WAL keeps its index in memory shared by every process using the file, so they must all run on one machine. On
    PythonAnywhere the website, consoles and scheduled tasks run on different machines over a network filesystem: under
    WAL, a migration run from a console can stay invisible to the website. Leaving WAL needs every other connection
    closed; while one is open the database stays in WAL, and the next start tries again.
    """
    if engine.url.get_backend_name() != "sqlite":
        return
    async with engine.connect() as conn:
        if await conn.scalar(text("PRAGMA journal_mode")) != "wal":
            return
        try:
            await conn.exec_driver_sql("PRAGMA journal_mode=DELETE")
        except OperationalError:
            logger.warning(
                "%s is still in WAL mode: another process has it open. Stop the website, then reload it.",
                engine.url.database,
            )


engine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
