"""Hospedagem pública dos cards no Cloudflare R2, para a WhatsMiau baixar a imagem por URL.

Upload pela API REST da Cloudflare (PUT do objeto) com um token de API com permissão de
escrita no bucket; a leitura é pública pelo domínio r2.dev do bucket.
"""

import httpx

API = "https://api.cloudflare.com/client/v4"


class CardHostError(Exception):
    pass


class CardHost:
    def __init__(
        self, client: httpx.AsyncClient, account_id: str, bucket: str, api_token: str,
        public_base_url: str,
    ):
        self.client = client
        self.upload_base = f"{API}/accounts/{account_id}/r2/buckets/{bucket}/objects"
        self.headers = {"Authorization": f"Bearer {api_token}"}
        self.public_base_url = public_base_url.rstrip("/")

    async def upload(self, key: str, png: bytes) -> str:
        """Envia o PNG e devolve a URL pública dele."""
        try:
            response = await self.client.put(
                f"{self.upload_base}/{key}", content=png, timeout=60,
                headers=self.headers | {"Content-Type": "image/png"},
            )
        except httpx.HTTPError as e:
            raise CardHostError(f"rede: {e}") from None
        if response.status_code >= 400:
            try:
                errors = response.json().get("errors") or []
                message = "; ".join(e.get("message", "") for e in errors) or response.text
            except ValueError:
                message = response.text
            raise CardHostError(f"R2 recusou o upload ({response.status_code}): {message[:200]}")
        return f"{self.public_base_url}/{key}"
