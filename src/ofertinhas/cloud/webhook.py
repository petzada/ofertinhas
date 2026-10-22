"""Updates do bot do admin recebidos por webhook, despachados aos mesmos handlers do polling.

No PC, a `Application` da PTB faz esse roteamento; aqui ele é refeito à mão com as mesmas
regras (botões → `on_callback`, comandos conhecidos → `on_command`, outro texto →
`on_text`). O "aguardando texto novo" do botão Editar fica no banco, porque o Durable Object
pode ser descarregado entre um update e outro.
"""

from telegram import Update

from .. import db
from ..approval.bot import BotDeps, on_callback, on_command, on_text
from ..approval.commands import COMMANDS

BOT_COMMANDS = frozenset({*COMMANDS, "cancelar", "start", "ajuda"})
AWAITING_EDIT_KEY = "bot:awaiting_edit"


async def handle_update(data: dict, bot, deps: BotDeps) -> None:
    update = Update.de_json(data, bot)
    stored = db.get_setting(deps.conn, AWAITING_EDIT_KEY)
    deps.awaiting_edit = tuple(stored) if stored else None
    try:
        if update.callback_query is not None:
            await on_callback(deps, update)
        elif update.message is not None and update.message.text:
            words = update.message.text.split()
            if words[0].startswith("/"):
                name = words[0].lstrip("/").split("@")[0].lower()
                if name in BOT_COMMANDS:
                    await on_command(deps, update, name, words[1:])
            else:
                await on_text(deps, update)
    finally:
        db.set_setting(deps.conn, AWAITING_EDIT_KEY,
                       list(deps.awaiting_edit) if deps.awaiting_edit else None)
