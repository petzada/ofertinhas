"""Mensagem de status fixada no chat do admin, editada nos horários do job `status`.

A mesma mensagem é editada (sem notificar) em vez de mandar uma nova; se ela sumiu (apagada
ou desafixada e apagada), sai outra, que é fixada no lugar.
"""

import html
import sqlite3
from datetime import datetime

from . import db
from .config import AppConfig
from .models import TZ, CandidateState
from .pipeline import INFLATED_KEY
from .publisher.telegram import TelegramError
from .stock import group_stock

STATUS_MESSAGE_KEY = "status:message"  # {"chat": ..., "message_id": ...}
LAST_COLLECT_KEY = "collector:last_run"  # quando a extensão começou a última coleta


def last_collect(conn: sqlite3.Connection) -> datetime | None:
    """Início da última coleta da extensão; sem registro, a última oferta vista."""
    started = db.get_setting(conn, LAST_COLLECT_KEY)
    if started:
        return datetime.fromisoformat(started)
    seen = conn.execute("SELECT MAX(updated_at) FROM offers").fetchone()[0]
    return datetime.fromisoformat(seen) if seen else None


def _hhmm(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%H:%M")


def _ago(now: datetime, then: datetime) -> str:
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 60:
        return f"há {minutes} min"
    if minutes < 48 * 60:
        return f"há {minutes // 60} h"
    return f"há {minutes // (24 * 60)} dias"


def status_text(conn: sqlite3.Connection, cfg: AppConfig, now: datetime, dry_run: bool,
                whatsapp_state: str, version: str | None = None) -> str:
    lines = [f"📌 <b>Ofertinhas</b> • atualizado às {_hhmm(now)}",
             "🧪 Modo de teste: posts só no chat do admin" if dry_run else "Posts reais nos grupos"]
    for g in group_stock(conn, cfg, now, dry_run):
        until = "cobre o dia" if g.ends_at is None else f"estoque até {_hhmm(g.ends_at)}"
        lines += [
            "",
            f"<b>Grupo {html.escape(g.key)}</b> ({len(g.niches)} nichos)",
            f"• prontas: {g.ready} • esperando link: {g.waiting_links} • reserva: {g.reserve}",
            f"• posts hoje: {g.posts_today}/{g.max_posts} • {until}",
        ]
    counts = db.count_candidates(conn)
    lines.append("")
    lines.append(f"Cards para você aprovar: {counts.get(CandidateState.PENDING.value, 0)}")
    collected = last_collect(conn)
    lines.append("Última coleta: " + (
        f"{_hhmm(collected)} ({_ago(now, collected)})" if collected else "nunca"))
    paused = db.get_setting(conn, db.EXTENSION_PAUSED_KEY)
    if paused:
        lines.append(f"⏸️ Extensão pausada: {html.escape(str(paused.get('reason')))}")
    day = db.get_setting(conn, INFLATED_KEY.format(date=now.astimezone(TZ).date().isoformat()))
    lines.append(f"Descontos inflados barrados hoje: {day['inflated'] if day else 0}")
    lines.append(f"WhatsApp: {html.escape(whatsapp_state)}")
    if version:
        lines.append(f"Versão: <code>{html.escape(version)}</code>")
    return "\n".join(lines)


async def pin_status(conn: sqlite3.Connection, telegram, chat_id: int | str, text: str) -> str:
    """Edita a mensagem fixada ou, se ela não existe mais, manda e fixa uma nova."""
    stored = db.get_setting(conn, STATUS_MESSAGE_KEY)
    if stored and stored["chat"] == str(chat_id):
        try:
            await telegram.edit_message(chat_id, stored["message_id"], text)
            return "edited"
        except TelegramError:
            pass  # apagada: vai uma nova
    message_id = await telegram.send_message(chat_id, text, silent=True)
    db.set_setting(conn, STATUS_MESSAGE_KEY, {"chat": str(chat_id), "message_id": message_id})
    await telegram.pin_message(chat_id, message_id)
    return "sent"
