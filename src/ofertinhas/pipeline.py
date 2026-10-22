"""Etapas do ciclo de vida das ofertas; cada uma lê o estado do banco e grava o próximo."""

import dataclasses
import logging
import sqlite3
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from . import db
from .approval.actions import custom_caption
from .config import AppConfig, NicheConfig, Profile
from .creative.image import render_card
from .creative.text import caption_values, fill, render_caption
from .creative.themes import theme_for
from .models import ACTIVE_STATES, COOLDOWN_STATES, Candidate, CandidateState, Offer, utcnow
from .ranking.filters import passes
from .ranking.niches import match_niches
from .ranking.scoring import Score, score_offer

log = logging.getLogger(__name__)


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


async def render_linked(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    cards_dir: Path,
    templates_dir: Path,
    fetch_image: Callable[[str | None], Awaitable[Image.Image | None]],
    now: datetime | None = None,
) -> int:
    """Gera legenda e card das candidatas com link (`linked` → `rendered`).

    A legenda é uma só para Telegram e WhatsApp (formato neutro) e o rodízio de modelos é
    por nicho. Uma candidata com problema é registrada no log e não trava as outras.
    """
    cards_dir.mkdir(parents=True, exist_ok=True)
    rendered = 0
    for cand in db.candidates_by_state(conn, CandidateState.LINKED):
        try:
            offer = db.get_offer(conn, cand.mlb_id)
            template = (
                cfg.for_niche(cand.niche).template if cand.niche in cfg.niches else cand.niche
            )
            custom = custom_caption(conn, cand.mlb_id, cand.niche)
            if custom:
                caption = fill(custom, caption_values(offer))
            else:
                caption = render_caption(conn, offer, template, cand.niche, templates_dir, now=now)
            png = render_card(offer, theme_for(cand.niche), await fetch_image(offer.image_url))
            path = cards_dir / f"{cand.mlb_id}-{cand.niche}.png"
            path.write_bytes(png)
        except Exception:
            log.exception("falha ao gerar criativo de %s/%s", cand.mlb_id, cand.niche)
            continue
        db.save_candidate(
            conn,
            dataclasses.replace(
                cand, state=CandidateState.RENDERED, caption=caption, card_path=str(path)
            ),
        )
        rendered += 1
    return rendered
