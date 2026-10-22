from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.models import Candidate, CandidateState, Offer

T0 = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)  # 12:00 em São Paulo


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def offer(**kw) -> Offer:
    base = dict(
        mlb_id="MLB1",
        title="Air Fryer",
        price=300.0,
        original_price=500.0,
        commission_pct=12.0,
        category_path=("MLB1574", "MLB5726"),
        permalink="https://produto.mercadolivre.com.br/MLB-1",
        collected_at=T0,
    )
    base.update(kw)
    return Offer(**base)


def candidate(**kw) -> Candidate:
    base = dict(
        mlb_id="MLB1",
        niche="casa",
        state=CandidateState.PENDING,
        score=70.0,
        breakdown={"commission_pct": 30.0, "discount_pct": 40.0},
        ref_price=300.0,
        decided_at=T0,
    )
    base.update(kw)
    return Candidate(**base)


def test_migrate_is_idempotent(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    db.migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == version > 0


def test_upsert_reports_new_then_existing(conn):
    assert db.upsert_offer(conn, offer(), now=T0) is True
    assert db.upsert_offer(conn, offer(price=280.0), now=T0 + timedelta(hours=1)) is False
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 1


def test_upsert_updates_price_and_keeps_first_seen(conn):
    db.upsert_offer(conn, offer(), now=T0)
    later = T0 + timedelta(hours=2)
    db.upsert_offer(conn, offer(price=280.0, full=True, collected_at=later), now=later)
    stored = db.get_offer(conn, "MLB1")
    assert stored.price == 280.0
    assert stored.full is True
    assert stored.collected_at == T0
    assert stored.category_path == ("MLB1574", "MLB5726")


def test_price_history_only_on_change(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.upsert_offer(conn, offer(), now=T0 + timedelta(minutes=15))
    db.upsert_offer(conn, offer(price=250.0), now=T0 + timedelta(minutes=30))
    prices = [r[0] for r in conn.execute("SELECT price FROM price_history ORDER BY seen_at")]
    assert prices == [300.0, 250.0]


def test_upsert_keeps_affiliate_link_and_candidates(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.set_affiliate_link(conn, "MLB1", "https://mercadolivre.com/sec/abc")
    db.save_candidate(conn, candidate(state=CandidateState.APPROVED))
    db.upsert_offer(conn, offer(price=290.0), now=T0)
    assert db.get_offer(conn, "MLB1").affiliate_link == "https://mercadolivre.com/sec/abc"
    assert db.get_candidate(conn, "MLB1", "casa").state is CandidateState.APPROVED


def test_candidate_roundtrip(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.save_candidate(conn, candidate(caption="oi", notified_at=T0))
    got = db.get_candidate(conn, "MLB1", "casa")
    assert got == candidate(caption="oi", notified_at=T0)


def test_save_candidate_replaces(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.save_candidate(conn, candidate())
    db.save_candidate(conn, candidate(state=CandidateState.REJECTED, score=10.0))
    assert db.get_candidate(conn, "MLB1", "casa").state is CandidateState.REJECTED
    assert len(db.candidates_for_offer(conn, "MLB1")) == 1


def test_candidates_by_state_ordered_by_score(conn):
    for i, score in enumerate([50.0, 90.0, 70.0]):
        db.upsert_offer(conn, offer(mlb_id=f"MLB{i}"), now=T0)
        db.save_candidate(conn, candidate(mlb_id=f"MLB{i}", score=score))
    db.save_candidate(conn, candidate(mlb_id="MLB0", niche="tech", score=99.0))
    got = db.candidates_by_state(conn, CandidateState.PENDING, niche="casa")
    assert [c.score for c in got] == [90.0, 70.0, 50.0]


def test_last_post_at_ignores_failures(conn):
    db.record_post(
        conn, mlb_id="MLB1", niche="casa", channel="telegram", chat="-1001",
        status="sent", sent_at=T0, message_id="10",
    )
    db.record_post(
        conn, mlb_id="MLB2", niche="casa", channel="telegram", chat="-1001",
        status="failed", sent_at=T0 + timedelta(minutes=5), error="timeout",
    )
    assert db.last_post_at(conn, "-1001") == T0
    assert db.last_post_at(conn, "-999") is None


def test_posts_today_uses_sao_paulo_day(conn):
    yesterday_local = datetime(2026, 10, 22, 2, 30, tzinfo=UTC)  # 23:30 do dia 21 em SP
    today_local = datetime(2026, 10, 22, 3, 30, tzinfo=UTC)  # 00:30 do dia 22 em SP
    for t in (yesterday_local, today_local, T0):
        db.record_post(
            conn, mlb_id="MLB1", niche="casa", channel="whatsapp", chat="g@g.us",
            status="sent", sent_at=t,
        )
    assert db.posts_today(conn, "g@g.us", now=T0) == 2


def test_settings_roundtrip(conn):
    assert db.get_setting(conn, "x", default={}) == {}
    db.set_setting(conn, "x", {"a": 1})
    assert db.get_setting(conn, "x") == {"a": 1}


def test_niche_override_by_dotted_path(conn):
    db.set_niche_override(conn, "casa", "weights.discount_pct", 30)
    db.set_niche_override(conn, "casa", "auto_approve_at", 85)
    db.set_niche_override(conn, "casa", "weights.full", 0)
    assert db.niche_overrides(conn, "casa") == {
        "weights": {"discount_pct": 30, "full": 0},
        "auto_approve_at": 85,
    }
    assert db.niche_overrides(conn, "tech") == {}
