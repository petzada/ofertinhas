"""Título curto e legível a partir do título do anúncio do Mercado Livre."""

import re

SMALL_WORDS = {"a", "o", "e", "de", "da", "do", "das", "dos", "com", "para", "em", "sem", "por"}
ACRONYMS = {"TV", "USB", "LED", "HD", "SSD", "HDMI", "JBL", "LG", "PC", "RGB", "UV", "PS5", "XL"}
MLB_CODE = re.compile(r"\bMLB-?\d{6,}\b", re.IGNORECASE)
TRAILING_JUNK = re.compile(r"[\s\-–|,/;:]+$")


def _is_sku(token: str) -> bool:
    return (
        len(token) >= 10
        and any(c.isalpha() for c in token)
        and any(c.isdigit() for c in token)
    )


def _is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.7


def _soften(words: list[str]) -> list[str]:
    out = []
    for i, word in enumerate(words):
        if any(c.isdigit() for c in word) or word in ACRONYMS:
            out.append(word)
        elif i > 0 and word.lower() in SMALL_WORDS:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return out


def short_title(title: str, max_len: int = 60) -> str:
    words = [w for w in MLB_CODE.sub(" ", title).split() if not _is_sku(w)]
    if _is_shouting(" ".join(words)):
        words = _soften(words)
    text = TRAILING_JUNK.sub("", " ".join(words))
    if len(text) <= max_len:
        return text

    if text[max_len] == " ":
        words = text[:max_len].split()
    else:
        words = text[: max_len + 1].split()[:-1]  # descarta a palavra cortada
    while len(words) > 1 and words[-1].lower() in SMALL_WORDS:
        words.pop()
    return TRAILING_JUNK.sub("", " ".join(words))
