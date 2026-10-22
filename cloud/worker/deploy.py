"""Deploy versionado do Worker, num comando só.

1. Recusa se há mudança não commitada no código (o commit é a versão; `--allow-dirty` força).
2. Roda os testes da nuvem e o teste do bundle (`--skip-tests` pula).
3. Monta o bundle com o `version.json` (commit, hash do config.yaml e data).
4. Guarda uma cópia do config.yaml deste deploy em `data/deploys/` (o config fica fora do Git
   e não vai ao R2, que é público) e anota o deploy em `data/deploys/deploys.jsonl`.
5. Publica com `--tag <commit>` e `--message`, que aparecem no histórico de versões do Worker.

Depois, o `/health` e o `/admin/status` mostram o `build` que está no ar.
Uso (na pasta cloud/worker, com o .venv no PATH): python deploy.py [--allow-dirty] [--dry-run]
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime

from build import ROOT, build

HERE = ROOT / "cloud" / "worker"
DEPLOYS = ROOT / "data" / "deploys"
TESTS = ["tests/cloud"]


def dirty_files() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="deploy versionado do Worker")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="publica mesmo com mudança não commitada (a versão leva +mod)")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="monta e valida no wrangler sem publicar")
    args = parser.parse_args()

    dirty = dirty_files()
    if dirty and not args.allow_dirty:
        print("Há mudança não commitada; faça o commit antes (ou use --allow-dirty):",
              *dirty, sep="\n  ", file=sys.stderr)
        return 1
    if not args.skip_tests:
        tests = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q"], cwd=ROOT)
        if tests.returncode != 0:
            print("Testes falharam; nada foi publicado.", file=sys.stderr)
            return tests.returncode

    info = build()
    version = info["commit"] + ("+mod" if info["dirty"] else "")
    message = f"{version} config {info['config_sha']}"
    command = ["uvx", "--from", "workers-py", "pywrangler", "deploy",
               "--tag", version, "--message", message]
    if args.dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=HERE)
    if result.returncode != 0 or args.dry_run:
        return result.returncode

    DEPLOYS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    shutil.copy(ROOT / "config.yaml", DEPLOYS / f"{stamp}-{version}-{info['config_sha']}.yaml")
    with (DEPLOYS / "deploys.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(info | {"deployed_at": stamp}) + "\n")
    print(f"publicado: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
