"""Persistência em SQLite.

Datas são gravadas em ISO 8601 em UTC, o que permite comparar como texto.
"""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import ACTIVE_STATES, TZ, Candidate, CandidateState, Offer, utcnow

# Setting com {reason, url, at} enquanto a extensão estiver pausada; ausente = ativa.
EXTENSION_PAUSED_KEY = "extension_paused"
# Settings com a data (AAAA-MM-DD) no fim da chave: cota e descontos inflados do dia.
DAILY_KEY_PREFIXES = ("quota:", "price_check:")
DAILY_KEEP_DAYS = 14

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
    """
    ALTER TABLE offers ADD COLUMN item_type TEXT NOT NULL DEFAULT 'product';
    ALTER TABLE offers ADD COLUMN extra_commission INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE offers ADD COLUMN pix_only INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE offers ADD COLUMN international INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE offers ADD COLUMN highlight TEXT;
    ALTER TABLE offers ADD COLUMN shipping_checked_at TEXT;
    """,
    """
    ALTER TABLE offers ADD COLUMN search_code TEXT;
    ALTER TABLE offers ADD COLUMN link_requested_at TEXT;
    ALTER TABLE offers ADD COLUMN link_attempts INTEGER NOT NULL DEFAULT 0;
    """,
    """
    ALTER TABLE price_history ADD COLUMN original_price REAL;
    """,
    """
    CREATE TABLE polls (
        message_id TEXT PRIMARY KEY,
        niche TEXT NOT NULL,
        poll_key TEXT NOT NULL,
        chat TEXT NOT NULL,
        week TEXT NOT NULL,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL,
        sent_at TEXT NOT NULL
    );
    CREATE INDEX polls_by_niche ON polls (niche, sent_at);
    CREATE TABLE poll_votes (
        message_id TEXT NOT NULL,
        voter TEXT NOT NULL,
        options_json TEXT NOT NULL,
        voted_at TEXT NOT NULL,
        PRIMARY KEY (message_id, voter)
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

    Na atualização, preserva a data em que foi vista pela primeira vez, o link de afiliado e
    o frete/Full verificados na página do produto (a coleta não traz esses dados).
    """
    now = now or utcnow()
    previous = conn.execute(
        "SELECT price, original_price FROM offers WHERE mlb_id = ?", (offer.mlb_id,)
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
        item_type=offer.item_type,
        extra_commission=int(offer.extra_commission),
        pix_only=int(offer.pix_only),
        international=int(offer.international),
        highlight=offer.highlight,
        updated_at=_ts(now),
    )
    with conn:
        if previous is None:
            fields |= dict(
                mlb_id=offer.mlb_id,
                collected_at=_ts(offer.collected_at),
                free_shipping=int(offer.free_shipping),
                is_full=int(offer.full),
                shipping_checked_at=(
                    _ts(offer.shipping_checked_at) if offer.shipping_checked_at else None
                ),
            )
            cols = ", ".join(fields)
            marks = ", ".join(f":{k}" for k in fields)
            conn.execute(f"INSERT INTO offers ({cols}) VALUES ({marks})", fields)
        else:
            sets = ", ".join(f"{k} = :{k}" for k in fields)
            conn.execute(
                f"UPDATE offers SET {sets} WHERE mlb_id = :mlb_id",
                fields | {"mlb_id": offer.mlb_id},
            )
        if (previous is None or previous["price"] != offer.price
                or previous["original_price"] != offer.original_price):
            conn.execute(
                "INSERT INTO price_history (mlb_id, price, original_price, seen_at) "
                "VALUES (?, ?, ?, ?)",
                (offer.mlb_id, offer.price, offer.original_price, _ts(now)),
            )
    return previous is None


def price_points(
    conn: sqlite3.Connection, mlb_id: str, since: datetime
) -> list[tuple[datetime, float, float | None]]:
    """(desde quando, preço, preço "de") que valeram a partir de `since`, em ordem.

    O histórico só grava mudanças, então inclui o último registro de antes de `since`: é o
    preço que estava valendo quando a janela começou."""
    rows = conn.execute(
        "SELECT seen_at, price, original_price FROM price_history WHERE mlb_id = ? AND "
        "seen_at >= (SELECT COALESCE(MAX(seen_at), '') FROM price_history "
        "            WHERE mlb_id = ? AND seen_at < ?) "
        "ORDER BY seen_at",
        (mlb_id, mlb_id, _ts(since)),
    )
    return [(_dt(r["seen_at"]), r["price"], r["original_price"]) for r in rows]


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
        item_type=row["item_type"],
        extra_commission=bool(row["extra_commission"]),
        pix_only=bool(row["pix_only"]),
        international=bool(row["international"]),
        highlight=row["highlight"],
        free_shipping=bool(row["free_shipping"]),
        full=bool(row["is_full"]),
        shipping_checked_at=_dt(row["shipping_checked_at"]),
        collected_at=_dt(row["collected_at"]),
        affiliate_link=row["affiliate_link"],
        search_code=row["search_code"],
        link_requested_at=_dt(row["link_requested_at"]),
        link_attempts=row["link_attempts"],
        last_seen_at=_dt(row["updated_at"]),
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


