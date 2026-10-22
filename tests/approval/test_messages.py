from datetime import UTC, datetime

import pytest

from ofertinhas.approval.messages import (
    approval_caption,
    approval_keyboard,
    make_callback,
    niche_keyboard,
    parse_callback,
)
from ofertinhas.models import Candidate, CandidateState, Offer

NOW = datetime(2026, 10, 22, 15, tzinfo=UTC)


def offer(**kw):
    base = dict(
        mlb_id="MLB4123456789", title="Fritadeira <Air> Fryer & Cia", price=299.9,
        original_price=499.9, commission_pct=12, category_path=("MLB1574",),
        permalink="https://produto.mercadolivre.com.br/MLB-4123456789", free_shipping=True,
    )
    base.update(kw)
    return Offer(**base)


def cand(**kw):
    base = dict(
        mlb_id="MLB4123456789", niche="casa", state=CandidateState.PENDING, score=72.4,
        breakdown={"commission_pct": 21.0, "discount_pct": 16.7, "full": 0.0},
        ref_price=299.9, decided_at=NOW,
    )
    base.update(kw)
    return Candidate(**base)


def test_caption_has_score_price_commission_and_breakdown():
    text = approval_caption(offer(), cand())
    assert "CASA" in text and "72,4" in text
    assert "R$ 299,90" in text and "-40%" in text
    assert "12%" in text and "R$ 35,99" in text
    assert "Comissão % 21,0" in text and "Desconto 16,7" in text
    assert "Full" not in text  # critério zerado não aparece
    assert "🚚 Frete grátis" in text
    assert 'href="https://produto.mercadolivre.com.br/MLB-4123456789"' in text


def test_caption_shows_pix_only():
    assert "no Pix" in approval_caption(offer(pix_only=True), cand())
    assert "no Pix" not in approval_caption(offer(), cand())


def test_caption_shows_extra_commission_and_international():
    text = approval_caption(offer(extra_commission=True, international=True), cand())
    assert "ganhos extras" in text.lower() and "internacional" in text.lower()


def test_caption_escapes_html_from_title():
    text = approval_caption(offer(), cand())
    assert "&lt;Air&gt;" in text and "&amp; Cia" in text


def test_callback_roundtrip():
    data = make_callback("a", "MLB4123456789", "casa")
    assert parse_callback(data) == ("a", ["MLB4123456789", "casa"])


def test_callback_too_long_is_an_error():
    with pytest.raises(ValueError, match="64"):
        make_callback("m", "MLB4123456789", "x" * 30, "y" * 30)


def test_approval_keyboard_buttons():
    kb = approval_keyboard("MLB1", "casa")
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert data == ["a:MLB1:casa", "r:MLB1:casa", "e:MLB1:casa", "n:MLB1:casa"]


def test_niche_keyboard_lists_other_niches_and_cancel():
    kb = niche_keyboard("MLB1", "casa", ["casa", "tech", "pets"])
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert data == ["m:MLB1:casa:tech", "m:MLB1:casa:pets", "x:MLB1:casa"]
