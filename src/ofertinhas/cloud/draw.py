"""Desenho dos cards fora do Durable Object, no isolate leve do Worker de entrada.

O Durable Object carrega FastAPI, PTB e pydantic; desenhar o card lá (Pillow) passa do
limite de memória do isolate, que é reiniciado no meio do tick. Então o DO só monta as
tarefas (oferta + legenda) e grava o resultado; o Worker desenha e grava o PNG no R2.
Este módulo é o lado do Worker: importa só o criativo, sem banco nem config.
"""

import dataclasses
import gc
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from ..creative.image import render_card
from ..creative.themes import theme_for
from ..models import Offer

log = logging.getLogger(__name__)
DATETIME_FIELDS = ("shipping_checked_at", "collected_at", "link_requested_at", "last_seen_at")


def offer_to_json(offer: Offer) -> dict:
    data = dataclasses.asdict(offer)
    data["category_path"] = list(offer.category_path)
    for name in DATETIME_FIELDS:
        data[name] = data[name].isoformat() if data[name] else None
    return data


def offer_from_json(data: dict) -> Offer:
    data = dict(data, category_path=tuple(data["category_path"]))
    for name in DATETIME_FIELDS:
        data[name] = datetime.fromisoformat(data[name]) if data[name] else None
    return Offer(**data)


async def draw_cards(
    tasks: list[dict],
    fetch_image: Callable[[str | None], Awaitable[object]],
    save: Callable[[str, bytes], Awaitable[str]],
) -> list[dict]:
    """Desenha e grava cada card; uma tarefa com problema não trava as outras."""
    results = []
    for task in tasks:
        try:
            offer = offer_from_json(task["offer"])
            png = render_card(offer, theme_for(task["niche"], task["brand"]),
                              await fetch_image(offer.image_url))
            ref = await save(f"{task['mlb_id']}-{task['niche']}.png", png)
        except Exception:
            log.exception("falha ao desenhar o card de %s/%s", task.get("mlb_id"),
                          task.get("niche"))
            continue
        finally:
            gc.collect()  # o heap do Pyodide não encolhe: libera as imagens antes da próxima
        results.append({"mlb_id": task["mlb_id"], "niche": task["niche"],
                        "caption": task["caption"], "card_path": ref, "price": offer.price})
    return results
