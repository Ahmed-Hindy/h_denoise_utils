"""Unit tests for the UI denoising lock behaviour (Task 4.1).

Covers:
  - After _apply_ui_lock(True), all _lockable_widgets() are disabled.
  - After _apply_ui_lock(True), control_btn is still enabled.
  - After _apply_ui_lock(True) then _apply_ui_lock(False), all widgets are
    restored to their original states.
  - A widget disabled before the run remains disabled after unlock.
  - Calling _apply_ui_lock(False) with no prior lock is a no-op.
  - Ctrl+Enter shortcut calls _stop_denoise when is_running=True.
  - Scan and temporal callbacks cannot re-enable locked widgets mid-run.
  - F5 scan shortcut is ignored while is_running=True.
  - Drag-and-drop input changes are ignored while is_running=True.

Requirements: 1.1, 1.2, 2.1, 2.2, 3.3, 4.1, 5.1, 5.2
"""

import pytest
from h_denoise_utils.ui.main_window import BaseWindow
from h_denoise_utils.ui.qt_compat import QtCore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def window(qtbot):
    """Create a BaseWindow and register it with qtbot for cleanup."""
    w = BaseWindow()
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# Test 1 – After _apply_ui_lock(True), all lockable widgets are disabled
# Requirements: 1.1, 3.2, 5.1
# ---------------------------------------------------------------------------


def test_lock_disables_all_lockable_widgets(window):
    """All widgets returned by _lockable_widgets() must be disabled after lock."""
    window._apply_ui_lock(True)

    lockable = window._lockable_widgets()
    assert lockable, "_lockable_widgets() must not be empty"
    for widget in lockable:
        assert not widget.isEnabled(), (
            "Expected {} to be disabled after _apply_ui_lock(True)".format(widget)
        )


# ---------------------------------------------------------------------------
# Test 2 – After _apply_ui_lock(True), control_btn is still enabled
# Requirements: 1.2
# ---------------------------------------------------------------------------


def test_lock_leaves_control_btn_enabled(window):
    """control_btn must remain enabled during a lock so the user can stop the run."""
    window._apply_ui_lock(True)

    assert window.control_btn.isEnabled(), (
        "control_btn must stay enabled after _apply_ui_lock(True)"
    )


# ---------------------------------------------------------------------------
# Test 3 – Lock then unlock restores all widgets to their original states
# Requirements: 2.1, 2.2, 3.3
# ---------------------------------------------------------------------------


def test_unlock_restores_original_states(window):
    """After lock+unlock every lockable widget must have its pre-lock enabled state."""
    lockable = window._lockable_widgets()
    pre_run_states = {w: w.isEnabled() for w in lockable}

    window._apply_ui_lock(True)
    window._apply_ui_lock(False)

    for widget in lockable:
        assert widget.isEnabled() == pre_run_states[widget], (
            "Widget {} enabled state not restored after unlock".format(widget)
        )


# ---------------------------------------------------------------------------
# Test 4 – A widget disabled before the run remains disabled after unlock
# Requirements: 2.2, 3.3
# ---------------------------------------------------------------------------


def test_pre_disabled_widget_stays_disabled_after_unlock(window):
    """temporal_chk disabled before the run must stay disabled after unlock."""
    window.temporal_chk.setEnabled(False)

    window._apply_ui_lock(True)
    window._apply_ui_lock(False)

    assert not window.temporal_chk.isEnabled(), (
        "temporal_chk was disabled before the run and must remain disabled after unlock"
    )


# ---------------------------------------------------------------------------
# Test 5 – Calling _apply_ui_lock(False) with no prior lock is a no-op
# Requirements: 5.1, 5.2
# ---------------------------------------------------------------------------


def test_unlock_without_prior_lock_is_noop(window):
    """Calling _apply_ui_lock(False) on a fresh window must not change any widget state."""
    lockable = window._lockable_widgets()
    states_before = {w: w.isEnabled() for w in lockable}

    # Ensure _pre_run_enabled is empty (fresh window)
    assert window._pre_run_enabled == {}, (
        "_pre_run_enabled should be empty on a fresh window"
    )

    window._apply_ui_lock(False)

    for widget in lockable:
        assert widget.isEnabled() == states_before[widget], (
            "Widget {} state changed unexpectedly after unlock with no prior lock".format(
                widget
            )
        )


