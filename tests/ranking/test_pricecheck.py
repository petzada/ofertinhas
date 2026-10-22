from datetime import UTC, datetime, timedelta

from ofertinhas.config import PriceCheck
from ofertinhas.models import Offer
from ofertinhas.ranking.pricecheck import check_price

NOW = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
CHECK = PriceCheck()  # 30 dias, 5% de folga


def offer(price=100.0, original=200.0) -> Offer:
    return Offer(mlb_id="MLB1", title="Produto", price=price, commission_pct=20,
                 category_path=("MLB1574",), permalink="https://x", original_price=original)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def test_without_history_the_offer_passes_as_announced():
    verdict = check_price(offer(), [], CHECK)
    assert not verdict.inflated and verdict.offer.discount_pct == 50


def test_price_that_only_went_down_is_a_real_deal():
    points = [(days_ago(10), 150.0, 200.0), (NOW, 100.0, 200.0)]
    verdict = check_price(offer(), points, CHECK)
    assert not verdict.inflated and verdict.offer.discount_pct == 50


def test_price_that_was_lower_recently_zeroes_the_discount():
    points = [(days_ago(10), 80.0, 200.0), (days_ago(3), 130.0, 200.0), (NOW, 100.0, 200.0)]
    verdict = check_price(offer(), points, CHECK)
    assert verdict.inflated and "R$ 80.00" in verdict.reason
    assert verdict.offer.discount_pct == 0


def test_small_oscillation_is_tolerated():
    points = [(days_ago(5), 96.0, 200.0), (NOW, 100.0, 200.0)]  # 4% abaixo: dentro da folga
    assert not check_price(offer(), points, CHECK).inflated


def test_inflated_original_price_counts_the_discount_from_the_old_one():
    points = [(days_ago(8), 100.0, 125.0), (NOW, 100.0, 200.0)]
    verdict = check_price(offer(), points, CHECK)
    assert verdict.inflated and '"de" subiu' in verdict.reason
    assert verdict.offer.original_price == 125.0 and verdict.offer.discount_pct == 20


def test_history_without_original_price_does_not_flag():
    points = [(days_ago(8), 100.0, None), (NOW, 100.0, 200.0)]
    assert not check_price(offer(), points, CHECK).inflated


def test_disabled_check_keeps_the_offer():
    points = [(days_ago(10), 50.0, 200.0), (NOW, 100.0, 200.0)]
    assert not check_price(offer(), points, PriceCheck(enabled=False)).inflated
