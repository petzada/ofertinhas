"""Card de aprovação no Telegram e os botões inline.

`callback_data` do Telegram aceita no máximo 64 bytes, então os dados vão compactos:
`<ação>:<mlb_id>:<nicho>[:<extra>]`.
"""

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..creative.text import brl
from ..creative.title import short_title
from ..models import Candidate, Offer

CALLBACK_LIMIT = 64

def approval_caption(offer: Offer, cand: Candidate) -> str:
    """Legenda HTML do card que o admin recebe para decidir: só o essencial, bem espaçado."""
    pix = " no Pix" if offer.pix_only else ""
    lines = [
        f"<b>{html.escape(cand.niche.upper())}</b>  ·  nota <b>{cand.score:.0f}</b>",
        "",
        html.escape(short_title(offer.title, 90)),
        "",
        f"Por:  <b>R$ {brl(offer.price)}</b>{pix}",
    ]
    if offer.discount_pct > 0:
        lines.append(f"De:  R$ {brl(offer.original_price)}")
        lines.append(f"Desconto:  <b>{offer.discount_pct:.0f}%</b>")
    lines.append(f"Comissão:  <b>{offer.commission_pct:g}%</b>")
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
