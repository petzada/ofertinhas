"""Card promocional 1080×1080 da oferta: foto, preço, selos, QR code e link.

Tudo é desenhado por código (Pillow), sem IA, para que o link e o preço saiam sempre exatos.
"""

import io
import re
from functools import lru_cache
from pathlib import Path

import httpx
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..models import Offer
from .text import brl
from .themes import Theme
from .title import short_title

FONTS_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
CARD_SIZE = (1080, 1080)
PRODUCT_BOX = (60, 130, 1020, 690)
PRODUCT_INNER = (100, 160, 980, 660)
INFO_BOX = (60, 710, 1020, 1010)
BADGE_CENTER = (920, 210)
BADGE_RADIUS = 95
QR_SIZE = 240
TEXT_LEFT = 100
TEXT_WIDTH = 620
CHIP_COLORS = {"FRETE GRÁTIS": "#00A650", "FULL": "#1F1F1F"}
ML_IMAGE_SIZE = re.compile(r"-[A-Z](\.(?:webp|jpe?g|png))$")


@lru_cache(maxsize=64)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / name), size)


def fit_font(
    text: str, name: str, start: int, max_width: float, min_size: int = 20
) -> ImageFont.FreeTypeFont:
    size = start
    while size > min_size and _font(name, size).getlength(text) > max_width:
        size -= 2
    return _font(name, size)


def _ellipsize(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    while text and font.getlength(text + "…") > max_width:
        text = text.rsplit(" ", 1)[0] if " " in text else text[:-1]
    return text.rstrip() + "…"


def wrap_text(
    text: str, font: ImageFont.FreeTypeFont, max_width: float, max_lines: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word if font.getlength(word) <= max_width else _ellipsize(word, font, max_width)
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(lines[-1], font, max_width)
    return lines


def _qr_image(link: str) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    qr.box_size = max(1, QR_SIZE // (qr.modules_count + 2 * qr.border))
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _paste_product(card: Image.Image, product: Image.Image) -> None:
    left, top, right, bottom = PRODUCT_INNER
    fitted = ImageOps.contain(product.convert("RGBA"), (right - left, bottom - top))
    x = left + (right - left - fitted.width) // 2
    y = top + (bottom - top - fitted.height) // 2
    card.paste(fitted, (x, y), fitted)


def _draw_chips(draw: ImageDraw.ImageDraw, labels: list[str]) -> None:
    font = _font("Poppins-SemiBold.ttf", 24)
    x, y = 90, 616
    for label in labels:
        width = font.getlength(label) + 40
        draw.rounded_rectangle((x, y, x + width, y + 50), radius=25, fill=CHIP_COLORS[label])
        draw.text((x + width / 2, y + 26), label, font=font, fill="white", anchor="mm")
        x += width + 14


def _draw_badge(draw: ImageDraw.ImageDraw, discount: float, theme: Theme) -> None:
    cx, cy = BADGE_CENTER
    r = BADGE_RADIUS
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=theme.badge)
    draw.text((cx, cy - 14), f"-{discount:.0f}%", font=_font("Poppins-ExtraBold.ttf", 54),
              fill="white", anchor="mm")
    draw.text((cx, cy + 36), "OFF", font=_font("Poppins-Bold.ttf", 28), fill="white", anchor="mm")


def render_card(offer: Offer, theme: Theme, product: Image.Image | None) -> bytes:
    if not offer.affiliate_link:
        raise ValueError(f"oferta {offer.mlb_id} sem link de afiliado")
    card = Image.new("RGB", CARD_SIZE, theme.bg)
    draw = ImageDraw.Draw(card)

    draw.text((60, 40), theme.label, font=_font("Poppins-ExtraBold.ttf", 46), fill=theme.footer)

    draw.rounded_rectangle(PRODUCT_BOX, radius=36, fill=theme.panel)
    if product is not None:
        _paste_product(card, product)
    chips = [label for label, on in (("FRETE GRÁTIS", offer.free_shipping), ("FULL", offer.full))
             if on]
    _draw_chips(draw, chips)
    if offer.discount_pct > 0:
        _draw_badge(draw, offer.discount_pct, theme)

    draw.rounded_rectangle(INFO_BOX, radius=36, fill=theme.panel)
    title_font = _font("Poppins-SemiBold.ttf", 38)
    y = 732
    for line in wrap_text(short_title(offer.title, 120), title_font, TEXT_WIDTH, 2):
        draw.text((TEXT_LEFT, y), line, font=title_font, fill=theme.text)
        y += 50
    if offer.discount_pct > 0:
        de = f"De R$ {brl(offer.original_price)}"
        de_font = _font("Poppins-Regular.ttf", 30)
        draw.text((TEXT_LEFT, 866), de, font=de_font, fill=theme.muted, anchor="lm")
        draw.line((TEXT_LEFT, 866, TEXT_LEFT + de_font.getlength(de), 866),
                  fill=theme.muted, width=3)
    por = f"R$ {brl(offer.price)}"
    por_font = fit_font(por, "Poppins-ExtraBold.ttf", 80, TEXT_WIDTH)
    draw.text((TEXT_LEFT, 940), por, font=por_font, fill=theme.price, anchor="lm")

    qr = _qr_image(offer.affiliate_link)
    card.paste(qr, (INFO_BOX[2] - 30 - qr.width, INFO_BOX[1] + (300 - qr.height) // 2))

    footer = offer.affiliate_link.removeprefix("https://").removeprefix("http://")
    footer_font = fit_font(footer, "Poppins-SemiBold.ttf", 30, 960)
    draw.text((540, 1045), footer, font=footer_font, fill=theme.footer, anchor="mm")

    buf = io.BytesIO()
    card.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def upgrade_image_url(url: str) -> str:
    """Pede a maior versão da foto em vez da miniatura (`-I.webp` → `-F.webp`)."""
    if "mlstatic.com" not in url:
        return url
    return ML_IMAGE_SIZE.sub(r"-F\1", url)


async def fetch_product_image(client: httpx.AsyncClient, url: str | None) -> Image.Image | None:
    if not url:
        return None
    for candidate in dict.fromkeys([upgrade_image_url(url), url]):
        try:
            response = await client.get(candidate, timeout=15, follow_redirects=True)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            image.load()
            return image
        except (httpx.HTTPError, OSError):
            continue
    return None
