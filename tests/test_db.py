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
    db.upsert_offer(conn, offer(price=280.0, pix_only=True, collected_at=later), now=later)
    stored = db.get_offer(conn, "MLB1")
    assert stored.price == 280.0
    assert stored.pix_only is True
    assert stored.collected_at == T0
    assert stored.category_path == ("MLB1574", "MLB5726")


def test_new_offer_fields_roundtrip(conn):
    db.upsert_offer(conn, offer(item_type="user_product", extra_commission=True, pix_only=True,
                                international=True, highlight="MAIS VENDIDO"), now=T0)
    stored = db.get_offer(conn, "MLB1")
    assert (stored.item_type, stored.extra_commission, stored.pix_only, stored.international,
            stored.highlight) == ("user_product", True, True, True, "MAIS VENDIDO")
    assert stored.shipping_checked_at is None


def test_collection_does_not_overwrite_checked_shipping(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.set_shipping(conn, "MLB1", free_shipping=True, full=True, now=T0)
    db.upsert_offer(conn, offer(price=250.0), now=T0 + timedelta(minutes=20))  # coleta não sabe
    stored = db.get_offer(conn, "MLB1")
    assert stored.free_shipping is True and stored.full is True
    assert stored.shipping_checked_at == T0
    assert stored.price == 250.0


def test_link_request_bookkeeping(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.mark_link_requested(conn, "MLB1", T0)
    assert db.get_offer(conn, "MLB1").link_requested_at == T0
    assert db.record_link_failure(conn, "MLB1") == 1
    assert db.record_link_failure(conn, "MLB1") == 2
    db.set_affiliate_link(conn, "MLB1", "https://meli.la/abc", search_code="QL81M2-HWKB")
    stored = db.get_offer(conn, "MLB1")
    assert stored.affiliate_link == "https://meli.la/abc"
    assert stored.search_code == "QL81M2-HWKB"
    assert stored.link_attempts == 0


def test_empty_category_path_is_allowed(conn):
    db.upsert_offer(conn, offer(category_path=()), now=T0)
    assert db.get_offer(conn, "MLB1").category_path == ()


def test_price_history_only_on_change(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.upsert_offer(conn, offer(), now=T0 + timedelta(minutes=15))
    db.upsert_offer(conn, offer(price=250.0), now=T0 + timedelta(minutes=30))
    prices = [r[0] for r in conn.execute("SELECT price FROM price_history ORDER BY seen_at")]
    assert prices == [300.0, 250.0]


def test_price_history_records_original_price_changes(conn):
    db.upsert_offer(conn, offer(), now=T0)
    db.upsert_offer(conn, offer(original_price=600.0), now=T0 + timedelta(hours=1))
    points = db.price_points(conn, "MLB1", T0 - timedelta(days=1))
    assert [(p, o) for _, p, o in points] == [(300.0, 500.0), (300.0, 600.0)]


def test_price_points_include_the_price_in_force_when_the_window_starts(conn):
    db.upsert_offer(conn, offer(price=200.0), now=T0 - timedelta(days=40))
    db.upsert_offer(conn, offer(price=210.0), now=T0 - timedelta(days=35))
    db.upsert_offer(conn, offer(price=300.0), now=T0)
    points = db.price_points(conn, "MLB1", T0 - timedelta(days=30))
    assert [p for _, p, _ in points] == [210.0, 300.0]


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


def test_prune_drops_old_finished_work_and_keeps_what_rules_need(conn):
    now = T0 + timedelta(days=90)
    db.upsert_offer(conn, offer(mlb_id="MLB1"), now=T0)  # sumiu, descartada há 90 dias
    db.save_candidate(conn, candidate(mlb_id="MLB1", state=CandidateState.DISCARDED))
    db.upsert_offer(conn, offer(mlb_id="MLB2"), now=T0)  # velha, mas ainda no fluxo
    db.save_candidate(conn, candidate(mlb_id="MLB2", state=CandidateState.APPROVED))
    db.upsert_offer(conn, offer(mlb_id="MLB3", price=200.0), now=T0)  # vista hoje de novo
    db.upsert_offer(conn, offer(mlb_id="MLB3", price=210.0), now=T0 + timedelta(days=10))
    db.upsert_offer(conn, offer(mlb_id="MLB3", price=220.0), now=now)
    db.set_setting(conn, "quota:casa:2026-07-01", {"auto": 1, "review": 0})
    db.set_setting(conn, "quota:casa:2027-01-19", {"auto": 1, "review": 0})
    db.set_setting(conn, "override:casa", {"paused": True})

    removed = db.prune(conn, now, keep_days=60)

    assert removed == {"candidates": 1, "offers": 1, "price_history": 1, "settings": 1}
    assert db.get_offer(conn, "MLB1") is None
    assert db.get_candidate(conn, "MLB2", "casa").state is CandidateState.APPROVED
    # o preço que valia no corte (210) fica, para a conferência de desconto
    assert [p for _, p, _ in db.price_points(conn, "MLB3", now - timedelta(days=30))] == [
        210.0, 220.0]
    assert db.get_setting(conn, "quota:casa:2027-01-19") and db.get_setting(conn, "override:casa")
    assert db.prune(conn, now, keep_days=60) == {
        "candidates": 0, "offers": 0, "price_history": 0, "settings": 0}
