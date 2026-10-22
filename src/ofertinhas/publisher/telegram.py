"""Envio aos grupos do Telegram pela Bot API, com retry só quando faz sentido."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

API = "https://api.telegram.org"


class TelegramError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class TelegramSender:
    def __init__(
        self,
        client: httpx.AsyncClient,
        token: str,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = 3,
        base_url: str = API,
    ):
        self.client = client
        self.url = f"{base_url}/bot{token}"
        self.sleep = sleep
        self.max_attempts = max_attempts

    async def _call(self, method: str, **request) -> dict:
        last_error: TelegramError | None = None
        for attempt in range(1, self.max_attempts + 1):
            wait = 2**attempt
            try:
                response = await self.client.post(f"{self.url}/{method}", timeout=30, **request)
            except httpx.HTTPError as e:
                last_error = TelegramError(f"rede: {e}", retryable=True)
            else:
                data = response.json()
                if data.get("ok"):
                    return data["result"]
                description = data.get("description", f"HTTP {response.status_code}")
                if response.status_code == 429:
                    wait = data.get("parameters", {}).get("retry_after", wait)
                    last_error = TelegramError(description, retryable=True)
                elif response.status_code >= 500:
                    last_error = TelegramError(description, retryable=True)
                else:
                    raise TelegramError(description, retryable=False)
            if attempt < self.max_attempts:
                await self.sleep(wait)
        raise last_error

    async def send_photo(self, chat_id: int | str, png: bytes, caption_html: str) -> str:
        result = await self._call(
            "sendPhoto",
            data={"chat_id": str(chat_id), "caption": caption_html, "parse_mode": "HTML"},
            files={"photo": ("card.png", png, "image/png")},
        )
        return str(result["message_id"])

    async def send_message(self, chat_id: int | str, text_html: str,
                           silent: bool = False) -> str:
        result = await self._call(
            "sendMessage", json={"chat_id": chat_id, "text": text_html, "parse_mode": "HTML",
                                 "disable_notification": silent},
        )
        return str(result["message_id"])

    async def edit_message(self, chat_id: int | str, message_id: str, text_html: str) -> None:
        """Troca o texto; o mesmo texto de antes ("message is not modified") não é erro."""
        try:
            await self._call("editMessageText", json={
                "chat_id": chat_id, "message_id": int(message_id), "text": text_html,
                "parse_mode": "HTML",
            })
        except TelegramError as e:
            if "not modified" not in str(e):
                raise

    async def pin_message(self, chat_id: int | str, message_id: str) -> None:
        await self._call("pinChatMessage", json={
            "chat_id": chat_id, "message_id": int(message_id), "disable_notification": True,
        })
