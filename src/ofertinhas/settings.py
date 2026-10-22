"""Caminhos e endereços vindos do ambiente (.env)."""

import os
from pathlib import Path

DEFAULT_PORTAL_URL = "https://www.mercadolivre.com.br/afiliados"


def data_dir() -> Path:
    return Path(os.environ.get("OFERTINHAS_DATA_DIR", "data")).resolve()


def chrome_profile_dir() -> Path:
    return data_dir() / "chrome-profile"


def debug_dir() -> Path:
    return data_dir() / "debug"


def portal_url() -> str:
    return os.environ.get("ML_PORTAL_URL", DEFAULT_PORTAL_URL)
