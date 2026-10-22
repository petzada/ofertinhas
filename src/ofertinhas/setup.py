"""Preparação local: config.yaml, .env e a config que a extensão lê sozinha.

Nunca sobrescreve o que já existe, só preenche o que falta. O token não aparece no relatório.
"""

import json
import shutil
from pathlib import Path

from dotenv import dotenv_values, set_key

from .settings import new_token

EXTENSION_CONFIG = Path("extension") / "config.local.json"


def run_setup(root: Path, affiliate_tag: str | None) -> list[str]:
    report = []
    config = root / "config.yaml"
    if not config.exists():
        shutil.copyfile(root / "config.example.yaml", config)
        report.append("config.yaml criado a partir do exemplo")

    env_path = root / ".env"
    if not env_path.exists():
        shutil.copyfile(root / ".env.example", env_path)
        report.append(".env criado a partir do exemplo")
    env = dotenv_values(env_path)
    if not env.get("EXTENSION_TOKEN"):
        set_key(env_path, "EXTENSION_TOKEN", new_token(), quote_mode="never")
        report.append("token da extensão gerado no .env")
    if affiliate_tag:
        set_key(env_path, "ML_AFFILIATE_TAG", affiliate_tag, quote_mode="never")
        report.append(f"ML_AFFILIATE_TAG={affiliate_tag} no .env")

    env = dotenv_values(env_path)
    port = env.get("API_PORT") or "8765"
    extension_config = root / EXTENSION_CONFIG
    extension_config.write_text(
        json.dumps({"backendUrl": f"http://127.0.0.1:{port}", "token": env["EXTENSION_TOKEN"]},
                   indent=2),
        encoding="utf-8",
    )
    report.append(f"{EXTENSION_CONFIG.as_posix()} gravado (a extensão lê o token dele)")
    if not env.get("ML_AFFILIATE_TAG"):
        report.append("falta ML_AFFILIATE_TAG: rode de novo com --tag <sua tag>")
    return report
