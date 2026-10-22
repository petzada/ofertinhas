import httpx
import pytest
import respx

from ofertinhas.publisher.telegram import TelegramError, TelegramSender

TOKEN = "123:ABC"
URL = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
PNG = b"\x89PNG fake"


def ok(message_id=42):
    return httpx.Response(200, json={"ok": True, "result": {"message_id": message_id}})


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
async def sender(sleeps):
    async def fake_sleep(s):
        sleeps.append(s)

    async with httpx.AsyncClient() as client:
        yield TelegramSender(client, TOKEN, sleep=fake_sleep)


@respx.mock
async def test_send_photo_multipart(sender):
    route = respx.post(URL).mock(return_value=ok())
    assert await sender.send_photo(-1001, PNG, "<b>Oferta</b>") == "42"
    body = route.calls.last.request.content
    assert b'name="chat_id"' in body and b"-1001" in body
    assert b'name="parse_mode"' in body and b"HTML" in body
    assert b"<b>Oferta</b>" in body
    assert b'filename="card.png"' in body and PNG in body


@respx.mock
async def test_429_waits_retry_after(sender, sleeps):
    respx.post(URL).mock(side_effect=[
        httpx.Response(429, json={"ok": False, "error_code": 429, "description": "Too Many",
                                  "parameters": {"retry_after": 7}}),
        ok(),
    ])
    assert await sender.send_photo(-1, PNG, "x") == "42"
    assert sleeps == [7]


@respx.mock
async def test_400_is_not_retried(sender, sleeps):
    route = respx.post(URL).mock(return_value=httpx.Response(
        400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    ))
    with pytest.raises(TelegramError, match="chat not found") as exc:
        await sender.send_photo(-1, PNG, "x")
    assert exc.value.retryable is False
    assert route.call_count == 1 and sleeps == []


@respx.mock
async def test_network_errors_retry_with_backoff_then_fail(sender, sleeps):
    respx.post(URL).mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(TelegramError) as exc:
        await sender.send_photo(-1, PNG, "x")
    assert exc.value.retryable is True
    assert sleeps == [2, 4]


@respx.mock
async def test_send_message(sender):
    route = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(return_value=ok(7))
    assert await sender.send_message(5, "oi") == "7"
    assert route.calls.last.request.read()