# ---------------------------------------------------------------------------
# Test 6 – Ctrl+Enter shortcut calls _stop_denoise when is_running=True
# Requirements: 4.1
# ---------------------------------------------------------------------------


def test_ctrl_enter_calls_stop_denoise_when_running(window, monkeypatch):
    """When is_running=True, activating the Ctrl+Enter shortcut must invoke _stop_denoise."""
    stop_calls = []

    def fake_stop_denoise():
        stop_calls.append(True)

    monkeypatch.setattr(window, "_stop_denoise", fake_stop_denoise)

    # Simulate a running state
    window._ui_state.is_running = True

    # Trigger the shortcut by emitting its activated signal directly
    assert window._control_shortcut_enter is not None, (
        "_control_shortcut_enter shortcut must be set up"
    )
    window._control_shortcut_enter.activated.emit()

    assert len(stop_calls) == 1, (
        "Expected _stop_denoise to be called once via Ctrl+Enter when is_running=True"
    )


# ---------------------------------------------------------------------------
# Test 7 - Scan completion cannot unlock scan_btn while running
# Requirements: 1.1, 3.1, 3.2
# ---------------------------------------------------------------------------


def test_scan_busy_callback_keeps_scan_button_disabled_while_running(window):
    """A scan state callback must not re-enable scan_btn during an active run."""
    window._ui_state.is_running = True
    window._apply_ui_lock(True)

    window._set_scan_busy(False)

    assert not window.scan_btn.isEnabled(), (
        "scan_btn must remain disabled while is_running=True"
    )

    window._ui_state.is_running = False
    window._apply_ui_lock(False)
    assert window.scan_btn.isEnabled(), "scan_btn must restore after unlock"


# ---------------------------------------------------------------------------
# Test 8 - Temporal callback cannot unlock temporal_chk while running
# Requirements: 1.1, 3.1, 3.2
# ---------------------------------------------------------------------------


def test_temporal_callback_keeps_checkbox_disabled_while_running(
    window, monkeypatch
):
    """Temporal state refreshes must not re-enable temporal_chk during a run."""
    monkeypatch.setattr(window, "_motion_vectors_available", lambda: True)
    window.backend_combo.setCurrentText("Optix")
    window._update_temporal_state(desired_checked=True)
    assert window.temporal_chk.isEnabled(), "temporal_chk must start enabled"

    window._ui_state.is_running = True
    window._apply_ui_lock(True)

    assert window._update_temporal_state(desired_checked=True)
    assert not window.temporal_chk.isEnabled(), (
        "temporal_chk must remain disabled while is_running=True"
    )

    window._ui_state.is_running = False
    window._apply_ui_lock(False)
    assert window.temporal_chk.isEnabled(), "temporal_chk must restore after unlock"


# ---------------------------------------------------------------------------
# Test 9 - F5 scan shortcut is ignored while running
# Requirements: 1.1, 3.1, 4.1
# ---------------------------------------------------------------------------


def test_f5_scan_shortcut_is_ignored_while_running(window, monkeypatch):
    """The scan shortcut must not start analysis while a denoise run is active."""
    analyze_calls = []

    def fake_analyze_input(force=False):
        analyze_calls.append(force)

    monkeypatch.setattr(window, "_analyze_input", fake_analyze_input)
    window._ui_state.is_running = True

    assert window._scan_shortcut_f5 is not None, "_scan_shortcut_f5 must be set up"
    window._scan_shortcut_f5.activated.emit()

    assert analyze_calls == [], "F5 scan shortcut must be ignored during a run"


# ---------------------------------------------------------------------------
# Test 10 - Drag-and-drop input changes are ignored while running
# Requirements: 1.1, 3.1
# ---------------------------------------------------------------------------


def test_drop_input_is_ignored_while_running(window, tmp_path, monkeypatch):
    """Window-level drops must not change the active input while locked."""
    dropped_file = tmp_path / "beauty.exr"
    dropped_file.write_text("placeholder")
    set_path_calls = []

    def fake_set_path_text(path, analyze=False, clear_selected=False):
        set_path_calls.append((path, analyze, clear_selected))

    monkeypatch.setattr(window, "_set_path_text", fake_set_path_text)
    window._ui_state.is_running = True

    window._set_path_from_drop([QtCore.QUrl.fromLocalFile(str(dropped_file))])

    assert set_path_calls == [], "drop must not update path while is_running=True"
    assert window._input_state.selected_files == []


