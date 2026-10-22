"""Persistência em SQLite.

Datas são gravadas em ISO 8601 em UTC, o que permite comparar como texto.
"""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import TZ, Candidate, CandidateState, Offer, utcnow

MIGRATIONS = [
    """
    CREATE TABLE offers (
        mlb_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        price REAL NOT NULL,
        original_price REAL,
        commission_pct REAL NOT NULL,
        category_path TEXT NOT NULL,
        permalink TEXT NOT NULL,
        image_url TEXT,
        rating REAL,
        sold_count INTEGER,
        free_shipping INTEGER NOT NULL DEFAULT 0,
        is_full INTEGER NOT NULL DEFAULT 0,
        collected_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        affiliate_link TEXT
    );
    CREATE TABLE price_history (
        mlb_id TEXT NOT NULL REFERENCES offers(mlb_id),
        price REAL NOT NULL,
        seen_at TEXT NOT NULL
    );
    CREATE INDEX price_history_mlb ON price_history(mlb_id, seen_at);
    CREATE TABLE candidates (
        mlb_id TEXT NOT NULL REFERENCES offers(mlb_id),
        niche TEXT NOT NULL,
        state TEXT NOT NULL,
        score REAL NOT NULL,
        breakdown_json TEXT NOT NULL,
        ref_price REAL NOT NULL,
        decided_at TEXT NOT NULL,
        caption TEXT,
        card_path TEXT,
        notified_at TEXT,
        PRIMARY KEY (mlb_id, niche)
    );
    CREATE INDEX candidates_state ON candidates(state, niche, score);
    CREATE TABLE posts (
        id INTEGER PRIMARY KEY,
        mlb_id TEXT NOT NULL,
        niche TEXT NOT NULL,
        channel TEXT NOT NULL,
        chat TEXT NOT NULL,
        status TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        message_id TEXT,
        price REAL,
        attempts INTEGER NOT NULL DEFAULT 1,
        error TEXT
    );
    CREATE INDEX posts_chat ON posts(chat, status, sent_at);
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL
    );
    CREATE TABLE template_usage (
        chat TEXT PRIMARY KEY,
        template_idx INTEGER NOT NULL,
        used_at TEXT NOT NULL
    );
    """,
]


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    # Um único processo asyncio usa a conexão; o servidor HTTP pode atendê-la de outra thread.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript(f"BEGIN; {script} PRAGMA user_version = {number}; COMMIT;")


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# --- ofertas ---------------------------------------------------------------


def upsert_offer(conn: sqlite3.Connection, offer: Offer, now: datetime | None = None) -> bool:
    """Grava a oferta e devolve True se ela é nova.

    Na atualização, preserva a data em que foi vista pela primeira vez e o link de afiliado.
    """
    now = now or utcnow()
    previous = conn.execute(
        "SELECT price FROM offers WHERE mlb_id = ?", (offer.mlb_id,)
    ).fetchone()
    fields = dict(
        title=offer.title,
        price=offer.price,
        original_price=offer.original_price,
        commission_pct=offer.commission_pct,
        category_path=json.dumps(list(offer.category_path)),
        permalink=offer.permalink,
        image_url=offer.image_url,
        rating=offer.rating,
        sold_count=offer.sold_count,
        free_shipping=int(offer.free_shipping),
        is_full=int(offer.full),
        updated_at=_ts(now),
    )
    with conn:
        if previous is None:
            fields |= dict(mlb_id=offer.mlb_id, collected_at=_ts(offer.collected_at))
            cols = ", ".join(fields)
            marks = ", ".join(f":{k}" for k in fields)
            conn.execute(f"INSERT INTO offers ({cols}) VALUES ({marks})", fields)
        else:
            sets = ", ".join(f"{k} = :{k}" for k in fields)
            conn.execute(
                f"UPDATE offers SET {sets} WHERE mlb_id = :mlb_id",
                fields | {"mlb_id": offer.mlb_id},
            )
        if previous is None or previous["price"] != offer.price:
            conn.execute(
                "INSERT INTO price_history (mlb_id, price, seen_at) VALUES (?, ?, ?)",
                (offer.mlb_id, offer.price, _ts(now)),
            )
    return previous is None


def _offer_from_row(row: sqlite3.Row) -> Offer:
    return Offer(
        mlb_id=row["mlb_id"],
        title=row["title"],
        price=row["price"],
        original_price=row["original_price"],
        commission_pct=row["commission_pct"],
        category_path=tuple(json.loads(row["category_path"])),
        permalink=row["permalink"],
        image_url=row["image_url"],
        rating=row["rating"],
        sold_count=row["sold_count"],
        free_shipping=bool(row["free_shipping"]),
        full=bool(row["is_full"]),
        collected_at=_dt(row["collected_at"]),
        affiliate_link=row["affiliate_link"],
    )


def get_offer(conn: sqlite3.Connection, mlb_id: str) -> Offer | None:
    row = conn.execute("SELECT * FROM offers WHERE mlb_id = ?", (mlb_id,)).fetchone()
    return _offer_from_row(row) if row else None


