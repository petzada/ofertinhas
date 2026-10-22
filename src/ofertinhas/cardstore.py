"""Onde os PNG dos cards ficam entre a geração e o post: disco no PC, R2 na nuvem.

`save` devolve a referência gravada em `card_path`; `load` lê de volta pela referência.
"""

from pathlib import Path
from typing import Protocol


class CardStore(Protocol):
    async def save(self, name: str, png: bytes) -> str: ...

    async def load(self, ref: str) -> bytes: ...


class DiskCards:
    def __init__(self, folder: Path):
        self.folder = folder

    async def save(self, name: str, png: bytes) -> str:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / name
        path.write_bytes(png)
        return str(path)

    async def load(self, ref: str) -> bytes:
        return Path(ref).read_bytes()
