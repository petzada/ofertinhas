"""Envia os segredos do .env ao Worker pelo stdin do `wrangler secret bulk`, sem imprimir valores.

Na primeira vez, cria o TELEGRAM_WEBHOOK_SECRET e o grava no .env.
Uso (na pasta cloud/worker, com o .venv no PATH): python push_secrets.py
"""

import json
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
NAMES = (
    "EXTENSION_TOKEN", "EXTENSION_ORIGIN", "TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID",
    "ML_AFFILIATE_TAG", "WHATSMIAU_API_KEY", "WHATSMIAU_INSTANCE", "R2_PUBLIC_URL",
    "TELEGRAM_WEBHOOK_SECRET",
)


def main() -> int:
    values = dotenv_values(ENV_FILE)
    if not values.get("TELEGRAM_WEBHOOK_SECRET"):
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.write("\n# Segredo do webhook do bot na nuvem (cloud/worker/push_secrets.py)\n"
                    f"TELEGRAM_WEBHOOK_SECRET={secrets.token_urlsafe(32)}\n")
        values = dotenv_values(ENV_FILE)
        print("TELEGRAM_WEBHOOK_SECRET criado no .env")
    payload = {n: values[n] for n in NAMES if values.get(n)}
    print("enviando:", ", ".join(payload))
    result = subprocess.run(
        ["uvx", "--from", "workers-py", "pywrangler", "secret", "bulk"],
        input=json.dumps(payload), text=True, cwd=Path(__file__).parent,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
