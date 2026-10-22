"""Converte o texto neutro das legendas para cada canal.

O formato neutro é o do WhatsApp: `*negrito*` e `~riscado~`, sem atravessar linhas.
"""

import html
import re

TELEGRAM_CAPTION_LIMIT = 1024

BOLD = re.compile(r"\*([^\s*](?:[^*\n]*[^\s*])?)\*")
STRIKE = re.compile(r"~([^\s~](?:[^~\n]*[^\s~])?)~")
TAG = re.compile(r"<[^>]+>")


def to_whatsapp(neutral: str) -> str:
    return neutral


def to_telegram_html(neutral: str) -> str:
    text = html.escape(neutral, quote=False)
    text = BOLD.sub(r"<b>\1</b>", text)
    return STRIKE.sub(r"<s>\1</s>", text)


def visible_length(telegram_html: str) -> int:
    """Tamanho que o Telegram conta na legenda: sem tags e com entidades decodificadas."""
    return len(html.unescape(TAG.sub("", telegram_html)))
