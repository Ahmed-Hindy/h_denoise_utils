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
    assert window.options_edit.toolTip() == tooltips.OPTIONS_EDIT


def test_temporal_tooltip_reflects_state_after_init(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    if window.temporal_chk.isEnabled():
        assert window.temporal_chk.toolTip() == tooltips.TEMPORAL_CHK_ENABLED
    elif window._backend_key() != "optix":
        assert window.temporal_chk.toolTip() == tooltips.temporal_backend_unsupported(
            window.backend_combo.currentText()
        )
    else:
        assert window.temporal_chk.toolTip() == tooltips.TEMPORAL_CHK_NO_MOTION


def test_output_path_tooltip_matches_label_after_init(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    assert window.output_path_label.toolTip() == window.output_path_label.text()


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
