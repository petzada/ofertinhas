"""Nota de 0 a 100 de uma oferta dentro de um nicho.

Cada critério é normalizado de 0 a 1 contra um alvo absoluto (`targets`), então a nota
não depende das outras ofertas do ciclo e as notas de corte têm sempre o mesmo sentido.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from ..config import NicheConfig, Targets
from ..models import Offer


@dataclass(frozen=True)
class Score:
    mlb_id: str
    niche: str
    score: float
    breakdown: dict[str, float]  # pontos de cada critério, já ponderados


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def normalized_criteria(offer: Offer, targets: Targets, now: datetime) -> dict[str, float]:
    age_hours = (now - offer.collected_at).total_seconds() / 3600
    rating = 0.0
    if offer.rating is not None:
        rating = _clamp((offer.rating - targets.rating_floor) / (5 - targets.rating_floor))
    sold = 0.0
    if offer.sold_count:
        sold = _clamp(math.log1p(offer.sold_count) / math.log1p(targets.sold_count))
    return {
        "commission_pct": _clamp(offer.commission_pct / targets.commission_pct),
        "discount_pct": _clamp(offer.discount_pct / targets.discount_pct),
        "commission_brl": _clamp(offer.commission_brl / targets.commission_brl),
        "rating": rating,
        "sold_count": sold,
        "freshness": _clamp(1 - age_hours / targets.freshness_hours),
        "free_shipping": float(offer.free_shipping),
        "full": float(offer.full),
    }


def score_offer(offer: Offer, niche: NicheConfig, now: datetime) -> Score:
    weights = niche.weights.model_dump()
    total = sum(weights.values())
    norm = normalized_criteria(offer, niche.targets, now)
    points = {k: weights[k] / total * 100 * norm[k] for k in weights}
    return Score(
        mlb_id=offer.mlb_id,
        niche=niche.name,
        score=round(sum(points.values()), 1),
        breakdown={k: round(v, 1) for k, v in points.items()},
    )
