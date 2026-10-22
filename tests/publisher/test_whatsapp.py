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
async def test_send_image_by_public_url_and_caption(sender):
    # a WhatsMiau só aceita a imagem por URL pública (base64 e upload são recusados)
    route = respx.post(f"{BASE}/message/sendMedia/Ofertas01").mock(
        return_value=httpx.Response(201, json={"key": {"id": "ABC123"}})
    )
    url = "https://pub-x.r2.dev/cards/MLB1-casa.png"
    assert await sender.send_image(JID, url, "*Oferta*") == "ABC123"
    request = route.calls.last.request
    assert request.headers["apikey"] == "chave"
    body = json.loads(request.content)
    assert body["number"] == JID and body["mediatype"] == "image"
    assert body["mimetype"] == "image/png" and body["caption"] == "*Oferta*"
    assert body["media"] == url


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
        await sender.send_image(JID, "https://pub-x.r2.dev/c.png", "y")
    assert exc.value.retryable is False and route.call_count == 1 and sleeps == []


@respx.mock
async def test_huge_error_messages_are_truncated(sender):
    respx.post(f"{BASE}/message/sendMedia/Ofertas01").mock(return_value=httpx.Response(
        400, json={"error": {"Op": "Get", "URL": "iVBOR" * 10_000}}))
    with pytest.raises(WhatsAppError) as exc:
        await sender.send_image(JID, "https://pub-x.r2.dev/c.png", "y")
    assert len(str(exc.value)) <= 300


@respx.mock
async def test_server_errors_retry_with_backoff(sender, sleeps):
    ok = httpx.Response(200, json={"key": {"id": "Z"}})
    respx.post(f"{BASE}/message/sendMedia/Ofertas01").mock(
        side_effect=[httpx.Response(502), httpx.ConnectError("x"), ok]
    )
    assert await sender.send_image(JID, "https://pub-x.r2.dev/c.png", "y") == "Z"
    assert sleeps == [2, 4]


@respx.mock
async def test_pairing_code_for_number(sender):
    route = respx.get(f"{BASE}/instance/connect/Ofertas01").mock(return_value=httpx.Response(
        200, json={"id": "Ofertas01", "connected": False, "pairingCode": "ABCD-1234"}))
    assert await sender.pairing_code("+55 (11) 98888-7777") == "ABCD-1234"
    assert route.calls.last.request.url.params["number"] == "5511988887777"


@respx.mock
async def test_pairing_code_missing_is_an_error(sender):
    respx.get(f"{BASE}/instance/connect/Ofertas01").mock(
        return_value=httpx.Response(200, json={"connected": True}))
    with pytest.raises(WhatsAppError, match="código"):
        await sender.pairing_code("5511988887777")


@respx.mock
async def test_connection_state(sender):
    respx.get(f"{BASE}/instance/connectionState/Ofertas01").mock(return_value=httpx.Response(
        200, json={"instance": {"state": "open"}, "state": "open"}))
    assert await sender.connection_state() == "open"


@respx.mock
async def test_presence_errors_are_ignored(sender):
    respx.post(f"{BASE}/chat/sendPresence/Ofertas01").mock(return_value=httpx.Response(500))
    await sender.send_presence(JID)  # não levanta


@respx.mock
async def test_send_poll_single_and_multiple_choice(sender):
    route = respx.post(f"{BASE}/message/sendPoll/Ofertas01").mock(
        return_value=httpx.Response(201, json={"key": {"id": "POLL1"}})
    )
    assert await sender.send_poll(JID, "Quando?", ["2026", "2027"], multi=False) == "POLL1"
    body = json.loads(route.calls.last.request.content)
    assert body == {"number": JID, "name": "Quando?", "values": ["2026", "2027"],
                    "selectableCount": 1}
    await sender.send_poll(JID, "Quais?", ["a", "b", "c"], multi=True)
    assert json.loads(route.calls.last.request.content)["selectableCount"] == 0
