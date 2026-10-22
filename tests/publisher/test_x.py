import base64
import hashlib
import hmac
import json
from urllib.parse import quote

import httpx
import pytest
import respx

from ofertinhas.creative.format import X_LIMIT, to_x, x_length
from ofertinhas.publisher.x import UPLOAD_V1, UPLOAD_V2, XError, XSender, oauth1_header

KEYS = dict(api_key="ck", api_secret="cs", token="tk", token_secret="ts")
LINK = "https://meli.la/1aWWv7B"


def enc(value):
    return quote(value, safe="~-._")


def test_oauth1_signature_follows_the_spec():
    header = oauth1_header("POST", "https://api.x.com/2/tweets", nonce="abc", timestamp="1",
                           **KEYS)
    params = ("oauth_consumer_key=ck&oauth_nonce=abc&oauth_signature_method=HMAC-SHA1"
              "&oauth_timestamp=1&oauth_token=tk&oauth_version=1.0")
    base = f"POST&{enc('https://api.x.com/2/tweets')}&{enc(params)}"
    expected = base64.b64encode(hmac.new(b"cs&ts", base.encode(), hashlib.sha1).digest())
    assert header.startswith("OAuth ")
    assert f'oauth_signature="{enc(expected.decode())}"' in header
    assert 'oauth_token="tk"' in header and 'oauth_version="1.0"' in header


def sender(client):
    return XSender(client, "ck", "cs", "tk", "ts", nonce=lambda: "n", clock=lambda: 1.0)


@respx.mock
async def test_thread_has_card_and_text_then_the_link_as_reply():
    upload = respx.post(UPLOAD_V2).respond(200, json={"data": {"id": "m1"}})
    tweets = respx.post("https://api.x.com/2/tweets").mock(side_effect=[
        httpx.Response(201, json={"data": {"id": "t1"}}),
        httpx.Response(201, json={"data": {"id": "t2"}}),
    ])
    async with httpx.AsyncClient() as client:
        assert await sender(client).post_thread(b"png", "Oferta", LINK) == ("t1", "t2")
    assert upload.calls[0].request.headers["Authorization"].startswith("OAuth ")
    first, reply = (json.loads(c.request.content) for c in tweets.calls)
    assert first == {"text": "Oferta", "media": {"media_ids": ["m1"]}}
    assert reply == {"text": LINK, "reply": {"in_reply_to_tweet_id": "t1"}}


@respx.mock
async def test_upload_falls_back_to_v1_when_v2_is_refused():
    respx.post(UPLOAD_V2).respond(403, json={"title": "Forbidden"})
    respx.post(UPLOAD_V1).respond(200, json={"media_id_string": "m9"})
    async with httpx.AsyncClient() as client:
        assert await sender(client).upload_png(b"png") == "m9"


@respx.mock
async def test_errors_carry_the_reason_and_say_if_retrying_helps():
    respx.post(UPLOAD_V2).respond(503, json={"title": "Service Unavailable"})
    async with httpx.AsyncClient() as client:
        with pytest.raises(XError) as error:
            await sender(client).upload_png(b"png")
    assert error.value.retryable and "503" in str(error.value)


def test_x_text_drops_link_and_formatting_and_points_to_the_reply():
    neutral = (f"🔥 *Air Fryer Mondial 4L*\n\nDe ~R$ 499,90~ por *R$ 299,90* (40% OFF)\n"
               f"⭐ 4,8 • 1.000+ vendidos\n\n👉 {LINK}")
    text = to_x(neutral, LINK)
    assert LINK not in text and "*" not in text and "~" not in text
    assert "De R$ 499,90 por R$ 299,90 (40% OFF)" in text
    assert text.endswith("👇 Link no post abaixo")


def test_x_text_keeps_a_template_that_already_points_down():
    text = to_x(f"🚨 ACHADINHO 🚨\n\nCorre antes que acabe 👇\n{LINK}", LINK)
    assert text.endswith("Corre antes que acabe 👇") and "Link no post" not in text


def test_x_text_fits_in_280():
    long = "🔥 " + "Kit Panelas Antiaderente Tramontina Paris " * 8
    text = to_x(f"{long}\n\n🔎 No app, busque: ABC123\n⭐ 4,9\n\n👉 {LINK}", LINK)
    assert x_length(text) <= X_LIMIT and "🔎" not in text and text.endswith("abaixo")
