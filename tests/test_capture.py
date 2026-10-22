import json

import pytest

from ofertinhas.capture import CaptureRecorder, response_filename, should_record


@pytest.mark.parametrize(
    ("url", "content_type", "expected"),
    [
        ("https://www.mercadolivre.com.br/affiliate/api/v2/offers", "application/json", True),
        ("https://api.mercadolibre.com/items/MLB1", "application/json; charset=utf-8", True),
        ("https://www.mercadolivre.com.br/afiliados", "text/html", False),
        ("https://http2.mlstatic.com/D_NQ_NP_123-O.webp", "image/webp", False),
        ("https://www.mercadolivre.com.br/melidata/tracks", "application/json", False),
        ("https://www.google-analytics.com/collect", "application/json", False),
    ],
)
def test_should_record(url, content_type, expected):
    assert should_record(url, content_type) is expected


def test_response_filename_is_numbered_and_readable():
    name = response_filename(7, "https://www.mercadolivre.com.br/affiliate-program/api/offers?page=2")
    assert name == "0007-www-mercadolivre-com-br-affiliate-program-api-offers.json"


class FakeRequest:
    method = "POST"
    post_data = '{"url": "https://produto.mercadolivre.com.br/MLB-1"}'


class FakeResponse:
    def __init__(self, url, content_type="application/json", body=b'{"ok": true}'):
        self.url = url
        self.status = 200
        self.headers = {"content-type": content_type}
        self.request = FakeRequest()
        self._body = body

    async def body(self):
        return self._body


class FakePage:
    def __init__(self, html, url="https://www.mercadolivre.com.br/afiliados"):
        self.html = html
        self.url = url

    async def content(self):
        return self.html

    async def title(self):
        return "Afiliados"

    async def screenshot(self, path, full_page=False):
        with open(path, "wb") as f:
            f.write(b"png")


async def test_recorder_saves_json_body_and_index(tmp_path):
    rec = CaptureRecorder(tmp_path)
    await rec.on_response(FakeResponse("https://www.mercadolivre.com.br/api/offers"))
    await rec.on_response(FakeResponse("https://http2.mlstatic.com/x.webp", "image/webp"))
    files = list((tmp_path / "responses").iterdir())
    assert [f.name for f in files] == ["0001-www-mercadolivre-com-br-api-offers.json"]
    entry = json.loads((tmp_path / "responses.jsonl").read_text(encoding="utf-8"))
    assert entry["method"] == "POST" and entry["status"] == 200
    assert "MLB-1" in entry["post_data"]
    assert rec.responses == 1


async def test_recorder_skips_huge_bodies(tmp_path):
    rec = CaptureRecorder(tmp_path, max_body=10)
    await rec.on_response(FakeResponse("https://www.mercadolivre.com.br/api/x", body=b"x" * 11))
    assert rec.responses == 0


async def test_snapshot_dedupes_identical_pages(tmp_path):
    rec = CaptureRecorder(tmp_path)
    assert await rec.snapshot(FakePage("<p>a</p>")) is True
    assert await rec.snapshot(FakePage("<p>a</p>")) is False
    assert await rec.snapshot(FakePage("<p>b</p>")) is True
    names = sorted(f.name for f in (tmp_path / "pages").iterdir())
    assert names == ["001.html", "001.png", "002.html", "002.png"]
    lines = (tmp_path / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1])["file"] == "002.html"
