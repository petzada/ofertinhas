import subprocess
import sys


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "ofertinhas", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "ofertinhas" in result.stdout


def test_new_token_prints_env_line(capsys):
    from ofertinhas.__main__ import main

    assert main(["new-token"]) == 0
    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line.startswith("EXTENSION_TOKEN=") and len(first_line) > 50
