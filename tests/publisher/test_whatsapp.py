import base64
import json

import httpx
import pytest
import respx

from ofertinhas.publisher.whatsapp import WhatsAppError, WhatsAppSender

BASE = "https://api.whatsmiau.dev/v2"
JID = "120363000000000001@g.us"


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
async def sender(sleeps):
    async def fake_sleep(s):
        sleeps.append(s)

    async with httpx.AsyncClient() as client:
        yield WhatsAppSender(client, BASE, "chave", "Ofertas01", sleep=fake_sleep)


@respx.mock
async def test_send_image_with_base64_and_caption(sender):
    route = respx.post(f"{BASE}/message/sendMedia/Ofertas01").mock(
        return_value=httpx.Response(201, json={"key": {"id": "ABC123"}})
    )
    assert await sender.send_image(JID, b"\x89PNG", "*Oferta*") == "ABC123"
    request = route.calls.last.request
    assert request.headers["apikey"] == "chave"
    body = json.loads(request.content)
    assert body["number"] == JID and body["mediatype"] == "image"
    assert body["mimetype"] == "image/png" and body["caption"] == "*Oferta*"
    assert base64.b64decode(body["media"]) == b"\x89PNG"


@respx.mock
async def test_list_groups(sender):
    respx.get(f"{BASE}/group/fetchAllGroups/Ofertas01").mock(return_value=httpx.Response(
        200, json=[{"id": JID, "subject": "Achadinhos"}]))
    assert await sender.list_groups() == [{"id": JID, "subject": "Achadinhos"}]


@respx.mock
async def test_client_errors_are_not_retried(sender, sleeps):
    route = respx.post(f"{BASE}/message/sendMedia/Ofertas01").mock(
        return_value=httpx.Response(400, json={"message": "número inválido"}))
    with pytest.raises(WhatsAppError, match="inválido") as exc:
        await sender.send_image(JID, b"x", "y")
    assert exc.value.retryable is False and route.call_count == 1 and sleeps == []


@respx.mock
async def test_server_errors_retry_with_backoff(sender, sleeps):
    ok = httpx.Response(200, json={"key": {"id": "Z"}})
    respx.post(f"{BASE}/message/sendMedia/Ofertas01").mock(
        side_effect=[httpx.Response(502), httpx.ConnectError("x"), ok]
    )
    assert await sender.send_image(JID, b"x", "y") == "Z"
    assert sleeps == [2, 4]


@respx.mock
async def test_presence_errors_are_ignored(sender):
    respx.post(f"{BASE}/chat/sendPresence/Ofertas01").mock(return_value=httpx.Response(500))
    await sender.send_presence(JID)  # não levanta
