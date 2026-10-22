import re
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.cloud.sqlstore import DOConnection, to_positional
from ofertinhas.models import Candidate, CandidateState, Offer

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
REFUSED = re.compile(r"^\s*(BEGIN|COMMIT|SAVEPOINT)|PRAGMA\s+user_version", re.I)


class FakeDOSql:
    """Imita o `ctx.storage.sql`: recusa BEGIN e PRAGMA user_version, só aceita `?` e roda
    várias instruções quando não há parâmetros."""

    def __init__(self):
        self.raw = sqlite3.connect(":memory:", isolation_level=None)
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.calls: list[str] = []

    def exec(self, sql, *params):
        self.calls.append(sql)
        if REFUSED.search(sql):
            raise RuntimeError("not authorized: SQLITE_AUTH")
        if ":" in re.sub(r"'[^']*'", "", sql):
            raise RuntimeError("parâmetro nomeado não suportado")
        if not params and sql.count(";") > 1:
            # executescript faria COMMIT e quebraria a transação; uma instrução por vez
            for statement in filter(str.strip, sql.split(";")):
                self.raw.execute(statement)
            return [], []
        cur = self.raw.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [list(r) for r in cur.fetchall()]

    def transaction(self, fn):
        self.raw.execute("SAVEPOINT tx")
        try:
            result = fn()
        except Exception:
            self.raw.execute("ROLLBACK TO tx")
            self.raw.execute("RELEASE tx")
            raise
        self.raw.execute("RELEASE tx")
        return result


@pytest.fixture
def fake():
    return FakeDOSql()


@pytest.fixture
def conn(fake):
    c = DOConnection(fake.exec, fake.transaction)
    db.migrate(c)
    return c


def offer(**kw):
    base = dict(mlb_id="MLB1", title="Fone", price=99.9, original_price=199.9, commission_pct=12,
                category_path=("MLB1000", "MLB1051"), permalink="https://x", collected_at=NOW)
    return Offer(**base | kw)


def test_migrations_run_once_and_version_goes_to_meta(fake, conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    before = len(fake.calls)
    db.migrate(conn)
    assert all("CREATE TABLE offers" not in c for c in fake.calls[before:])
    cols = [r[1] for r in fake.raw.execute("PRAGMA table_info(offers)")]
    assert "link_attempts" in cols


def test_failed_migration_rolls_back(fake):
    c = DOConnection(fake.exec, fake.transaction)
    with pytest.raises(sqlite3.OperationalError):
        c.executescript("BEGIN; CREATE TABLE a (x); CREATE TABLE a (x); "
                        "PRAGMA user_version = 1; COMMIT;")
    assert c.execute("PRAGMA user_version").fetchone()[0] == 0
    assert not fake.raw.execute("SELECT name FROM sqlite_master WHERE name = 'a'").fetchall()


def test_named_params_become_positional():
    sql, params = to_positional("UPDATE t SET a = :a, b = :b WHERE id = :id", {
        "id": 1, "a": "x", "b": None,
    })
    assert sql == "UPDATE t SET a = ?, b = ? WHERE id = ?"
    assert params == ["x", None, 1]


def test_offers_round_trip_with_named_params(conn):
    assert db.upsert_offer(conn, offer(), now=NOW) is True
    assert db.upsert_offer(conn, offer(price=89.9), now=NOW + timedelta(hours=1)) is False
    got = db.get_offer(conn, "MLB1")
    assert got.price == 89.9
    assert got.category_path == ("MLB1000", "MLB1051")
    assert got.collected_at == NOW
    assert got.last_seen_at == NOW + timedelta(hours=1)
    db.set_affiliate_link(conn, "MLB1", "https://meli.la/abc")
    assert db.record_link_failure(conn, "MLB1") == 1
    assert db.get_offers(conn, ["MLB1", "MLB9"])[0].affiliate_link == "https://meli.la/abc"


def test_candidates_posts_and_settings(conn):
    db.upsert_offer(conn, offer(), now=NOW)
    cand = Candidate(mlb_id="MLB1", niche="tech", state=CandidateState.RENDERED, score=80.5,
                     breakdown={"desconto": 40.0}, ref_price=99.9, decided_at=NOW,
                     caption="oi", card_path="cards/MLB1-tech.png")
    db.save_candidate(conn, cand)
    assert db.candidates_by_state(conn, CandidateState.RENDERED, "tech") == [cand]
    assert db.count_candidates(conn) == {"rendered": 1}

    db.record_post(conn, mlb_id="MLB1", niche="tech", channel="telegram", chat="-100",
                   status="sent", sent_at=NOW, message_id="7", price=99.9)
    assert db.last_post_at(conn, "-100") == NOW
    assert db.posts_today(conn, "-100", NOW) == 1
    assert db.posts_today_summary(conn, NOW) == [("tech", "telegram", 1)]

    db.set_setting(conn, "x", {"a": [1, 2]})
    assert db.get_setting(conn, "x") == {"a": [1, 2]}
    assert db.get_setting(conn, "nada", 5) == 5
    db.set_niche_override(conn, "tech", "weights.full", 3)
    assert db.niche_overrides(conn, "tech") == {"weights": {"full": 3}}


def test_row_accepts_index_and_name(conn):
    row = conn.execute("SELECT 1 AS a, 'b' AS b").fetchone()
    assert (row[0], row["b"], len(row), row.keys()) == (1, "b", 2, ["a", "b"])
    assert conn.execute("SELECT 1 WHERE 0").fetchone() is None
