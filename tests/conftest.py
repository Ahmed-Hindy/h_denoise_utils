"""Pytest helpers for environment-sensitive test collection."""

import importlib.util
import os
import sys


_QT_TEST_FILES = {
    "test_aov_scan_manager.py",
    "test_logging_handler.py",
    "test_ui_main_window.py",
    "test_ui_tooltips.py",
}
_QT_BINDINGS = ("PySide6", "PySide2", "PyQt6", "PyQt5")


def _qt_binding_available():
    # type: () -> bool
    return any(importlib.util.find_spec(binding) for binding in _QT_BINDINGS)


def _display_available():
    # type: () -> bool
    if not sys.platform.startswith("linux"):
        return True

    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in {"offscreen", "minimal"}:
        return True

    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def pytest_ignore_collect(collection_path, config):
    # type: (object, object) -> bool
    filename = os.path.basename(os.fspath(collection_path))
    if filename not in _QT_TEST_FILES:
        return False
    return not (_qt_binding_available() and _display_available())
