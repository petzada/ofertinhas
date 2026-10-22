"""API HTTP local usada só pela extensão do navegador.

Escuta em 127.0.0.1 e exige o header `X-Ofertinhas-Token` em todas as rotas. Sem token
configurado no `.env`, recusa tudo.
"""

import json
import secrets
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .. import __version__, db
from ..affiliate.links import LinkError, apply_link_result, next_link_request
from ..alerts import notify_throttled
from ..collector.categories import ROOT_CATEGORIES
from ..collector.parsers import parse_hub_search
from ..config import AppConfig
from ..models import utcnow
from ..pipeline import niche_configs, score_and_route
from ..settings import Settings

TOKEN_HEADER = "X-Ofertinhas-Token"
PORTAL_URL = "https://www.mercadolivre.com.br/afiliados/hub?is_affiliate=true"
SEARCH_URL = (
    "https://www.mercadolivre.com.br/affiliate-program/api/hub/search"
    "?is_affiliate=true&device=desktop"
)
SEARCH_PATH = "/affiliate-program/api/hub/search"
UNKNOWN_FORMAT_EVERY = timedelta(hours=1)
ALERT_EVERY = timedelta(minutes=30)


@dataclass
class ApiState:
    settings: Settings
    conn: sqlite3.Connection
    cfg: AppConfig
    notify: Callable[[str], Awaitable[None]]  # mensagem para o admin no Telegram
    clock: Callable[[], datetime] = field(default=utcnow)


class RawCapture(BaseModel):
    url: str
    request_body: dict[str, Any] | None = None
    status: int = 200
    body: Any = None


class LinkReport(BaseModel):
    mlb_id: str
    response: dict[str, Any] | None = None
    error: str | None = None


class Alert(BaseModel):
    reason: str
    url: str | None = None


def create_app(state: ApiState) -> FastAPI:
    app = FastAPI(title="Ofertinhas", docs_url=None, redoc_url=None, openapi_url=None)
    if state.settings.extension_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[state.settings.extension_origin],
            allow_methods=["GET", "POST"],
            allow_headers=[TOKEN_HEADER, "Content-Type"],
        )

    async def require_token(
        token: str | None = Header(default=None, alias=TOKEN_HEADER),
    ) -> None:
        expected = state.settings.extension_token
        if not expected or not token or not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="token inválido")

    router = APIRouter(dependencies=[Depends(require_token)])
    conn = state.conn

    @router.get("/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__}

    @router.get("/ext/config")
    async def ext_config() -> dict:
        col = state.cfg.collector
        pause = db.get_setting(conn, db.EXTENSION_PAUSED_KEY)
        paused_niches = {n for n, c in niche_configs(conn, state.cfg).items() if c.paused}
        categories = [
            {"id": c, "name": ROOT_CATEGORIES[c]}
            for c in state.cfg.collector_categories(paused_niches)
        ]
        if col.include_unfiltered:
            categories.append(None)
        return {
            "paused": pause is not None,
            "pause_reason": pause["reason"] if pause else None,
            "window": [t.strftime("%H:%M") for t in col.window],
            "collect_every_min": col.every_min,
            "collect_jitter_min": col.jitter_min,
            "pages_per_category": col.pages_per_category,
            "page_size": 18,
            "request_gap_s": list(col.request_gap_s),
            "max_links_per_hour": col.max_links_per_hour,
            "link_gap_s": list(col.link_gap_s),
            "portal_url": PORTAL_URL,
            "search_url": SEARCH_URL,
            "categories": categories,
        }

    @router.post("/ext/raw")
    async def ext_raw(capture: RawCapture) -> dict:
        if SEARCH_PATH not in capture.url:
            return {"ignored": True}
        now = state.clock()
        offers = parse_hub_search(capture.request_body, capture.body, now=now)
        if offers is None:
            folder = state.settings.data_dir / "unparsed"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{now.strftime('%Y%m%d-%H%M%S-%f')}.json"
            path.write_text(json.dumps(capture.model_dump(), ensure_ascii=False), encoding="utf-8")
            await notify_throttled(
                conn, state.notify, "unknown-format",
                f"⚠️ O portal mudou o formato da busca. Resposta salva em {path.name}; "
                "grave um HAR novo para eu atualizar o leitor.",
                now, UNKNOWN_FORMAT_EVERY,
            )
            return {"parsed": 0, "unknown": True}
        new = sum(db.upsert_offer(conn, o, now=now) for o in offers)
        routed = score_and_route(conn, state.cfg, [o.mlb_id for o in offers], now=now)
        return {
            "parsed": len(offers),
            "new": new,
            "routed": {cand_state.value: n for cand_state, n in routed.items()},
        }

    @router.get("/ext/link-requests")
    async def ext_link_requests() -> dict:
        tag = state.settings.ml_affiliate_tag
        if not tag:
            await notify_throttled(
                conn, state.notify, "missing-tag",
                "⚠️ Há ofertas aprovadas, mas falta ML_AFFILIATE_TAG no .env para gerar links.",
                state.clock(), UNKNOWN_FORMAT_EVERY,
            )
            return {"request": None, "error": "ML_AFFILIATE_TAG ausente no .env"}
        return {"request": next_link_request(conn, tag, state.clock())}

    @router.post("/ext/links")
    async def ext_links(report: LinkReport) -> dict:
        try:
            gave_up = apply_link_result(conn, report.mlb_id, report.response, report.error)
        except LinkError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        if gave_up:
            await state.notify(
                f"⚠️ Não consegui gerar o link de {report.mlb_id} depois de 3 tentativas "
                f"(último erro: {report.error or 'resposta inválida'}). "
                "A oferta foi deixada de lado."
            )
        offer = db.get_offer(conn, report.mlb_id)
        return {"ok": offer.affiliate_link is not None}

    @router.post("/ext/alert")
    async def ext_alert(alert: Alert) -> dict:
        now = state.clock()
        db.set_setting(conn, db.EXTENSION_PAUSED_KEY,
                       {"reason": alert.reason, "url": alert.url, "at": now.isoformat()})
        await notify_throttled(
            conn, state.notify, f"extension:{alert.reason}",
            f"⏸️ A extensão parou: {alert.reason}. Resolva no Brave e use /retomar coleta "
            "ou o botão Retomar da extensão.",
            now, ALERT_EVERY,
        )
        return {"paused": True}

    @router.post("/ext/resume")
    async def ext_resume() -> dict:
        db.set_setting(conn, db.EXTENSION_PAUSED_KEY, None)
        return {"paused": False}

    app.include_router(router)
    app.state.ofertinhas = state
    return app
