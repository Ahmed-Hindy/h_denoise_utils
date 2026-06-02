"""UI smoke tests for the main window."""

import os

from h_denoise_utils import __version__
from h_denoise_utils.ui import main_window as main_window_module
from h_denoise_utils.ui.main_window import BaseWindow
from h_denoise_utils.ui.sections import QWIDGETSIZE_MAX
from h_denoise_utils.ui.worker import DenoiseWorker


def _has_ancestor(widget, ancestor):
    parent = widget.parentWidget()
    while parent is not None:
        if parent is ancestor:
            return True
        parent = parent.parentWidget()
    return False


def test_window_title_includes_version(qtbot, monkeypatch):
    monkeypatch.delenv("ENV_IS_DEV", raising=False)
    window = BaseWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == f"Denoiser {__version__}"


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


def test_about_dialog_uses_package_version(qtbot, monkeypatch):
    window = BaseWindow()
    qtbot.addWidget(window)
    captured = {}

    def fake_about(parent, title, message):
        captured["parent"] = parent
        captured["title"] = title
        captured["message"] = message

    monkeypatch.setattr(
        main_window_module.QtWidgets.QMessageBox,
        "about",
        fake_about,
    )

    window._show_about()

    assert captured["parent"] is window
    assert captured["title"] == "About Denoiser"
    assert f"<b>Denoiser</b><br>Version {__version__}<br><br>" in captured["message"]


def test_output_label_updates(qtbot, tmp_path):
    window = BaseWindow()
    qtbot.addWidget(window)
    window.path_edit.setCurrentText(str(tmp_path))
    window._update_output_label()
    text = window.output_path_label.text()
    assert "Destination:" in text
    path_text = text.split("Destination:", 1)[1].strip()
    assert os.path.basename(path_text).lower().endswith("denoised")


def test_auto_scan_skips_focus_loss_repeat_but_scan_button_forces(qtbot, tmp_path):
    class FakeAovScan:
        def __init__(self):
            self.starts = []

        def start(self, path, selected_files):
            self.starts.append((path, tuple(selected_files)))

        def cancel(self):
            pass

    exr_path = tmp_path / "CanRun_sh001_renderCompositingMain_v001.0001.exr"
    exr_path.write_bytes(b"")

    window = BaseWindow()
    qtbot.addWidget(window)
    fake_scan = FakeAovScan()
    window._aov_scan = fake_scan

    window._set_selected_files([str(exr_path)])
    window._set_path_text(str(exr_path), analyze=True)
    window.path_edit.lineEdit().editingFinished.emit()

    assert len(fake_scan.starts) == 1

    window._on_scan_requested()

    assert len(fake_scan.starts) == 2


