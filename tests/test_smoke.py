from __future__ import annotations

import pytest

from karstlab.cli.main import main
from karstlab.version import __version__


def test_version_is_setup_release() -> None:
    assert __version__ == "1.1.0"


def test_doctor_command_runs(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Runtime check: package import OK" in captured.out
