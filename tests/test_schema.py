import re
import sqlite3
from contextlib import closing

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from app.db.schema import MIGRATIONS, SchemaOutOfDate, check_schema
from app.db.session import create_engine, leave_wal

HEAD = ScriptDirectory(str(MIGRATIONS)).get_current_head()


@pytest.fixture
async def database(tmp_path):
    """Builds a database with the app's tables and, unless None, an Alembic version."""
    engines = []

    async def build(version: str | None, tables: bool = True):
        engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / f'schema{len(engines)}.db'}")
        engines.append(engine)
        async with engine.begin() as conn:
            if tables:
                await conn.run_sync(Base.metadata.create_all)
            if version is not None:
                await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                await conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": version})
        return engine

    yield build
    for engine in engines:
        await engine.dispose()


async def test_a_migrated_database_starts(database):
    await check_schema(await database(HEAD))


async def test_a_forgotten_migration_stops_the_api_with_the_command_to_run(database):
    engine = await database("0006")
    expected = rf"at migration 0006, but this code needs {HEAD}\..*alembic upgrade head"
    with pytest.raises(SchemaOutOfDate, match=expected):
        await check_schema(engine)


async def test_a_database_migrated_by_newer_code_is_refused(database):
    engine = await database("9999")
    with pytest.raises(SchemaOutOfDate, match=re.escape(f"(its newest is {HEAD})")):
        await check_schema(engine)


async def test_an_empty_database_is_refused(database):
    engine = await database(None, tables=False)
    with pytest.raises(SchemaOutOfDate, match="none \\(it is empty\\)"):
        await check_schema(engine)


async def test_databases_built_without_alembic_are_left_alone(database):
    """The tests and the screenshot demo build their tables directly: nothing to check."""
    await check_schema(await database(None))


async def test_a_database_stamped_without_migrating_is_refused(database):
    engine = await database(HEAD)
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users DROP COLUMN session_version"))
        await conn.execute(text("DROP TABLE email_logins"))
    with pytest.raises(SchemaOutOfDate, match=rf"at migration {HEAD}, but it lacks .*users\.session_version") as error:
        await check_schema(engine)
    assert "email_logins" in str(error.value) and "alembic stamp" in str(error.value)


def sqlite_file(path, journal_mode: str) -> str:
    with closing(sqlite3.connect(path)) as db:
        db.execute(f"PRAGMA journal_mode={journal_mode}")
        db.execute("CREATE TABLE learners (name TEXT)")
    return f"sqlite+aiosqlite:///{path}"


async def test_a_wal_database_moves_to_the_rollback_journal(tmp_path):
    engine = create_engine(sqlite_file(tmp_path / "wal.db", "WAL"))
    await leave_wal(engine)
    async with engine.connect() as conn:
        assert await conn.scalar(text("PRAGMA journal_mode")) == "delete"
    await engine.dispose()


async def test_a_wal_database_in_use_elsewhere_is_left_for_the_next_start(tmp_path, caplog):
    path = tmp_path / "busy.db"
    engine = create_async_engine(sqlite_file(path, "WAL"), connect_args={"timeout": 0.1})
    with closing(sqlite3.connect(path)) as other:
        other.execute("SELECT * FROM learners").fetchall()
        await leave_wal(engine)
    assert "still in WAL mode" in caplog.text
    async with engine.connect() as conn:
        assert await conn.scalar(text("PRAGMA journal_mode")) == "wal"
    await engine.dispose()