def test_action_bar_contains_output_button_and_settings_width_is_bounded(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    assert window.open_output_btn.parentWidget().objectName() == "actionBar"
    assert window.advanced_section.maximumWidth() == 960
    assert window.advanced_section.maximumHeight() == 48


def test_destination_and_settings_share_configuration_scroll_area(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    assert window.config_scroll is not None
    assert window.config_scroll.objectName() == "configScroll"
    assert window.config_scroll.viewport().objectName() == "configScrollViewport"
    assert window.config_scroll.widget() is window.config_scroll_body
    assert window.config_scroll_body.objectName() == "configScrollBody"
    assert window.output_section.parentWidget() is window.config_scroll_body
    assert window.advanced_section.parentWidget() is window.config_scroll_body
    layout = window.config_scroll_body.layout()
    assert layout.itemAt(layout.count() - 1).spacerItem() is not None
    assert window.adv_scroll is None
    assert window.advanced_body.isHidden()
    assert window.advanced_settings_body.isHidden()

    window._toggle_advanced(True)

    assert not window.advanced_body.isHidden()
    assert window.advanced_settings_body.isHidden()
    assert window.advanced_section.maximumHeight() == QWIDGETSIZE_MAX


def test_settings_has_basic_and_collapsed_advanced_rows(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    window._toggle_advanced(True)

    assert _has_ancestor(window.prefix_edit, window.advanced_body)
    assert _has_ancestor(window.beauty_combo, window.advanced_body)
    assert _has_ancestor(window.albedo_combo, window.advanced_body)
    assert _has_ancestor(window.normal_combo, window.advanced_body)
    assert not _has_ancestor(window.prefix_edit, window.advanced_settings_body)
    assert _has_ancestor(window.backend_combo, window.advanced_settings_body)
    assert _has_ancestor(window.optix_version_combo, window.advanced_settings_body)
    assert _has_ancestor(window.denoiser_status_label, window.advanced_settings_body)
    assert window.backend_combo.currentText() == "OptiX"
    assert window.optix_version_combo.currentText() == "OptiX 9.0"

    window._toggle_advanced_settings(True)

    assert not window.advanced_settings_body.isHidden()


def test_backend_selector_switches_summary_and_optix_runtime_state(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    assert window._backend_key() == "optix"
    assert window.summary_motion.text() == "Mode: OptiX 9.0"
    assert window.optix_version_combo.isEnabled()

    window.backend_combo.setCurrentText("OIDN")

    assert window._backend_key() == "oidn"
    assert window.summary_motion.text() == "Mode: OIDN"
    assert not window.optix_version_combo.isEnabled()


def test_oidn_backend_start_uses_oidn_resolver_and_config(qtbot, tmp_path, monkeypatch):
    input_file = tmp_path / "input.exr"
    input_file.write_bytes(b"placeholder")
    exe = tmp_path / "Denoiser.exe"
    exe.write_text("placeholder")
    captured = {}

    class FakeSignal:
        def connect(self, callback):
            pass

    class FakeWorker:
        def __init__(
            self,
            input_path,
            denoise_config,
            aov_config,
            denoiser_path,
            extensions=None,
            file_list=None,
        ):
            captured["input_path"] = input_path
            captured["denoise_config"] = denoise_config
            captured["aov_config"] = aov_config
            captured["denoiser_path"] = denoiser_path
            captured["extensions"] = extensions
            captured["file_list"] = file_list
            self.progress = FakeSignal()
            self.log_message = FakeSignal()
            self.completed = FakeSignal()
            self.finished = FakeSignal()

        def start(self):
            captured["started"] = True

        def deleteLater(self):
            pass

    monkeypatch.setattr(
        main_window_module,
        "resolve_bundled_oidn_denoiser",
        lambda required=False: str(exe),
    )
    monkeypatch.setattr(main_window_module, "DenoiseWorker", FakeWorker)

    window = BaseWindow()
    qtbot.addWidget(window)
    window.backend_combo.setCurrentText("OIDN")
    window._set_path_text(str(input_file), analyze=False)

    window._start_denoise()

    assert captured["started"] is True
    assert captured["input_path"] == str(input_file)
    assert captured["denoise_config"].backend == "oidn"
    assert captured["denoiser_path"] == str(exe)


def test_worker_thread_finished_ignores_stale_sender(qtbot, monkeypatch):
    window = BaseWindow()
    qtbot.addWidget(window)
    old_worker = object()
    current_worker = object()

    window.worker = current_worker
    monkeypatch.setattr(BaseWindow, "sender", lambda self: old_worker)

    window._on_worker_thread_finished()

    assert window.worker is current_worker

    monkeypatch.setattr(BaseWindow, "sender", lambda self: current_worker)

    window._on_worker_thread_finished()

    assert window.worker is None


def test_finished_error_summary_logs_error(qtbot, monkeypatch):
    window = BaseWindow()
    qtbot.addWidget(window)
    logs = []
    monkeypatch.setattr(window, "_log", lambda message, level="info": logs.append((message, level)))

    window._on_finished(
        {
            "status": "error",
            "error": "Preparation failed: No image files found",
            "processed": 0,
            "skipped": 0,
            "failed": [],
        }
    )

    assert logs[-1] == (
        "Processed: 0, Skipped: 0, Failed: 0 - Preparation failed: No image files found",
        "error",
    )


def test_worker_error_summary_marks_terminal_error():
    summary = DenoiseWorker._error_summary("No image files found")

    assert summary == {
        "status": "error",
        "error": "No image files found",
        "processed": 0,
        "skipped": 0,
        "failed": [],
    }


def test_f5_triggers_scan(qtbot, tmp_path):
    class FakeAovScan:
        def __init__(self):
            self.starts = []

        def start(self, path, selected_files):
            self.starts.append((path, tuple(selected_files)))

        def cancel(self):
            pass

    exr_path = tmp_path / "shot.0001.exr"
    exr_path.write_bytes(b"")

    window = BaseWindow()
    qtbot.addWidget(window)
    fake_scan = FakeAovScan()
    window._aov_scan = fake_scan
    window._set_path_text(str(tmp_path), analyze=False)

    assert window._scan_shortcut_f5 is not None
    window._scan_shortcut_f5.activated.emit()

    assert len(fake_scan.starts) == 1


def test_splitter_state_persists(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)
    window.resize(860, 700)
    window.main_splitter.setSizes([400, 300])
    saved_state = window.main_splitter.saveState()
    window._save_splitter_state()
    window.main_splitter.setSizes([120, 120])
    window._restore_splitter_state()
    assert window.main_splitter.saveState() == saved_state


def test_summary_chip_bad_for_invalid_path(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)
    window._set_path_text("/path/that/does/not/exist", analyze=False)
    assert window.summary_files.objectName() == "summaryChipBad"


def test_legacy_houdini_controls_are_not_present(qtbot):
    window = BaseWindow()
    qtbot.addWidget(window)

    assert hasattr(window, "backend_combo")
    assert not hasattr(window, "thread_spin")
    assert not hasattr(window, "denoiser_combo")
    assert not hasattr(window, "exrmode_combo")
    assert not hasattr(window, "options_edit")
