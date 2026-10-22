import json
from pathlib import Path

from dotenv import dotenv_values

from ofertinhas.setup import run_setup

ROOT = Path(__file__).parents[1]


def prepare(tmp_path):
    for name in ("config.example.yaml", ".env.example"):
        (tmp_path / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "extension").mkdir()
    return tmp_path


def test_creates_config_env_and_extension_config(tmp_path):
    root = prepare(tmp_path)
    report = run_setup(root, affiliate_tag="minhatag")
    env = dotenv_values(root / ".env")
    assert (root / "config.yaml").read_text(encoding="utf-8").startswith("# Copie")
    assert len(env["EXTENSION_TOKEN"]) >= 40
    assert env["ML_AFFILIATE_TAG"] == "minhatag"
    ext = json.loads((root / "extension" / "config.local.json").read_text(encoding="utf-8"))
    assert ext == {"backendUrl": "http://127.0.0.1:8765", "token": env["EXTENSION_TOKEN"]}
    assert env["EXTENSION_TOKEN"] not in "\n".join(report)  # nunca mostra o token


def test_keeps_existing_values(tmp_path):
    root = prepare(tmp_path)
    (root / "config.yaml").write_text("meu: config\n", encoding="utf-8")
    (root / ".env").write_text("EXTENSION_TOKEN=antigo\nTELEGRAM_BOT_TOKEN=123:abc\n",
                               encoding="utf-8")
    run_setup(root, affiliate_tag="minhatag")
    env = dotenv_values(root / ".env")
    assert (root / "config.yaml").read_text(encoding="utf-8") == "meu: config\n"
    assert env["EXTENSION_TOKEN"] == "antigo"
    assert env["TELEGRAM_BOT_TOKEN"] == "123:abc"
    assert env["ML_AFFILIATE_TAG"] == "minhatag"
    ext = json.loads((root / "extension" / "config.local.json").read_text(encoding="utf-8"))
    assert ext["token"] == "antigo"


def test_does_not_overwrite_tag_without_new_value(tmp_path):
    root = prepare(tmp_path)
    run_setup(root, affiliate_tag="minhatag")
    run_setup(root, affiliate_tag=None)
    assert dotenv_values(root / ".env")["ML_AFFILIATE_TAG"] == "minhatag"


def test_respects_custom_api_port(tmp_path):
    root = prepare(tmp_path)
    (root / ".env").write_text("API_PORT=9000\n", encoding="utf-8")
    run_setup(root, affiliate_tag=None)
    ext = json.loads((root / "extension" / "config.local.json").read_text(encoding="utf-8"))
    assert ext["backendUrl"] == "http://127.0.0.1:9000"