def offers_seen_since(conn: sqlite3.Connection, since: datetime) -> list[Offer]:
    """Ofertas que apareceram numa coleta desde `since`, da mais recente para a mais antiga."""
    rows = conn.execute("SELECT * FROM offers WHERE updated_at >= ? ORDER BY updated_at DESC",
                        (_ts(since),))
    return [_offer_from_row(r) for r in rows]


def set_shipping(
    conn: sqlite3.Connection, mlb_id: str, *, free_shipping: bool, full: bool, now: datetime
) -> None:
    """Frete grátis e Full verificados na página do produto."""
    with conn:
        conn.execute(
            "UPDATE offers SET free_shipping = ?, is_full = ?, shipping_checked_at = ? "
            "WHERE mlb_id = ?",
            (int(free_shipping), int(full), _ts(now), mlb_id),
        )


def set_affiliate_link(
    conn: sqlite3.Connection, mlb_id: str, link: str, search_code: str | None = None
) -> None:
    with conn:
        conn.execute(
            "UPDATE offers SET affiliate_link = ?, search_code = ?, link_attempts = 0 "
            "WHERE mlb_id = ?",
            (link, search_code, mlb_id),
        )


def mark_link_requested(conn: sqlite3.Connection, mlb_id: str, now: datetime) -> None:
    with conn:
        conn.execute(
            "UPDATE offers SET link_requested_at = ? WHERE mlb_id = ?", (_ts(now), mlb_id)
        )


def record_link_failure(conn: sqlite3.Connection, mlb_id: str) -> int:
    """Soma uma tentativa de link falha e devolve o total."""
    with conn:
        conn.execute(
            "UPDATE offers SET link_attempts = link_attempts + 1 WHERE mlb_id = ?", (mlb_id,)
        )
    return conn.execute(
        "SELECT link_attempts FROM offers WHERE mlb_id = ?", (mlb_id,)
    ).fetchone()[0]


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


def delete_candidate(conn: sqlite3.Connection, mlb_id: str, niche: str) -> None:
    with conn:
        conn.execute("DELETE FROM candidates WHERE mlb_id = ? AND niche = ?", (mlb_id, niche))


def candidates_for_offer(conn: sqlite3.Connection, mlb_id: str) -> list[Candidate]:
    rows = conn.execute("SELECT * FROM candidates WHERE mlb_id = ?", (mlb_id,))
    return [_candidate_from_row(r) for r in rows]


def count_candidates(conn: sqlite3.Connection, niche: str | None = None) -> dict[str, int]:
    sql = "SELECT state, COUNT(*) FROM candidates"
    params: list[Any] = []
    if niche is not None:
        sql += " WHERE niche = ?"
        params.append(niche)
    return {r[0]: r[1] for r in conn.execute(sql + " GROUP BY state", params)}


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


def posts_today_summary(conn: sqlite3.Connection, now: datetime) -> list[tuple[str, str, int]]:
    """(nicho, canal, enviados) no dia corrente de São Paulo."""
    start = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = conn.execute(
        """
        SELECT niche, channel, COUNT(*) FROM posts
        WHERE status = 'sent' AND sent_at >= ? AND sent_at < ?
        GROUP BY niche, channel ORDER BY niche, channel
        """,
        (_ts(start), _ts(start + timedelta(days=1))),
    )
    return [(r[0], r[1], r[2]) for r in rows]


def last_post_at(conn: sqlite3.Connection, chat: str) -> datetime | None:
    row = conn.execute(
        "SELECT MAX(sent_at) FROM posts WHERE chat = ? AND status = 'sent'", (chat,)
    ).fetchone()
    return _dt(row[0])


def sent_to_chat_since(conn: sqlite3.Connection, mlb_id: str, chat: str, since: datetime) -> bool:
    row = conn.execute(
        "SELECT 1 FROM posts WHERE mlb_id = ? AND chat = ? AND status = 'sent' AND sent_at >= ?",
        (mlb_id, chat, _ts(since)),
    ).fetchone()
    return row is not None


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


# --- enquetes --------------------------------------------------------------


def record_poll(conn: sqlite3.Connection, *, message_id: str, niche: str, poll_key: str,
                chat: str, week: str, question: str, options: list[str],
                sent_at: datetime) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO polls (message_id, niche, poll_key, chat, week, question, "
            "options_json, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, niche, poll_key, chat, week, question, json.dumps(options),
             _ts(sent_at)),
        )


