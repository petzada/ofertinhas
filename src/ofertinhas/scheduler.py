"""Jobs periódicos do backend, cada um isolado: se um falha, os outros seguem."""

import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .alerts import notify_throttled

log = logging.getLogger(__name__)
ERROR_ALERT_EVERY = timedelta(minutes=30)

# id → gatilho do APScheduler
TRIGGERS = {
    "notify_pending": {"trigger": "interval", "minutes": 1},
    "render": {"trigger": "interval", "minutes": 1},
    "publish": {"trigger": "interval", "minutes": 1},
    "expire": {"trigger": "interval", "minutes": 15},
    "backup": {"trigger": "cron", "hour": 4, "minute": 0},
}


def guarded(
    name: str,
    job: Callable[[], Awaitable[object]],
    conn: sqlite3.Connection,
    notify: Callable[[str], Awaitable[None]],
    clock: Callable[[], datetime],
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        try:
            await job()
        except Exception as e:  # um job com erro não pode derrubar o processo
            log.exception("job %s falhou", name)
            await notify_throttled(
                conn, notify, f"job:{name}", f"⚠️ Erro no job {name}: {e}", clock(),
                ERROR_ALERT_EVERY,
            )

    return run


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
            max_instances=1,
            coalesce=True,
            **TRIGGERS[name],
        )
    return scheduler
