"""Monta o bundle do Worker: o pacote `ofertinhas` do repositório, fontes, modelos de texto e
o config.yaml. Rode antes de cada `pywrangler deploy`; os gerados ficam no .gitignore."""

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "src"
BUNDLE = SRC / "bundle"

# Só rodam no PC (CLI, Windows, servidor local); no Worker não são importados.
LOCAL_ONLY = {"__main__.py", "run.py", "winops.py", "setup.py", "telegram_setup.py", "har.py",
              "backup.py", "scheduler.py"}


def main() -> None:
    target = SRC / "ofertinhas"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(
        ROOT / "src" / "ofertinhas", target,
        ignore=lambda folder, names: [
            n for n in names
            if n == "__pycache__" or (Path(folder).name == "ofertinhas" and n in LOCAL_ONLY)
        ],
    )
    shutil.rmtree(BUNDLE, ignore_errors=True)
    shutil.copytree(ROOT / "assets" / "fonts", BUNDLE / "fonts",
                    ignore=shutil.ignore_patterns("*.txt"))
    shutil.copytree(ROOT / "templates" / "text", BUNDLE / "templates")
    shutil.copy(ROOT / "config.yaml", BUNDLE / "config.yaml")
    files = sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file())
    print(f"bundle pronto: {len(files)} arquivos em {SRC}")


if __name__ == "__main__":
    main()
