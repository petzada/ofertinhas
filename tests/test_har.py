import base64
import json

from ofertinhas.har import extract_har, scrub_json, scrub_url

SECRET_COOKIE = "ssid=ghy-SEGREDO-COOKIE"
SECRET_AUTH = "Bearer APP_USR-SEGREDO-AUTH"


def entry(url, body, mime="application/json", status=200, method="GET", post=None, b64=False):
    text = json.dumps(body) if not isinstance(body, str) else body
    content = {"mimeType": mime, "text": text}
    if b64:
        content = {"mimeType": mime, "text": base64.b64encode(text.encode()).decode(),
                   "encoding": "base64"}
    req = {
        "method": method,
        "url": url,
        "headers": [{"name": "Cookie", "value": SECRET_COOKIE},
                    {"name": "Authorization", "value": SECRET_AUTH}],
        "cookies": [{"name": "ssid", "value": "ghy-SEGREDO-COOKIE"}],
    }
    if post:
        req["postData"] = {"mimeType": "application/json", "text": json.dumps(post)}
    resp_headers = [{"name": "Set-Cookie", "value": SECRET_COOKIE}]
    return {
        "request": req,
        "response": {"status": status, "content": content, "headers": resp_headers},
    }


def har(*entries):
    return {"log": {"entries": list(entries)}}


def write_har(tmp_path, data):
    path = tmp_path / "portal.har"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_keeps_only_ml_json(tmp_path):
    path = write_har(tmp_path, har(
        entry("https://www.mercadolivre.com.br/affiliate/api/offers?page=1", {"results": [1]}),
        entry("https://http2.mlstatic.com/x.webp", "bin", mime="image/webp"),
        entry("https://www.google-analytics.com/collect", {"a": 1}),
        entry("https://www.mercadolivre.com.br/melidata/tracks", {"t": 1}),
    ))
    out = tmp_path / "fixtures"
    files = extract_har(path, out)
    assert [f.name for f in files] == ["001-www-mercadolivre-com-br-affiliate-api-offers.json"]
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["response"]["body"] == {"results": [1]}
    assert saved["request"]["url"].endswith("offers?page=1")
    assert (out / "index.md").exists()


def test_no_secrets_survive(tmp_path):
    path = write_har(tmp_path, har(
        entry(
            "https://www.mercadolivre.com.br/api/me?access_token=TOKEN123&caller=fulano@gmail.com",
            {"user": {"id": 98765, "email": "fulano@gmail.com", "first_name": "Fulano",
                      "nickname": "FULANO123"},
             "note": "contato fulano@gmail.com", "nome_livre": "Fulano da Silva"},
            method="POST",
            post={"url": "https://produto.mercadolivre.com.br/MLB-1", "csrf_token": "CSRF999"},
        ),
    ))
    out = tmp_path / "fixtures"
    extract_har(path, out, masks={"Fulano da Silva": "Pessoa Exemplo"})
    dumped = "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    for secret in ("SEGREDO", "TOKEN123", "fulano@gmail.com", "FULANO123", "CSRF999",
                   "Fulano da Silva", "98765"):
        assert secret not in dumped, secret
    assert "MLB-1" in dumped  # dado útil preservado
    assert "Pessoa Exemplo" in dumped


def test_base64_bodies_are_decoded(tmp_path):
    path = write_har(tmp_path, har(
        entry("https://www.mercadolivre.com.br/api/x", {"ok": True}, b64=True),
    ))
    files = extract_har(path, tmp_path / "out")
    assert json.loads(files[0].read_text(encoding="utf-8"))["response"]["body"] == {"ok": True}


def test_cli_har_extract_with_mask(tmp_path):
    from ofertinhas.__main__ import main

    path = write_har(tmp_path, har(
        entry("https://www.mercadolivre.com.br/api/x", {"title": "Loja do Fulano"}),
    ))
    out = tmp_path / "out"
    assert main(["har-extract", str(path), "--out", str(out), "--mask", "Fulano=Exemplo"]) == 0
    assert "Loja do Exemplo" in next(out.glob("001-*.json")).read_text(encoding="utf-8")


def test_scrub_json_masks_sensitive_keys_recursively():
    data = {"a": [{"token": "x", "price": 10}], "phone": {"number": "119"}}
    assert scrub_json(data) == {"a": [{"token": "REDACTED", "price": 10}], "phone": "REDACTED"}


def test_scrub_json_masks_affiliate_private_urls():
    data = {"urls": [{"short_url": "https://meli.la/abc", "long_url": "https://x?ref=SEGREDO",
                      "list_url": "https://myaccount/x", "deeplink_list_url": "meli://x"}]}
    assert scrub_json(data) == {"urls": [{"short_url": "https://meli.la/abc",
                                          "long_url": "REDACTED", "list_url": "REDACTED",
                                          "deeplink_list_url": "REDACTED"}]}


def test_scrub_url_masks_sensitive_query_params():
    url = "https://x.mercadolivre.com.br/a?access_token=abc&page=2&csrf=1"
    assert scrub_url(url) == "https://x.mercadolivre.com.br/a?access_token=REDACTED&page=2&csrf=REDACTED"
