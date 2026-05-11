"""Tests for the AOV scan manager."""

import time

from h_denoise_utils.ui import aov_scan_manager
from h_denoise_utils.ui.aov_scan_manager import AovScanManager


def _slow_analyze(_path, _selected_files):
    time.sleep(0.05)
    return {"status": "ok", "planes": ["C"], "exr_file": _path, "error": None}


def test_aov_scan_manager_timeout_emits(qtbot, monkeypatch):
    monkeypatch.setattr(aov_scan_manager, "analyze_aovs", _slow_analyze)
    manager = AovScanManager(timeout_ms=5)
    completed = {"called": False}

    def _on_completed(_result):
        completed["called"] = True

    manager.completed.connect(_on_completed)

    with qtbot.waitSignal(manager.timed_out, timeout=1000):
        manager.start("fake.exr", [])

    qtbot.wait(200)
    assert completed["called"] is False


def test_aov_scan_manager_cancel_suppresses_signals(qtbot, monkeypatch):
    monkeypatch.setattr(aov_scan_manager, "analyze_aovs", _slow_analyze)
    manager = AovScanManager(timeout_ms=1000)
    completed = {"called": False}
    timed_out = {"called": False}

    def _on_completed(_result):
        completed["called"] = True

    def _on_timed_out():
        timed_out["called"] = True

    manager.completed.connect(_on_completed)
    manager.timed_out.connect(_on_timed_out)

    with qtbot.waitSignal(manager.started, timeout=1000):
        manager.start("fake.exr", [])

    manager.cancel()

    qtbot.wait(200)
    assert completed["called"] is False
    assert timed_out["called"] is False
