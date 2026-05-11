"""UI smoke tests for the main window."""

import os

from h_denoise_utils.ui.main_window import BaseWindow


def test_window_constructs(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)
    assert window.log_table is not None
    assert window.output_path_label is not None
    assert window.log_filter_combo.count() == 5
    assert window.log_filter_combo.itemText(0) == "All"


def test_append_log_adds_row(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)
    window._append_log("Hello", "info")
    assert window.log_table.rowCount() == 1
    assert window.log_table.item(0, 1).text() == "Hello"


def test_output_label_updates(qtbot, tmp_path):
    window = BaseWindow()
    qtbot.addWidget(window)
    window.path_edit.setCurrentText(str(tmp_path))
    window._update_output_label()
    text = window.output_path_label.text()
    assert "Destination:" in text
    path_text = text.split("Destination:", 1)[1].strip()
    assert os.path.basename(path_text).lower().endswith("denoised")