def poll_sent(conn: sqlite3.Connection, niche: str, chat: str, week: str) -> bool:
    return conn.execute("SELECT 1 FROM polls WHERE niche = ? AND chat = ? AND week = ?",
                        (niche, chat, week)).fetchone() is not None


def poll_history(conn: sqlite3.Connection, niche: str) -> list[str]:
    """`poll_key` das enquetes do nicho, da mais antiga para a mais nova."""
    return [r["poll_key"] for r in conn.execute(
        "SELECT poll_key FROM polls WHERE niche = ? ORDER BY sent_at", (niche,))]


def get_poll(conn: sqlite3.Connection, message_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,)).fetchone()
    if row is None:
        return None
    poll = dict(zip(row.keys(), row, strict=True))
    poll["options"] = json.loads(poll.pop("options_json"))
    return poll


def recent_polls(conn: sqlite3.Connection, limit: int, niche: str | None = None) -> list[dict]:
    sql, params = "SELECT message_id FROM polls", []
    if niche:
        sql, params = sql + " WHERE niche = ?", [niche]
    rows = conn.execute(sql + " ORDER BY sent_at DESC LIMIT ?", (*params, limit))
    return [get_poll(conn, r["message_id"]) for r in rows]


def set_poll_vote(conn: sqlite3.Connection, message_id: str, voter: str, options: list[str],
                  voted_at: datetime) -> None:
    """O voto mais recente de cada pessoa vale (no WhatsApp dá para trocar o voto); lista
    vazia é voto retirado."""
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO poll_votes (message_id, voter, options_json, voted_at) "
            "VALUES (?, ?, ?, ?)", (message_id, voter, json.dumps(options), _ts(voted_at)),
        )


def poll_votes(conn: sqlite3.Connection, message_id: str) -> list[list[str]]:
    return [json.loads(r["options_json"]) for r in conn.execute(
        "SELECT options_json FROM poll_votes WHERE message_id = ?", (message_id,))]


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


# --- limpeza ---------------------------------------------------------------


def prune(conn: sqlite3.Connection, now: datetime, keep_days: int) -> dict[str, int]:
    """Apaga o que passou de `keep_days` e não serve mais a nenhuma regra.

    - candidatas fora do fluxo (descartadas, expiradas, postadas, recusadas) decididas antes
      do corte; quem chama garante `keep_days` maior que o cooldown de repost;
    - ofertas que não aparecem na coleta desde o corte e não têm mais candidata;
    - histórico de preços anterior ao corte, menos o registro que valia no corte (base da
      conferência de desconto, ver `price_points`);
    - settings do dia (cota, descontos inflados) com mais de `DAILY_KEEP_DAYS` dias.
    Os posts ficam: são poucos e guardam o histórico de envio.
    """
    cutoff = _ts(now - timedelta(days=keep_days))
    active = sorted(s.value for s in ACTIVE_STATES)
    marks = ", ".join("?" for _ in active)
    old_day = (now.astimezone(TZ) - timedelta(days=DAILY_KEEP_DAYS)).date().isoformat()
    gone = "updated_at < ? AND mlb_id NOT IN (SELECT mlb_id FROM candidates)"
    removed = {}
    with conn:
        removed["candidates"] = _delete(
            conn, "candidates", f"decided_at < ? AND state NOT IN ({marks})", (cutoff, *active))
        _delete(conn, "price_history",
                f"mlb_id IN (SELECT mlb_id FROM offers WHERE {gone})", (cutoff,))
        removed["offers"] = _delete(conn, "offers", gone, (cutoff,))
        removed["price_history"] = _delete(
            conn, "price_history",
            "seen_at < (SELECT MAX(h.seen_at) FROM price_history h "
            "WHERE h.mlb_id = price_history.mlb_id AND h.seen_at < ?)", (cutoff,))
        stale = [
            row["key"] for row in conn.execute(
                "SELECT key FROM settings WHERE "
                + " OR ".join("key LIKE ?" for _ in DAILY_KEY_PREFIXES),
                [f"{prefix}%" for prefix in DAILY_KEY_PREFIXES],
            )
            if row["key"].rsplit(":", 1)[-1] < old_day
        ]
        for key in stale:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        removed["settings"] = len(stale)
    return removed


def _delete(conn: sqlite3.Connection, table: str, where: str, params: tuple) -> int:
    """DELETE que devolve quantas linhas saíram (o SQLite do Durable Object não tem
    `rowcount`)."""
    count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
    if count:
        conn.execute(f"DELETE FROM {table} WHERE {where}", params)
    return count
