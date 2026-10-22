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
    backup = scheduler.get_job("backup").trigger.triggers[0]
    assert str(backup.fields[5]) == "4" and str(backup.fields[6]) == "0"  # 04:00


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


def test_wake_tasks_wake_the_pc_and_run_the_session():
    from pathlib import PureWindowsPath  # caminho do Windows também no CI (Linux)

    from ofertinhas.winops import wake_tasks_script

    script = wake_tasks_script(PureWindowsPath(r"C:\p\.venv\Scripts\python.exe"),
                               PureWindowsPath(r"C:\p"), ["05:30", "17:00"], 45, 120)
    assert r"'C:\p\.venv\Scripts\pythonw.exe'" in script
    assert "'-m ofertinhas wake-session --minutes 45 --max-minutes 120'" in script
    assert "-ExecutionTimeLimit (New-TimeSpan -Minutes 135)" in script
    assert "-WakeToRun" in script and "-StartWhenAvailable" in script
    assert "-TaskName 'Ofertinhas coleta 05h30'" in script
    assert "-Daily -At '17:00'" in script


def test_wake_session_holds_while_the_cloud_is_busy():
    from ofertinhas.winops import hold_awake

    slept, states, answers = [], [], iter([True, True, False])
    total = hold_awake(45, 120, lambda: next(answers), sleep=slept.append, awake=states.append)
    assert total == 55 and slept == [45 * 60, 300, 300] and states == [True, False]


def test_wake_session_stops_at_the_ceiling():
    from ofertinhas.winops import hold_awake

    slept = []
    total = hold_awake(45, 52, lambda: True, sleep=slept.append, awake=lambda _: None)
    assert total == 52 and slept == [45 * 60, 300, 120]


def test_cloud_busy_reads_the_stock(tmp_path):
    import json
    from types import SimpleNamespace

    from ofertinhas.winops import cloud_busy

    conf = tmp_path / "config.local.json"
    conf.write_text(json.dumps({"backendUrl": "https://x.dev/", "token": "t"}), encoding="utf-8")
    calls = []

    def get(url, headers, timeout):
        calls.append((url, headers))
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"collect_now": False, "waiting_links": 3})

    assert cloud_busy(conf, get) is True
    assert calls == [("https://x.dev/ext/stock", {"X-Ofertinhas-Token": "t"})]
    assert cloud_busy(tmp_path / "nao-existe.json", get) is False
