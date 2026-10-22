"""Card de aprovação no Telegram e os botões inline.

`callback_data` do Telegram aceita no máximo 64 bytes, então os dados vão compactos:
`<ação>:<mlb_id>:<nicho>[:<extra>]`.
"""

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..creative.text import badges, brl
from ..creative.title import short_title
from ..models import Candidate, Offer

CALLBACK_LIMIT = 64
CRITERIA_LABELS = {
    "commission_pct": "Comissão %",
    "discount_pct": "Desconto",
    "commission_brl": "Comissão R$",
    "rating": "Avaliação",
    "sold_count": "Vendidos",
    "freshness": "Novidade",
    "free_shipping": "Frete grátis",
    "full": "Full",
}


def _num(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def approval_caption(offer: Offer, cand: Candidate) -> str:
    """Legenda HTML do card que o admin recebe para decidir."""
    price = f"R$ {brl(offer.price)}"
    if offer.pix_only:
        price += " no Pix"
    if offer.discount_pct > 0:
        price += f" (de R$ {brl(offer.original_price)}, -{offer.discount_pct:.0f}%)"
    selos = badges(offer)
    if offer.extra_commission:
        selos.append("💎 Ganhos extras")
    if offer.international:
        selos.append("🌎 Internacional")
    breakdown = " • ".join(
        f"{CRITERIA_LABELS.get(k, k)} {_num(v)}" for k, v in cand.breakdown.items() if v > 0
    )
    lines = [
        f"<b>{html.escape(cand.niche.upper())}</b> • nota <b>{_num(cand.score)}</b>",
        html.escape(short_title(offer.title, 90)),
        f"💰 {price}",
        f"🤝 Comissão {offer.commission_pct:g}% ≈ R$ {brl(offer.commission_brl)}",
    ]
    if selos:
        lines.append(" • ".join(selos))
    if breakdown:
        lines.append(f"<i>{breakdown}</i>")
    lines.append(f'<a href="{html.escape(offer.permalink)}">Ver no Mercado Livre</a>')
    return "\n".join(lines)


def make_callback(action: str, *parts: str) -> str:
    data = ":".join((action, *parts))
    if len(data.encode()) > CALLBACK_LIMIT:
        raise ValueError(f"callback_data passa de {CALLBACK_LIMIT} bytes: {data}")
    return data


def parse_callback(data: str) -> tuple[str, list[str]]:
    action, *parts = data.split(":")
    return action, parts


def approval_keyboard(mlb_id: str, niche: str) -> InlineKeyboardMarkup:
    def button(label: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(label, callback_data=make_callback(action, mlb_id, niche))

    return InlineKeyboardMarkup([
        [button("✅ Aprovar", "a"), button("❌ Rejeitar", "r")],
        [button("✏️ Editar texto", "e"), button("🔁 Trocar nicho", "n")],
    ])


def niche_keyboard(mlb_id: str, current: str, niches: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(n, callback_data=make_callback("m", mlb_id, current, n))]
        for n in niches
        if n != current
    ]
    cancel = InlineKeyboardButton("↩️ Cancelar", callback_data=make_callback("x", mlb_id, current))
    rows.append([cancel])
    return InlineKeyboardMarkup(rows)
