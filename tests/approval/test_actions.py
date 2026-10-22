from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.approval import actions
from ofertinhas.approval.actions import ActionError
from ofertinhas.config import load_config
from ofertinhas.models import Candidate, CandidateState, Offer

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)
EXAMPLE = Path(__file__).parents[2] / "config.example.yaml"
S = CandidateState


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def cfg():
    return load_config(EXAMPLE)


def seed(conn, mlb_id="MLB1", niche="casa", state=S.PENDING, score=70.0):
    db.upsert_offer(conn, Offer(
        mlb_id=mlb_id, title="Air Fryer", price=299.9, original_price=499.9,
        commission_pct=12, category_path=("MLB1574",), permalink="https://x", collected_at=NOW,
    ), now=NOW)
    db.save_candidate(conn, Candidate(
        mlb_id=mlb_id, niche=niche, state=state, score=score, breakdown={},
        ref_price=299.9, decided_at=NOW - timedelta(hours=1),
    ))


def state(conn, mlb_id="MLB1", niche="casa"):
    return db.get_candidate(conn, mlb_id, niche).state


def test_approve_pending(conn):
    seed(conn)
    assert "Aprovada" in actions.approve(conn, "MLB1", "casa", NOW)
    cand = db.get_candidate(conn, "MLB1", "casa")
    assert cand.state is S.APPROVED and cand.decided_at == NOW


def test_approve_is_idempotent(conn):
    seed(conn, state=S.LINKED)
    assert "já" in actions.approve(conn, "MLB1", "casa", NOW).lower()
    assert state(conn) is S.LINKED


def test_cannot_approve_rejected(conn):
    seed(conn, state=S.REJECTED)
    with pytest.raises(ActionError):
        actions.approve(conn, "MLB1", "casa", NOW)


def test_unknown_offer(conn):
    with pytest.raises(ActionError, match="não encontrada"):
        actions.approve(conn, "MLB404", "casa", NOW)


def test_reject_pending_and_idempotent(conn):
    seed(conn)
    actions.reject(conn, "MLB1", "casa", NOW)
    assert state(conn) is S.REJECTED
    assert "já" in actions.reject(conn, "MLB1", "casa", NOW).lower()


def test_cannot_reject_already_posted(conn):
    seed(conn, state=S.POSTED)
    with pytest.raises(ActionError):
        actions.reject(conn, "MLB1", "casa", NOW)


def test_custom_caption_appends_link_when_missing(conn):
    seed(conn)
    actions.set_custom_caption(conn, "MLB1", "casa", "Olha que *achado*: {titulo_curto}")
    assert actions.custom_caption(conn, "MLB1", "casa") == (
        "Olha que *achado*: {titulo_curto}\n\n👉 {link}"
    )


def test_custom_caption_rejects_unknown_variable(conn):
    seed(conn)
    with pytest.raises(ActionError, match="precoo"):
        actions.set_custom_caption(conn, "MLB1", "casa", "{precoo} {link}")


def test_custom_caption_rejects_text_too_long_for_telegram(conn):
    seed(conn)
    with pytest.raises(ActionError, match="longo"):
        actions.set_custom_caption(conn, "MLB1", "casa", "a" * 1000)


def test_custom_caption_none_by_default(conn):
    assert actions.custom_caption(conn, "MLB1", "casa") is None


def test_change_niche_rescores_and_moves(conn, cfg):
    seed(conn)
    new = actions.change_niche(conn, cfg, "MLB1", "casa", "tech", NOW)
    assert new.niche == "tech" and new.state is S.PENDING and new.score > 0
    assert db.get_candidate(conn, "MLB1", "casa") is None
    assert db.get_candidate(conn, "MLB1", "tech") == new


def test_change_niche_validates(conn, cfg):
    seed(conn)
    with pytest.raises(ActionError):
        actions.change_niche(conn, cfg, "MLB1", "casa", "pets", NOW)
    with pytest.raises(ActionError):
        actions.change_niche(conn, cfg, "MLB1", "casa", "casa", NOW)


def test_force_top_approves_best_pending(conn):
    seed(conn, "MLB1", score=61)
    seed(conn, "MLB2", score=75)
    seed(conn, "MLB3", niche="tech", score=99)
    cand = actions.force_top(conn, "casa", NOW)
    assert cand.mlb_id == "MLB2"
    assert state(conn, "MLB2") is S.APPROVED
    assert state(conn, "MLB1") is S.PENDING


def test_force_top_without_pending(conn):
    assert actions.force_top(conn, "casa", NOW) is None
