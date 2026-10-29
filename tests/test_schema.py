import re

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db.base import Base
from app.db.schema import MIGRATIONS, SchemaOutOfDate, check_schema
from app.db.session import create_engine

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
