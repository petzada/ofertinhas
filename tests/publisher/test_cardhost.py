import hashlib
from datetime import UTC, datetime

import httpx
import pytest
import respx

from ofertinhas.publisher.cardhost import CardHost, CardHostError, sign_s3_put

ACCOUNT = "acc123"
TOKEN = "tok-valor"
VERIFY = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/tokens/verify"
S3_PUT = f"https://{ACCOUNT}.r2.cloudflarestorage.com/ofertinhas-cards/cards/MLB1-casa.png"
NOW = datetime(2026, 10, 22, 6, 30, tzinfo=UTC)


@pytest.fixture
async def host():
    async with httpx.AsyncClient() as client:
        yield CardHost(client, ACCOUNT, "ofertinhas-cards", TOKEN, "https://pub-x.r2.dev/",
                       clock=lambda: NOW)


def verified(token_id="tokid"):
    return httpx.Response(200, json={"success": True, "result": {"id": token_id,
                                                                 "status": "active"}})


@respx.mock
async def test_upload_by_s3_with_credentials_derived_from_token(host):
    verify = respx.get(VERIFY).mock(return_value=verified())
    put = respx.put(S3_PUT).mock(return_value=httpx.Response(200))
    url = await host.upload("cards/MLB1-casa.png", b"\x89PNG")
    assert url == "https://pub-x.r2.dev/cards/MLB1-casa.png"
    request = put.calls.last.request
    assert request.content == b"\x89PNG"
    assert request.headers["content-type"] == "image/png"
    assert request.headers["x-amz-date"] == "20261022T063000Z"
    assert request.headers["x-amz-content-sha256"] == hashlib.sha256(b"\x89PNG").hexdigest()
    assert request.headers["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=tokid/20261022/auto/s3/aws4_request, "
        "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date, Signature="
    )
    assert verify.calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"
    await host.upload("cards/MLB1-casa.png", b"\x89PNG")
    assert verify.call_count == 1  # id do token buscado uma vez só


@respx.mock
async def test_upload_error(host):
    respx.get(VERIFY).mock(return_value=verified())
    respx.put(S3_PUT).mock(return_value=httpx.Response(403, text="<Error>AccessDenied</Error>"))
    with pytest.raises(CardHostError, match="403"):
        await host.upload("cards/MLB1-casa.png", b"x")


@respx.mock
async def test_invalid_token(host):
    respx.get(VERIFY).mock(return_value=httpx.Response(
        401, json={"success": False, "errors": [{"message": "Invalid API Token"}]}))
    with pytest.raises(CardHostError, match="Invalid API Token"):
        await host.upload("cards/MLB1-casa.png", b"x")


def test_signature_is_deterministic_and_depends_on_secret():
    args = dict(host="h", path="/b/k.png", body=b"x", access_key="id", now=NOW)
    a = sign_s3_put(secret="s1", **args)
    assert a == sign_s3_put(secret="s1", **args)
    assert a["Authorization"] != sign_s3_put(secret="s2", **args)["Authorization"]
