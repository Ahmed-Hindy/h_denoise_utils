"""Unit tests for the UI denoising lock behaviour (Task 4.1).

Covers:
  - After _apply_ui_lock(True), all _lockable_widgets() are disabled.
  - After _apply_ui_lock(True), control_btn is still enabled.
  - After _apply_ui_lock(True) then _apply_ui_lock(False), all widgets are
    restored to their original states.
  - A widget disabled before the run remains disabled after unlock.
  - Calling _apply_ui_lock(False) with no prior lock is a no-op.
  - Ctrl+Enter shortcut calls _stop_denoise when is_running=True.

Requirements: 1.1, 1.2, 2.1, 2.2, 3.3, 4.1, 5.1, 5.2
"""

import pytest
from h_denoise_utils.ui.main_window import BaseWindow


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
