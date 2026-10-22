"""Grava páginas e respostas JSON reais do Mercado Livre para mapear o portal.

Abre o navegador visível com o perfil persistente. Você faz login e navega pelas telas, e
tudo que for JSON de domínio do ML vai sendo gravado em disco. Também é gravado um snapshot
(HTML e PNG) sempre que o conteúdo da página muda. Ao fechar a janela, a captura termina.
A saída fica em `data/capture/`, fora do Git, porque pode conter dados pessoais.
"""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from .browser import is_ml_host, launch_context, slugify

NOISE_MARKERS = ("melidata", "/tracks", "/analytics", "/clog", "/metrics", "/beacon")
MAX_BODY_BYTES = 2_000_000


def should_record(url: str, content_type: str) -> bool:
    if not is_ml_host(url) or "json" not in content_type.lower():
        return False
    path = urlparse(url).path.lower()
    return not any(marker in path for marker in NOISE_MARKERS)


def response_filename(index: int, url: str) -> str:
    parsed = urlparse(url)
    return f"{index:04d}-{slugify(parsed.netloc + parsed.path)[:80]}.json"


def _append_jsonl(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class CaptureRecorder:
    def __init__(self, out_dir: Path, max_body: int = MAX_BODY_BYTES):
        self.out_dir = out_dir
        self.max_body = max_body
        self.responses = 0
        self._page_hashes: set[str] = set()
        (out_dir / "responses").mkdir(parents=True, exist_ok=True)
        (out_dir / "pages").mkdir(parents=True, exist_ok=True)

    @property
    def pages(self) -> int:
        return len(self._page_hashes)

    async def on_response(self, response) -> None:
        try:
            if not should_record(response.url, response.headers.get("content-type", "")):
                return
            body = await response.body()
        except Exception:
            return  # a resposta pode sumir se a página navegar antes
        if len(body) > self.max_body:
            return
        self.responses += 1
        name = response_filename(self.responses, response.url)
        (self.out_dir / "responses" / name).write_bytes(body)
        _append_jsonl(
            self.out_dir / "responses.jsonl",
            {
                "file": name,
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
                "post_data": response.request.post_data,
            },
        )

    async def snapshot(self, page) -> bool:
        """Grava HTML e PNG da página se o conteúdo mudou desde o último snapshot."""
        html = await page.content()
        digest = hashlib.sha1(html.encode("utf-8")).hexdigest()
        if digest in self._page_hashes:
            return False
        self._page_hashes.add(digest)
        stem = f"{len(self._page_hashes):03d}"
        (self.out_dir / "pages" / f"{stem}.html").write_text(html, encoding="utf-8")
        await page.screenshot(path=str(self.out_dir / "pages" / f"{stem}.png"), full_page=True)
        _append_jsonl(
            self.out_dir / "pages.jsonl",
            {"file": f"{stem}.html", "url": page.url, "title": await page.title()},
        )
        return True


async def run_capture(
    start_url: str,
    out_dir: Path,
    profile_dir: Path,
    max_minutes: float = 30,
    snapshot_every_s: float = 5,
) -> CaptureRecorder:
    recorder = CaptureRecorder(out_dir)
    async with async_playwright() as pw:
        context = await launch_context(pw, profile_dir, headless=False)
        closed = asyncio.Event()
        context.on("close", lambda _: closed.set())
        context.on("response", recorder.on_response)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(start_url)

        deadline = time.monotonic() + max_minutes * 60
        while not closed.is_set() and context.pages and time.monotonic() < deadline:
            for p in list(context.pages):
                try:
                    await recorder.snapshot(p)
                except Exception:
                    pass  # página navegando ou fechando
            try:
                await asyncio.wait_for(closed.wait(), timeout=snapshot_every_s)
            except TimeoutError:
                pass
        try:
            await context.close()
        except Exception:
            pass
    return recorder
