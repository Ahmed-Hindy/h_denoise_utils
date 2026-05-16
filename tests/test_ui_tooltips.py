"""Tests for GUI tooltip coverage."""

from h_denoise_utils.ui import tooltips
from h_denoise_utils.ui.main_window import BaseWindow


def test_static_tooltips_applied_on_init(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    assert window.preset_combo.toolTip() == tooltips.PRESET_COMBO
    assert window.thread_spin.toolTip() == tooltips.THREAD_SPIN
    assert window.control_btn.toolTip() == tooltips.CONTROL_BTN_START
    assert window.log_filter_combo.toolTip() == tooltips.LOG_FILTER_COMBO
    assert window.aovs_input.toolTip() == tooltips.AOVS_INPUT
    assert window.aovs_input.custom_input.toolTip() == tooltips.AOVS_CUSTOM_INPUT


def test_control_btn_tooltip_switches_with_running_state(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    window._ui_state.is_running = True
    window.control_btn.setText("Stop")
    window.control_btn.setToolTip(tooltips.CONTROL_BTN_STOP)
    assert window.control_btn.toolTip() == tooltips.CONTROL_BTN_STOP

    window._ui_state.is_running = False
    window.control_btn.setText("Denoise")
    window.control_btn.setToolTip(tooltips.CONTROL_BTN_START)
    assert window.control_btn.toolTip() == tooltips.CONTROL_BTN_START
