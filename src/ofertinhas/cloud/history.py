"""Importação do histórico do banco local para a nuvem, na virada.

Vão só as ofertas postadas ou rejeitadas ainda em cooldown (para não repostar), os posts
recentes e as cotas (para o ritmo e os limites do dia continuarem de onde pararam) e os
ajustes feitos pelo bot (`/pausar`, `/peso`, `/corte`). Reimportar não duplica.

As decisões locais (postada/rejeitada) substituem a da nuvem para a mesma oferta e nicho: a
nuvem pode já ter ranqueado de novo uma oferta que o PC postou há poucos dias.
"""

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

TABLES = ("offers", "candidates", "posts", "settings")  # ofertas antes, pelas chaves estrangeiras
SETTINGS_PREFIXES = ("override:", "quota:")
IDENT = re.compile(r"[a-z_][a-z0-9_]*")


def export_rows(conn: sqlite3.Connection, now: datetime, days: int = 8) -> dict[str, list[dict]]:
    since = (now - timedelta(days=days)).isoformat()
    candidates = conn.execute(
        "SELECT * FROM candidates WHERE state IN ('posted', 'rejected') AND decided_at >= ?",
        (since,),
    ).fetchall()
    ids = sorted({c["mlb_id"] for c in candidates})
    marks = ", ".join("?" for _ in ids)
    offers = conn.execute(f"SELECT * FROM offers WHERE mlb_id IN ({marks})", ids).fetchall()
    posts = conn.execute("SELECT * FROM posts WHERE sent_at >= ?", (since,)).fetchall()
    settings = [r for r in conn.execute("SELECT * FROM settings")
                if r["key"].startswith(SETTINGS_PREFIXES)]
    return {name: [dict(r) for r in rows]
            for name, rows in zip(TABLES, (offers, candidates, posts, settings), strict=True)}


def import_rows(conn, data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    counts = {}
    for table in TABLES:
        inserted = 0
        for row in data.get(table) or []:
            cols = list(row)
            if not cols or not all(IDENT.fullmatch(c) for c in cols):
                raise ValueError(f"coluna inválida em {table}: {cols}")
            before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            verb = "INSERT OR REPLACE" if table == "candidates" else "INSERT OR IGNORE"
            conn.execute(
                f"{verb} INTO {table} ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols],
            )
            after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            inserted += after - before if verb == "INSERT OR IGNORE" else 1
        counts[table] = inserted
    return counts
