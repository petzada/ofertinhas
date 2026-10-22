"""Hospedagem pública dos cards no Cloudflare R2, para a WhatsMiau baixar a imagem por URL.

Upload pela API S3 do R2 (o token com escopo de bucket não vale na API REST de objetos). As
credenciais S3 saem do próprio token, como a Cloudflare documenta: Access Key ID = id do
token e Secret = SHA-256 do valor do token. A leitura é pública pelo domínio r2.dev.
"""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

API = "https://api.cloudflare.com/client/v4"
REGION = "auto"
SIGNED_HEADERS = "content-type;host;x-amz-content-sha256;x-amz-date"


class CardHostError(Exception):
    pass


def sign_s3_put(
    *, host: str, path: str, body: bytes, access_key: str, secret: str, now: datetime,
    content_type: str = "image/png",
) -> dict[str, str]:
    """Headers de um PUT assinado com AWS Signature V4 (serviço s3, região auto)."""
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([
        "PUT", path, "",
        f"content-type:{content_type}\nhost:{host}\nx-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n",
        SIGNED_HEADERS, payload_hash,
    ])
    scope = f"{day}/{REGION}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    key = f"AWS4{secret}".encode()
    for part in (day, REGION, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Authorization": f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                         f"SignedHeaders={SIGNED_HEADERS}, Signature={signature}",
    }


class CardHost:
    def __init__(
        self, client: httpx.AsyncClient, account_id: str, bucket: str, api_token: str,
        public_base_url: str, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.client = client
        self.account_id = account_id
        self.bucket = bucket
        self.api_token = api_token.strip()
        self.public_base_url = public_base_url.rstrip("/")
        self.host = f"{account_id}.r2.cloudflarestorage.com"
        self.clock = clock
        self._access_key: str | None = None

    async def _access_key_id(self) -> str:
        if self._access_key is None:
            response = await self.client.get(
                f"{API}/accounts/{self.account_id}/tokens/verify", timeout=30,
                headers={"Authorization": f"Bearer {self.api_token}"},
            )
            data = response.json()
            if not data.get("success"):
                errors = "; ".join(e.get("message", "") for e in data.get("errors", []))
                raise CardHostError(f"token do R2 recusado: {errors or response.status_code}")
            self._access_key = data["result"]["id"]
        return self._access_key

    async def upload(self, key: str, png: bytes) -> str:
        """Envia o PNG e devolve a URL pública dele."""
        try:
            path = f"/{self.bucket}/{quote(key, safe='/')}"
            headers = sign_s3_put(
                host=self.host, path=path, body=png, access_key=await self._access_key_id(),
                secret=hashlib.sha256(self.api_token.encode()).hexdigest(), now=self.clock(),
            )
            response = await self.client.put(f"https://{self.host}{path}", content=png,
                                             headers=headers, timeout=60)
        except httpx.HTTPError as e:
            raise CardHostError(f"rede: {e}") from None
        if response.status_code >= 400:
            raise CardHostError(
                f"R2 recusou o upload ({response.status_code}): {response.text[:200]}"
            )
        return f"{self.public_base_url}/{key}"
