"""Decisões do admin sobre as ofertas, independentes do Telegram.

Cada função devolve a mensagem para o admin ou levanta `ActionError` com o motivo.
"""

import dataclasses
import sqlite3
from datetime import datetime

from .. import db
from ..config import AppConfig
from ..creative.text import caption_values, fill
from ..models import Candidate, CandidateState, Offer
from ..ranking.scoring import score_offer

S = CandidateState
# Já passaram da aprovação: aprovar de novo não muda nada.
AFTER_APPROVAL = {S.APPROVED, S.LINKED, S.LINK_FAILED, S.RENDERED, S.QUEUED, S.POSTED}
LINK_LINE = "\n\n👉 {link}"


class ActionError(Exception):
    pass


def _candidate(conn: sqlite3.Connection, mlb_id: str, niche: str) -> Candidate:
    cand = db.get_candidate(conn, mlb_id, niche)
    if cand is None:
        raise ActionError(f"Oferta {mlb_id} não encontrada no nicho {niche}.")
    return cand


def approve(conn: sqlite3.Connection, mlb_id: str, niche: str, now: datetime) -> str:
    cand = _candidate(conn, mlb_id, niche)
    if cand.state in AFTER_APPROVAL:
        return "Essa oferta já foi aprovada."
    if cand.state is not S.PENDING:
        raise ActionError(f"Não dá para aprovar: a oferta está como {cand.state.value}.")
    db.save_candidate(conn, dataclasses.replace(cand, state=S.APPROVED, decided_at=now))
    return "✅ Aprovada. O link de afiliado será gerado pela extensão."


def reject(conn: sqlite3.Connection, mlb_id: str, niche: str, now: datetime) -> str:
    cand = _candidate(conn, mlb_id, niche)
    if cand.state is S.REJECTED:
        return "Essa oferta já foi rejeitada."
    if cand.state is not S.PENDING:
        raise ActionError(f"Não dá para rejeitar: a oferta está como {cand.state.value}.")
    db.save_candidate(conn, dataclasses.replace(cand, state=S.REJECTED, decided_at=now))
    return "❌ Rejeitada."


def _caption_key(mlb_id: str, niche: str) -> str:
    return f"caption:{mlb_id}:{niche}"


def set_custom_caption(conn: sqlite3.Connection, mlb_id: str, niche: str, text: str) -> str:
    """Grava um texto próprio para a oferta; pode usar as mesmas variáveis dos modelos."""
    _candidate(conn, mlb_id, niche)
    template = text.strip()
    if "{link}" not in template:
        template += LINK_LINE
    sample = Offer(
        mlb_id=mlb_id, title="x", price=1.0, commission_pct=1.0, category_path=("x",),
        permalink="x", affiliate_link="https://mercadolivre.com/sec/x",
    )
    try:
        fill(template, caption_values(sample))
    except (ValueError, IndexError) as e:
        raise ActionError(f"Texto inválido: {e}") from None
    db.set_setting(conn, _caption_key(mlb_id, niche), template)
    return "✏️ Texto salvo. Ele será usado no lugar do modelo."


def custom_caption(conn: sqlite3.Connection, mlb_id: str, niche: str) -> str | None:
    return db.get_setting(conn, _caption_key(mlb_id, niche))


def change_niche(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    mlb_id: str,
    from_niche: str,
    to_niche: str,
    now: datetime,
) -> Candidate:
    from ..pipeline import niche_configs  # evita import circular

    cand = _candidate(conn, mlb_id, from_niche)
    if cand.state is not S.PENDING:
        raise ActionError("Só dá para trocar o nicho de uma oferta pendente.")
    if to_niche == from_niche or to_niche not in cfg.niches:
        raise ActionError(f"Nicho inválido: {to_niche}.")
    offer = db.get_offer(conn, mlb_id)
    score = score_offer(offer, niche_configs(conn, cfg)[to_niche], now)
    new = Candidate(
        mlb_id=mlb_id, niche=to_niche, state=S.PENDING, score=score.score,
        breakdown=score.breakdown, ref_price=offer.price, decided_at=now,
        notified_at=cand.notified_at,
    )
    db.save_candidate(conn, new)
    db.delete_candidate(conn, mlb_id, from_niche)
    return new


def force_top(conn: sqlite3.Connection, niche: str, now: datetime) -> Candidate | None:
    """Aprova a melhor pendente do nicho, ignorando a nota de corte (o ritmo continua valendo)."""
    pending = db.candidates_by_state(conn, S.PENDING, niche=niche)
    if not pending:
        return None
    best = dataclasses.replace(pending[0], state=S.APPROVED, decided_at=now)
    db.save_candidate(conn, best)
    return best
