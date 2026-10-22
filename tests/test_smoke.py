import subprocess
import sys


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "ofertinhas", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "ofertinhas" in result.stdout


def test_api_command_explains_missing_token(tmp_path, monkeypatch, capsys):
    from ofertinhas.__main__ import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXTENSION_TOKEN", raising=False)
    assert main(["api"]) == 1
    assert "EXTENSION_TOKEN" in capsys.readouterr().err


def test_api_command_explains_missing_config(tmp_path, monkeypatch, capsys):
    from ofertinhas.__main__ import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXTENSION_TOKEN", "tok")
    assert main(["api"]) == 1
    assert "config.example.yaml" in capsys.readouterr().err


def test_new_token_prints_env_line(capsys):
    from ofertinhas.__main__ import main

    assert main(["new-token"]) == 0
    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line.startswith("EXTENSION_TOKEN=") and len(first_line) > 50
