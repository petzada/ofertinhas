"""Jobs periódicos do backend no PC, nos horários do `SCHEDULE` (o mesmo da nuvem)."""

import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .jobs import SCHEDULE, At, Every, at_times, guarded

TIMEZONE = "America/Sao_Paulo"


def trigger(spec: Every | At):
    if isinstance(spec, Every):
        return IntervalTrigger(minutes=spec.minutes, timezone=TIMEZONE)
    return OrTrigger([CronTrigger(hour=t.hour, minute=t.minute, timezone=TIMEZONE)
                      for t in at_times(spec)])


def build_scheduler(
    jobs: dict[str, Callable[[], Awaitable[object]]],
    conn: sqlite3.Connection,
    notify: Callable[[str], Awaitable[None]],
    clock: Callable[[], datetime],
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    for name, job in jobs.items():
        scheduler.add_job(
            guarded(name, job, conn, notify, clock),
            id=name,
            name=name,
            max_instances=1,
            coalesce=True,
            trigger=trigger(SCHEDULE[name]),
        )
    return scheduler