# ---------------------------------------------------------------------------
# Property-Based Tests (Task 4.2)
# ---------------------------------------------------------------------------
# NOTE: hypothesis @given is not compatible with the qtbot fixture directly.
# We create the Qt window inside each test body and clean up manually.

from hypothesis import given, settings
from hypothesis import strategies as st
from h_denoise_utils.ui.qt_compat import QtWidgets


def _get_or_create_app():
    """Return the existing QApplication or create one if needed."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


# ---------------------------------------------------------------------------
# Property 1: Lock disables all lockable widgets
# Feature: ui-denoising-lock, Property 1: lock disables all lockable widgets
# Validates: Requirements 1.1, 3.2
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(enabled_flags=st.lists(st.booleans(), min_size=0, max_size=100))
def test_property_lock_disables_all_lockable_widgets(enabled_flags):
    # Feature: ui-denoising-lock, Property 1: lock disables all lockable widgets
    # Validates: Requirements 1.1, 3.2
    _get_or_create_app()
    w = BaseWindow()
    try:
        lockable = w._lockable_widgets()
        # Apply the random enabled/disabled assignment (cycling if fewer flags than widgets)
        for i, widget in enumerate(lockable):
            flag = enabled_flags[i % len(enabled_flags)] if enabled_flags else True
            widget.setEnabled(flag)

        w._apply_ui_lock(True)

        for widget in lockable:
            assert not widget.isEnabled(), (
                "Expected {} to be disabled after _apply_ui_lock(True)".format(widget)
            )
    finally:
        w.close()


# ---------------------------------------------------------------------------
# Property 2: Lock/unlock round-trip preserves pre-run enabled states
# Feature: ui-denoising-lock, Property 2: lock/unlock round-trip preserves pre-run enabled states
# Validates: Requirements 2.1, 2.2, 3.3
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(enabled_flags=st.lists(st.booleans(), min_size=0, max_size=100))
def test_property_lock_unlock_roundtrip_preserves_states(enabled_flags):
    # Feature: ui-denoising-lock, Property 2: lock/unlock round-trip preserves pre-run enabled states
    # Validates: Requirements 2.1, 2.2, 3.3
    _get_or_create_app()
    w = BaseWindow()
    try:
        lockable = w._lockable_widgets()
        # Apply the random enabled/disabled assignment
        for i, widget in enumerate(lockable):
            flag = enabled_flags[i % len(enabled_flags)] if enabled_flags else True
            widget.setEnabled(flag)

        # Capture the pre-lock states
        pre_lock_states = {widget: widget.isEnabled() for widget in lockable}

        # Lock then unlock
        w._apply_ui_lock(True)
        w._apply_ui_lock(False)

        # Each widget must be restored to its original state
        for widget in lockable:
            assert widget.isEnabled() == pre_lock_states[widget], (
                "Widget {} state not restored after lock/unlock round-trip. "
                "Expected {}, got {}".format(
                    widget, pre_lock_states[widget], widget.isEnabled()
                )
            )
    finally:
        w.close()


# ---------------------------------------------------------------------------
# Property 3: Unlock with no prior lock is a no-op
# Feature: ui-denoising-lock, Property 3: unlock with no prior lock is a no-op
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(st.data())
def test_property_unlock_without_prior_lock_is_noop(data):
    # Feature: ui-denoising-lock, Property 3: unlock with no prior lock is a no-op
    # Validates: Requirements 5.1, 5.2
    _get_or_create_app()
    w = BaseWindow()
    try:
        lockable = w._lockable_widgets()

        # Capture widget states on a fresh window (no prior lock)
        assert w._pre_run_enabled == {}, (
            "_pre_run_enabled must be empty on a fresh window"
        )
        states_before = {widget: widget.isEnabled() for widget in lockable}

        # Call unlock with no prior lock — must be a no-op
        w._apply_ui_lock(False)

        for widget in lockable:
            assert widget.isEnabled() == states_before[widget], (
                "Widget {} state changed unexpectedly after unlock with no prior lock. "
                "Expected {}, got {}".format(
                    widget, states_before[widget], widget.isEnabled()
                )
            )
    finally:
        w.close()
