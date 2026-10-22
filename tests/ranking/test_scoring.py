from datetime import UTC, datetime, timedelta

import pytest

from ofertinhas.config import load_config_text
from ofertinhas.models import Offer
from ofertinhas.ranking.scoring import score_offer

NOW = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)

CFG_TEXT = """
niches:
  casa:
    categories: [MLB1574]
    telegram_chat_id: -1
"""


def niche(**overrides):
    return load_config_text(CFG_TEXT).for_niche("casa", overrides=overrides)


def perfect(**kw) -> Offer:
    base = dict(
        mlb_id="MLB1",
        title="Air Fryer",
        price=400.0,
        original_price=1000.0,  # 60% OFF
        commission_pct=20.0,  # R$ 80 de comissão
        category_path=("MLB1574",),
        permalink="https://x",
        rating=5.0,
        sold_count=5000,
        free_shipping=True,
        full=True,
        collected_at=NOW,
    )
    base.update(kw)
    return Offer(**base)


def test_offer_hitting_every_target_scores_100():
    s = score_offer(perfect(), niche(), NOW)
    assert s.score == 100.0
    assert s.niche == "casa" and s.mlb_id == "MLB1"


def test_values_above_target_are_capped():
    assert score_offer(perfect(commission_pct=40.0), niche(), NOW).score == 100.0


def test_breakdown_sums_to_score():
    o = perfect(commission_pct=7.0, original_price=500.0, rating=4.3, sold_count=120, full=False)
    s = score_offer(o, niche(), NOW - timedelta(hours=5))
    assert sum(s.breakdown.values()) == pytest.approx(s.score, abs=0.2)


def test_only_weighted_criteria_count():
    zero = {k: 0 for k in ("discount_pct", "commission_brl", "rating", "sold_count",
                           "freshness", "free_shipping", "full")}
    n = niche(weights=zero | {"commission_pct": 1})
    s = score_offer(perfect(commission_pct=10.0, full=False), n, NOW)
    assert s.score == 50.0
    assert s.breakdown["full"] == 0


def test_rating_scales_from_floor_to_five():
    n = niche(weights={k: 0 for k in ("commission_pct", "discount_pct", "commission_brl",
                                       "sold_count", "freshness", "free_shipping", "full")})
    assert score_offer(perfect(rating=4.0), n, NOW).score == 0.0
    assert score_offer(perfect(rating=4.5), n, NOW).score == 50.0
    assert score_offer(perfect(rating=None), n, NOW).score == 0.0


def test_sold_count_uses_log_scale():
    n = niche(weights={k: 0 for k in ("commission_pct", "discount_pct", "commission_brl",
                                       "rating", "freshness", "free_shipping", "full")})
    few = score_offer(perfect(sold_count=70), n, NOW).score
    assert 45 < few < 55  # log1p(70) / log1p(5000) ≈ 0,5
    assert score_offer(perfect(sold_count=None), n, NOW).score == 0.0


def test_freshness_decays_linearly():
    n = niche(weights={k: 0 for k in ("commission_pct", "discount_pct", "commission_brl",
                                       "rating", "sold_count", "free_shipping", "full")})
    assert score_offer(perfect(), n, NOW + timedelta(hours=12)).score == 50.0
    assert score_offer(perfect(), n, NOW + timedelta(hours=30)).score == 0.0


def test_no_discount_scores_zero_on_discount():
    s = score_offer(perfect(original_price=None), niche(), NOW)
    assert s.breakdown["discount_pct"] == 0
