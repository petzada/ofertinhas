"""O backend inteiro dentro do Durable Object: API da extensão, webhook do bot e jobs.

É o equivalente do `run.py`, com três trocas: o banco é o SQLite do Durable Object, os cards
ficam no R2 e o bot recebe updates por webhook. O relógio dos jobs é o Cron do Worker, que
chama `tick` a cada minuto.
"""

import logging
import secrets
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException, Request
from telegram import Bot

from .. import db
from ..api.app import ApiState, create_app
from ..approval.bot import BotDeps
from ..config import load_config
from ..creative.image import fetch_product_image
from ..jobs import guarded, make_jobs
from ..models import utcnow
from ..publisher.telegram import TelegramSender
from ..publisher.whatsapp import WhatsAppSender
from ..settings import Settings
from .cards import Bucket, R2CardHost, R2Cards
from .history import import_rows
from .webhook import handle_update

log = logging.getLogger("ofertinhas")
WEBHOOK_HEADER = "X-Telegram-Bot-Api-Secret-Token"
EVERY_MINUTE = ("expire", "render", "publish", "notify_pending")
EXPIRE_EVERY_MIN = 15
LAST_TICK_KEY = "cron:last_tick"


def is_dry_run(env: Mapping[str, str]) -> bool:
    """Teste por padrão: só posta nos grupos com DRY_RUN=false explícito."""
    return (env.get("DRY_RUN") or "true").strip().lower() not in ("0", "false", "no", "nao")


class CloudBackend:
    def __init__(
        self,
        env: Mapping[str, str],
        conn,
        bucket: Bucket,
        bundle_dir: Path,
        http: httpx.AsyncClient,
        clock: Callable[[], datetime] = utcnow,
        bot: Bot | None = None,
    ):
        self.settings = settings = Settings.from_env(env)
        settings.require("EXTENSION_TOKEN", "TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID")
        self.conn = conn
        self.cfg = cfg = load_config(bundle_dir / "config.yaml")
        self.clock = clock
        self.dry_run = is_dry_run(env)
        self.webhook_secret = env.get("TELEGRAM_WEBHOOK_SECRET") or None
        self.bucket = bucket
        self.telegram = TelegramSender(http, settings.telegram_bot_token)
        self.whatsapp = None
        if settings.whatsmiau_api_key and settings.whatsmiau_instance:
            self.whatsapp = WhatsAppSender(http, settings.whatsmiau_base_url,
                                           settings.whatsmiau_api_key, settings.whatsmiau_instance)
        card_host = R2CardHost(bucket, settings.r2_public_url) if settings.r2_public_url else None
        self.bot = bot or Bot(settings.telegram_bot_token)
        self._bot_ready = bot is not None
        self.bot_deps = BotDeps(conn=conn, cfg=cfg, admin_chat_id=settings.admin_chat_id,
                                clock=clock)

        async def fetch_image(url):
            return await fetch_product_image(http, url)

        self.jobs = make_jobs(
            conn=conn, cfg=cfg, templates_dir=bundle_dir / "templates", bot=self.bot,
            telegram=self.telegram, whatsapp=self.whatsapp, cards=card_host,
            card_store=R2Cards(bucket), fetch_image=fetch_image, notify=self.notify,
            admin_chat_id=settings.admin_chat_id, dry_run=self.dry_run, clock=clock,
        )
        self._running: set[str] = set()
        self.app = self._build_app()

    async def notify(self, text: str) -> None:
        try:
            await self.telegram.send_message(self.settings.admin_chat_id, text)
        except Exception:
            log.exception("não consegui avisar o admin: %s", text)

    async def _ready_bot(self) -> Bot:
        if not self._bot_ready:
            await self.bot.initialize()
            self._bot_ready = True
        return self.bot

    async def _save_unparsed(self, name: str, text: str) -> str:
        key = f"unparsed/{name}"
        await self.bucket.put(key, text.encode(), "application/json")
        return f"R2 {key}"

    def _build_app(self):
        app = create_app(ApiState(settings=self.settings, conn=self.conn, cfg=self.cfg,
                                  notify=self.notify, clock=self.clock,
                                  save_unparsed=self._save_unparsed))

        @app.post("/tg/{secret}")
        async def telegram_webhook(secret: str, request: Request) -> dict:
            expected = self.webhook_secret
            header = request.headers.get(WEBHOOK_HEADER, "")
            if not expected or not (secrets.compare_digest(secret, expected)
                                    and secrets.compare_digest(header, expected)):
                raise HTTPException(status_code=404)
            update = await request.json()
            try:
                await handle_update(update, await self._ready_bot(), self.bot_deps)
            except Exception:  # o Telegram reenviaria o mesmo update sem parar
                log.exception("falha ao tratar o update %s", update.get("update_id"))
            return {"ok": True}

        @app.get("/admin/status", dependencies=[Depends(app.state.require_token)])
        async def admin_status() -> dict:
            return {"dry_run": self.dry_run, "last_tick": db.get_setting(self.conn, LAST_TICK_KEY),
                    "candidates": db.count_candidates(self.conn)}

        @app.post("/admin/import", dependencies=[Depends(app.state.require_token)])
        async def admin_import(request: Request) -> dict:
            return {"imported": import_rows(self.conn, await request.json())}

        return app

    async def tick(self) -> list[str]:
        """Roda os jobs do minuto; um job que ainda está rodando (de um minuto anterior) é
        pulado, como o `max_instances=1` do APScheduler no PC."""
        now = self.clock()
        db.set_setting(self.conn, LAST_TICK_KEY, {"at": now.isoformat(), "ran": [],
                                                   "skipped": sorted(self._running)})
        due = [n for n in EVERY_MINUTE if n != "expire" or now.minute % EXPIRE_EVERY_MIN == 0]
        ran = []
        for name in due:
            if name in self._running:
                continue
            self._running.add(name)
            try:
                await guarded(name, self._job(name), self.conn, self.notify, self.clock)()
                ran.append(name)
            finally:
                self._running.discard(name)
        db.set_setting(self.conn, LAST_TICK_KEY, {"at": now.isoformat(), "ran": ran,
                                                   "skipped": sorted(self._running)})
        return ran

    def _job(self, name: str):
        job = self.jobs[name]
        if name != "notify_pending":
            return job

        async def with_bot():  # os cards de aprovação saem pela PTB, que precisa do getMe
            await self._ready_bot()
            return await job()

        return with_bot
