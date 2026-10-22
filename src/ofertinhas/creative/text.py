"""Legendas das postagens a partir de modelos de texto por nicho.

Os modelos ficam em `templates/text/<nome>.txt`, separados por uma linha `---`. Uma linha
cujas variáveis ficam vazias (ex.: sem selos) é removida inteira.
"""

import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from string import Formatter

from .. import db
from ..models import Offer, utcnow
from .title import short_title

SEPARATOR = re.compile(r"^---\s*$", re.MULTILINE)


def brl(value: float) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def badges(offer: Offer) -> list[str]:
    pairs = (("🚚 Frete grátis", offer.free_shipping), ("⚡ Full", offer.full))
    return [label for label, on in pairs if on]


def caption_values(offer: Offer) -> dict[str, str]:
    if not offer.affiliate_link:
        raise ValueError(f"oferta {offer.mlb_id} sem link de afiliado")
    discount = offer.discount_pct
    por = brl(offer.price)
    de = brl(offer.original_price) if discount > 0 else ""
    desconto = f"{discount:.0f}" if discount > 0 else ""
    pix = " no Pix" if offer.pix_only else ""
    if discount > 0:
        preco = f"De ~R$ {de}~ por *R$ {por}{pix}* ({desconto}% OFF)"
    else:
        preco = f"Por *R$ {por}{pix}*"
    return {
        "titulo_curto": short_title(offer.title),
        "preco": preco,
        "preco_por": por,
        "preco_de": de,
        "desconto": desconto,
        "selos": " • ".join(badges(offer)),
        "nota": f"{offer.rating:.1f}".replace(".", ",") if offer.rating else "",
        "vendidos": _thousands(offer.sold_count) if offer.sold_count else "",
        "link": offer.affiliate_link,
        "codigo_busca": offer.search_code or "",
    }


def fill(template: str, values: dict[str, str]) -> str:
    lines = []
    for line in template.splitlines():
        fields = [name for _, name, _, _ in Formatter().parse(line) if name]
        unknown = [f for f in fields if f not in values]
        if unknown:
            raise ValueError(f"variável desconhecida no modelo: {', '.join(unknown)}")
        if any(values[f] == "" for f in fields):
            continue
        lines.append(line.format(**values))
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def load_templates(templates_dir: Path, name: str) -> list[str]:
    path = templates_dir / f"{name}.txt"
    if not path.exists():
        path = templates_dir / "default.txt"
    parts = SEPARATOR.split(path.read_text(encoding="utf-8"))
    return [p.strip() for p in parts if p.strip()]


def render_caption(
    conn: sqlite3.Connection,
    offer: Offer,
    template_name: str,
    rotation_key: str,
    templates_dir: Path,
    rng: random.Random | None = None,
    now: datetime | None = None,
) -> str:
    """Legenda neutra com um modelo sorteado, nunca o mesmo da última vez em `rotation_key`."""
    templates = load_templates(templates_dir, template_name)
    choices = list(range(len(templates)))
    last = db.last_template_idx(conn, rotation_key)
    if len(choices) > 1 and last in choices:
        choices.remove(last)
    idx = (rng or random).choice(choices)
    db.record_template_use(conn, rotation_key, idx, now or utcnow())
    return fill(templates[idx], caption_values(offer))
