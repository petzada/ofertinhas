"""Posts no X em thread: o primeiro com o card e o texto, a resposta só com o link.

O link vai sozinho na resposta para o X montar o preview do Mercado Livre. Autenticação
OAuth 1.0a de usuário (as mesmas 4 chaves do app do X: API key/secret e access
token/secret), como no projeto xcopadomundo. A imagem sobe pelo endpoint de mídia v2; se a
conta ainda não tiver acesso a ele, tenta o v1.1.
"""

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from urllib.parse import quote

import httpx

API = "https://api.x.com/2"
UPLOAD_V2 = f"{API}/media/upload"
UPLOAD_V1 = "https://upload.twitter.com/1.1/media/upload.json"
MAX_ERROR_CHARS = 300


class XError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _enc(value: str) -> str:
    return quote(value, safe="~-._")


def oauth1_header(method: str, url: str, *, api_key: str, api_secret: str, token: str,
                  token_secret: str, nonce: str, timestamp: str) -> str:
    """Header `Authorization` OAuth 1.0a (HMAC-SHA1). Corpo JSON ou multipart não entra na
    assinatura; só os parâmetros oauth_* (as chamadas daqui não usam query string)."""
    oauth = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    params = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(oauth.items()))
    base = "&".join((method.upper(), _enc(url), _enc(params)))
    key = f"{_enc(api_secret)}&{_enc(token_secret)}".encode()
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key, base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


def _error(response: httpx.Response) -> XError:
    try:
        data = response.json()
        detail = data.get("detail") or data.get("title") or data.get("errors") or data
    except ValueError:
        detail = response.text
    retryable = response.status_code == 429 or response.status_code >= 500
    return XError(f"X {response.status_code}: {str(detail)[:MAX_ERROR_CHARS]}", retryable)


class XSender:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        nonce: Callable[[], str] = lambda: secrets.token_hex(16),
        clock: Callable[[], float] = time.time,
    ):
        self.client = client
        self.keys = dict(api_key=api_key, api_secret=api_secret, token=access_token,
                         token_secret=access_token_secret)
        self.nonce = nonce
        self.clock = clock

    def _auth(self, method: str, url: str) -> dict[str, str]:
        header = oauth1_header(method, url, nonce=self.nonce(),
                               timestamp=str(int(self.clock())), **self.keys)
        return {"Authorization": header}

    async def _post(self, url: str, **request) -> httpx.Response:
        try:
            return await self.client.post(url, headers=self._auth("POST", url), timeout=60,
                                          **request)
        except httpx.HTTPError as e:
            raise XError(f"rede: {e}", retryable=True) from None

    async def upload_png(self, png: bytes) -> str:
        files = {"media": ("card.png", png, "image/png")}
        response = await self._post(UPLOAD_V2, data={"media_category": "tweet_image",
                                                     "media_type": "image/png"}, files=files)
        if response.status_code < 400 and (response.json().get("data") or {}).get("id"):
            return str(response.json()["data"]["id"])
        if response.status_code == 429 or response.status_code >= 500:
            raise _error(response)
        # v2 recusado (acesso da conta ou formato): o v1.1 ainda aceita upload simples
        legacy = await self._post(UPLOAD_V1, data={"media_category": "tweet_image"},
                                  files=files)
        if legacy.status_code >= 400:
            raise XError(f"upload recusado: {_error(response)} | v1.1: {_error(legacy)}")
        return str(legacy.json()["media_id_string"])

    async def post(self, text: str, *, media_id: str | None = None,
                   reply_to: str | None = None) -> str:
        body: dict = {"text": text}
        if media_id:
            body["media"] = {"media_ids": [media_id]}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        response = await self._post(f"{API}/tweets", json=body)
        if response.status_code >= 400:
            raise _error(response)
        return str(response.json()["data"]["id"])

    async def post_thread(self, png: bytes, text: str, link: str) -> tuple[str, str]:
        """(id do post com o card, id da resposta com o link)."""
        first = await self.post(text, media_id=await self.upload_png(png))
        return first, await self.post(link, reply_to=first)
