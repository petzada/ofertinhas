"""Teste de um nicho nas ofertas já coletadas, sem decidir nem postar nada.

Mostra o que entraria no nicho (e se sairia automática, para aprovação ou descartada pela
regra de desconto e comissão) e o que ficaria de fora e por quê. Serve para ajustar
`categories`, `required_keywords` e `blocked_keywords` com produtos reais antes de ligar.
"""

import sqlite3
from collections import Counter
from datetime import datetime, timedelta

from . import db
from .config import NicheConfig
from .models import CandidateState
from .pipeline import checked_offer, decide
from .ranking.filters import passes
from .ranking.niches import match_niches
from .ranking.scoring import score_offer

DECISION = {CandidateState.APPROVED: "automática", CandidateState.PENDING: "para aprovar",
            CandidateState.DISCARDED: "descartada pela regra"}


def niche_preview(conn: sqlite3.Connection, niche: NicheConfig, now: datetime, days: float,
                  sample: int = 40) -> dict:
    since = now - timedelta(days=days)
    offers = db.offers_seen_since(conn, since)
    in_niche, reasons, decisions = 0, Counter(), Counter()
    matched: list[dict] = []
    left_out: list[dict] = []
    for offer in offers:
        if not match_niches(offer, [niche]):
            continue
        in_niche += 1
        ok, reason = passes(offer, niche.filters)
        if not ok:
            reasons[reason] += 1
            if len(left_out) < sample:
                left_out.append({"title": offer.title, "reason": reason})
            continue
        verdict = checked_offer(conn, offer, niche, now)
        state = decide(score_offer(verdict.offer, niche, now).score, niche, verdict.offer)
        decisions[DECISION[state]] += 1
        if len(matched) < sample:
            matched.append({"title": offer.title, "decision": DECISION[state],
                            "discount_pct": verdict.offer.discount_pct,
                            "commission_pct": offer.commission_pct})
    return {
        "days": days,
        "offers_seen": len(offers),
        "in_categories": in_niche,
        "matched": sum(decisions.values()),
        "decisions": dict(decisions),
        "left_out_by_reason": dict(reasons.most_common()),
        "matched_sample": matched,
        "left_out_sample": left_out,
    }
