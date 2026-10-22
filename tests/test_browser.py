import random
from datetime import UTC, datetime

import pytest

from ofertinhas.browser import dump_debug, human_pause, is_login_url


class FakePage:
    url = "https://www.mercadolivre.com.br/afiliados"

    async def content(self):
        return "<html><body>oi</body></html>"

    async def screenshot(self, path, full_page=False):
        with open(path, "wb") as f:
            f.write(b"\x89PNG")


async def test_human_pause_stays_within_bounds():
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    rng = random.Random(42)
    for _ in range(50):
        await human_pause(2, 6, rng=rng, sleep=fake_sleep)
    assert all(2 <= w <= 6 for w in waits)
    assert len(set(waits)) > 1


async def test_dump_debug_writes_screenshot_html_and_url(tmp_path):
    out = await dump_debug(
        FakePage(), "Link falhou: MLB1", tmp_path, now=datetime(2026, 10, 22, 15, tzinfo=UTC)
    )
    assert out.parent == tmp_path
    assert out.name == "20261022-150000-link-falhou-mlb1"
    assert (out / "page.png").read_bytes() == b"\x89PNG"
    assert "oi" in (out / "page.html").read_text(encoding="utf-8")
    assert (out / "url.txt").read_text(encoding="utf-8") == FakePage.url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.mercadolivre.com/jms/mlb/lgz/login?platform_id=ML", True),
        ("https://www.mercadolivre.com.br/login", True),
        ("https://www.mercadolivre.com.br/afiliados/linkbuilder", False),
        ("https://produto.mercadolivre.com.br/MLB-123-login-gamer", False),
        ("https://example.com/login", False),
    ],
)
def test_is_login_url(url, expected):
    assert is_login_url(url) is expected