def get_offers(conn: sqlite3.Connection, mlb_ids: Iterable[str]) -> list[Offer]:
    ids = list(mlb_ids)
    if not ids:
        return []
    marks = ", ".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM offers WHERE mlb_id IN ({marks})", ids)
    by_id = {r["mlb_id"]: _offer_from_row(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def set_affiliate_link(conn: sqlite3.Connection, mlb_id: str, link: str) -> None:
    with conn:
        conn.execute("UPDATE offers SET affiliate_link = ? WHERE mlb_id = ?", (link, mlb_id))


# --- candidatos ------------------------------------------------------------


def _candidate_from_row(row: sqlite3.Row) -> Candidate:
    return Candidate(
        mlb_id=row["mlb_id"],
        niche=row["niche"],
        state=CandidateState(row["state"]),
        score=row["score"],
        breakdown=json.loads(row["breakdown_json"]),
        ref_price=row["ref_price"],
        decided_at=_dt(row["decided_at"]),
        caption=row["caption"],
        card_path=row["card_path"],
        notified_at=_dt(row["notified_at"]),
    )


def save_candidate(conn: sqlite3.Connection, cand: Candidate) -> None:
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO candidates
                (mlb_id, niche, state, score, breakdown_json, ref_price, decided_at,
                 caption, card_path, notified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cand.mlb_id,
                cand.niche,
                cand.state.value,
                cand.score,
                json.dumps(cand.breakdown),
                cand.ref_price,
                _ts(cand.decided_at),
                cand.caption,
                cand.card_path,
                _ts(cand.notified_at) if cand.notified_at else None,
            ),
        )


def get_candidate(conn: sqlite3.Connection, mlb_id: str, niche: str) -> Candidate | None:
    row = conn.execute(
        "SELECT * FROM candidates WHERE mlb_id = ? AND niche = ?", (mlb_id, niche)
    ).fetchone()
    return _candidate_from_row(row) if row else None


def candidates_for_offer(conn: sqlite3.Connection, mlb_id: str) -> list[Candidate]:
    rows = conn.execute("SELECT * FROM candidates WHERE mlb_id = ?", (mlb_id,))
    return [_candidate_from_row(r) for r in rows]


def candidates_by_state(
    conn: sqlite3.Connection, state: CandidateState, niche: str | None = None
) -> list[Candidate]:
    sql = "SELECT * FROM candidates WHERE state = ?"
    params: list[Any] = [state.value]
    if niche is not None:
        sql += " AND niche = ?"
        params.append(niche)
    rows = conn.execute(sql + " ORDER BY score DESC, decided_at", params)
    return [_candidate_from_row(r) for r in rows]


# --- postagens -------------------------------------------------------------


def record_post(
    conn: sqlite3.Connection,
    *,
    mlb_id: str,
    niche: str,
    channel: str,
    chat: str,
    status: str,
    sent_at: datetime,
    message_id: str | None = None,
    price: float | None = None,
    attempts: int = 1,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO posts
                (mlb_id, niche, channel, chat, status, sent_at, message_id, price, attempts, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mlb_id, niche, channel, chat, status, _ts(sent_at),
                message_id, price, attempts, error,
            ),
        )


def last_post_at(conn: sqlite3.Connection, chat: str) -> datetime | None:
    row = conn.execute(
        "SELECT MAX(sent_at) FROM posts WHERE chat = ? AND status = 'sent'", (chat,)
    ).fetchone()
    return _dt(row[0])


def posts_today(conn: sqlite3.Connection, chat: str, now: datetime) -> int:
    """Posts enviados no chat no dia corrente do horário de São Paulo."""
    start = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    row = conn.execute(
        """
        SELECT COUNT(*) FROM posts
        WHERE chat = ? AND status = 'sent' AND sent_at >= ? AND sent_at < ?
        """,
        (chat, _ts(start), _ts(end)),
    ).fetchone()
    return row[0]


# --- rodízio de modelos de texto -------------------------------------------


def last_template_idx(conn: sqlite3.Connection, key: str) -> int | None:
    row = conn.execute("SELECT template_idx FROM template_usage WHERE chat = ?", (key,)).fetchone()
    return row[0] if row else None


def record_template_use(conn: sqlite3.Connection, key: str, idx: int, now: datetime) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO template_usage (chat, template_idx, used_at) VALUES (?, ?, ?)",
            (key, idx, _ts(now)),
        )


# --- configurações em tempo de execução ------------------------------------


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
            (key, json.dumps(value)),
        )


def niche_overrides(conn: sqlite3.Connection, niche: str) -> dict[str, Any]:
    return get_setting(conn, f"override:{niche}", default={})


def set_niche_override(conn: sqlite3.Connection, niche: str, path: str, value: Any) -> None:
    """Grava um override do nicho; `path` usa ponto para campos aninhados (`weights.full`)."""
    overrides = niche_overrides(conn, niche)
    *parents, leaf = path.split(".")
    node = overrides
    for key in parents:
        node = node.setdefault(key, {})
    node[leaf] = value
    set_setting(conn, f"override:{niche}", overrides)
