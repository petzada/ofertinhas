"""Jobs periódicos do backend, montados do mesmo jeito no PC (APScheduler) e na nuvem (Cron).

`SCHEDULE` é o calendário único dos dois: o `scheduler.py` o traduz em gatilhos do
APScheduler e a nuvem pergunta a `is_due` a cada minuto. Cada job é isolado por `guarded`: se
um falha, os outros seguem e o admin é avisado.
"""

import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from . import db
from .alerts import notify_throttled
from .approval.bot import BotDeps, send_pending_cards
from .cardstore import CardStore, DiskCards
from .config import AppConfig
from .models import TZ, utcnow
from .pipeline import render_linked
from .publisher.publish import publish_due
from .publisher.queue import expire_stale
from .publisher.whatsapp import WhatsAppError
from .status import pin_status, status_text
from .stock import alert_low_stock

log = logging.getLogger("ofertinhas")
ERROR_ALERT_EVERY = timedelta(minutes=30)


@dataclass(frozen=True)
class Every:
    minutes: int  # divide a hora: 1, 5, 15...


@dataclass(frozen=True)
class At:
    times: tuple[str, ...]  # "HH:MM" no horário de São Paulo


# Ordem = ordem em que a nuvem roda os jobs do mesmo minuto.
SCHEDULE: dict[str, Every | At] = {
    "expire": Every(15),
    "publish": Every(1),
    "stock_alert": Every(5),
    "notify_pending": Every(1),
    "render": Every(1),
    "backup": At(("04:00",)),
    "prune": At(("04:30",)),
    "status": At(("08:00", "13:00", "20:00")),
}


def is_due(spec: Every | At, now: datetime) -> bool:
    """O job roda no minuto `now` (o Cron da nuvem chama uma vez por minuto)."""
    local = now.astimezone(TZ)
    if isinstance(spec, Every):
        return (local.hour * 60 + local.minute) % spec.minutes == 0
    return local.strftime("%H:%M") in spec.times


def at_times(spec: At) -> list[time]:
    return [time.fromisoformat(t) for t in spec.times]


def make_jobs(
    *,
    conn: sqlite3.Connection,
    cfg: AppConfig,
    templates_dir: Path,
    bot,
    telegram,
    fetch_image: Callable[[str | None], Awaitable[object]],
    notify: Callable[[str], Awaitable[None]],
    admin_chat_id: int,
    dry_run: bool,
    data_dir: Path | None = None,
    card_store: CardStore | None = None,
    whatsapp=None,
    cards=None,
    whatsapp_test_jid: str | None = None,
    x=None,
    clock: Callable[[], datetime] = utcnow,
    version: str | None = None,
) -> dict[str, Callable[[], Awaitable[object]]]:
    """Com `data_dir` (PC), os cards ficam em disco e há backup diário do SQLite; na nuvem,
    passe `card_store` (R2) e o banco conta com a recuperação do Durable Object."""
    deps = BotDeps(conn=conn, cfg=cfg, admin_chat_id=admin_chat_id, clock=clock)
    store = card_store or DiskCards(data_dir / "cards")

    async def notify_pending():
        return await send_pending_cards(bot, deps)

    async def render():
        return await render_linked(conn, cfg, store, templates_dir, fetch_image, now=clock())

    async def publish():
        posted = await publish_due(conn, cfg, telegram=telegram, whatsapp=whatsapp,
                                   card_host=cards, admin_chat_id=admin_chat_id,
                                   dry_run=dry_run, now=clock(), notify=notify, card_store=store,
                                   whatsapp_test_jid=whatsapp_test_jid, x=x)
        if posted:
            log.info("postadas: %s", ", ".join(posted))
        return posted

    async def expire():
        return expire_stale(conn, cfg, clock())

    async def stock_alert():
        return await alert_low_stock(conn, cfg, notify, clock(), dry_run)

    async def prune():
        removed = db.prune(conn, clock(), cfg.retention_days)
        log.info("limpeza: %s", removed)
        return removed

    async def status():
        text = status_text(conn, cfg, clock(), dry_run, await whatsapp_state(), version)
        return await pin_status(conn, telegram, admin_chat_id, text)

    async def whatsapp_state() -> str:
        if not cfg.whatsapp_enabled:
            return "travado (whatsapp_enabled: false)"
        if whatsapp is None:
            return "sem chave da WhatsMiau"
        try:
            return await whatsapp.connection_state()
        except WhatsAppError as e:
            return f"erro ao consultar: {e}"

    jobs = {"notify_pending": notify_pending, "render": render, "publish": publish,
            "expire": expire, "stock_alert": stock_alert, "prune": prune, "status": status}
    if data_dir is not None:
        async def backup():
            from .backup import backup_database  # cópia de arquivo: só no PC

            return backup_database(conn, data_dir / "backups", clock())

        jobs["backup"] = backup
    return jobs


def guarded(
    name: str,
    job: Callable[[], Awaitable[object]],
    conn: sqlite3.Connection,
    notify: Callable[[str], Awaitable[None]],
    clock: Callable[[], datetime],
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        try:
            await job()
        except Exception as e:  # um job com erro não pode derrubar o processo
            log.exception("job %s falhou", name)
            await notify_throttled(
                conn, notify, f"job:{name}", f"⚠️ Erro no job {name}: {e}", clock(),
                ERROR_ALERT_EVERY,
            )

    return run
