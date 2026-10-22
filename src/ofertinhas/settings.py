"""Caminhos e endereços vindos do ambiente (.env)."""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("OFERTINHAS_DATA_DIR", "data")).resolve()
