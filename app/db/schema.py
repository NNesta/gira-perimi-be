"""Start-up check that the database has exactly the migrations the code expects.

Without it, a forgotten `alembic upgrade head` after a deploy only shows up later, as "no such column" errors on
whichever request first touches a new column (Google sign-in, after 0008). With it, the API does not start, and its
error log says what to run.
"""

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import BASE_DIR
from app.db.base import Base

MIGRATIONS = BASE_DIR / "alembic"
MIGRATE = ".venv/bin/python -m app.cli backup && .venv/bin/alembic upgrade head"


class SchemaOutOfDate(RuntimeError):
    pass


def missing_columns(conn: Connection) -> list[str]:
    """The tables and columns the models use that the database lacks, e.g. ["users.session_version"]."""
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    missing = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            missing.append(table.name)
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{column.name}" for column in table.columns if column.name not in present]
    return missing


async def check_schema(engine: AsyncEngine) -> None:
    """Raises SchemaOutOfDate unless the database is at the code's newest migration and has every column it needs.

    A database built by `Base.metadata.create_all` (the tests, the demo database for screenshots) has tables but no
    alembic_version: Alembic does not manage it, so it is left alone.
    """
    database = engine.url.database
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        if "alembic_version" in tables:
            current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        elif tables:
            return
        else:
            current = None
        missing = await conn.run_sync(missing_columns)
    script = ScriptDirectory(str(MIGRATIONS))
    head = script.get_current_head()
    if current == head:
        if missing:
            raise SchemaOutOfDate(
                f"The database {database} says it is at migration {head}, but it lacks {', '.join(missing)}: its "
                "alembic_version was changed without running the migrations (alembic stamp?). Find the newest "
                "migration whose changes it really has (`.venv/bin/alembic history`), mark it with "
                f"`.venv/bin/alembic stamp <revision>`, then run: {MIGRATE}"
            )
        return
    if current is None or current in {rev.revision for rev in script.walk_revisions()}:
        raise SchemaOutOfDate(
            f"The database {database} is at migration {current or 'none (it is empty)'}, but this code needs {head}. "
            f"Back it up and migrate, then reload the API: {MIGRATE}"
        )
    raise SchemaOutOfDate(
        f"The database {database} is at migration {current}, which this code does not know (its newest is {head}): "
        "newer code migrated it. Deploy that code again, or restore the backup taken before that migration."
    )
