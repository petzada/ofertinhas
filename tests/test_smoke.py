import subprocess
import sys


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "ofertinhas", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "ofertinhas" in result.stdout
