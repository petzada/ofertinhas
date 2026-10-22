import httpx
import pytest
import respx
from dotenv import dotenv_values

from ofertinhas.telegram_setup import TelegramSetupError, find_admin_chat, save_admin_chat

TOKEN = "123:ABC"
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"


def update(chat_id, chat_type="private", text="/start", first_name="Marcio"):
    return {"update_id": chat_id, "message": {
        "chat": {"id": chat_id, "type": chat_type, "first_name": first_name}, "text": text}}


@respx.mock
async def test_finds_latest_private_chat():
    respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": True, "result": [
        update(111), update(-100999, chat_type="supergroup"), update(222),
    ]}))
    async with httpx.AsyncClient() as client:
        chat_id, name = await find_admin_chat(client, TOKEN)
    assert (chat_id, name) == (222, "Marcio")


@respx.mock
async def test_no_private_message_explains_what_to_do():
    respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": True, "result": []}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(TelegramSetupError, match="/start"):
            await find_admin_chat(client, TOKEN)


@respx.mock
async def test_invalid_token():
    respx.get(URL).mock(return_value=httpx.Response(
        401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(TelegramSetupError, match="token"):
            await find_admin_chat(client, TOKEN)


def test_save_admin_chat(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=123:ABC\nADMIN_CHAT_ID=\n", encoding="utf-8")
    save_admin_chat(env, 222)
    values = dotenv_values(env)
    assert values["ADMIN_CHAT_ID"] == "222" and values["TELEGRAM_BOT_TOKEN"] == "123:ABC"
