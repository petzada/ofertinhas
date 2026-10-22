"""Identificação do que está rodando: commit do código e hash do config.yaml.

Na nuvem, o `cloud/worker/deploy.py` grava `version.json` no bundle; no PC, sai do Git na
hora. Aparece no `/health`, no `/admin/status` e na mensagem de status fixada.
"""

import hashlib
import json
import subprocess
from pathlib import Path

BUILD_FILE = "version.json"


def config_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def load_build(bundle_dir: Path) -> dict | None:
    path = bundle_dir / BUILD_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def local_build(project: Path, config_path: Path) -> dict:
    """Commit atual (com `dirty` se há mudança não commitada) e hash do config."""

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=project, capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {
        "commit": git("rev-parse", "--short=12", "HEAD") or "desconhecido",
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "config_sha": config_sha(config_path) if config_path.exists() else None,
    }


def describe(build: dict | None) -> str | None:
    """`abc1234+mod • config 1a2b3c4d5e6f`, para mostrar ao admin."""
    if not build:
        return None
    text = str(build.get("commit", "?"))[:7] + ("+mod" if build.get("dirty") else "")
    if build.get("config_sha"):
        text += f" • config {build['config_sha']}"
    return text
