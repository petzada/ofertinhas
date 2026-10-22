"""Respostas do portal de afiliados → `Offer`. Formato em `docs/notes/portal-mapping.md`."""

import logging
import re
from datetime import datetime
from typing import Any

from ..models import Offer, utcnow

log = logging.getLogger(__name__)

IMAGE_URL = "https://http2.mlstatic.com/D_NQ_NP_2X_{id}-F.webp"
PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
SOLD = re.compile(r"\+?\s*([\d.]+)\s*(mil|mi)?\b", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\{[^}]*\}\s*")


def parse_sold(text: str) -> int | None:
    """`"| +5mil vendidos"` → 5000; `None` quando não há número."""
    match = SOLD.search(text)
    if not match:
        return None
    number = int(match.group(1).replace(".", ""))
    unit = (match.group(2) or "").lower()
    return number * {"mil": 1_000, "mi": 1_000_000}.get(unit, 1)


def _commission(chip: dict[str, Any]) -> float:
    """Dois formatos: `"{ganancia} {extra}"` + `label.text = "17%"`, ou `"GANHOS 12%"`."""
    for text in (chip.get("label", {}).get("text", ""), chip.get("pill", {}).get("text", "")):
        match = PERCENT.search(text)
        if match:
            return float(match.group(1).replace(",", "."))
    raise ValueError(f"comissão não encontrada no chip: {chip}")


def _review(component: dict[str, Any] | None) -> tuple[float | None, int | None]:
    if component is None:
        return None, None
    values = {v.get("key"): v for v in component["review_compacted"].get("values", [])}
    rating_text = values.get("label", {}).get("label", {}).get("text")
    sold_text = values.get("label2", {}).get("label", {}).get("text", "")
    rating = float(rating_text.replace(",", ".")) if rating_text else None
    return rating, parse_sold(sold_text)


def _permalink(url: str) -> str:
    return url if url.startswith("http") else f"https://{url}"


def _parse_card(card: dict[str, Any], category_path: tuple[str, ...], now: datetime) -> Offer:
    meta = card["metadata"]
    comps = {c["id"]: c for c in card["components"]}
    price = comps["price"]["price"]
    rating, sold = _review(comps.get("review_compacted"))
    pictures = card.get("pictures", {}).get("pictures", [])
    highlight = comps.get("highlight", {}).get("highlight", {}).get("text")
    discount_label = price.get("discount_label", {}).get("text", "")
    return Offer(
        mlb_id=meta["id"],
        title=comps["title"]["title"]["text"],
        price=float(price["current_price"]["value"]),
        original_price=(
            float(price["previous_price"]["value"]) if "previous_price" in price else None
        ),
        commission_pct=_commission(comps["affiliates_commission_chip"]["chip"]),
        category_path=category_path,
        permalink=_permalink(meta["url"]),
        image_url=IMAGE_URL.format(id=pictures[0]["id"]) if pictures else None,
        rating=rating,
        sold_count=sold,
        item_type=meta.get("type", "product"),
        extra_commission=meta.get("extra_commission") == "true",
        pix_only="pix" in discount_label.lower(),
        international="cbt" in comps,
        highlight=PLACEHOLDER.sub("", highlight).strip() if highlight else None,
        collected_at=now,
    )


def parse_hub_search(
    request_body: dict[str, Any] | None,
    response_body: Any,
    now: datetime | None = None,
) -> list[Offer] | None:
    """Ofertas de uma resposta de `hub/search`.

    Devolve `None` quando o formato não é reconhecido: resposta sem `polycards`, ou nenhum
    card legível numa página com cards. É o sinal de que o ML mudou o formato.
    """
    try:
        cards = response_body["polycard_client_model"]["polycards"]
    except (KeyError, TypeError):
        return None
    if not isinstance(cards, list):
        return None
    filters = (request_body or {}).get("filters") or []
    category = next((f.get("value") for f in filters if f.get("id") == "category"), None)
    category_path = (category,) if category else ()
    now = now or utcnow()

    offers = []
    for card in cards:
        if not _has_commission(card):
            continue  # produto fora do programa de afiliados: não serve, mas não é erro
        try:
            offers.append(_parse_card(card, category_path, now))
        except (KeyError, TypeError, ValueError, IndexError) as e:
            log.warning("card ignorado: %s (%r)", e, card.get("metadata", {}).get("id"))
    if any(_has_commission(c) for c in cards) and not offers:
        return None
    return offers


def _has_commission(card: Any) -> bool:
    """Card sem o selo "GANHOS x%" é de produto sem comissão (o portal manda `none` nos
    campos de comissão). Uma página inteira assim é válida: só não tem o que aproveitar."""
    components = card.get("components") if isinstance(card, dict) else None
    if not isinstance(components, list):
        return True  # estrutura estranha: deixa o leitor decidir (e avisar)
    return any(c.get("id") == "affiliates_commission_chip" for c in components)
