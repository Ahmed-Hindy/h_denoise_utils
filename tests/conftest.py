"""Pytest helpers for environment-sensitive test collection."""

import importlib.util
import os
import sys

_QT_TEST_FILES = {
    "test_aov_scan_manager.py",
    "test_logging_handler.py",
    "test_ui_denoising_lock.py",
    "test_ui_main_window.py",
    "test_ui_tooltips.py",
}
_QT_BINDINGS = ("PySide6", "PyQt6")


def _qt_binding_available() -> bool:
    """Check whether a supported Qt binding can be imported.

    Returns:
        True when any supported Qt binding is available.
    """
    return any(importlib.util.find_spec(binding) for binding in _QT_BINDINGS)


def _display_available() -> bool:
    """Check whether the current environment can run Qt tests.

    Returns:
        True when Qt can use a display or a headless platform plugin.
    """
    if not sys.platform.startswith("linux"):
        return True

    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in {"offscreen", "minimal"}:
        return True

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pytest_ignore_collect(collection_path: object, config: object) -> bool:
    """Skip Qt-dependent tests when no Qt binding or display is available.

    Args:
        collection_path: Path-like object for the test file being collected.
        config: Active pytest configuration.

    Returns:
        True when pytest should ignore the file during collection.
    """
    filename = os.path.basename(os.fspath(collection_path))
    if filename not in _QT_TEST_FILES:
        return False
    return not (_qt_binding_available() and _display_available())
