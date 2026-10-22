"""Segredos e caminhos vindos do ambiente (arquivo `.env` na raiz do projeto)."""

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

WHATSMIAU_BASE_URL = "https://api.whatsmiau.dev/v2"


class SettingsError(ValueError):
    pass


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _int(env: Mapping[str, str], name: str, default: int | None = None) -> int | None:
    value = env.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise SettingsError(f"{name} precisa ser um número inteiro: {value!r}") from None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    api_port: int
    extension_token: str | None
    extension_origin: str | None  # chrome-extension://<id>, para CORS
    telegram_bot_token: str | None
    admin_chat_id: int | None
    whatsmiau_api_key: str | None
    whatsmiau_instance: str | None
    whatsmiau_base_url: str = WHATSMIAU_BASE_URL

    _ENV_NAMES = {
        "EXTENSION_TOKEN": "extension_token",
        "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
        "ADMIN_CHAT_ID": "admin_chat_id",
        "WHATSMIAU_API_KEY": "whatsmiau_api_key",
        "WHATSMIAU_INSTANCE": "whatsmiau_instance",
    }

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        return cls(
            data_dir=Path(env.get("OFERTINHAS_DATA_DIR") or "data").resolve(),
            config_path=Path(env.get("OFERTINHAS_CONFIG") or "config.yaml").resolve(),
            api_port=_int(env, "API_PORT", 8765),
            extension_token=env.get("EXTENSION_TOKEN") or None,
            extension_origin=env.get("EXTENSION_ORIGIN") or None,
            telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN") or None,
            admin_chat_id=_int(env, "ADMIN_CHAT_ID"),
            whatsmiau_api_key=env.get("WHATSMIAU_API_KEY") or None,
            whatsmiau_instance=env.get("WHATSMIAU_INSTANCE") or None,
            whatsmiau_base_url=env.get("WHATSMIAU_BASE_URL") or WHATSMIAU_BASE_URL,
        )

    @classmethod
    def load(cls, dotenv_path: str | Path = ".env") -> "Settings":
        """`.env` primeiro; variáveis de ambiente do sistema têm precedência."""
        values = {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}
        return cls.from_env(values | dict(os.environ))

    def require(self, *env_names: str) -> None:
        missing = [n for n in env_names if getattr(self, self._ENV_NAMES[n]) in (None, "")]
        if missing:
            raise SettingsError(f"faltam no .env: {', '.join(missing)}")
