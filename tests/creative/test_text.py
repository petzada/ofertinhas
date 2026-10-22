import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ofertinhas import db
from ofertinhas.creative.format import TELEGRAM_CAPTION_LIMIT, to_telegram_html, visible_length
from ofertinhas.creative.text import brl, caption_values, fill, load_templates, render_caption
from ofertinhas.models import Offer

TEMPLATES = Path(__file__).parents[2] / "templates" / "text"
LINK = "https://mercadolivre.com/sec/1AbC2dE"


def offer(**kw) -> Offer:
    base = dict(
        mlb_id="MLB1", title="FRITADEIRA AIR FRYER MONDIAL 4L", price=299.9,
        original_price=499.9, commission_pct=12, category_path=("MLB1574",),
        permalink="https://x", rating=4.7, sold_count=1234, free_shipping=True, full=True,
        affiliate_link=LINK,
    )
    base.update(kw)
    return Offer(**base)


def test_brl():
    assert brl(1299.9) == "1.299,90"
    assert brl(9.5) == "9,50"


def test_values_with_discount_and_badges():
    v = caption_values(offer())
    assert v["titulo_curto"] == "Fritadeira Air Fryer Mondial 4L"
    assert v["preco"] == "De ~R$ 499,90~ por *R$ 299,90* (40% OFF)"
    assert v["selos"] == "🚚 Frete grátis • ⚡ Full"
    assert v["nota"] == "4,7" and v["vendidos"] == "1.234"
    assert v["link"] == LINK


def test_values_with_pix_only_discount():
    v = caption_values(offer(pix_only=True))
    assert v["preco"] == "De ~R$ 499,90~ por *R$ 299,90 no Pix* (40% OFF)"


def test_values_without_discount():
    v = caption_values(offer(original_price=None, free_shipping=False, full=False))
    assert v["preco"] == "Por *R$ 299,90*"
    assert v["preco_de"] == "" and v["desconto"] == "" and v["selos"] == ""


def test_offer_without_link_is_an_error():
    with pytest.raises(ValueError, match="link"):
        caption_values(offer(affiliate_link=None))


def test_fill_drops_lines_with_empty_values():
    tpl = "🔥 {titulo_curto}\n{selos}\n⭐ {nota}\n\n👉 {link}"
    out = fill(tpl, {"titulo_curto": "X", "selos": "", "nota": "4,5", "link": LINK})
    assert out == f"🔥 X\n⭐ 4,5\n\n👉 {LINK}"


def test_fill_collapses_blank_lines_left_by_dropped_lines():
    out = fill("A\n\n{selos}\n\nB", {"selos": ""})
    assert out == "A\n\nB"


def test_fill_unknown_variable_is_an_error():
    with pytest.raises(ValueError, match="cupao"):
        fill("{cupao}", {})


def test_rotation_never_repeats_last_template(tmp_path):
    (tmp_path / "casa.txt").write_text("A {link}\n---\nB {link}\n---\nC {link}", encoding="utf-8")
    conn = db.connect(":memory:")
    rng = random.Random(1)
    now = datetime(2026, 10, 22, tzinfo=UTC)
    firsts = [
        render_caption(conn, offer(), "casa", "casa", tmp_path, rng=rng, now=now)[0]
        for _ in range(30)
    ]
    assert all(a != b for a, b in zip(firsts, firsts[1:], strict=False))
    assert set(firsts) == {"A", "B", "C"}


def test_missing_template_falls_back_to_default(tmp_path):
    (tmp_path / "default.txt").write_text("D {link}", encoding="utf-8")
    assert load_templates(tmp_path, "pets") == ["D {link}"]


@pytest.mark.parametrize("path", sorted(TEMPLATES.glob("*.txt")), ids=lambda p: p.name)
def test_shipped_templates_render_within_telegram_limit(path):
    worst = offer(title="X" * 300, sold_count=999_999)
    for tpl in load_templates(TEMPLATES, path.stem):
        text = fill(tpl, caption_values(worst))
        assert "{" not in text and "}" not in text
        assert visible_length(to_telegram_html(text)) < TELEGRAM_CAPTION_LIMIT
        assert LINK in text


def test_shipped_templates_exist():
    names = {p.stem for p in TEMPLATES.glob("*.txt")}
    assert {"default", "casa", "tech"} <= names
    for name in names:
        assert len(load_templates(TEMPLATES, name)) >= 5
