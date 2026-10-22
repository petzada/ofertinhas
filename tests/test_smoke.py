import subprocess
import sys


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "ofertinhas", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "ofertinhas" in result.stdout


def test_capture_product_requires_url():
    import pytest

    from ofertinhas.__main__ import main

    with pytest.raises(SystemExit) as exc:
        main(["capture", "product"])
    assert exc.value.code == 2
