"""Processo principal: API da extensão + bot do Telegram + jobs, no mesmo loop asyncio."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
import uvicorn

from . import db
from .api.app import ApiState, create_app
from .approval.bot import BotDeps, build_application
from .config import AppConfig
from .creative.image import fetch_product_image
from .jobs import make_jobs
from .models import utcnow
from .publisher.cardhost import CardHost
from .publisher.telegram import TelegramSender
from .publisher.whatsapp import WhatsAppSender
from .scheduler import build_scheduler
from .settings import Settings
from .winops import keep_awake

log = logging.getLogger("ofertinhas")
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "text"


def setup_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(logs / "ofertinhas.log", maxBytes=2_000_000,
                                       backupCount=5, encoding="utf-8")
    console = logging.StreamHandler()
    for handler in (file_handler, console):
        handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [file_handler, console]
    logging.getLogger("httpx").setLevel(logging.WARNING)  # não logar URLs com o token do bot


def whatsapp_sender(settings: Settings, http: httpx.AsyncClient) -> WhatsAppSender | None:
    if not (settings.whatsmiau_api_key and settings.whatsmiau_instance):
        return None
    return WhatsAppSender(http, settings.whatsmiau_base_url, settings.whatsmiau_api_key,
                          settings.whatsmiau_instance)


def card_host(settings: Settings, http: httpx.AsyncClient) -> CardHost | None:
    if not (settings.r2_account_id and settings.r2_bucket and settings.r2_public_url
            and settings.r2_api_token):
        return None
    return CardHost(http, settings.r2_account_id, settings.r2_bucket, settings.r2_api_token,
                    settings.r2_public_url)


async def run(settings: Settings, cfg: AppConfig, dry_run: bool) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(settings.data_dir / "ofertinhas.db")
    http = httpx.AsyncClient()
    telegram = TelegramSender(http, settings.telegram_bot_token)
    whatsapp = whatsapp_sender(settings, http)

    async def notify(text: str) -> None:
        try:
            await telegram.send_message(settings.admin_chat_id, text)
        except Exception:
            log.exception("não consegui avisar o admin: %s", text)

    async def fetch_image(url):
        return await fetch_product_image(http, url)

    bot_deps = BotDeps(conn=conn, cfg=cfg, admin_chat_id=settings.admin_chat_id)
    application = build_application(settings.telegram_bot_token, bot_deps)
    jobs = make_jobs(
        conn=conn, cfg=cfg, data_dir=settings.data_dir, templates_dir=TEMPLATES_DIR,
        bot=application.bot, telegram=telegram, whatsapp=whatsapp,
        cards=card_host(settings, http), fetch_image=fetch_image, notify=notify,
        admin_chat_id=settings.admin_chat_id, dry_run=dry_run,
    )
    scheduler = build_scheduler(jobs, conn, notify, utcnow)
    server = uvicorn.Server(uvicorn.Config(
        create_app(ApiState(settings=settings, conn=conn, cfg=cfg, notify=notify)),
        host="127.0.0.1", port=settings.api_port, log_level="warning",
    ))

    keep_awake(True)
    try:
        async with application:
            await application.start()
            await application.updater.start_polling()
            scheduler.start()
            mode = "🧪 MODO DE TESTE: todo post vem só para este chat" if dry_run else "posts reais"
            if dry_run or not cfg.whatsapp_enabled:
                wa_state = "travado"
            else:
                wa_state = "ligado" if whatsapp else "sem chave da WhatsMiau no .env"
            await notify(f"✅ Ofertinhas ligado ({mode}; WhatsApp {wa_state}).")
            log.info("Ofertinhas rodando: API em 127.0.0.1:%s, %s", settings.api_port, mode)
            await server.serve()  # até Ctrl+C
            scheduler.shutdown(wait=False)
            await application.updater.stop()
            await application.stop()
    finally:
        keep_awake(False)
        await http.aclose()
        conn.close()
