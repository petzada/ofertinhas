"""Segredos e caminhos vindos do ambiente (arquivo `.env` na raiz do projeto)."""

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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


def _whatsapp_target(value: str | None) -> str | None:
    """JID como veio; número de telefone só com os dígitos (+55 11 9... → 55119...)."""
    if not value or not value.strip():
        return None
    value = value.strip()
    return value if "@" in value else "".join(c for c in value if c.isdigit()) or None


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
    ml_affiliate_tag: str | None = None  # etiqueta de afiliado usada no createLink
    whatsmiau_base_url: str = WHATSMIAU_BASE_URL
    # Cloudflare R2: cards públicos para o WhatsApp (a WhatsMiau só aceita imagem por URL)
    r2_account_id: str | None = None
    r2_bucket: str | None = None
    r2_public_url: str | None = None
    r2_api_token: str | None = None
    # Em dry-run, o WhatsApp vai só para cá (número com DDI e DDD ou JID), nunca para o grupo.
    whatsapp_test_jid: str | None = None
    # X (OAuth 1.0a de usuário): as 4 chaves do app no developer.x.com, com Read and Write
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_token_secret: str | None = None
    # Rotas /admin/* da nuvem (postar agora, importar histórico): token próprio, para quem
    # tiver o token da extensão (que fica no navegador) não poder postar nem apagar nada.
    admin_token: str | None = None

    @property
    def x_keys(self) -> tuple[str, str, str, str] | None:
        keys = (self.x_api_key, self.x_api_secret, self.x_access_token,
                self.x_access_token_secret)
        return keys if all(keys) else None

    _ENV_NAMES = {
        "ML_AFFILIATE_TAG": "ml_affiliate_tag",
        "EXTENSION_TOKEN": "extension_token",
        "ADMIN_TOKEN": "admin_token",
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
            ml_affiliate_tag=env.get("ML_AFFILIATE_TAG") or None,
            whatsmiau_base_url=env.get("WHATSMIAU_BASE_URL") or WHATSMIAU_BASE_URL,
            r2_account_id=env.get("R2_ACCOUNT_ID") or None,
            r2_bucket=env.get("R2_BUCKET") or None,
            r2_public_url=env.get("R2_PUBLIC_URL") or None,
            r2_api_token=env.get("R2_API_TOKEN") or None,
            whatsapp_test_jid=_whatsapp_target(env.get("WHATSAPP_TEST_JID")),
            x_api_key=env.get("X_API_KEY") or None,
            x_api_secret=env.get("X_API_SECRET") or None,
            x_access_token=env.get("X_ACCESS_TOKEN") or None,
            x_access_token_secret=env.get("X_ACCESS_TOKEN_SECRET") or None,
            admin_token=env.get("ADMIN_TOKEN") or None,
        )

    @classmethod
    def load(cls, dotenv_path: str | Path = ".env") -> "Settings":
        """`.env` primeiro; variáveis de ambiente do sistema têm precedência."""
        from dotenv import dotenv_values  # só no PC; na nuvem os segredos vêm do Worker

        values = {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}
        return cls.from_env(values | dict(os.environ))

    def require(self, *env_names: str) -> None:
        missing = [n for n in env_names if getattr(self, self._ENV_NAMES[n]) in (None, "")]
        if missing:
            raise SettingsError(f"faltam no .env: {', '.join(missing)}")
