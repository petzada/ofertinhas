"""Envia os segredos do .env ao Worker pelo stdin do `wrangler secret bulk`, sem imprimir valores.

Na primeira vez, cria o TELEGRAM_WEBHOOK_SECRET e o ADMIN_TOKEN e os grava no .env.
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
    "EXTENSION_TOKEN", "ADMIN_TOKEN", "EXTENSION_ORIGIN", "TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID",
    "ML_AFFILIATE_TAG", "WHATSMIAU_API_KEY", "WHATSMIAU_INSTANCE", "R2_PUBLIC_URL",
    "TELEGRAM_WEBHOOK_SECRET", "WHATSAPP_TEST_JID", "X_API_KEY", "X_API_SECRET",
    "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
)


# Criados no .env na primeira vez que faltarem: nome → comentário que vai junto.
GENERATED = {
    "TELEGRAM_WEBHOOK_SECRET": "Segredo do webhook do bot na nuvem",
    "ADMIN_TOKEN": "Token das rotas /admin/* da nuvem (header X-Ofertinhas-Admin)",
}


def main() -> int:
    values = dotenv_values(ENV_FILE)
    for name, comment in GENERATED.items():
        if values.get(name):
            continue
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n# {comment} (cloud/worker/push_secrets.py)\n"
                    f"{name}={secrets.token_urlsafe(32)}\n")
        print(f"{name} criado no .env")
    values = dotenv_values(ENV_FILE)
    payload = {n: values[n] for n in NAMES if values.get(n)}
    print("enviando:", ", ".join(payload))
    result = subprocess.run(
        ["uvx", "--from", "workers-py", "pywrangler", "secret", "bulk"],
        input=json.dumps(payload), text=True, cwd=Path(__file__).parent,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
