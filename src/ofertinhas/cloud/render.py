"""Lado do Durable Object no desenho dos cards: monta as tarefas e grava o resultado.

Ver `draw.py`: o desenho em si roda no Worker de entrada, para não estourar a memória do DO.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from .. import db
from ..config import AppConfig
from ..models import CandidateState
from ..pipeline import linked_caption, mark_rendered
from .draw import offer_to_json

log = logging.getLogger(__name__)
MAX_PER_MINUTE = 3  # o Cron chama de minuto em minuto; a fila anda sem pesar num só isolate


def render_tasks(conn: sqlite3.Connection, cfg: AppConfig, templates_dir: Path, now: datetime,
                 limit: int = MAX_PER_MINUTE) -> list[dict]:
    """Candidatas com link, maior nota primeiro, com a oferta e a legenda já prontas."""
    tasks = []
    for cand in db.candidates_by_state(conn, CandidateState.LINKED):
        if len(tasks) >= limit:
            break
        try:
            offer = db.get_offer(conn, cand.mlb_id)
            caption = linked_caption(conn, cfg, cand, offer, templates_dir, now)
        except Exception:
            log.exception("falha na legenda de %s/%s", cand.mlb_id, cand.niche)
            continue
        tasks.append({"mlb_id": cand.mlb_id, "niche": cand.niche, "caption": caption,
                      "brand": cfg.brand, "offer": offer_to_json(offer)})
    return tasks


def apply_rendered(conn: sqlite3.Connection, results: list[dict]) -> int:
    return sum(
        mark_rendered(conn, r["mlb_id"], r["niche"], r["caption"], r["card_path"])
        for r in results
    )
