"""Aponta o bot do Telegram para o webhook do Worker (ou volta ao polling com --delete).

Só rode com o `run` local parado: com o webhook ativo, o polling do PC deixa de receber
updates, e com o polling ativo o Telegram recusa o webhook.
Uso (na pasta cloud/worker, com o .venv): python set_webhook.py [--delete]
"""

import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
WORKER_URL = "https://ofertinhas.marciopetigrosso.workers.dev"


def main() -> int:
    env = dotenv_values(ROOT / ".env")
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
