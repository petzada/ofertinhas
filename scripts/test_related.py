"""Testes afetados pelo branch, para rodar antes de abrir o PR.

- Python: `pytest --testmon` (só os testes cujo código executado mudou; o 1º run monta o
  .testmondata e passa por todos).
- Extensão: `node --test` quando o diff contra `origin/main` toca `extension/`.

Uso: `.venv/Scripts/python scripts/test_related.py` (Linux/macOS: `.venv/bin/python`).
Chama os binários direto, sem lista de arquivos no shell.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "origin/main"


def changed_files() -> list[str]:
    # merge-base + working tree: pega commits do branch e mudanças ainda não commitadas.
    try:
        base = subprocess.run(
            ["git", "merge-base", BASE, "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        out = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    return [line for line in out.splitlines() if line.strip()]


def main() -> int:
    code = subprocess.call([sys.executable, "-m", "pytest", "--testmon", "-q"], cwd=ROOT)
    # 5 = nenhum teste selecionado (nada afetado): não é falha.
    if code not in (0, 5):
        return code
    if any(f.startswith("extension/") for f in changed_files()):
        node = shutil.which("node")
        if node is None:
            print("node não encontrado: testes da extensão pulados", file=sys.stderr)
            return 1
        code = subprocess.call([node, "--test", "tests/**/*.test.js"], cwd=ROOT / "extension")
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
