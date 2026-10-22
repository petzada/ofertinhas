"""Descobre o chat privado do admin com o bot (depois de um /start) e grava no .env."""

from pathlib import Path

import httpx
from dotenv import set_key

from .publisher.telegram import API


class TelegramSetupError(Exception):
    pass


async def find_admin_chat(client: httpx.AsyncClient, token: str) -> tuple[int, str]:
    """(chat_id, nome) da mensagem privada mais recente enviada ao bot."""
    response = await client.get(f"{API}/bot{token}/getUpdates", timeout=20)
    data = response.json()
    if not data.get("ok"):
        raise TelegramSetupError(
            f"o Telegram recusou o token ({data.get('description', response.status_code)}); "
            "confira TELEGRAM_BOT_TOKEN no .env"
        )
    private = [
        u["message"]["chat"] for u in data["result"]
        if u.get("message", {}).get("chat", {}).get("type") == "private"
    ]
    if not private:
        raise TelegramSetupError(
            "nenhuma mensagem privada encontrada: abra a conversa com o bot, mande /start "
            "e rode o comando de novo"
        )
    chat = private[-1]
    return chat["id"], chat.get("first_name", "")


def save_admin_chat(env_path: Path, chat_id: int) -> None:
    set_key(env_path, "ADMIN_CHAT_ID", str(chat_id), quote_mode="never")
