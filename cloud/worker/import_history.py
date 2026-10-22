"""Leva do banco local para a nuvem as ofertas em cooldown e os posts dos últimos 8 dias.

Rode na virada, com o `run` local já parado (assim nada novo entra no banco local depois).
Uso (na pasta cloud/worker, com o .venv): python import_history.py [url-do-worker]
"""

import sqlite3
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

from ofertinhas.cloud.history import export_rows
from ofertinhas.models import utcnow

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = "https://ofertinhas.marciopetigrosso.workers.dev"


def main() -> int:
    url = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL).rstrip("/")
    token = dotenv_values(ROOT / ".env")["EXTENSION_TOKEN"]
    conn = sqlite3.connect(ROOT / "data" / "ofertinhas.db")
    conn.row_factory = sqlite3.Row
    data = export_rows(conn, utcnow())
    conn.close()
    print("exportado:", {table: len(rows) for table, rows in data.items()})
    response = httpx.post(f"{url}/admin/import", json=data, timeout=120,
                          headers={"X-Ofertinhas-Token": token})
    print("nuvem:", response.status_code, response.text[:300])
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
