"""Transforma um HAR gravado no navegador em fixtures de teste sem dados sensíveis.

Só entram respostas JSON de domínios do Mercado Livre. Headers e cookies nunca são
copiados, e e-mails, tokens e campos pessoais são mascarados nos corpos e nas URLs.
"""

import base64
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .text import slugify

ML_HOSTS = ("mercadolivre.com", "mercadolibre.com")
NOISE_MARKERS = ("melidata", "/tracks", "/analytics", "/clog", "/metrics", "/beacon")
REDACTED = "REDACTED"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
FAKE_EMAIL = "usuario@example.com"

SENSITIVE_EXACT = {
    "email", "first_name", "last_name", "nickname", "phone", "document", "cpf",
    "identification", "password", "address", "zip_code", "user_id", "cust_id",
    "customer_id", "buyer_id", "caller_id", "user", "users", "customer", "buyer",
    "me", "account", "profile",
    # createLink: lista de desejos do afiliado e URL longa com o token de afiliado
    "list_url", "deeplink_list_url", "long_url",
}
SENSITIVE_PARTS = ("token", "csrf", "session", "secret", "auth", "cookie", "ssid")


def is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return k in SENSITIVE_EXACT or any(part in k for part in SENSITIVE_PARTS)


def scrub_text(text: str, masks: Mapping[str, str] | None = None) -> str:
    for old, new in (masks or {}).items():
        text = text.replace(old, new)
    return EMAIL_RE.sub(FAKE_EMAIL, text)


def scrub_json(data: Any, masks: Mapping[str, str] | None = None) -> Any:
    if isinstance(data, dict):
        return {
            k: REDACTED if is_sensitive_key(k) else scrub_json(v, masks) for k, v in data.items()
        }
    if isinstance(data, list):
        return [scrub_json(v, masks) for v in data]
    if isinstance(data, str):
        return scrub_text(data, masks)
    return data


def scrub_url(url: str, masks: Mapping[str, str] | None = None) -> str:
    parts = urlparse(url)
    query = [
        (k, REDACTED if is_sensitive_key(k) else scrub_text(v, masks))
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    path = scrub_text(parts.path, masks)
    return urlunparse(parts._replace(path=path, query=urlencode(query)))


def _is_wanted(url: str, mime: str) -> bool:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    return (
        any(h in host for h in ML_HOSTS)
        and "json" in mime.lower()
        and not any(marker in path for marker in NOISE_MARKERS)
    )


def _parse_body(text: str | None, masks: Mapping[str, str] | None) -> Any:
    if text is None:
        return None
    try:
        return scrub_json(json.loads(text), masks)
    except ValueError:
        return scrub_text(text, masks)


def extract_har(
    har_path: Path, out_dir: Path, masks: Mapping[str, str] | None = None
) -> list[Path]:
    """Grava uma fixture por resposta JSON do ML e um `index.md`; devolve os arquivos."""
    har = json.loads(har_path.read_text(encoding="utf-8-sig"))
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    index_rows: list[str] = []

    for entry in har["log"]["entries"]:
        req, resp = entry["request"], entry["response"]
        content = resp.get("content", {})
        if not _is_wanted(req["url"], content.get("mimeType", "")):
            continue
        text = content.get("text")
        if text is not None and content.get("encoding") == "base64":
            text = base64.b64decode(text).decode("utf-8", errors="replace")
        url = scrub_url(req["url"], masks)
        fixture = {
            "request": {
                "method": req["method"],
                "url": url,
                "body": _parse_body(req.get("postData", {}).get("text"), masks),
            },
            "response": {"status": resp["status"], "body": _parse_body(text, masks)},
        }
        parsed = urlparse(req["url"])
        name = f"{len(written) + 1:03d}-{slugify(parsed.netloc + parsed.path)[:60]}.json"
        path = out_dir / name
        path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
        index_rows.append(f"| {name} | {req['method']} | {resp['status']} | `{url[:120]}` |")

    (out_dir / "index.md").write_text(
        "| arquivo | método | status | url |\n|---|---|---|---|\n" + "\n".join(index_rows) + "\n",
        encoding="utf-8",
    )
    return written
