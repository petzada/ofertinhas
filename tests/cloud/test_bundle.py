"""O que vai para produção: o bundle do Worker montado pelo `cloud/worker/build.py`.

Monta o bundle numa pasta temporária e, num processo à parte, importa o pacote copiado com
as dependências que só existem no PC bloqueadas, sobe o backend e chama o `/health`. Pega
import quebrado, arquivo que faltou no bundle e dependência nova que o Worker não instala.
"""

import ast
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
WORKER = ROOT / "cloud" / "worker"
# distribuição do pip → nome do import
IMPORT_NAMES = {"fastapi": "fastapi", "uvicorn": "uvicorn", "apscheduler": "apscheduler",
                "python-telegram-bot": "telegram", "httpx": "httpx", "pillow": "PIL",
                "qrcode": "qrcode", "pydantic": "pydantic", "pyyaml": "yaml",
                "python-dotenv": "dotenv", "tzdata": "tzdata"}

SMOKE = r'''
import json, sys
from pathlib import Path

src, blocked = Path(sys.argv[1]), set(sys.argv[2].split(","))
sys.meta_path[:] = [f for f in sys.meta_path if "editable" not in repr(f).lower()]
sys.path[:] = [str(src)] + [p for p in sys.path if Path(p).resolve() != Path(sys.argv[3])]


class OnlyOnThePC:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in blocked:
            raise ImportError(f"{name} só existe no PC, não no Worker")


sys.meta_path.insert(0, OnlyOnThePC())

import httpx
from fastapi.testclient import TestClient

import ofertinhas
from ofertinhas import db
from ofertinhas.cloud.backend import CloudBackend

assert Path(ofertinhas.__file__).resolve().is_relative_to(src.resolve()), ofertinhas.__file__


class Bucket:
    async def put(self, key, data, content_type): ...
    async def get(self, key): return None


env = {"EXTENSION_TOKEN": "t", "ADMIN_TOKEN": "a", "TELEGRAM_BOT_TOKEN": "1:x",
       "ADMIN_CHAT_ID": "1"}
backend = CloudBackend(env, db.connect(":memory:"), Bucket(), src / "bundle",
                       httpx.AsyncClient(), bot=object())
health = TestClient(backend.app).get("/health", headers={"X-Ofertinhas-Token": "t"}).json()
print(json.dumps({"health": health, "jobs": sorted(backend.jobs)}))
'''


def _deps(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    names = set()
    for spec in data["project"]["dependencies"]:
        name = spec.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower()
        if name not in IMPORT_NAMES:
            pytest.fail(f"dependência nova sem nome de import em IMPORT_NAMES: {name}")
        names.add(IMPORT_NAMES[name])
    return names


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("worker_build", WORKER / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    out = tmp_path_factory.mktemp("worker-src")
    info = build.build(ROOT / "config.example.yaml", out)
    return build, out, info


def test_bundle_leaves_the_pc_only_modules_out(built):
    build, out, info = built
    package = out / "ofertinhas"
    assert (package / "cloud" / "backend.py").exists()
    assert not [n for n in build.LOCAL_ONLY if (package / n).exists()]
    assert (out / "bundle" / "config.yaml").exists() and (out / "bundle" / "fonts").is_dir()
    stored = json.loads((out / "bundle" / "version.json").read_text(encoding="utf-8"))
    assert stored == info and stored["commit"] and stored["config_sha"]


def test_bundle_imports_and_serves_without_pc_dependencies(built):
    _, out, info = built
    blocked = _deps(ROOT / "pyproject.toml") - _deps(WORKER / "pyproject.toml")
    assert {"uvicorn", "apscheduler", "dotenv"} <= blocked
    result = subprocess.run(
        [sys.executable, "-c", SMOKE, str(out), ",".join(sorted(blocked)),
         str((ROOT / "src").resolve())],
        capture_output=True, text=True, cwd=out, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["health"]["ok"] and data["health"]["build"]["commit"] == info["commit"]
    assert {"publish", "prune", "status"} <= set(data["jobs"])


def test_wrangler_uploads_the_bundle_data_files(built):
    from fnmatch import fnmatch

    _, out, _ = built
    rules = tomllib.loads((WORKER / "wrangler.toml").read_text(encoding="utf-8"))["rules"]
    globs = [g.removeprefix("**/") for rule in rules for g in rule["globs"]]
    data = [p.relative_to(out).as_posix() for p in (out / "bundle").rglob("*")
            if p.is_file() and p.suffix != ".txt"]  # .txt já sobe por padrão
    missing = [f for f in data if not any(fnmatch(f, g) or fnmatch(f, f"*/{g}") for g in globs)]
    assert not missing, f"sem regra no wrangler.toml, não sobem: {missing}"


def test_worker_receives_every_secret_it_needs():
    def names(path: Path, var: str) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == var for t in node.targets):
                return set(ast.literal_eval(node.value))
        raise AssertionError(f"{var} não está em {path.name}")

    passed = names(WORKER / "src" / "entry.py", "ENV_NAMES")
    pushed = names(WORKER / "push_secrets.py", "NAMES")
    assert pushed <= passed  # segredo enviado que o Worker não repassa ao backend
    assert {"EXTENSION_TOKEN", "ADMIN_TOKEN", "TELEGRAM_BOT_TOKEN"} <= pushed
