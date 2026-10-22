"""Cópia diária do SQLite, mantendo os últimos 7 dias."""

import sqlite3
from datetime import datetime
from pathlib import Path

KEEP = 7


def backup_database(conn: sqlite3.Connection, folder: Path, now: datetime) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"ofertinhas-{now.strftime('%Y%m%d')}.db"
    copy = sqlite3.connect(target)
    try:
        conn.backup(copy)
    finally:
        copy.close()
    for old in sorted(folder.glob("ofertinhas-*.db"))[:-KEEP]:
        old.unlink()
    return target
