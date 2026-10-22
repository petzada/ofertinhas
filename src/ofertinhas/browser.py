"""Chromium com perfil persistente, onde fica a sessão logada do Mercado Livre.

O perfil só pode ser aberto por um processo por vez, e o trabalho usa uma aba por vez
(o lock), para poupar CPU e parecer navegação humana.
"""

import asyncio
import random
import re
import unicodedata
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from .models import utcnow

ML_HOSTS = ("mercadolivre.com", "mercadolibre.com")


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def is_ml_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(h in host for h in ML_HOSTS)


def is_login_url(url: str) -> bool:
    """A URL é a tela de login do Mercado Livre (sessão expirada)."""
    segments = urlparse(url).path.lower().split("/")
    return is_ml_host(url) and "login" in segments


async def human_pause(
    min_s: float = 2,
    max_s: float = 6,
    rng: random.Random | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    await sleep((rng or random).uniform(min_s, max_s))


async def dump_debug(page: Page, label: str, debug_root: Path, now: datetime | None = None) -> Path:
    """Salva screenshot, HTML e URL da página para investigar uma falha."""
    stamp = (now or utcnow()).strftime("%Y%m%d-%H%M%S")
    out = debug_root / f"{stamp}-{slugify(label)}"
    out.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(out / "page.png"), full_page=True)
    (out / "page.html").write_text(await page.content(), encoding="utf-8")
    (out / "url.txt").write_text(page.url, encoding="utf-8")
    return out


async def launch_context(
    pw: Playwright, profile_dir: Path, headless: bool = True
) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    return await pw.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 768} if headless else None,
    )


class BrowserSession:
    """Contexto persistente compartilhado pelo coletor e pelo gerador de links."""

    def __init__(self, profile_dir: Path, headless: bool = True):
        self.profile_dir = profile_dir
        self.headless = headless
        self._lock = asyncio.Lock()
        self._pw: Playwright | None = None
        self.context: BrowserContext | None = None

    async def __aenter__(self) -> "BrowserSession":
        self._pw = await async_playwright().start()
        self.context = await launch_context(self._pw, self.profile_dir, self.headless)
        return self

    async def __aexit__(self, *exc) -> None:
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    @asynccontextmanager
    async def page(self) -> AsyncIterator[Page]:
        async with self._lock:
            page = await self.context.new_page()
            try:
                yield page
            finally:
                await page.close()

    async def is_logged_in(self, url: str) -> bool:
        async with self.page() as page:
            await page.goto(url, wait_until="domcontentloaded")
            return not is_login_url(page.url)
