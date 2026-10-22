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


def test_caption_is_short_and_spaced():
    text = approval_caption(offer(title="Fritadeira Air Fryer Mondial 4L"), cand())
    assert text == (
        "<b>CASA</b>  ·  nota <b>72</b>\n"
        "\n"
        "Fritadeira Air Fryer Mondial 4L\n"
        "\n"
        "Por:  <b>R$ 299,90</b>\n"
        "De:  R$ 499,90\n"
        "Desconto:  <b>40%</b>\n"
        "Comissão:  <b>12%</b>"
    )


def test_caption_without_discount_skips_old_price_lines():
    text = approval_caption(offer(original_price=None), cand())
    assert "De:" not in text and "Desconto:" not in text
    assert "Por:  <b>R$ 299,90</b>" in text


def test_caption_shows_pix_only():
    assert "Por:  <b>R$ 299,90</b> no Pix" in approval_caption(offer(pix_only=True), cand())
    assert "no Pix" not in approval_caption(offer(), cand())


def test_caption_has_no_extras():
    text = approval_caption(offer(extra_commission=True, international=True), cand())
    for extra in ("href", "Frete", "Ganhos", "Internacional", "R$ 35,99"):
        assert extra not in text


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
