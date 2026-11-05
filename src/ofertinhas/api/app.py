"""API HTTP local usada só pela extensão do navegador.

Escuta em 127.0.0.1 e exige o header `X-Ofertinhas-Token` em todas as rotas. Sem token
configurado no `.env`, recusa tudo.
"""

import json
import secrets
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .. import __version__, db
from ..affiliate.links import LinkError, apply_link_result, next_link_request
from ..alerts import notify_throttled
from ..collector.amazon import SEARCH_PATH as AMAZON_SEARCH_PATH
from ..collector.amazon import collect_requests, parse_deals
from ..collector.categories import ROOT_CATEGORIES
from ..collector.parsers import parse_hub_search
from ..config import AppConfig
from ..models import utcnow
from ..pipeline import ingest_offers, niche_configs
from ..roas import earnings_request, parse_daily, save_earnings
from ..settings import Settings
from ..status import LAST_COLLECT_KEY, last_collect
from ..stock import collect_now, group_stock, niches_needing_links

TOKEN_HEADER = "X-Ofertinhas-Token"
ADMIN_HEADER = "X-Ofertinhas-Admin"
PORTAL_URL = "https://www.mercadolivre.com.br/afiliados/hub?is_affiliate=true"
AMAZON_LAST_KEY = "amazon:last_collect"
SEARCH_URL = (
    "https://www.mercadolivre.com.br/affiliate-program/api/hub/search"
    "?is_affiliate=true&device=desktop"
)
SEARCH_PATH = "/affiliate-program/api/hub/search"
ROTATION_KEY = "collector:rotation"
UNKNOWN_FORMAT_EVERY = timedelta(hours=1)
ALERT_EVERY = timedelta(minutes=30)


@dataclass
class ApiState:
    settings: Settings
    conn: sqlite3.Connection
    cfg: AppConfig
    notify: Callable[[str], Awaitable[None]]  # mensagem para o admin no Telegram
    clock: Callable[[], datetime] = field(default=utcnow)
    # (nome, json) → onde ficou; sem isso, grava em data_dir/unparsed (na nuvem, vai ao R2)
    save_unparsed: Callable[[str, str], Awaitable[str]] | None = None
    dry_run: bool = False  # o estoque é contado no ritmo do modo em que os posts saem
    build: dict | None = None  # commit e hash do config (ver buildinfo)


class RawCapture(BaseModel):
    url: str
    request_body: dict[str, Any] | None = None
    status: int = 200
    body: Any = None


class LinkReport(BaseModel):
    mlb_id: str
    response: dict[str, Any] | None = None
    error: str | None = None


class EarningsReport(BaseModel):
    since: str  # AAAA-MM-DD
    until: str  # exclusivo
    body: dict[str, Any]


class Alert(BaseModel):
    reason: str
    url: str | None = None


