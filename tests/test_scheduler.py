import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.backup import backup_database
from ofertinhas.scheduler import build_scheduler, guarded
from ofertinhas.winops import keep_awake

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)


class Notes:
    def __init__(self):
        self.sent = []

    async def __call__(self, text):
        self.sent.append(text)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


async def test_guarded_job_swallows_errors_and_warns_once(conn):
    notes = Notes()
    clock = {"now": NOW}

    async def broken():
        raise RuntimeError("explodiu")

    job = guarded("publish", broken, conn, notes, lambda: clock["now"])
    await job()
    await job()
    assert len(notes.sent) == 1 and "publish" in notes.sent[0] and "explodiu" in notes.sent[0]
    clock["now"] = NOW + timedelta(minutes=31)
    await job()
    assert len(notes.sent) == 2


async def test_guarded_job_runs_normally(conn):
    calls = []

    async def ok():
        calls.append(1)

    await guarded("x", ok, conn, Notes(), lambda: NOW)()
    assert calls == [1]


def test_build_scheduler_registers_every_job(conn):
    async def noop():
        pass

    scheduler = build_scheduler(
        {"notify_pending": noop, "render": noop, "publish": noop, "expire": noop, "backup": noop},
        conn, Notes(), lambda: NOW,
    )
    assert {j.id for j in scheduler.get_jobs()} == {
        "notify_pending", "render", "publish", "expire", "backup",
    }


def test_backup_rotates_keeping_seven(tmp_path):
    source = tmp_path / "ofertinhas.db"
    conn = db.connect(source)
    backups = tmp_path / "backups"
    for day in range(10):
        backup_database(conn, backups, datetime(2026, 10, 1 + day, tzinfo=UTC))
    files = sorted(p.name for p in backups.iterdir())
    assert len(files) == 7
    assert files[-1] == "ofertinhas-20261010.db"
    restored = sqlite3.connect(backups / files[-1])
    assert restored.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    restored.close()
    conn.close()


def test_keep_awake_uses_windows_flags():
    calls = []
    keep_awake(True, set_state=calls.append)
    keep_awake(False, set_state=calls.append)
    assert calls == [0x80000000 | 0x00000001, 0x80000000]
