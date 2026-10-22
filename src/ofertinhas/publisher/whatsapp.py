"""Envio aos grupos do WhatsApp pela API da WhatsMiau.dev (padrão Evolution API).

Rotas e formato conforme https://whatsmiau.dev/docs/getting-started; a imagem vai em base64.
"""

import asyncio
import base64
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


class WhatsAppError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(data, dict):
        inner = data.get("response")
        for value in (data.get("message"), inner.get("message") if isinstance(inner, dict)
                      else None, data.get("error")):
            if value:
                return str(value)
    return f"HTTP {response.status_code}"


class WhatsAppSender:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        instance: str,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_attempts: int = 3,
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.headers = {"apikey": api_key}
        self.instance = instance
        self.sleep = sleep
        self.max_attempts = max_attempts

    async def _call(self, method: str, path: str, **request) -> Any:
        last_error: WhatsAppError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self.client.request(
                    method, f"{self.base_url}{path}", headers=self.headers, timeout=60, **request
                )
            except httpx.HTTPError as e:
                last_error = WhatsAppError(f"rede: {e}", retryable=True)
            else:
                if response.status_code < 400:
                    return response.json() if response.content else None
                retryable = response.status_code == 429 or response.status_code >= 500
                error = WhatsAppError(_error_message(response), retryable=retryable)
                if not retryable:
                    raise error
                last_error = error
            if attempt < self.max_attempts:
                await self.sleep(2**attempt)
        raise last_error

    async def connection_state(self) -> str:
        """`open`, `closed`, `connecting` ou `qr-code`."""
        data = await self._call("GET", f"/instance/connectionState/{self.instance}")
        return str((data or {}).get("state", "desconhecido"))

    async def pairing_code(self, number: str) -> str:
        """Código de 8 caracteres para digitar no app do WhatsApp do número (Aparelhos
        conectados → Conectar com número de telefone), no lugar do QR code."""
        digits = "".join(c for c in number if c.isdigit())
        data = await self._call(
            "GET", f"/instance/connect/{self.instance}", params={"number": digits}
        )
        code = (data or {}).get("pairingCode")
        if not code:
            raise WhatsAppError("a API não devolveu código de pareamento", retryable=False)
        return str(code)

    async def list_groups(self) -> list[dict]:
        return await self._call(
            "GET", f"/group/fetchAllGroups/{self.instance}", params={"getParticipants": "false"}
        )

    async def send_presence(self, jid: str, delay_ms: int = 3000) -> None:
        """Mostra "digitando…" antes do post; se a API não aceitar, segue sem."""
        try:
            await self._call("POST", f"/chat/sendPresence/{self.instance}", json={
                "number": jid, "presence": "composing", "type": "text", "delay": delay_ms,
            })
        except WhatsAppError:
            pass

    async def send_image(self, jid: str, png: bytes, caption: str) -> str:
        data = await self._call("POST", f"/message/sendMedia/{self.instance}", json={
            "number": jid,
            "mediatype": "image",
            "mimetype": "image/png",
            "fileName": "oferta.png",
            "media": base64.b64encode(png).decode(),
            "caption": caption,
        })
        key = data.get("key") if isinstance(data, dict) else None
        return str(key.get("id", "")) if isinstance(key, dict) else ""
