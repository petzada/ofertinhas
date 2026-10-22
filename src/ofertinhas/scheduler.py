"""Jobs periódicos do backend, cada um isolado: se um falha, os outros seguem."""

import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .jobs import guarded

# id → gatilho do APScheduler
TRIGGERS = {
    "notify_pending": {"trigger": "interval", "minutes": 1},
    "render": {"trigger": "interval", "minutes": 1},
    "publish": {"trigger": "interval", "minutes": 1},
    "expire": {"trigger": "interval", "minutes": 15},
    "stock_alert": {"trigger": "interval", "minutes": 5},
    "backup": {"trigger": "cron", "hour": 4, "minute": 0},
}


def build_scheduler(
    jobs: dict[str, Callable[[], Awaitable[object]]],
    conn: sqlite3.Connection,
    notify: Callable[[str], Awaitable[None]],
    clock: Callable[[], datetime],
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    for name, job in jobs.items():
        scheduler.add_job(
            guarded(name, job, conn, notify, clock),
            id=name,
            name=name,
            max_instances=1,
            coalesce=True,
            **TRIGGERS[name],
        )
    return scheduler
