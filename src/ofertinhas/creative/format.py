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


X_LIMIT = 280
X_LINK_HINT = "👇 Link no post abaixo"
# Linhas que saem primeiro quando o texto passa do limite do X (as menos importantes).
X_OPTIONAL = ("🔎", "⭐")


def x_length(text: str) -> int:
    """Tamanho como o X conta: emojis e caracteres fora do latim valem 2."""
    return sum(1 if ord(c) <= 0x10FF else 2 for c in text)


def to_x(neutral: str, link: str) -> str:
    """Texto do primeiro post da thread: sem `*`/`~` (o X não formata) e sem o link, que vai
    sozinho na resposta para aparecer o preview. Cabe em 280 caracteres."""
    text = STRIKE.sub(r"\1", BOLD.sub(r"\1", neutral))
    lines = []
    for line in text.splitlines():
        if link in line:
            line = line.replace(link, "").strip()
            if not any(c.isalnum() for c in line):
                continue  # sobrou só emoji/seta: a dica do link substitui
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    body = "\n".join(lines)
    hint = "" if body.rstrip().endswith("👇") else f"\n\n{X_LINK_HINT}"
    for prefix in X_OPTIONAL:
        if x_length(body + hint) <= X_LIMIT:
            break
        body = "\n".join(line for line in body.splitlines() if not line.startswith(prefix))
    if x_length(body + hint) > X_LIMIT:
        while x_length(body + "…" + hint) > X_LIMIT:
            body = body[:-1]
        body = body.rstrip() + "…"
    return (body + hint).strip()


def visible_length(telegram_html: str) -> int:
    """Tamanho que o Telegram conta na legenda: sem tags e com entidades decodificadas."""
    return len(html.unescape(TAG.sub("", telegram_html)))