def _check(token: str | None, expected: str | None) -> None:
    if not expected or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="token inválido")


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
        _check(token, state.settings.extension_token)

    async def require_admin(
        token: str | None = Header(default=None, alias=ADMIN_HEADER),
    ) -> None:
        """Rotas de admin: só o ADMIN_TOKEN; sem ele configurado, recusa tudo."""
        _check(token, state.settings.admin_token)

    router = APIRouter(dependencies=[Depends(require_token)])
    conn = state.conn

    async def save_unparsed(name: str, text: str) -> str:
        if state.save_unparsed is not None:
            return await state.save_unparsed(name, text)
        folder = state.settings.data_dir / "unparsed"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
        return name

    @router.get("/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__, "build": state.build}

    def rotate(all_ids: list[str], advance: bool) -> list[str]:
        """Próximas `categories_per_cycle` categorias; só a coleta faz o rodízio andar."""
        size = state.cfg.collector.categories_per_cycle
        if not all_ids or size >= len(all_ids):
            return all_ids
        offset = db.get_setting(conn, ROTATION_KEY, 0) % len(all_ids)
        if advance:
            db.set_setting(conn, ROTATION_KEY, (offset + size) % len(all_ids))
        return [all_ids[(offset + i) % len(all_ids)] for i in range(size)]

    def amazon_requests(now) -> dict | None:
        src = state.cfg.sources.amazon
        if src is None:
            return None
        last = db.get_setting(conn, AMAZON_LAST_KEY)
        if last and now - datetime.fromisoformat(last) < timedelta(minutes=src.every_min):
            return None
        db.set_setting(conn, AMAZON_LAST_KEY, now.isoformat())
        paused = {n for n, c in niche_configs(conn, state.cfg).items() if c.paused}
        return {
            "requests": collect_requests(src, state.cfg.collector_categories(paused)),
            "gap_s": list(state.cfg.collector.request_gap_s),
        }

    @router.get("/ext/config")
    async def ext_config(purpose: str | None = None) -> dict:
        col = state.cfg.collector
        pause = db.get_setting(conn, db.EXTENSION_PAUSED_KEY)
        paused_niches = {n for n, c in niche_configs(conn, state.cfg).items() if c.paused}
        collecting = purpose == "collect"
        ids = rotate(state.cfg.collector_categories(paused_niches), advance=collecting)
        now = state.clock()
        if collecting:
            db.set_setting(conn, LAST_COLLECT_KEY, now.isoformat())
        categories = [{"id": c, "name": ROOT_CATEGORIES[c]} for c in ids]
        if col.include_unfiltered:
            categories.append(None)
        return {
            "paused": pause is not None,
            "pause_reason": pause["reason"] if pause else None,
            "window": [t.strftime("%H:%M") for t in col.window] if col.window else None,
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
            # pedido de coleta fora de hora (estoque curto); a extensão confere a cada 30 s
            "collect_now": not collecting
            and collect_now(
                conn,
                state.cfg,
                group_stock(conn, state.cfg, now, state.dry_run),
                now,
                last_collect(conn),
            ),
            "collect_now_gap_min": col.collect_now_gap_min,
            # relatório de ganhos do portal (ROAS no status): a extensão lê quando vier
            "earnings": earnings_request(conn, now),
            # Ofertas do Dia da Amazon: lista de leituras quando estiver na hora (ver amazon.py)
            "amazon": amazon_requests(now) if collecting else None,
        }

    def ingest(offers, now) -> dict:
        return ingest_offers(conn, state.cfg, offers, now)

    @router.post("/ext/raw")
    async def ext_raw(capture: RawCapture) -> dict:
        amazon = state.cfg.sources.amazon
        if amazon and AMAZON_SEARCH_PATH in capture.url:
            now = state.clock()
            if not isinstance(capture.body, dict) or "products" not in capture.body:
                saved = await save_unparsed(
                    f"amazon-{now:%Y%m%d-%H%M%S-%f}.json",
                    json.dumps(capture.model_dump(), ensure_ascii=False),
                )
                await notify_throttled(
                    conn,
                    state.notify,
                    "amazon-format",
                    f"⚠️ A Amazon mudou o formato das ofertas. Salvo em {saved}.",
                    now,
                    UNKNOWN_FORMAT_EVERY,
                )
                return {"parsed": 0, "unknown": True}
            department = (capture.request_body or {}).get("department")
            return ingest(parse_deals(capture.body, amazon, department, now=now), now)
        if SEARCH_PATH not in capture.url:
            return {"ignored": True}
        now = state.clock()
        offers = parse_hub_search(capture.request_body, capture.body, now=now)
        if offers is None:
            saved = await save_unparsed(
                f"{now.strftime('%Y%m%d-%H%M%S-%f')}.json",
                json.dumps(capture.model_dump(), ensure_ascii=False),
            )
            await notify_throttled(
                conn,
                state.notify,
                "unknown-format",
                f"⚠️ O portal mudou o formato da busca. Resposta salva em {saved}; "
                "grave um HAR novo para eu atualizar o leitor.",
                now,
                UNKNOWN_FORMAT_EVERY,
            )
            return {"parsed": 0, "unknown": True}
        return ingest(offers, now)

    @router.get("/ext/link-requests")
    async def ext_link_requests() -> dict:
        tag = state.settings.ml_affiliate_tag
        if not tag:
            await notify_throttled(
                conn,
                state.notify,
                "missing-tag",
                "⚠️ Há ofertas aprovadas, mas falta ML_AFFILIATE_TAG no .env para gerar links.",
                state.clock(),
                UNKNOWN_FORMAT_EVERY,
            )
            return {"request": None, "error": "ML_AFFILIATE_TAG ausente no .env"}
        now = state.clock()
        needy = niches_needing_links(conn, state.cfg, now, state.dry_run)
        return {"request": next_link_request(conn, tag, now, niches=needy)}

    @router.post("/ext/earnings")
    async def ext_earnings(report: EarningsReport) -> dict:
        try:
            rows = parse_daily(
                report.body, date.fromisoformat(report.since), date.fromisoformat(report.until)
            )
        except (KeyError, TypeError, ValueError) as e:
            name = f"earnings-{state.clock():%Y%m%d-%H%M%S}.json"
            where = await save_unparsed(name, json.dumps(report.body, ensure_ascii=False))
            raise HTTPException(
                422, f"relatório de ganhos inesperado ({e}); salvo em {where}"
            ) from e
        return {"saved": save_earnings(conn, rows, state.clock())}

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
        db.set_setting(
            conn,
            db.EXTENSION_PAUSED_KEY,
            {"reason": alert.reason, "url": alert.url, "at": now.isoformat()},
        )
        await notify_throttled(
            conn,
            state.notify,
            f"extension:{alert.reason}",
            f"⏸️ A extensão parou: {alert.reason}. Resolva no Brave e use /retomar coleta "
            "ou o botão Retomar da extensão.",
            now,
            ALERT_EVERY,
        )
        return {"paused": True}

    @router.get("/ext/stock")
    async def ext_stock() -> dict:
        """Estoque de cada grupo e até quando ele dura, para o popup da extensão."""
        now = state.clock()
        groups = group_stock(conn, state.cfg, now, state.dry_run)
        return {
            "collect_now": collect_now(conn, state.cfg, groups, now, last_collect(conn)),
            "ready": sum(g.ready for g in groups),
            "waiting_links": sum(g.waiting_links for g in groups),
            "reserve": sum(g.reserve for g in groups),
            "groups": [g.as_dict() for g in groups],
        }

    @router.post("/ext/resume")
    async def ext_resume() -> dict:
        db.set_setting(conn, db.EXTENSION_PAUSED_KEY, None)
        return {"paused": False}

    app.include_router(router)
    app.state.ofertinhas = state
    app.state.require_token = require_token
    app.state.require_admin = require_admin  # para as rotas /admin/* da nuvem
    return app
