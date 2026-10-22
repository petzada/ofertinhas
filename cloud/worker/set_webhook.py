"""Aponta o bot do Telegram para o webhook do Worker (ou volta ao polling com --delete).

Só rode com o `run` local parado: com o webhook ativo, o polling do PC deixa de receber
updates, e com o polling ativo o Telegram recusa o webhook.
Com --whatsapp, aponta o webhook da WhatsMiau para a rota /wa/ (votos das enquetes). Se a
instância já tiver outro webhook, só troca com --force.
Uso (na pasta cloud/worker, com o .venv):
    python set_webhook.py [--delete | --whatsapp [--force]]
"""

import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
WORKER_URL = "https://ofertinhas.marciopetigrosso.workers.dev"
WHATSMIAU_URL = "https://api.whatsmiau.dev/v2"
# Os votos podem vir como mensagem nova ou como atualização da enquete (ver polls.py).
WHATSAPP_EVENTS = ["messages.upsert", "messages.update"]


def whatsapp(env: dict) -> int:
    base = (env.get("WHATSMIAU_BASE_URL") or WHATSMIAU_URL).rstrip("/")
    instance = env["WHATSMIAU_INSTANCE"]
    headers = {"apikey": env["WHATSMIAU_API_KEY"]}
    url = f"{WORKER_URL}/wa/{env['WHATSMIAU_WEBHOOK_SECRET']}"
    current = httpx.get(f"{base}/webhook/find/{instance}", headers=headers, timeout=30)
    current_url = ((current.json() or {}).get("url") or "") if current.is_success else ""
    ours = current_url.startswith(f"{WORKER_URL}/wa/")
    if current_url and not ours and "--force" not in sys.argv:
        print(f"a instância já manda eventos para {current_url}; use --force para trocar")
        return 1
    result = httpx.post(f"{base}/webhook/set/{instance}", headers=headers, timeout=30, json={
        "webhook": {"enabled": True, "url": url, "events": WHATSAPP_EVENTS},
    })
    print("resposta:", result.status_code, result.text[:300].replace(url, "<url com segredo>"))
    return 0 if result.is_success else 1


def main() -> int:
    env = dotenv_values(ROOT / ".env")
    if "--whatsapp" in sys.argv:
        return whatsapp(env)
    api = f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}"
    if "--delete" in sys.argv:
        result = httpx.post(f"{api}/deleteWebhook", timeout=30).json()
    else:
        secret = env["TELEGRAM_WEBHOOK_SECRET"]
        result = httpx.post(f"{api}/setWebhook", timeout=30, json={
            "url": f"{WORKER_URL}/tg/{secret}",
            "secret_token": secret,
            "allowed_updates": ["message", "callback_query"],
        }).json()
    info = httpx.get(f"{api}/getWebhookInfo", timeout=30).json().get("result", {})
    print("resposta:", result.get("ok"), result.get("description"))
    print("webhook ativo:", bool(info.get("url")), "| pendentes:", info.get("pending_update_count"),
          "| último erro:", info.get("last_error_message"))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
