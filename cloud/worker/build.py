"""Monta o bundle do Worker: o pacote `ofertinhas` do repositório, fontes, modelos de texto, o
config.yaml e o `version.json` (commit e hash do config, ver `ofertinhas.buildinfo`).

Quem faz o deploy é o `deploy.py`, que chama este build. Os gerados ficam no .gitignore.
Uso direto: python build.py [--config caminho] [--out pasta]
"""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from ofertinhas.buildinfo import BUILD_FILE, local_build

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "src"

# Só rodam no PC (CLI, Windows, servidor local); no Worker não são importados.
LOCAL_ONLY = {"__main__.py", "run.py", "winops.py", "setup.py", "telegram_setup.py", "har.py",
              "backup.py", "scheduler.py"}


def build(config: Path = ROOT / "config.yaml", out: Path = SRC) -> dict:
    """Copia tudo para `out` (a pasta `src` do Worker) e devolve o que foi gravado no
    `version.json`."""
    target = out / "ofertinhas"
    bundle = out / "bundle"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(
        ROOT / "src" / "ofertinhas", target,
        ignore=lambda folder, names: [
            n for n in names
            if n == "__pycache__" or (Path(folder).name == "ofertinhas" and n in LOCAL_ONLY)
        ],
    )
    shutil.rmtree(bundle, ignore_errors=True)
    shutil.copytree(ROOT / "assets" / "fonts", bundle / "fonts",
                    ignore=shutil.ignore_patterns("*.txt"))
    shutil.copytree(ROOT / "templates" / "text", bundle / "templates")
    shutil.copy(config, bundle / "config.yaml")
    info = local_build(ROOT, config) | {"built_at": datetime.now(UTC).isoformat()}
    (bundle / BUILD_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--out", type=Path, default=SRC)
    args = parser.parse_args()
    info = build(args.config, args.out)
    files = sorted(p.relative_to(args.out).as_posix() for p in args.out.rglob("*")
                   if p.is_file())
    print(f"bundle pronto: {len(files)} arquivos em {args.out} ({info['commit']}, "
          f"config {info['config_sha']})")


if __name__ == "__main__":
    main()
