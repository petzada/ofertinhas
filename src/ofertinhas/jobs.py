"""Jobs periódicos do backend, montados do mesmo jeito no PC (APScheduler) e na nuvem (Cron).

Cada job é isolado por `guarded`: se um falha, os outros seguem e o admin é avisado.
"""

import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path

from .alerts import notify_throttled
from .approval.bot import BotDeps, send_pending_cards
from .cardstore import CardStore, DiskCards
from .config import AppConfig
from .models import utcnow
from .pipeline import render_linked
from .publisher.publish import publish_due
from .publisher.queue import expire_stale

log = logging.getLogger("ofertinhas")
ERROR_ALERT_EVERY = timedelta(minutes=30)


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
    clock: Callable[[], datetime] = utcnow,
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
                                   whatsapp_test_jid=whatsapp_test_jid)
        if posted:
            log.info("postadas: %s", ", ".join(posted))
        return posted

    async def expire():
        return expire_stale(conn, cfg, clock())

    jobs = {"notify_pending": notify_pending, "render": render, "publish": publish,
            "expire": expire}
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
