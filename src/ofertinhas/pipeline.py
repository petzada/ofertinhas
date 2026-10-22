"""Etapas do ciclo de vida das ofertas; cada uma lê o estado do banco e grava o próximo."""

import sqlite3
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

from . import db
from .config import AppConfig, NicheConfig, Profile
from .models import ACTIVE_STATES, COOLDOWN_STATES, Candidate, CandidateState, Offer, utcnow
from .ranking.filters import passes
from .ranking.niches import match_niches
from .ranking.scoring import Score, score_offer


def niche_configs(conn: sqlite3.Connection, cfg: AppConfig) -> dict[str, NicheConfig]:
    """Config efetiva de cada nicho, com os overrides do bot aplicados."""
    return {n: cfg.for_niche(n, db.niche_overrides(conn, n)) for n in cfg.niche_names()}


def eligible_again(cand: Candidate | None, offer: Offer, rules: Profile, now: datetime) -> bool:
    if cand is None:
        return True
    if cand.state in ACTIVE_STATES:
        return False
    if cand.state in COOLDOWN_STATES:
        if now - cand.decided_at >= timedelta(days=rules.repost_cooldown_days):
            return True
        return offer.price <= cand.ref_price * (1 - rules.repost_price_drop_pct / 100)
    return True  # descartada ou expirada: pode ser ranqueada de novo


def decide(score: float, niche: NicheConfig) -> CandidateState:
    if score >= niche.auto_approve_at:
        return CandidateState.APPROVED
    if score >= niche.manual_review_at:
        return CandidateState.PENDING
    return CandidateState.DISCARDED


def score_and_route(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    mlb_ids: Iterable[str],
    now: datetime | None = None,
) -> Counter[CandidateState]:
    """Ranqueia as ofertas coletadas e decide o destino de cada uma por nicho.

    Sem `multi_niche`, a oferta vai só para o nicho de maior nota (empate: ordem da config)
    e fica bloqueada inteira enquanto estiver no fluxo ou em cooldown em qualquer nicho.
    """
    now = now or utcnow()
    all_niches = niche_configs(conn, cfg)
    active = [n for n in all_niches.values() if not n.paused]
    fallback_rules = Profile(**cfg.defaults)  # para candidatos de nichos removidos da config
    counts: Counter[CandidateState] = Counter()

    for offer in db.get_offers(conn, mlb_ids):
        existing = {c.niche: c for c in db.candidates_for_offer(conn, offer.mlb_id)}
        if not cfg.multi_niche and not all(
            eligible_again(c, offer, all_niches.get(c.niche, fallback_rules), now)
            for c in existing.values()
        ):
            continue

        scores: list[Score] = []
        for name in match_niches(offer, active):
            niche = all_niches[name]
            if not passes(offer, niche.filters)[0]:
                continue
            if not eligible_again(existing.get(name), offer, niche, now):
                continue
            scores.append(score_offer(offer, niche, now))
        if not scores:
            continue
        if not cfg.multi_niche:
            scores = [max(scores, key=lambda s: s.score)]

        for s in scores:
            state = decide(s.score, all_niches[s.niche])
            db.save_candidate(
                conn,
                Candidate(
                    mlb_id=offer.mlb_id,
                    niche=s.niche,
                    state=state,
                    score=s.score,
                    breakdown=s.breakdown,
                    ref_price=offer.price,
                    decided_at=now,
                ),
            )
            counts[state] += 1
    return counts
