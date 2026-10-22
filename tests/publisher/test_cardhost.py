import httpx
import pytest
import respx

from ofertinhas.publisher.cardhost import CardHost, CardHostError

ACCOUNT = "acc123"
UPLOAD = (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/r2/buckets/"
          "ofertinhas-cards/objects/cards/MLB1-casa.png")


@pytest.fixture
async def host():
    async with httpx.AsyncClient() as client:
        yield CardHost(client, ACCOUNT, "ofertinhas-cards", "tok",
                       "https://pub-x.r2.dev/")


@respx.mock
async def test_upload_returns_public_url(host):
    route = respx.put(UPLOAD).mock(return_value=httpx.Response(200, json={"success": True}))
    url = await host.upload("cards/MLB1-casa.png", b"\x89PNG")
    assert url == "https://pub-x.r2.dev/cards/MLB1-casa.png"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer tok"
    assert request.headers["content-type"] == "image/png"
    assert request.content == b"\x89PNG"


@respx.mock
async def test_upload_error(host):
    respx.put(UPLOAD).mock(return_value=httpx.Response(
        403, json={"success": False, "errors": [{"message": "Unauthorized"}]}))
    with pytest.raises(CardHostError, match="Unauthorized"):
        await host.upload("cards/MLB1-casa.png", b"x")
