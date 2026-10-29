"""Start-up check that the database has exactly the migrations the code expects.

Without it, a forgotten `alembic upgrade head` after a deploy only shows up later, as "no such column" errors on
whichever request first touches a new column (Google sign-in, after 0008). With it, the API does not start, and its
error log says what to run.
"""

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import BASE_DIR

MIGRATIONS = BASE_DIR / "alembic"
MIGRATE = ".venv/bin/python -m app.cli backup && .venv/bin/alembic upgrade head"


class SchemaOutOfDate(RuntimeError):
    pass


async def check_schema(engine: AsyncEngine) -> None:
    """Raises SchemaOutOfDate unless the database is at the code's newest migration.

    A database built by `Base.metadata.create_all` (the tests, the demo database for screenshots) has tables but no
    alembic_version: Alembic does not manage it, so it is left alone.
    """
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        if "alembic_version" in tables:
            current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        elif tables:
            return
        else:
            current = None
    script = ScriptDirectory(str(MIGRATIONS))
    head = script.get_current_head()
    if current == head:
        return
    if current is None or current in {rev.revision for rev in script.walk_revisions()}:
        raise SchemaOutOfDate(
            f"The database is at migration {current or 'none (it is empty)'}, but this code needs {head}. "
            f"Back it up and migrate, then reload the API: {MIGRATE}"
        )
    raise SchemaOutOfDate(
        f"The database is at migration {current}, which this code does not know (its newest is {head}): newer code "
        "migrated it. Deploy that code again, or restore the backup taken before that migration."
    )
