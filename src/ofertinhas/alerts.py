"""Avisos ao admin sem repetir o mesmo assunto a todo momento."""

import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from . import db


async def notify_throttled(
    conn: sqlite3.Connection,
    notify: Callable[[str], Awaitable[None]],
    key: str,
    text: str,
    now: datetime,
    every: timedelta,
) -> bool:
    """Envia `text` se o assunto `key` não foi avisado no último `every`."""
    last = db.get_setting(conn, f"alert:{key}")
    if last and now - datetime.fromisoformat(last) < every:
        return False
    db.set_setting(conn, f"alert:{key}", now.isoformat())
    await notify(text)
    return True
