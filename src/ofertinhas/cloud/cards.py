"""Cards no R2 pelo binding do Worker: o card store dos jobs e o host público do WhatsApp.

`bucket` é qualquer objeto com `async put(key, data, content_type)` e `async get(key)` que
devolve os bytes ou None; a entrada do Worker embrulha o binding R2 nessa interface.
"""

from typing import Protocol

from ..publisher.cardhost import CardHostError

PREFIX = "cards/"


class Bucket(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes | None: ...


class R2Cards:
    def __init__(self, bucket: Bucket):
        self.bucket = bucket

    async def save(self, name: str, png: bytes) -> str:
        key = PREFIX + name
        await self.bucket.put(key, png, "image/png")
        return key

    async def load(self, ref: str) -> bytes:
        data = await self.bucket.get(ref)
        if data is None:
            raise FileNotFoundError(f"card ausente no R2: {ref}")
        return data


class R2CardHost:
    """Mesma interface do `CardHost` (S3) do PC, mas gravando pelo binding."""

    def __init__(self, bucket: Bucket, public_base_url: str):
        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")

    async def upload(self, key: str, png: bytes) -> str:
        try:
            await self.bucket.put(key, png, "image/png")
        except Exception as e:
            raise CardHostError(f"R2 recusou o upload: {e}") from None
        return f"{self.public_base_url}/{key}"
