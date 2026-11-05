"""Legendas das postagens a partir de modelos de texto por nicho.

Os modelos ficam em `templates/text/<nome>.txt`, separados por uma linha `---`. Uma linha
cujas variáveis ficam vazias (ex.: sem selos) é removida inteira.

Um nicho pode ter modelos por tema em `templates/text/<nome>/<tema>.txt`
(ex.: `mulher/perfume.txt`).
O tema sai da categoria raiz e do título da oferta (`topic_of`); sem arquivo do tema, vale o
`<nome>.txt`. O rodízio que evita repetir o último modelo é por nicho e tema.
"""

import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from string import Formatter

from .. import db
from ..models import Offer, utcnow
from ..ranking.filters import contains_term, normalize_text
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


BEAUTY, FASHION, JEWELRY, HOME, APPLIANCES = "MLB1246", "MLB1430", "MLB3937", "MLB1574", "MLB5726"

# (tema, categorias raiz onde vale, termos do título). O primeiro que casar ganha; categorias
# vazias valem para qualquer uma. Termos com `*` pegam o começo da palavra, como nos filtros.
TOPICS: tuple[tuple[str, frozenset[str], tuple[str, ...]], ...] = (
    ("perfume", frozenset({BEAUTY}), ("perfume*", "body splash", "colonia*", "eau de")),
    (
        "maquiagem",
        frozenset({BEAUTY}),
        (
            "maquiagem",
            "batom*",
            "base",
            "corretivo*",
            "paleta*",
            "sombra*",
            "blush",
            "rimel",
            "mascara de cilios",
            "delineador*",
            "gloss",
            "lip*",
            "pincel*",
            "pinceis",
            "iluminador*",
            "po compacto",
            "po solto",
            "primer",
            "esmalte*",
            "unha*",
        ),
    ),
    ("cuidados", frozenset({BEAUTY}), ()),
    ("moda", frozenset({FASHION, JEWELRY}), ()),
    (
        "cozinha",
        frozenset({HOME, APPLIANCES}),
        (
            "panela*",
            "frigideira*",
            "cacarola*",
            "airfryer",
            "air fryer",
            "fritadeira*",
            "liquidificador*",
            "batedeira*",
            "mixer",
            "cafeteira*",
            "sanduicheira*",
            "chaleira*",
            "torradeira*",
            "multiprocessador*",
            "processador*",
            "talher*",
            "faqueiro*",
            "faca*",
            "pote",
            "potes",
            "marmita*",
            "assadeira*",
            "travessa*",
            "tigela*",
            "xicara*",
            "caneca*",
            "copo*",
            "taca*",
            "prato*",
            "jantar",
            "utensilio*",
            "espatula*",
            "tabua*",
            "escorredor*",
            "ralador*",
            "coador*",
            "garrafa termica*",
            "micro-ondas",
            "microondas",
            "forno*",
            "cooktop*",
            "fogao*",
            "pipoqueira*",
            "espremedor*",
            "cozinha",
        ),
    ),
    ("eletro", frozenset({APPLIANCES}), ()),
    ("casa", frozenset({HOME}), ()),
)


def topic_of(offer: Offer) -> str | None:
    """Tema da oferta para escolher o modelo de texto, ou None se nenhum casar."""
    root = offer.category_path[0] if offer.category_path else None
    title = normalize_text(offer.title)
    for topic, roots, terms in TOPICS:
        if root is not None and roots and root not in roots:
            continue
        if terms and any(contains_term(title, t) for t in terms):
            return topic
        if not terms and root is not None and root in roots:
            return topic
    return None


def load_templates(templates_dir: Path, name: str, topic: str | None = None) -> list[str]:
    path = templates_dir / f"{name}.txt"
    if topic and (templates_dir / name / f"{topic}.txt").exists():
        path = templates_dir / name / f"{topic}.txt"
    elif not path.exists():
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
    """Legenda com um modelo sorteado (do tema da oferta, se o nicho tiver), nunca o mesmo da
    última vez em `rotation_key` e tema."""
    topic = topic_of(offer)
    if topic and (templates_dir / template_name / f"{topic}.txt").exists():
        rotation_key = f"{rotation_key}:{topic}"
    else:
        topic = None
    templates = load_templates(templates_dir, template_name, topic)
    choices = list(range(len(templates)))
    last = db.last_template_idx(conn, rotation_key)
    if len(choices) > 1 and last in choices:
        choices.remove(last)
    idx = (rng or random).choice(choices)
    db.record_template_use(conn, rotation_key, idx, now or utcnow())
    return fill(templates[idx], caption_values(offer))
