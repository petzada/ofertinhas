"""Próxima oferta de cada grupo e expiração das que sumiram da coleta."""

import dataclasses
import sqlite3
from datetime import datetime, timedelta

from .. import db
from ..config import AppConfig, Profile
from ..models import Candidate, CandidateState

S = CandidateState
# Ainda não postadas e já aprovadas: se a oferta some da coleta, não vale mais a pena.
EXPIRABLE = (S.APPROVED, S.LINKED, S.RENDERED, S.QUEUED)


def next_for_niche(conn: sqlite3.Connection, niche: str) -> Candidate | None:
    ready = db.candidates_by_state(conn, S.RENDERED, niche=niche)
    return ready[0] if ready else None


def expire_stale(conn: sqlite3.Connection, cfg: AppConfig, now: datetime) -> int:
    from ..pipeline import niche_configs  # evita import circular

    rules = niche_configs(conn, cfg)
    fallback = Profile(**cfg.defaults)
    expired = 0
    for state in EXPIRABLE:
        for cand in db.candidates_by_state(conn, state):
            max_age = timedelta(hours=rules.get(cand.niche, fallback).max_offer_age_hours)
            offer = db.get_offer(conn, cand.mlb_id)
            if offer.last_seen_at is None or now - offer.last_seen_at > max_age:
                db.save_candidate(conn, dataclasses.replace(cand, state=S.EXPIRED))
                expired += 1
    return expired
