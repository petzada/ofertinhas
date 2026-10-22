from datetime import UTC, datetime

from ofertinhas.models import ACTIVE_STATES, Candidate, CandidateState, Offer


def make_offer(**kw) -> Offer:
    base = dict(
        mlb_id="MLB123",
        title="Air Fryer 4L",
        price=299.90,
        original_price=499.90,
        commission_pct=12.0,
        category_path=("MLB1574", "MLB5726"),
        permalink="https://produto.mercadolivre.com.br/MLB-123",
    )
    base.update(kw)
    return Offer(**base)


def test_discount_pct_from_original_price():
    assert make_offer().discount_pct == 40.0


def test_discount_pct_zero_without_original_price():
    assert make_offer(original_price=None).discount_pct == 0.0


def test_discount_pct_zero_when_original_not_higher():
    assert make_offer(original_price=299.90).discount_pct == 0.0


def test_commission_brl_rounded_to_cents():
    assert make_offer(price=99.99, commission_pct=12.5).commission_brl == 12.50


def test_category_id_is_leaf_of_path():
    assert make_offer().category_id == "MLB5726"


def test_collected_at_is_utc_aware():
    assert make_offer().collected_at.tzinfo is not None


def test_candidate_active_states():
    cand = Candidate(
        mlb_id="MLB123",
        niche="casa",
        state=CandidateState.PENDING,
        score=70.0,
        breakdown={},
        ref_price=299.90,
        decided_at=datetime.now(UTC),
    )
    assert cand.state in ACTIVE_STATES
    assert CandidateState.POSTED not in ACTIVE_STATES
