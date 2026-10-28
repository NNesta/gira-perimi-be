"""Daily copies of the SQLite database, so a bad deploy or a broken migration never costs learners their progress.

SQLite's online backup API copies the file safely while the site keeps writing to it (WAL included). Each copy is
checked with `PRAGMA integrity_check`, gzipped, and named after the Kigali day. Every copy from the last
BACKUP_KEEP_DAYS days is kept, plus the first copy of each of the last BACKUP_KEEP_MONTHS months.
"""

import gzip
import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings

NAME = re.compile(r"^tsinda-neza-(\d{4}-\d{2}-\d{2})\.db\.gz$")


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Backup:
    path: Path
    day: date
    size: int


def database_path(url: str | None = None) -> Path:
    parsed = make_url(url or settings.DATABASE_URL)
    if not parsed.drivername.startswith("sqlite") or parsed.database in (None, "", ":memory:"):
        raise BackupError("Backups only cover a SQLite database file.")
    return Path(parsed.database)


def list_backups(folder: Path | None = None) -> list[Backup]:
    folder = folder or settings.BACKUP_DIR
    if not folder.is_dir():
        return []
    found = []
    for path in folder.iterdir():
        if match := NAME.match(path.name):
            found.append(Backup(path, date.fromisoformat(match.group(1)), path.stat().st_size))
    return sorted(found, key=lambda b: b.day)


def backup(day: date, source: Path | None = None, folder: Path | None = None) -> Backup:
    """Writes today's copy (replacing an earlier one from the same day) and returns it."""
    source = source or database_path()
    folder = folder or settings.BACKUP_DIR
    if not source.is_file():
        raise BackupError(f"No database file at {source}")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"tsinda-neza-{day.isoformat()}.db.gz"
    raw = folder / f".{target.name}.db.tmp"
    packed = folder / f".{target.name}.tmp"
    try:
        with closing(sqlite3.connect(source)) as live, closing(sqlite3.connect(raw)) as copy:
            live.backup(copy)
            result = copy.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise BackupError(f"The copy failed its integrity check: {result}")
        with raw.open("rb") as plain, gzip.open(packed, "wb", compresslevel=6) as zipped:
            shutil.copyfileobj(plain, zipped)
        packed.replace(target)  # atomic: a half-written file never takes the place of a good one
    finally:
        raw.unlink(missing_ok=True)
        packed.unlink(missing_ok=True)
    return Backup(target, day, target.stat().st_size)


def prune(today: date, folder: Path | None = None) -> list[Backup]:
    """Deletes the copies outside the retention rules and returns them."""
    copies = list_backups(folder)
    keep = {b.path for b in copies if (today - b.day).days < settings.BACKUP_KEEP_DAYS}
    months = set()
    year, month = today.year, today.month
    for _ in range(settings.BACKUP_KEEP_MONTHS):
        months.add((year, month))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    first_of_month: dict[tuple[int, int], Backup] = {}
    for b in copies:  # oldest first
        first_of_month.setdefault((b.day.year, b.day.month), b)
    keep |= {b.path for key, b in first_of_month.items() if key in months}
    removed = [b for b in copies if b.path not in keep]
    for b in removed:
        b.path.unlink(missing_ok=True)
    return removed
