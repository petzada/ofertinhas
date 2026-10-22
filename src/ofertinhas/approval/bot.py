"""Bot privado do admin no Telegram: cards de aprovação, botões e comandos.

Os handlers recebem as dependências explicitamente e só fazem a ponte com o Telegram; as
decisões ficam em `actions` e `commands`.
"""

import dataclasses
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .. import db
from ..config import AppConfig
from ..models import CandidateState, utcnow
from . import actions
from .actions import ActionError
from .commands import COMMANDS, HELP, CommandContext, run_command
from .messages import approval_caption, approval_keyboard, niche_keyboard, parse_callback

log = logging.getLogger(__name__)
EDIT_PROMPT = (
    "✏️ Envie o novo texto da oferta. Pode usar variáveis como {titulo_curto}, {preco} e "
    "{selos}. Se não incluir {link}, ele entra no final. /cancelar para desistir."
)


@dataclass
class BotDeps:
    conn: sqlite3.Connection
    cfg: AppConfig
    admin_chat_id: int
    clock: Callable[[], datetime] = utcnow
    awaiting_edit: tuple[str, str] | None = field(default=None)


async def send_pending_cards(bot, deps: BotDeps, limit: int = 5) -> int:
    """Manda ao admin os cards das pendentes ainda não notificadas, até `limit` por vez,
    as de maior nota primeiro (o job roda a cada minuto)."""
    sent = 0
    for cand in db.candidates_by_state(deps.conn, CandidateState.PENDING):
        if sent >= limit:
            break
        if cand.notified_at is not None:
            continue
        offer = db.get_offer(deps.conn, cand.mlb_id)
        caption = approval_caption(offer, cand)
        keyboard = approval_keyboard(cand.mlb_id, cand.niche)
        try:
            if not offer.image_url:
                raise ValueError("sem foto")
            await bot.send_photo(chat_id=deps.admin_chat_id, photo=offer.image_url,
                                 caption=caption, parse_mode=ParseMode.HTML,
                                 reply_markup=keyboard)
        except Exception:
            try:
                await bot.send_message(chat_id=deps.admin_chat_id, text=caption,
                                       parse_mode=ParseMode.HTML, reply_markup=keyboard)
            except Exception:
                log.exception("não consegui enviar o card de %s ao admin", cand.mlb_id)
                continue
        db.save_candidate(deps.conn, dataclasses.replace(cand, notified_at=deps.clock()))
        sent += 1
    return sent


async def _close_card(q, status: str) -> None:
    """Acrescenta o resultado ao card e tira os botões."""
    if q.message.photo:
        await q.edit_message_caption(caption=f"{q.message.caption_html}\n\n<b>{status}</b>",
                                     parse_mode=ParseMode.HTML, reply_markup=None)
    else:
        await q.edit_message_text(text=f"{q.message.text_html}\n\n<b>{status}</b>",
                                  parse_mode=ParseMode.HTML, reply_markup=None)


async def on_callback(deps: BotDeps, update) -> None:
    q = update.callback_query
    if q.message is None or q.message.chat.id != deps.admin_chat_id:
        await q.answer()
        return
    action, parts = parse_callback(q.data)
    mlb_id, niche = parts[0], parts[1]
    now = deps.clock()
    try:
        if action in ("a", "r"):
            decide = actions.approve if action == "a" else actions.reject
            status = decide(deps.conn, mlb_id, niche, now)
            await q.answer(status)
            await _close_card(q, status)
        elif action == "e":
            deps.awaiting_edit = (mlb_id, niche)
            await q.answer()
            await q.message.reply_text(EDIT_PROMPT)
        elif action == "n":
            await q.answer()
            await q.edit_message_reply_markup(
                reply_markup=niche_keyboard(mlb_id, niche, deps.cfg.niche_names())
            )
        elif action == "m":
            new = actions.change_niche(deps.conn, deps.cfg, mlb_id, niche, parts[2], now)
            offer = db.get_offer(deps.conn, mlb_id)
            await q.answer(f"Movida para {new.niche}")
            card = approval_caption(offer, new)
            keyboard = approval_keyboard(mlb_id, new.niche)
            if q.message.photo:
                await q.edit_message_caption(caption=card, parse_mode=ParseMode.HTML,
                                             reply_markup=keyboard)
            else:
                await q.edit_message_text(text=card, parse_mode=ParseMode.HTML,
                                          reply_markup=keyboard)
        elif action == "x":
            await q.answer()
            await q.edit_message_reply_markup(reply_markup=approval_keyboard(mlb_id, niche))
        else:
            await q.answer()
    except ActionError as e:
        await q.answer(str(e), show_alert=True)


async def on_text(deps: BotDeps, update) -> None:
    if update.effective_chat.id != deps.admin_chat_id or deps.awaiting_edit is None:
        return
    mlb_id, niche = deps.awaiting_edit
    try:
        reply = actions.set_custom_caption(deps.conn, mlb_id, niche, update.message.text)
        deps.awaiting_edit = None
    except ActionError as e:
        reply = f"⚠️ {e}"
    await update.message.reply_text(reply)


async def on_command(deps: BotDeps, update, name: str, args: list[str]) -> None:
    chat_id = update.effective_chat.id
    if name != "chatid" and chat_id != deps.admin_chat_id:
        log.warning("comando /%s ignorado do chat %s", name, chat_id)
        return
    if name == "cancelar":
        deps.awaiting_edit = None
        reply = "Ok, nada foi alterado."
    elif name in ("start", "ajuda"):
        reply = HELP
    else:
        ctx = CommandContext(conn=deps.conn, cfg=deps.cfg, now=deps.clock(), chat_id=chat_id)
        reply = run_command(name, args, ctx)
    await update.message.reply_text(reply, parse_mode=ParseMode.HTML)


def build_application(token: str, deps: BotDeps) -> Application:
    app = Application.builder().token(token).build()

    async def callback(update, context):
        await on_callback(deps, update)

    async def text(update, context):
        await on_text(deps, update)

    async def command(update, context):
        name = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
        await on_command(deps, update, name, list(context.args or []))

    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(CommandHandler([*COMMANDS, "cancelar", "start", "ajuda"], command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    return app
