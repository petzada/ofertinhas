import io

import httpx
import pytest
import respx
from PIL import Image, ImageFont
from pyzbar.pyzbar import decode

from ofertinhas.creative.image import (
    BADGE_CENTER,
    BADGE_RADIUS,
    CARD_SIZE,
    FONTS_DIR,
    fetch_product_image,
    fit_font,
    render_card,
    upgrade_image_url,
    wrap_text,
)
from ofertinhas.creative.themes import theme_for
from ofertinhas.models import Offer

LINK = "https://mercadolivre.com/sec/1AbC2dE"


def offer(**kw) -> Offer:
    base = dict(
        mlb_id="MLB1", title="Fritadeira Air Fryer Mondial 4L Preta", price=299.9,
        original_price=499.9, commission_pct=12, category_path=("MLB1574",),
        permalink="https://x", free_shipping=True, full=True, affiliate_link=LINK,
    )
    base.update(kw)
    return Offer(**base)


def product_image() -> Image.Image:
    return Image.new("RGB", (500, 800), "#3366CC")


def open_png(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_card_is_square_png():
    img = open_png(render_card(offer(), theme_for("casa"), product_image()))
    assert img.format == "PNG"
    assert img.size == CARD_SIZE


def test_qr_decodes_to_exact_link():
    img = open_png(render_card(offer(), theme_for("tech"), product_image()))
    assert [d.data.decode() for d in decode(img)] == [LINK]


def test_discount_badge_only_with_discount():
    theme = theme_for("casa")
    with_discount = open_png(render_card(offer(), theme, product_image())).convert("RGB")
    no_discount = offer(original_price=None)
    without = open_png(render_card(no_discount, theme, product_image())).convert("RGB")
    badge_rgb = Image.new("RGB", (1, 1), theme.badge).getpixel((0, 0))
    probe = (BADGE_CENTER[0], BADGE_CENTER[1] - BADGE_RADIUS + 12)  # dentro do círculo, sem texto
    assert with_discount.getpixel(probe) == badge_rgb
    assert without.getpixel(probe) != badge_rgb


def test_renders_without_product_image():
    assert open_png(render_card(offer(), theme_for("x"), None)).size == CARD_SIZE


def test_card_requires_link():
    with pytest.raises(ValueError, match="link"):
        render_card(offer(affiliate_link=None), theme_for("casa"), None)


def test_wrap_text_limits_lines_and_width():
    font = ImageFont.truetype(str(FONTS_DIR / "Poppins-SemiBold.ttf"), 40)
    lines = wrap_text("Palavra " * 40, font, max_width=600, max_lines=2)
    assert len(lines) == 2
    assert all(font.getlength(line) <= 600 for line in lines)
    assert lines[-1].endswith("…")


def test_fit_font_shrinks_until_it_fits():
    font = fit_font("R$ 12.999.999,90", "Poppins-ExtraBold.ttf", start=90, max_width=400)
    assert font.getlength("R$ 12.999.999,90") <= 400
    assert font.size < 90


def test_upgrade_image_url_requests_original_size():
    url = "https://http2.mlstatic.com/D_NQ_NP_812345-MLB123-I.webp"
    assert upgrade_image_url(url) == "https://http2.mlstatic.com/D_NQ_NP_812345-MLB123-O.webp"
    assert upgrade_image_url("https://x/foto.png") == "https://x/foto.png"


@respx.mock
async def test_fetch_product_image_returns_none_on_failure():
    respx.get("https://img/ok.png").mock(
        return_value=httpx.Response(200, content=_png_bytes())
    )
    respx.get("https://img/fail.png").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        assert (await fetch_product_image(client, "https://img/ok.png")).size == (10, 10)
        assert await fetch_product_image(client, "https://img/fail.png") is None
        assert await fetch_product_image(client, None) is None


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    return buf.getvalue()
