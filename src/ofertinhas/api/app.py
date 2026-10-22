"""API HTTP local usada só pela extensão do navegador.

Escuta em 127.0.0.1 e exige o header `X-Ofertinhas-Token` em todas as rotas. Sem token
configurado no `.env`, recusa tudo.
"""

import secrets
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import AppConfig
from ..settings import Settings

TOKEN_HEADER = "X-Ofertinhas-Token"


@dataclass
class ApiState:
    settings: Settings
    conn: sqlite3.Connection
    cfg: AppConfig
    notify: Callable[[str], Awaitable[None]]  # mensagem para o admin no Telegram


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

    @router.get("/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__}

    app.include_router(router)
    app.state.ofertinhas = state
    return app
