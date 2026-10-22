"""O backend inteiro dentro do Durable Object: API da extensão, webhook do bot e jobs.

É o equivalente do `run.py`, com três trocas: o banco é o SQLite do Durable Object, os cards
ficam no R2 e o bot recebe updates por webhook. O relógio dos jobs é o Cron do Worker, que
chama `tick` a cada minuto.
"""

import json
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
from ..publisher.publish import publish_due
from ..publisher.telegram import TelegramSender
from ..publisher.whatsapp import WhatsAppSender
from ..publisher.x import XSender
from ..settings import Settings
from .cards import Bucket, R2CardHost, R2Cards
from .history import import_rows
from .render import apply_rendered, render_tasks
from .webhook import handle_update

log = logging.getLogger("ofertinhas")
WEBHOOK_HEADER = "X-Telegram-Bot-Api-Secret-Token"
# job → de quantos em quantos minutos roda (o Cron chama o tick a cada minuto). O "render"
# fica de fora: o card é desenhado no Worker de entrada (ver cloud/draw.py e cloud/render.py).
JOB_EVERY_MIN = {"expire": 15, "publish": 1, "stock_alert": 5, "notify_pending": 1}
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
        self.templates_dir = bundle_dir / "templates"
        self.telegram = TelegramSender(http, settings.telegram_bot_token)
        self.whatsapp = None
        if settings.whatsmiau_api_key and settings.whatsmiau_instance:
            self.whatsapp = WhatsAppSender(http, settings.whatsmiau_base_url,
                                           settings.whatsmiau_api_key, settings.whatsmiau_instance)
        self.card_host = card_host = (
            R2CardHost(bucket, settings.r2_public_url) if settings.r2_public_url else None
        )
        self.card_store = R2Cards(bucket)
        self.x = XSender(http, *settings.x_keys) if settings.x_keys else None
        self.bot = bot or Bot(settings.telegram_bot_token)
        self._bot_ready = bot is not None
        self.bot_deps = BotDeps(conn=conn, cfg=cfg, admin_chat_id=settings.admin_chat_id,
                                clock=clock)

        async def fetch_image(url):
            return await fetch_product_image(http, url)

        self.jobs = make_jobs(
            conn=conn, cfg=cfg, templates_dir=bundle_dir / "templates", bot=self.bot,
            telegram=self.telegram, whatsapp=self.whatsapp, cards=card_host,
            card_store=self.card_store, fetch_image=fetch_image, notify=self.notify,
            admin_chat_id=settings.admin_chat_id, dry_run=self.dry_run, clock=clock,
            whatsapp_test_jid=settings.whatsapp_test_jid, x=self.x,
        )
        self._running: set[str] = set()
        self.app = self._build_app()

    def render_tasks(self) -> list[dict]:
        return render_tasks(self.conn, self.cfg, self.templates_dir, self.clock())

    def render_done(self, results: list[dict]) -> int:
        return apply_rendered(self.conn, results)

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
                                  save_unparsed=self._save_unparsed, dry_run=self.dry_run))

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
        async def admin_status(posts: int = 6) -> dict:
            recent = self.conn.execute(
                "SELECT mlb_id, niche, channel, chat, status, sent_at, error FROM posts "
                "ORDER BY sent_at DESC LIMIT ?", (min(posts, 200),),
            )
            alerts = self.conn.execute(
                "SELECT key, value_json FROM settings WHERE key LIKE 'alert:%' ORDER BY key"
            )
            latest_links = self.conn.execute(
                "SELECT c.mlb_id, c.niche, c.state, o.link_requested_at, o.updated_at AS last_seen "
                "FROM candidates c JOIN offers o ON o.mlb_id = c.mlb_id "
                "WHERE o.affiliate_link IS NOT NULL AND o.link_requested_at IS NOT NULL "
                "ORDER BY o.link_requested_at DESC LIMIT 5"
            )
            last_collect = self.conn.execute("SELECT MAX(updated_at) FROM offers").fetchone()[0]
            return {"dry_run": self.dry_run, "last_tick": db.get_setting(self.conn, LAST_TICK_KEY),
                    "last_collect": last_collect,
                    "candidates": db.count_candidates(self.conn),
                    "recent_posts": [dict(zip(r.keys(), r, strict=True)) for r in recent],
                    "alerts": {r["key"]: json.loads(r["value_json"]) for r in alerts},
                    "latest_links": [dict(zip(r.keys(), r, strict=True)) for r in latest_links]}

        @app.post("/admin/post-now", dependencies=[Depends(app.state.require_token)])
        async def admin_post_now(mlb_id: str | None = None) -> dict:
            """Um post avulso por grupo agora, fora da janela e do intervalo; com `mlb_id`,
            só essa oferta (precisa estar com o card pronto)."""
            if "publish" in self._running:  # o job do minuto está postando: sem post duplo
                raise HTTPException(status_code=409, detail="postagem em andamento")
            self._running.add("publish")
            try:
                posted = await publish_due(
                    self.conn, self.cfg, telegram=self.telegram, whatsapp=self.whatsapp,
                    card_host=self.card_host, admin_chat_id=self.settings.admin_chat_id,
                    dry_run=self.dry_run, now=self.clock(), notify=self.notify,
                    card_store=self.card_store,
                    whatsapp_test_jid=self.settings.whatsapp_test_jid, force=True,
                    only_mlb=mlb_id, x=self.x,
                )
            finally:
                self._running.discard("publish")
            return {"dry_run": self.dry_run, "posted": posted}

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
        due = [n for n, every in JOB_EVERY_MIN.items() if now.minute % every == 0]
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
