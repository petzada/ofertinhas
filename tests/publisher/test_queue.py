from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer
from ofertinhas.publisher.queue import expire_stale, next_for_niche

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"
S = CandidateState


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def seed(conn, mlb_id, state=S.RENDERED, score=80.0, niche="casa", seen=NOW):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title="x", price=100, commission_pct=10, category_path=("MLB1574",),
        permalink="https://x", collected_at=seen,
    ), now=seen)
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state, score=score, breakdown={},
        ref_price=100, decided_at=seen,
    ))


def test_offer_remembers_when_it_was_last_seen(conn):
    seed(conn, "MLB1", seen=NOW - timedelta(hours=2))
    db.upsert_offer(conn, db.get_offer(conn, "MLB1"), now=NOW)
    offer = db.get_offer(conn, "MLB1")
    assert offer.collected_at == NOW - timedelta(hours=2)
    assert offer.last_seen_at == NOW


def test_next_for_niche_picks_best_rendered(conn):
    seed(conn, "MLB1", score=70)
    seed(conn, "MLB2", score=90)
    seed(conn, "MLB3", score=99, state=S.LINKED)
    seed(conn, "MLB4", score=95, niche="tech")
    assert next_for_niche(conn, "casa").mlb_id == "MLB2"
    assert next_for_niche(conn, "pets") is None


def test_expire_stale_offers_waiting_in_flow(conn):
    old = NOW - timedelta(hours=7)
    seed(conn, "MLB1", state=S.RENDERED, seen=old)
    seed(conn, "MLB2", state=S.APPROVED, seen=old)
    seed(conn, "MLB3", state=S.PENDING, seen=old)  # admin ainda decide
    seed(conn, "MLB4", state=S.RENDERED, seen=NOW - timedelta(hours=5))
    assert expire_stale(conn, load_config(EXAMPLE), NOW) == 2
    assert db.get_candidate(conn, "MLB1", "casa").state is S.EXPIRED
    assert db.get_candidate(conn, "MLB2", "casa").state is S.EXPIRED
    assert db.get_candidate(conn, "MLB3", "casa").state is S.PENDING
    assert db.get_candidate(conn, "MLB4", "casa").state is S.RENDERED


def test_max_age_is_configurable_per_niche(conn):
    seed(conn, "MLB1", seen=NOW - timedelta(hours=3))
    db.set_niche_override(conn, "casa", "max_offer_age_hours", 2)
    assert expire_stale(conn, load_config(EXAMPLE), NOW) == 1
