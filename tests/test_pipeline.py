from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas import db
from ofertinhas.config import load_config_text
from ofertinhas.models import Candidate, CandidateState, Offer
from ofertinhas.pipeline import score_and_route

NOW = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
S = CandidateState

# Só a comissão pesa: nota = comissão / 20 × 100.
CFG_TEXT = """
multi_niche: {multi}
defaults:
  weights: {{commission_pct: 1, discount_pct: 0, commission_brl: 0, rating: 0,
             sold_count: 0, freshness: 0, free_shipping: 0, full: 0}}
  auto_approve_at: 80
  manual_review_at: 60
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: -1
  tech:
    categories: [MLB1574]
    weights: {{commission_pct: 1, full: 1}}
    telegram_chat_id: -2
"""


def cfg(multi=False):
    return load_config_text(CFG_TEXT.format(multi=str(multi).lower()))


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def add(conn, mlb_id="MLB1", commission=18.0, price=100.0, **kw) -> str:
    o = Offer(
        mlb_id=mlb_id, title="Produto", price=price, commission_pct=commission,
        category_path=("MLB1574",), permalink="https://x", collected_at=NOW, **kw,
    )
    db.upsert_offer(conn, o, now=NOW)
    return mlb_id


def state(conn, mlb_id="MLB1", niche="casa"):
    c = db.get_candidate(conn, mlb_id, niche)
    return c.state if c else None


def put(conn, state_, niche="casa", ref_price=100.0, decided_at=NOW, mlb_id="MLB1"):
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state_, score=50.0, breakdown={},
        ref_price=ref_price, decided_at=decided_at,
    ))


@pytest.mark.parametrize(
    ("commission", "expected"),
    [(18.0, S.APPROVED), (16.0, S.APPROVED), (14.0, S.PENDING), (6.0, S.DISCARDED)],
)
def test_routes_by_score_band(conn, commission, expected):
    add(conn, commission=commission)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn) is expected


def test_returns_counts_per_state(conn):
    ids = [add(conn, "MLB1", 18.0), add(conn, "MLB2", 14.0), add(conn, "MLB3", 2.0)]
    counts = score_and_route(conn, cfg(), ids, now=NOW)
    assert counts == {S.APPROVED: 1, S.PENDING: 1, S.DISCARDED: 1}


def test_stores_score_breakdown_and_reference_price(conn):
    add(conn, commission=14.0, price=120.0)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    c = db.get_candidate(conn, "MLB1", "casa")
    assert c.score == 70.0
    assert c.breakdown["commission_pct"] == 70.0
    assert c.ref_price == 120.0 and c.decided_at == NOW


def test_filtered_offer_creates_no_candidate(conn):
    add(conn, price=5.0)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert db.candidates_for_offer(conn, "MLB1") == []


def test_active_candidate_is_not_rescored(conn):
    add(conn, commission=18.0)
    put(conn, S.PENDING)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert db.get_candidate(conn, "MLB1", "casa").score == 50.0


def test_discarded_is_rescored(conn):
    add(conn, commission=18.0)
    put(conn, S.DISCARDED)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn) is S.APPROVED


@pytest.mark.parametrize("previous", [S.POSTED, S.REJECTED])
def test_cooldown_blocks_repost(conn, previous):
    add(conn, price=95.0)  # só 5% mais barato
    put(conn, previous, decided_at=NOW - timedelta(days=3))
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn) is previous


def test_price_drop_releases_repost_inside_cooldown(conn):
    add(conn, price=90.0)  # 10% mais barato
    put(conn, S.POSTED, decided_at=NOW - timedelta(days=3))
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn) is S.APPROVED


def test_repost_allowed_after_cooldown(conn):
    add(conn, price=100.0)
    put(conn, S.POSTED, decided_at=NOW - timedelta(days=7))
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn) is S.APPROVED


def test_paused_niche_receives_nothing(conn):
    db.set_niche_override(conn, "casa", "paused", True)
    db.set_niche_override(conn, "tech", "paused", True)
    add(conn)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert db.candidates_for_offer(conn, "MLB1") == []


def test_override_changes_threshold(conn):
    db.set_niche_override(conn, "casa", "auto_approve_at", 95)
    db.set_niche_override(conn, "tech", "paused", True)
    add(conn, commission=18.0)
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn) is S.PENDING


def test_single_niche_mode_picks_best_score(conn):
    add(conn, commission=10.0, full=True)  # casa: 50; tech: (50 + 100) / 2 = 75
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn, niche="casa") is None
    assert state(conn, niche="tech") is S.PENDING


def test_single_niche_mode_blocks_offer_posted_in_other_niche(conn):
    add(conn, commission=18.0)
    put(conn, S.POSTED, niche="tech", decided_at=NOW - timedelta(days=1))
    score_and_route(conn, cfg(), ["MLB1"], now=NOW)
    assert state(conn, niche="casa") is None


def test_multi_niche_mode_routes_to_every_niche(conn):
    add(conn, commission=10.0, full=True)
    score_and_route(conn, cfg(multi=True), ["MLB1"], now=NOW)
    assert state(conn, niche="casa") is S.DISCARDED
    assert state(conn, niche="tech") is S.PENDING


def test_multi_niche_mode_checks_cooldown_per_niche(conn):
    add(conn, commission=18.0)
    put(conn, S.POSTED, niche="tech", decided_at=NOW - timedelta(days=1))
    score_and_route(conn, cfg(multi=True), ["MLB1"], now=NOW)
    assert state(conn, niche="casa") is S.APPROVED
    assert state(conn, niche="tech") is S.POSTED
