import pytest

from ofertinhas.config import Filters
from ofertinhas.models import Offer
from ofertinhas.ranking.filters import normalize_text, passes


def offer(**kw) -> Offer:
    base = dict(
        mlb_id="MLB1",
        title="Fone Bluetooth TWS",
        price=100.0,
        commission_pct=10.0,
        category_path=("MLB1000",),
        permalink="https://x",
        rating=4.5,
    )
    base.update(kw)
    return Offer(**base)


def test_default_filters_pass():
    assert passes(offer(), Filters()) == (True, None)


@pytest.mark.parametrize("price", [14.99, 3000.01])
def test_price_out_of_range(price):
    ok, reason = passes(offer(price=price), Filters())
    assert not ok and "preço" in reason


def test_price_limits_are_inclusive():
    assert passes(offer(price=15.0), Filters())[0]
    assert passes(offer(price=3000.0), Filters())[0]


def test_low_rating_rejected():
    ok, reason = passes(offer(rating=3.9), Filters())
    assert not ok and "avaliação" in reason


def test_missing_rating_passes():
    assert passes(offer(rating=None), Filters())[0]


def test_require_free_shipping():
    f = Filters(require_free_shipping=True)
    assert not passes(offer(free_shipping=False), f)[0]
    assert passes(offer(free_shipping=True), f)[0]


def test_require_full():
    f = Filters(require_full=True)
    assert not passes(offer(full=False), f)[0]
    assert passes(offer(full=True), f)[0]


def test_exclude_international():
    assert passes(offer(international=True), Filters())[0]
    ok, reason = passes(offer(international=True), Filters(exclude_international=True))
    assert not ok and "internacional" in reason


def test_blocked_keyword_ignores_case_and_accents():
    ok, reason = passes(offer(title="Tênis REPLICA Premium"), Filters())
    assert not ok and "réplica" in reason


def test_blocked_keyword_matches_whole_words_only():
    # "usado" não pode bloquear "abusado"
    assert passes(offer(title="Moletom Abusado Estampa"), Filters())[0]


def test_normalize_text():
    assert normalize_text("  Réplica  ÇÃO ") == "replica cao"
