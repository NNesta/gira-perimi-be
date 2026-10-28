import gzip
import sqlite3
from datetime import date, timedelta

import pytest

from app import cli
from app.core.config import settings
from app.services import backups


@pytest.fixture
def live_db(tmp_path, monkeypatch):
    """A small SQLite file standing in for the site's database, and a backup folder."""
    path = tmp_path / "site.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE learners (name TEXT)")
        db.executemany("INSERT INTO learners VALUES (?)", [("Keza",), ("Mugisha",)])
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    monkeypatch.setattr(settings, "BACKUP_DIR", tmp_path / "backups")
    return path


def test_database_path_only_for_sqlite():
    assert str(backups.database_path("sqlite+aiosqlite:////srv/app.db")) == "/srv/app.db"
    with pytest.raises(backups.BackupError):
        backups.database_path("postgresql+psycopg://u:p@db/app")


def test_backup_is_a_complete_compressed_copy(live_db, tmp_path):
    day = date(2026, 10, 27)
    made = backups.backup(day)
    assert made.path.name == "tsinda-neza-2026-10-27.db.gz" and made.size > 0

    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(made.path.read_bytes()))
    with sqlite3.connect(restored) as db:
        assert [r[0] for r in db.execute("SELECT name FROM learners ORDER BY name")] == ["Keza", "Mugisha"]

    with sqlite3.connect(live_db) as db:
        db.execute("INSERT INTO learners VALUES ('Aline')")
    backups.backup(day)  # same day: replaced, not duplicated
    assert [b.day for b in backups.list_backups()] == [day]
    assert not list(settings.BACKUP_DIR.glob(".*"))  # no temporary files left behind


def test_missing_database_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'nope.db'}")
    with pytest.raises(backups.BackupError):
        backups.backup(date(2026, 10, 27), folder=tmp_path)


def test_prune_keeps_recent_days_and_one_copy_per_month(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_KEEP_DAYS", 3)
    monkeypatch.setattr(settings, "BACKUP_KEEP_MONTHS", 2)
    today = date(2026, 10, 27)
    days = [today - timedelta(days=n) for n in range(70)]  # 27 Oct back to 19 Aug
    for day in days:
        (tmp_path / f"tsinda-neza-{day.isoformat()}.db.gz").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not a backup")

    removed = backups.prune(today, tmp_path)
    kept = sorted(b.day.isoformat() for b in backups.list_backups(tmp_path))
    assert kept == ["2026-09-01", "2026-10-01", "2026-10-25", "2026-10-26", "2026-10-27"]
    assert len(removed) == 70 - 5 and (tmp_path / "notes.txt").exists()


async def test_daily_task_backs_up_even_with_reminders_off(live_db, capsys):
    await cli.daily()  # reminders are off in tests: only the backup runs, and it succeeds
    out = capsys.readouterr().out
    assert "Backup:" in out and "Reminders are off" in out
    assert len(backups.list_backups()) == 1


async def test_daily_task_reports_a_failed_backup(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gone.db'}")
    monkeypatch.setattr(settings, "BACKUP_DIR", tmp_path / "backups")
    with pytest.raises(SystemExit) as exit_:
        await cli.daily()
    assert exit_.value.code == 1 and "Backup FAILED" in capsys.readouterr().err
