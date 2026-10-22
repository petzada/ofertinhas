"""Pedidos de link de afiliado para a extensão e validação do que ela devolve.

A extensão chama o `createLink` do portal de dentro da aba logada; o backend só monta o
corpo (igual ao que o portal envia) e confere a resposta. Ver docs/notes/portal-mapping.md.
"""

import dataclasses
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from .. import db
from ..models import CandidateState, Offer

S = CandidateState
CREATE_LINK_URL = "https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink"
SHORT_LINK = re.compile(r"^https://meli\.la/[A-Za-z0-9]+$")
REQUEST_COOLDOWN = timedelta(minutes=10)
MAX_ATTEMPTS = 3


class LinkError(Exception):
    pass


def _bare(url: str) -> str:
    """URL sem esquema, query e fragmento: `www.mercadolivre.com.br/.../p/MLB1`."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return f"{parsed.netloc}{parsed.path}"


def build_create_link_body(offer: Offer, tag: str) -> dict[str, Any]:
    return {
        "itemId": offer.mlb_id,
        "type": offer.item_type,
        "extraCommission": "true" if offer.extra_commission else "false",
        "itemAddToList": offer.mlb_id,
        "tag": tag,
        "urls": [_bare(offer.permalink)],
        "buyBoxWinner": offer.mlb_id,
    }


def parse_create_link_response(offer: Offer, response: dict[str, Any]) -> tuple[str, str | None]:
    """Devolve (link curto, código de busca) ou levanta `LinkError` com o motivo."""
    if response.get("total_error", 1) != 0 or not response.get("urls"):
        raise LinkError(f"createLink sem sucesso: {response.get('total_error')} erro(s)")
    url = response["urls"][0]
    short = url.get("short_url", "")
    if not SHORT_LINK.match(short):
        raise LinkError(f"link em formato inesperado: {short!r}")
    if _bare(url.get("origin_url", "")) != _bare(offer.permalink):
        raise LinkError("o link gerado aponta para outro produto")
    return short, url.get("regex")


def _promote(conn: sqlite3.Connection, mlb_id: str, to: CandidateState) -> None:
    for cand in db.candidates_for_offer(conn, mlb_id):
        if cand.state is S.APPROVED:
            db.save_candidate(conn, dataclasses.replace(cand, state=to))


def next_link_request(conn: sqlite3.Connection, tag: str, now: datetime) -> dict | None:
    """Próximo pedido para a extensão ou None.

    Primeiro as que o admin aprovou no bot (o card foi mostrado), depois as automáticas; dentro
    de cada grupo, a maior nota. Aprovadas cujo produto já tem link (de outro nicho) avançam
    direto, sem pedido.
    """
    for cand in db.candidates_by_state(conn, S.APPROVED):
        offer = db.get_offer(conn, cand.mlb_id)
        if offer.affiliate_link:
            _promote(conn, cand.mlb_id, S.LINKED)
    approved = db.candidates_by_state(conn, S.APPROVED)  # já ordenadas pela nota
    approved.sort(key=lambda c: c.notified_at is None)  # sort estável: as suas na frente
    for cand in approved:
        offer = db.get_offer(conn, cand.mlb_id)
        if offer.link_requested_at and now - offer.link_requested_at < REQUEST_COOLDOWN:
            continue
        db.mark_link_requested(conn, offer.mlb_id, now)
        return {
            "mlb_id": offer.mlb_id,
            "url": CREATE_LINK_URL,
            "body": build_create_link_body(offer, tag),
        }
    return None


def apply_link_result(
    conn: sqlite3.Connection,
    mlb_id: str,
    response: dict[str, Any] | None,
    error: str | None,
) -> bool:
    """Registra o resultado; devolve True quando o produto desistiu de vez (`link_failed`)."""
    offer = db.get_offer(conn, mlb_id)
    if offer is None:
        raise LinkError(f"oferta {mlb_id} desconhecida")
    if response is not None and error is None:
        try:
            short, code = parse_create_link_response(offer, response)
        except LinkError as e:
            error = str(e)
        else:
            db.set_affiliate_link(conn, mlb_id, short, search_code=code)
            _promote(conn, mlb_id, S.LINKED)
            return False
    if db.record_link_failure(conn, mlb_id) >= MAX_ATTEMPTS:
        _promote(conn, mlb_id, S.LINK_FAILED)
        return True
    return False
