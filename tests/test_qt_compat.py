"""Tests for the supported Qt binding contract."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("backend", ["pyside2", "pyqt5"])
def test_removed_qt_backends_are_rejected(backend: str) -> None:
    """Ensure removed Qt 5 bindings cannot be selected through the environment."""
    env = os.environ.copy()
    env["QT_BACKEND"] = backend

    result = subprocess.run(
        [sys.executable, "-c", "import h_denoise_utils.ui.qt_compat"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "Must be one of: pyside6, pyqt6" in result.stderr
