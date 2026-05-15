"""Main window for h_denoise_utils GUI"""

import json
import os
import re
import time

from .qt_compat import (
    QtAction,
    QtCore,
    QtGui,
    QtWidgets,
)

from ..core.config import (
    PRESETS,
    DenoiseConfig,
    AOVConfig,
)
from ..discovery.houdini import detect_houdini_versions
from .aov_scan_manager import AovScanManager
from .services.output_paths import preview_output_path
from .services.recent_paths import (
    load_recent_paths,
    remember_path,
    save_recent_paths,
)
from .state import (
    AovState,
    DenoiseState,
    InputState,
    UiState,
)
from .sections import (
    QWIDGETSIZE_MAX,
    build_action_bar,
    build_config_scroll,
    build_destination_section,
    build_extras_section,
    build_logs_section,
    build_source_section,
)
from .worker import DenoiseWorker
from ..utils.file_utils import compute_output_folder
from .logging_handler import QtLogHandler
import logging
from ..logger import get_log_dir, setup_logger


logger = logging.getLogger(__name__)


class BaseWindow(QtWidgets.QMainWindow):
    """Main UI widget for Denoiser - exact port of old UI."""

    # Standard AOV names for heuristics
    NORMAL_NAMES = {"N", "normal", "normals", "Normal"}
    ALBEDO_NAMES = {"albedo", "Albedo", "diffuse_albedo"}
    MOTION_NAMES = {"motionvectors", "motionvector"}

    def __init__(self, parent=None, initial_path=None):
        # type: (Optional[QtWidgets.QWidget], Optional[str]) -> None
        super(BaseWindow, self).__init__(parent)
        self.app_style = self.style()
        self.setAcceptDrops(True)
        self.worker = None  # type: Optional[DenoiseWorker]
        self._settings = QtCore.QSettings("h_denoise_utils", "h_denoise_utils")
        self._recent_paths = []  # type: List[str]
        self._input_state = InputState()
        self._aov_state = AovState()
        self._ui_state = UiState()
        self._denoise_state = DenoiseState()
        self.log_records = []  # type: List[dict]
        self._visible_log_records = []  # type: List[dict]
        self._run_start = None  # type: Optional[float]
        self._custom_preset = "Custom"
        self._auto_preset_enabled = True
        self._suppress_custom_changes = False
        self.drop_overlay = None  # type: Optional[QtWidgets.QLabel]
        self.log_table = None  # type: Optional[QtWidgets.QTableWidget]
        self.output_path_label = None  # type: Optional[QtWidgets.QLabel]
        self.action_dest_label = None  # type: Optional[QtWidgets.QLabel]
        self._package_logger = None  # type: Optional[logging.Logger]
        self._aov_timeout_ms = 10000
        self._aov_scan = AovScanManager(timeout_ms=self._aov_timeout_ms, parent=self)
        self.scan_spinner = None  # type: Optional[QtWidgets.QProgressBar]
        self.summary_files = None  # type: Optional[QtWidgets.QLabel]
        self.summary_planes = None  # type: Optional[QtWidgets.QLabel]
        self.summary_motion = None  # type: Optional[QtWidgets.QLabel]
        self.input_section = None  # type: Optional[QtWidgets.QFrame]
        self.input_body = None  # type: Optional[QtWidgets.QWidget]
        self.output_section = None  # type: Optional[QtWidgets.QFrame]
        self.output_body = None  # type: Optional[QtWidgets.QWidget]
        self.output_toggle = None  # type: Optional[QtWidgets.QToolButton]
        self.config_scroll = None  # type: Optional[QtWidgets.QScrollArea]
        self.config_scroll_body = None  # type: Optional[QtWidgets.QWidget]
        self._input_header_spacer = None  # type: Optional[QtWidgets.QWidget]
        self.denoise_section = None  # type: Optional[QtWidgets.QFrame]
        self.denoise_body = None  # type: Optional[QtWidgets.QWidget]
        self.denoise_toggle = None  # type: Optional[QtWidgets.QToolButton]
        self.adv_scroll = None  # type: Optional[QtWidgets.QScrollArea]
        self.advanced_section = None  # type: Optional[QtWidgets.QFrame]
        self.advanced_body = None  # type: Optional[QtWidgets.QWidget]
        self.advanced_toggle = None  # type: Optional[QtWidgets.QToolButton]
        self.motion_label = None  # type: Optional[QtWidgets.QLabel]
        self._path_analysis_timer = QtCore.QTimer(self)
        self._path_analysis_timer.setSingleShot(True)
        self._path_analysis_timer.setInterval(500)
        self._path_analysis_timer.timeout.connect(self._analyze_input)
        self._summary_planes_flash_timer = QtCore.QTimer(self)
        self._summary_planes_flash_timer.setSingleShot(True)
        self._summary_planes_flash_timer.timeout.connect(
            self._clear_summary_planes_flash
        )
        self._summary_planes_flash_original_style = None  # type: Optional[str]
        self._control_shortcut_enter = None  # type: Optional[object]
        self._control_shortcut_f5 = None  # type: Optional[object]

        self.houdini_versions = detect_houdini_versions()
        self._setup_menus()
        self._setup_ui()
        self._load_recent_paths()
        self._set_init_widget_values()

        # Setup logging handler for UI
        self.log_handler = QtLogHandler(self)
        self.log_handler.setFormatter(logging.Formatter("%(message)s"))
        self.log_handler.new_record.connect(self._log_from_handler)

        # Attach to package logger
        self._package_logger = setup_logger("h_denoise_utils")
        self._package_logger.addHandler(self.log_handler)

        self._connect_signals()
        self._connect_aov_scan()
        self._set_tooltips()

        if initial_path:
            self._set_path_text(os.path.normpath(initial_path), analyze=True)

    def closeEvent(self, event):
        # type: (QtGui.QCloseEvent) -> None
        if self._package_logger and self.log_handler:
            self._package_logger.removeHandler(self.log_handler)
            self.log_handler.close()
        if self._aov_scan:
            self._aov_scan.cancel()
        super(BaseWindow, self).closeEvent(event)

    def _load_stylesheet(self):
        # type: () -> None
        ui_dir = os.path.dirname(__file__)
        icons_dir = os.path.join(ui_dir, "icons")
        if os.path.isdir(icons_dir):
            # Stable QSS path prefix, independent of Houdini launch cwd.
            QtCore.QDir.addSearchPath("hdui", os.path.normpath(icons_dir))
        style_path = os.path.join(ui_dir, "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as stream:
                self.setStyleSheet(stream.read())

    # --- Menu & window setup ---
    def _setup_menus(self):
        # type: () -> None
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        exit_act = QtAction("E&xit", self)
        exit_act.setShortcut(QtGui.QKeySequence("Ctrl+Q"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        help_menu = menubar.addMenu("&Help")
        shortcuts_act = QtAction("&Shortcuts", self)
        shortcuts_act.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_act)
        open_logs_act = QtAction("Open &Logs Folder", self)
        open_logs_act.triggered.connect(self._open_logs_folder)
        help_menu.addAction(open_logs_act)
        about_act = QtAction("&About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _show_about(self):
        # type: () -> None
        QtWidgets.QMessageBox.about(
            self,
            "About Denoiser",
            "<b>Denoiser</b><br>Version 2.0<br><br>"
            "Denoises images using Houdini's <code>idenoise</code> (OIDN/OptiX), "
            "with smart AOV detection and temporal processing.",
        )

    def _show_shortcuts(self):
        # type: () -> None
        message = "Shortcuts:\n\nCtrl+Enter / F5: Denoise / Stop\nCtrl+Q: Quit"
        QtWidgets.QMessageBox.information(self, "Shortcuts", message)

    def _log_folder_path(self):
        # type: () -> str
        return get_log_dir()

    def _open_logs_folder(self):
        # type: () -> None
        path = self._log_folder_path()
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except OSError:
                QtWidgets.QMessageBox.warning(
                    self, "Logs Folder", "Unable to create the logs folder."
                )
                return
        opened = QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
        if not opened:
            QtWidgets.QMessageBox.warning(
                self, "Logs Folder", "Unable to open the logs folder."
            )

    def _setup_ui(self):
        # type: () -> None
        ENV_IS_DEV = str(os.environ.get("ENV_IS_DEV", "")).lower() == "true"
        self.setWindowTitle("Denoiser") if not ENV_IS_DEV else self.setWindowTitle(
            "Denoiser (DEV)"
        )
        _icon_path = os.path.join(os.path.dirname(__file__), "icons", "logo.ico")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QtGui.QIcon(_icon_path))
        self.resize(860, 700)
        self.setMinimumHeight(460)
        screen = self.screen() or QtWidgets.QApplication.primaryScreen()
        if screen:
            screen_cap = int(screen.availableGeometry().height() * 0.92)
            self.setMaximumHeight(max(self.minimumHeight(), screen_cap))

        container = QtWidgets.QWidget()
        self.setCentralWidget(container)
        main = QtWidgets.QVBoxLayout(container)
        container.setAcceptDrops(True)
        container.installEventFilter(self)

        self.drop_overlay = QtWidgets.QLabel("Drop file or folder anywhere", container)
        self.drop_overlay.setAlignment(QtCore.Qt.AlignCenter)
        self.drop_overlay.setAcceptDrops(True)
        self.drop_overlay.setStyleSheet(
            "QLabel{border:2px dashed #5a8fd1;border-radius:8px;"
            "background-color: rgba(90,143,209,40);color:#2a4c7f;}"
        )
        self.drop_overlay.setVisible(False)
        self.drop_overlay.installEventFilter(self)

        # Load stylesheet
        self._load_stylesheet()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        main.addWidget(splitter)
        top_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        logs_widget = QtWidgets.QWidget()
        logs_widget.setMaximumHeight(260)
        logs_layout = QtWidgets.QVBoxLayout(logs_widget)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        logs_layout.setSpacing(6)

        splitter.addWidget(top_widget)
        splitter.addWidget(logs_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 200])

        self._build_source_section(top_layout)
        config_layout = self._build_config_scroll(top_layout)
        self._build_destination_section(config_layout)
        self._build_extras_section(config_layout)
        config_layout.addStretch(1)
        self._build_action_bar(top_layout)
        self._build_logs_section(logs_layout)

    def _build_source_section(self, top_layout):
        # type: (QtWidgets.QVBoxLayout) -> None
        build_source_section(self, top_layout)

    def _build_config_scroll(self, top_layout):
        # type: (QtWidgets.QVBoxLayout) -> QtWidgets.QVBoxLayout
        return build_config_scroll(self, top_layout)

    def _build_destination_section(self, top_layout):
        # type: (QtWidgets.QVBoxLayout) -> None
        build_destination_section(self, top_layout)

    def _build_extras_section(self, top_layout):
        # type: (QtWidgets.QVBoxLayout) -> None
        build_extras_section(self, top_layout)

    def _build_action_bar(self, top_layout):
        # type: (QtWidgets.QVBoxLayout) -> None
        build_action_bar(self, top_layout)

    def _build_logs_section(self, logs_layout):
        # type: (QtWidgets.QVBoxLayout) -> None
        build_logs_section(self, logs_layout)

    def _set_init_widget_values(self):
        # type: () -> None
        self.preset_combo.setCurrentText("Beauty")
        self._apply_preset("Beauty")
        self._update_output_label()

    # --- Signal wiring ---
    def _connect_signals(self):
        # type: () -> None
        self.browse_btn.clicked.connect(self._browse)
        self.scan_btn.clicked.connect(self._analyze_input)
        self.open_output_btn.clicked.connect(self._open_output_folder)
        self.path_edit.currentTextChanged.connect(self._on_path_text_changed)
        self.path_edit.lineEdit().editingFinished.connect(self._analyze_input)
        self.path_edit.activated.connect(self._on_path_selected)
        self.files_remove_btn.clicked.connect(self._remove_selected_files)
        self.files_clear_btn.clicked.connect(self._clear_selected_files)

        self.custom_exe_btn.clicked.connect(self._pick_custom_exe)
        if self.output_toggle:
            self.output_toggle.toggled.connect(self._toggle_output_body)
        if self.denoise_toggle:
            self.denoise_toggle.toggled.connect(self._toggle_denoise_body)
        if self.aov_toggle:
            self.aov_toggle.toggled.connect(self._toggle_aov_body)
        if self.advanced_toggle:
            self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.control_btn.clicked.connect(self._on_control)
        self.backend_combo.currentTextChanged.connect(self._on_backend_changed)
        self.backend_combo.currentTextChanged.connect(self._mark_custom)
        self.temporal_chk.toggled.connect(self._mark_custom)
        self.normal_combo.currentTextChanged.connect(self._mark_custom)
        self.albedo_combo.currentTextChanged.connect(self._mark_custom)
        self.motion_combo.currentTextChanged.connect(self._on_motion_changed)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self.log_filter_combo.currentTextChanged.connect(self._refresh_log_view)
        self.options_edit.editingFinished.connect(self._on_options_edit_finished)
        self.log_table.customContextMenuRequested.connect(self._show_log_context_menu)
        shortcut_cls = getattr(QtWidgets, "QShortcut", None) or getattr(
            QtGui, "QShortcut", None
        )
        if shortcut_cls:
            self._control_shortcut_enter = shortcut_cls(
                QtGui.QKeySequence("Ctrl+Return"), self
            )
            self._control_shortcut_enter.activated.connect(self._on_control)
            self._control_shortcut_f5 = shortcut_cls(QtGui.QKeySequence("F5"), self)
            self._control_shortcut_f5.activated.connect(self._on_control)

    def _connect_aov_scan(self):
        # type: () -> None
        if not self._aov_scan:
            return
        self._aov_scan.started.connect(self._on_aov_scan_started)
        self._aov_scan.completed.connect(self._on_aov_analysis_complete)
        self._aov_scan.timed_out.connect(self._on_aov_analysis_timeout)

    def _set_tooltips(self):
        # type: () -> None
        self.path_edit.setToolTip(
            "Path to an image file or a folder containing images."
        )
        self.backend_combo.setToolTip("Oidn = CPU, Optix = GPU (NVIDIA)")
        self.temporal_chk.setToolTip(
            "Requires motion vectors AOV to enable temporal denoising"
        )
        self.files_list.setToolTip("Files selected for denoising")

    def _browse(self):
        # type: () -> None
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")
        if path:
            self._set_path_text(path, analyze=True, clear_selected=True)

    def _open_output_folder(self):
        # type: () -> None
        path = self._effective_input_path()
        if not path:
            QtWidgets.QMessageBox.information(
                self, "Destination Folder", "Select an input path first."
            )
            return
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(
                self, "Destination Folder", "Input path does not exist."
            )
            return
        output_folder = compute_output_folder(path, [])
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(output_folder))

    def _update_drop_overlay_geometry(self):
        # type: () -> None
        if self.drop_overlay:
            parent = self.drop_overlay.parentWidget()
            if parent:
                self.drop_overlay.setGeometry(parent.rect())

    def _set_drop_overlay_visible(self, visible):
        # type: (bool) -> None
        if self.drop_overlay:
            if visible:
                self._update_drop_overlay_geometry()
                self.drop_overlay.raise_()
            self.drop_overlay.setVisible(visible)

    def _set_path_from_drop(self, urls):
        # type: (List[QtCore.QUrl]) -> None
        paths = []
        for url in urls:
            local = url.toLocalFile()
            if local:
                paths.append(local)
        if not paths:
            return

        folders = [p for p in paths if os.path.isdir(p)]
        files = [p for p in paths if os.path.isfile(p)]

        if folders:
            if len(folders) > 1:
                QtWidgets.QMessageBox.information(
                    self,
                    "Drop",
                    "Multiple folders dropped. Using the first folder.",
                )
            self._set_path_text(folders[0], analyze=True, clear_selected=True)
            return

        if not files:
            return
        if len(files) == 1:
            self._set_selected_files([files[0]])
            self._set_path_text(files[0], analyze=True)
            return

        first_dir = os.path.dirname(files[0])
        same_dir = [f for f in files if os.path.dirname(f) == first_dir]
        if len(same_dir) != len(files):
            QtWidgets.QMessageBox.information(
                self,
                "Drop",
                "Multiple folders detected. Using files from: {}".format(first_dir),
            )
        self._set_selected_files(sorted(same_dir))
        self._set_path_text(first_dir, analyze=True)

    def dragEnterEvent(self, event):
        # type: (QtGui.QDragEnterEvent) -> None
        if event.mimeData().hasUrls():
            self._set_drop_overlay_visible(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        # type: (QtGui.QDragMoveEvent) -> None
        if event.mimeData().hasUrls():
            self._set_drop_overlay_visible(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        # type: (QtGui.QDragLeaveEvent) -> None
        self._set_drop_overlay_visible(False)
        event.accept()

    def dropEvent(self, event):
        # type: (QtGui.QDropEvent) -> None
        self._set_path_from_drop(event.mimeData().urls())
        self._set_drop_overlay_visible(False)
        event.acceptProposedAction()

    def eventFilter(self, obj, event):
        # type: (QtCore.QObject, QtCore.QEvent) -> bool

        if obj in (self.centralWidget(), self.drop_overlay):
            if event.type() == QtCore.QEvent.DragEnter:
                if event.mimeData().hasUrls():
                    self._set_drop_overlay_visible(True)
                    event.acceptProposedAction()
                    return True
            elif event.type() == QtCore.QEvent.DragMove:
                if event.mimeData().hasUrls():
                    self._set_drop_overlay_visible(True)
                    event.acceptProposedAction()
                    return True
            elif event.type() == QtCore.QEvent.DragLeave:
                self._set_drop_overlay_visible(False)
                return True
            elif event.type() == QtCore.QEvent.Drop:
                self._set_path_from_drop(event.mimeData().urls())
                self._set_drop_overlay_visible(False)
                event.acceptProposedAction()
                return True
            elif event.type() == QtCore.QEvent.Resize:
                self._update_drop_overlay_geometry()
        return super(BaseWindow, self).eventFilter(obj, event)

    def _load_recent_paths(self):
        # type: () -> None
        self._recent_paths = load_recent_paths(self._settings)
        self._refresh_recent_paths()

    def _save_recent_paths(self):
        # type: () -> None
        save_recent_paths(self._settings, self._recent_paths)

    # --- Input/path state ---
    def _refresh_recent_paths(self):
        # type: () -> None
        current = self.path_edit.currentText()
        self.path_edit.blockSignals(True)
        self.path_edit.clear()
        for path in self._recent_paths:
            self.path_edit.addItem(path)
        self.path_edit.blockSignals(False)
        self._set_path_text(current)

    def _set_input_path_state(self, path):
        # type: (str) -> None
        self._input_state.path = (path or "").strip()
        self._update_output_label()
        self._update_summary_strip()

    def _set_path_text(self, path, analyze=False, clear_selected=False):
        # type: (str, bool, bool) -> None
        if clear_selected:
            self._clear_selected_files()
        self.path_edit.blockSignals(True)
        self.path_edit.setCurrentText(path)
        self.path_edit.blockSignals(False)
        self._set_input_path_state(path)
        if analyze:
            self._analyze_input()

    def _on_path_text_changed(self, text):
        # type: (str) -> None
        self._set_input_path_state(text)
        path = (text or "").strip()
        if path and os.path.isdir(path):
            self._path_analysis_timer.start()
        else:
            self._path_analysis_timer.stop()

    def _current_input_path(self):
        # type: () -> str
        return self._input_state.path.strip()

    def _effective_input_path(self):
        # type: () -> str
        path = self._current_input_path()
        if self._input_state.selected_files:
            return self._input_state.selected_root or path
        return path

    def _remember_path(self, path):
        # type: (str) -> None
        self._recent_paths = remember_path(self._recent_paths, path, max_items=10)
        self._save_recent_paths()
        self._refresh_recent_paths()

    def _set_selected_files(self, files):
        # type: (List[str]) -> None
        selected_files = [f for f in files if f]
        self._input_state.selected_files = selected_files
        self._input_state.selected_root = ""
        self.files_list.clear()
        if not selected_files:
            self.files_panel.setVisible(False)
            self.files_label.setText("Selected files (0)")
            return

        root = os.path.dirname(selected_files[0])
        if all(os.path.dirname(f) == root for f in selected_files):
            self._input_state.selected_root = root

        if len(selected_files) == 1:
            self.files_label.setText(
                "Selected file: {}".format(os.path.basename(selected_files[0]))
            )
            self.files_list.setVisible(False)
            self.files_remove_btn.setVisible(False)
        else:
            for f in selected_files:
                item = QtWidgets.QListWidgetItem(os.path.basename(f))
                item.setToolTip(f)
                self.files_list.addItem(item)
            self.files_label.setText("Selected files ({})".format(len(selected_files)))
            self.files_list.setVisible(True)
            self.files_remove_btn.setVisible(True)

        self.files_panel.setVisible(True)
        self.files_clear_btn.setVisible(True)
        self._update_output_label()
        self._update_summary_strip()

    def _clear_selected_files(self):
        # type: () -> None
        selected_count = len(self._input_state.selected_files)
        if selected_count > 3 and self.sender() is self.files_clear_btn:
            response = QtWidgets.QMessageBox.question(
                self,
                "Clear Selected Files",
                "Clear {} selected files?".format(selected_count),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if response != QtWidgets.QMessageBox.Yes:
                return
        self._input_state.selected_files = []
        self._input_state.selected_root = ""
        self.files_list.clear()
        self.files_list.setVisible(True)
        self.files_remove_btn.setVisible(True)
        self.files_panel.setVisible(False)
        self.files_label.setText("Selected files (0)")
        self._update_output_label()
        self._update_summary_strip()

    def _remove_selected_files(self):
        # type: () -> None
        selected_rows = {item.row() for item in self.files_list.selectedIndexes()}
        if not selected_rows:
            return
        remaining = [
            f
            for i, f in enumerate(self._input_state.selected_files)
            if i not in selected_rows
        ]
        self._set_selected_files(remaining)

    def _on_path_selected(self, index):
        # type: (int) -> None
        path = self.path_edit.itemText(index)
        if path:
            self._set_path_text(path, analyze=True, clear_selected=True)

    def _set_scan_busy(self, busy):
        # type: (bool) -> None
        self._ui_state.scan_busy = busy
        if self.scan_spinner:
            self.scan_spinner.setVisible(busy)
        if self.scan_btn:
            self.scan_btn.setEnabled(not busy)

    # --- AOV scan lifecycle ---
    def _on_aov_scan_started(self):
        # type: () -> None
        self._set_scan_busy(True)

    def _on_aov_analysis_timeout(self):
        # type: () -> None
        self._set_scan_busy(False)
        self._log("AOV analysis timed out.", "warning")
        self._apply_planes([])

    def _on_aov_analysis_complete(self, result):
        # type: (dict) -> None
        self._set_scan_busy(False)

        status = result.get("status")
        exr_file = result.get("exr_file")
        self._aov_state.last_exr = exr_file
        self._aov_state.last_error = result.get("error") if status == "error" else None
        if status == "no_exr":
            self._log("No EXR file found to analyze.", "warning")
            self._apply_planes([])
            return
        if status == "no_planes":
            self._log("No valid planes found in EXR.", "warning")
            self._apply_planes([])
            return
        if status == "error":
            self._log("Failed to list planes: {}".format(result.get("error")), "error")
            self._apply_planes([])
            return

        if exr_file:
            self._log(
                "Analyzing AOVs from: {}".format(os.path.basename(exr_file)), "info"
            )
        planes = result.get("planes") or []
        self._log("Planes detected: {}".format(planes), "info")
        self._apply_planes(planes)
        self._flash_summary_planes()

    def _analyze_input(self):
        """Analyze input files to populate AOVs and configure settings."""
        path = self._effective_input_path()
        self._update_output_label()
        if not path or not os.path.exists(path):
            if self._aov_scan:
                self._aov_scan.cancel()
            self._set_scan_busy(False)
            self._apply_planes([])
            return
        self._remember_path(path)
        if self._aov_scan:
            self._aov_scan.start(path, self._input_state.selected_files)

    def _auto_select_preset(self, planes):
        # type: (List[str]) -> None
        if not self._auto_preset_enabled:
            return
        if self.preset_combo.currentText() == self._custom_preset:
            return
        lower = {p.lower() for p in planes}
        if lower.intersection({"beauty", "c", "rgba"}):
            preset = "Beauty"
        else:
            preset = "Misc"
        if self.preset_combo.currentText() != preset:
            self._set_preset_text(preset)
            self._apply_preset(preset)

    def _apply_planes(self, planes):
        # type: (List[str]) -> None
        if not planes:
            self._aov_state.planes = []
            self._update_planes_panel([])
            self._suppress_custom_changes = True
            try:
                self._update_temporal_state()
            finally:
                self._suppress_custom_changes = False
            return

        available_planes = list(planes)
        self._aov_state.planes = available_planes
        self._update_planes_panel(available_planes)
        self._auto_select_preset(available_planes)

        self._suppress_custom_changes = True
        try:
            for combo in [
                self.albedo_combo,
                self.normal_combo,
                self.motion_combo,
            ]:
                current = combo.currentText()
                combo.clear()
                combo.addItems([""] + available_planes)
                combo.setCurrentText(current)

            self.aovs_input.set_available_planes(available_planes)

            self._set_smart_selection(
                self.albedo_combo, self.ALBEDO_NAMES, available_planes
            )
            self._set_smart_selection(
                self.normal_combo, self.NORMAL_NAMES, available_planes
            )
            self._set_smart_selection(
                self.motion_combo, self.MOTION_NAMES, available_planes
            )
            self._update_temporal_state()
        finally:
            self._suppress_custom_changes = False

        if not self._motion_vectors_available():
            self._log(
                "Temporal denoising disabled: No motion vectors found.", "warning"
            )

        self._log("AOVs updated from analysis.", "success")

    def _update_planes_panel(self, planes):
        # type: (List[str]) -> None
        self._clear_planes_flow()
        for plane in planes:
            chip = QtWidgets.QLabel(plane)
            chip.setObjectName("aovPlaneChip")
            self.planes_flow_layout.addWidget(chip)
        timestamp = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.planes_toggle.setText("Detected AOVs ({})".format(len(planes)))
        self.planes_toggle.setToolTip(
            "Count: {} | Last scan: {}".format(len(planes), timestamp)
        )
        self._set_planes_preview(planes)
        has_planes = bool(planes)
        self.planes_toggle.setEnabled(has_planes)
        self.planes_body.setEnabled(has_planes)
        if not has_planes:
            self.planes_toggle.setChecked(False)
            self.planes_body.setVisible(False)
        max_height = 120 if has_planes and self.planes_toggle.isChecked() else 24
        self.planes_body.setMaximumHeight(max_height)
        self._update_summary_strip()

    def _toggle_planes_panel(self, checked):
        # type: (bool) -> None
        self.planes_body.setVisible(checked)
        self.planes_toggle.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        has_planes = bool(self._aov_state.planes)
        self.planes_body.setMaximumHeight(120 if checked and has_planes else 24)

    def _toggle_output_body(self, checked):
        # type: (bool) -> None
        if not self.output_body or not self.output_section:
            return
        self.output_body.setVisible(checked)
        if self.output_toggle:
            self.output_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.output_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _toggle_denoise_body(self, checked):
        # type: (bool) -> None
        if not self.denoise_body or not self.denoise_section:
            return
        self.denoise_body.setVisible(checked)
        if self.denoise_toggle:
            self.denoise_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.denoise_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _toggle_advanced(self, checked):
        # type: (bool) -> None
        if not self.advanced_section or not self.advanced_body:
            return
        self.advanced_body.setVisible(checked)
        if self.advanced_toggle:
            self.advanced_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.advanced_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _toggle_aov_body(self, checked):
        # type: (bool) -> None
        if not self.aov_body or not self.aov_section:
            return
        self.aov_body.setVisible(checked)
        if self.aov_toggle:
            self.aov_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.aov_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _clear_planes_flow(self):
        # type: () -> None
        while self.planes_flow_layout.count():
            item = self.planes_flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _output_preview_path(self):
        # type: () -> str
        selected_root = self._input_state.selected_root
        return preview_output_path(self._current_input_path(), selected_root)

    def _update_output_label(self):
        # type: () -> None
        if not self.output_path_label:
            return
        preview = self._output_preview_path()
        if preview:
            text = "Destination: {}".format(preview)
        else:
            text = "Destination: -"
        self.output_path_label.setText(text)
        self.output_path_label.setToolTip(text)
        if self.action_dest_label:
            action_text = "→ {}".format(preview if preview else "-")
            self.action_dest_label.setText(action_text)
            self.action_dest_label.setToolTip(action_text)
        self._update_summary_strip()

    def _update_summary_strip(self):
        # type: () -> None
        if not self.summary_files or not self.summary_planes or not self.summary_motion:
            return

        def _apply_chip_state(chip, object_name):
            # type: (QtWidgets.QLabel, str) -> None
            if chip.objectName() == object_name:
                return
            chip.setObjectName(object_name)
            chip_style = chip.style()
            chip_style.unpolish(chip)
            chip_style.polish(chip)

        selected_files = self._input_state.selected_files
        path = self._effective_input_path()
        if selected_files:
            files_text = "Files: {}".format(len(selected_files))
        elif path and os.path.isfile(path):
            files_text = "Files: 1"
        elif path and os.path.isdir(path):
            files_text = "Files: folder"
        else:
            files_text = "Files: -"

        has_files = bool(selected_files) or bool(
            path and (os.path.isfile(path) or os.path.isdir(path))
        )
        planes_count = len(self._aov_state.planes)
        motion_ok = self._motion_vectors_available()

        self.summary_files.setText(files_text)
        self.summary_planes.setText("Planes: {}".format(planes_count))
        motion_text = "Motion: OK" if motion_ok else "Motion: missing"
        self.summary_motion.setText(motion_text)

        _apply_chip_state(
            self.summary_files,
            "summaryChipOk" if has_files else "summaryChip",
        )
        _apply_chip_state(
            self.summary_planes,
            "summaryChipOk" if planes_count >= 1 else "summaryChipWarn",
        )
        _apply_chip_state(
            self.summary_motion,
            "summaryChipOk" if motion_ok else "summaryChipWarn",
        )

    def _flash_summary_planes(self):
        # type: () -> None
        if not self.summary_planes:
            return
        if not self._summary_planes_flash_timer.isActive():
            self._summary_planes_flash_original_style = self.summary_planes.styleSheet()
        self.summary_planes.setStyleSheet("QLabel { background-color: #5a8fd1; }")
        self._summary_planes_flash_timer.start(400)

    def _clear_summary_planes_flash(self):
        # type: () -> None
        if not self.summary_planes:
            return
        self.summary_planes.setStyleSheet(
            self._summary_planes_flash_original_style or ""
        )
        self._summary_planes_flash_original_style = None
        chip_style = self.summary_planes.style()
        chip_style.unpolish(self.summary_planes)
        chip_style.polish(self.summary_planes)

    def _set_planes_preview(self, planes):
        # type: (List[str]) -> None
        if not planes:
            self.planes_preview.setText("")
            return
        preview = ", ".join(planes[:4])
        if len(planes) > 4:
            preview += ", ..."
        self.planes_preview.setText(preview)

    def _set_smart_selection(self, combo, candidates, available_planes):
        # type: (QtWidgets.QComboBox, Set[str], List[str]) -> bool
        """Select item in combo if it matches candidates. Returns True if found."""
        current = combo.currentText()
        if current in available_planes:
            return True  # Already valid

        candidate_lower = {c.lower() for c in candidates}
        for plane in available_planes:
            # Check exact or case-insensitive match
            if plane in candidates or plane.lower() in candidate_lower:
                combo.setCurrentText(plane)
                return True

            # Check for common prefixes like "renderLayer.N"
            base_plane = plane.split(".")[-1]
            if base_plane in candidates or base_plane.lower() in candidate_lower:
                combo.setCurrentText(plane)
                return True

        if current and current.lower() in candidate_lower:
            combo.setCurrentText("")
        return False

    def _set_preset_text(self, preset_name):
        # type: (str) -> None
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(preset_name)
        self.preset_combo.blockSignals(False)

    @staticmethod
    def _backend_display(backend_key):
        # type: (str) -> str
        key = (backend_key or "").strip().lower()
        if key == "oidn":
            return "Oidn"
        if key == "optix":
            return "Optix"
        return backend_key

    def _backend_key(self):
        # type: () -> str
        return self.backend_combo.currentText().strip().lower()

    def _apply_preset(self, preset_name):
        # type: (str) -> None
        if preset_name not in PRESETS:
            return
        preset = PRESETS[preset_name]
        self._suppress_custom_changes = True
        try:
            backend_key = preset.get("backend", "optix")
            self.backend_combo.setCurrentText(self._backend_display(backend_key))
            self._apply_preset_plane(self.normal_combo, preset.get("normal", "normal"))
            self._apply_preset_plane(self.albedo_combo, preset.get("albedo", "albedo"))
            self._apply_preset_plane(
                self.motion_combo, preset.get("motion", "motionvectors")
            )
            self._update_temporal_state(
                desired_checked=bool(preset.get("temporal", False))
            )
        finally:
            self._suppress_custom_changes = False

    def _apply_preset_plane(self, combo, preset_value):
        # type: (QtWidgets.QComboBox, Optional[str]) -> None
        if not preset_value:
            combo.setCurrentText("")
            return
        available_planes = self._aov_state.planes
        if not available_planes:
            combo.setCurrentText("")
            return
        preset_lower = str(preset_value).lower()
        match = ""
        for plane in available_planes:
            if plane == preset_value:
                match = plane
                break
            if plane.lower() == preset_lower:
                match = plane
                break
            base_plane = plane.split(".")[-1]
            if base_plane.lower() == preset_lower:
                match = plane
                break
        combo.setCurrentText(match)

    def _mark_custom(self):
        # type: () -> None
        if self._suppress_custom_changes:
            return
        self._auto_preset_enabled = False
        if self.preset_combo.currentText() != self._custom_preset:
            self._set_preset_text(self._custom_preset)

    def _motion_vectors_available(self):
        # type: () -> bool
        motion_text = self.motion_combo.currentText().strip()
        available_planes = self._aov_state.planes
        if not motion_text or not available_planes:
            return False
        return motion_text.lower() in {p.lower() for p in available_planes}

    def _update_temporal_state(self, desired_checked=None):
        # type: (Optional[bool]) -> bool
        backend = self._backend_key()
        motion_valid = self._motion_vectors_available()
        allow_temporal = backend == "optix" and motion_valid

        if desired_checked is None:
            desired_checked = self.temporal_chk.isChecked()

        if allow_temporal:
            self.temporal_chk.setEnabled(True)
            self.temporal_chk.setChecked(bool(desired_checked))
            self.temporal_chk.setToolTip(
                "Use previous frame for temporal denoising (OptiX only)"
            )
        else:
            self.temporal_chk.setChecked(False)
            self.temporal_chk.setEnabled(False)
            if backend != "optix":
                self.temporal_chk.setToolTip(
                    "Temporal denoising not supported by {}".format(
                        self.backend_combo.currentText()
                    )
                )
            else:
                self.temporal_chk.setToolTip(
                    "Requires motion vectors AOV to enable temporal denoising"
                )

        self._update_summary_strip()
        return allow_temporal

    def _pick_custom_exe(self):
        # type: () -> None
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select idenoise executable", "", "Executables (*.exe);;All Files (*)"
        )
        if path:
            self.denoiser_combo.addItem(os.path.basename(path), path)
            self.denoiser_combo.setCurrentIndex(self.denoiser_combo.count() - 1)

    def _on_backend_changed(self, backend):
        # type: (str) -> None
        self._update_temporal_state()

    def _on_motion_changed(self, _):
        # type: (str) -> None
        self._update_temporal_state()
        self._mark_custom()

    def _on_preset_changed(self, preset_name):
        # type: (str) -> None
        if preset_name == self._custom_preset:
            self._auto_preset_enabled = False
            return
        if preset_name not in PRESETS:
            return
        self._auto_preset_enabled = False
        self._apply_preset(preset_name)

    def _on_control(self):
        # type: () -> None
        if self._ui_state.is_running:
            self._stop_denoise()
        else:
            self._start_denoise()

    def _on_options_edit_finished(self):
        # type: () -> None
        self._validate_options_json(show_message=False)

    def _validate_options_json(self, show_message=False):
        # type: (bool) -> bool
        text = self.options_edit.text().strip()
        if not text:
            self.options_edit.setProperty("error", False)
            options_style = self.options_edit.style()
            options_style.unpolish(self.options_edit)
            options_style.polish(self.options_edit)
            self.options_edit.setToolTip("")
            return True
        try:
            json.loads(text)
        except Exception as exc:
            self.options_edit.setProperty("error", True)
            options_style = self.options_edit.style()
            options_style.unpolish(self.options_edit)
            options_style.polish(self.options_edit)
            self.options_edit.setToolTip("Invalid JSON: {}".format(exc))
            if show_message:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Options JSON",
                    "Options JSON is invalid:\n{}".format(exc),
                )
            return False
        self.options_edit.setProperty("error", False)
        options_style = self.options_edit.style()
        options_style.unpolish(self.options_edit)
        options_style.polish(self.options_edit)
        self.options_edit.setToolTip("")
        return True

    # --- Denoise workflow ---
    def _start_denoise(self):
        # type: () -> None
        input_path = self._effective_input_path()
        selected_files = self._input_state.selected_files
        if selected_files and not input_path:
            input_path = selected_files[0]
        if not input_path or not os.path.exists(input_path):
            QtWidgets.QMessageBox.warning(self, "Error", "Invalid input path")
            return

        idenoise_path = self.denoiser_combo.currentData()
        if not idenoise_path:
            QtWidgets.QMessageBox.warning(
                self, "Error", "No idenoise executable selected"
            )
            return
        if not self._validate_options_json(show_message=True):
            return

        self._denoise_state.backend = self._backend_key()
        self._denoise_state.idenoise_path = idenoise_path
        self._denoise_state.threads = self.thread_spin.value()
        self._denoise_state.overwrite = self.overwrite_chk.isChecked()
        self._denoise_state.prefix = self.prefix_edit.text()
        self._denoise_state.options_json = self.options_edit.text().strip() or ""
        self._denoise_state.temporal = self.temporal_chk.isChecked()

        # Collect settings
        denoise_config = DenoiseConfig(
            backend=self._denoise_state.backend,
            temporal=self._denoise_state.temporal,
            overwrite=self._denoise_state.overwrite,
            threads=self._denoise_state.threads,
            prefix=self._denoise_state.prefix,
            exrmode=self._get_exrmode(),
            options_json=self._denoise_state.options_json or None,
        )

        aov_config = AOVConfig(
            normal_plane=self.normal_combo.currentText().strip() or None,
            albedo_plane=self.albedo_combo.currentText().strip() or None,
            motionvectors_plane=self.motion_combo.currentText().strip() or None,
            aovs_to_denoise=self.aovs_input.selected_chips() or None,
            extra_aovs=self._parse_space_list(self.extra_aovs_edit.text()),
        )

        # Start worker
        self.worker = DenoiseWorker(
            input_path,
            denoise_config,
            aov_config,
            idenoise_path,
            extensions=None,
            file_list=list(selected_files) if selected_files else None,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.log_message.connect(self._log)
        self.worker.finished.connect(self._on_finished)

        self._ui_state.is_running = True
        self._ui_state.progress_current = 0
        self._ui_state.progress_total = 0
        self.control_btn.setText("Stop")
        self.control_btn.setIcon(self.stop_icon)
        self.control_btn.setObjectName("stopBtn")
        button_style = self.control_btn.style()
        button_style.unpolish(self.control_btn)
        button_style.polish(self.control_btn)
        self.log_table.setRowCount(0)
        self.log_records = []
        self._visible_log_records = []

        self.progress.setValue(0)
        self._run_start = time.time()
        self.progress_label.setText("File 0 of 0 | ETA --:--")

        self.worker.start()

    def _stop_denoise(self):
        # type: () -> None
        if self.worker:
            self.worker.request_stop()
            self._log("Stopping...", "warning")

    def _on_progress(self, current, total):
        # type: (int, int) -> None
        self._ui_state.progress_current = current
        self._ui_state.progress_total = total
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self._update_progress_label(current, total)

    def _on_finished(self, summary):
        # type: (dict) -> None
        self._ui_state.is_running = False
        self.control_btn.setText("Denoise")
        self.control_btn.setIcon(self.play_icon)
        self.control_btn.setObjectName("primaryBtn")
        button_style = self.control_btn.style()
        button_style.unpolish(self.control_btn)
        button_style.polish(self.control_btn)
        self.worker = None

        msg = "Processed: {}, Skipped: {}, Failed: {}".format(
            summary.get("processed", 0),
            summary.get("skipped", 0),
            len(summary.get("failed", [])),
        )
        self._log(msg, "success" if not summary.get("failed") else "warning")
        if self._run_start:
            elapsed = time.time() - self._run_start
            self.progress_label.setText(
                "Completed in {}".format(self._format_eta(elapsed))
            )
        self._run_start = None

    def _update_progress_label(self, current, total):
        # type: (int, int) -> None
        if total <= 0:
            self.progress_label.setText("File 0 of 0 | ETA --:--")
            return
        if not self._run_start:
            self._run_start = time.time()
        if current <= 0:
            eta_text = "--:--"
        else:
            elapsed = time.time() - self._run_start
            avg = elapsed / float(current)
            remaining = max(0.0, avg * (total - current))
            eta_text = self._format_eta(remaining)
        self.progress_label.setText(
            "File {}/{} | ETA {}".format(current, total, eta_text)
        )

    @staticmethod
    def _format_eta(seconds):
        # type: (float) -> str
        secs = max(0, int(seconds + 0.5))
        mins, sec = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return "{:d}:{:02d}:{:02d}".format(hours, mins, sec)
        return "{:02d}:{:02d}".format(mins, sec)

    def _log_from_handler(self, msg, level_name):
        # type: (str, str) -> None
        """Handle log record from logging handler."""
        # Convert logging level name to UI level name
        # logging: DEBUG, INFO, WARNING, ERROR, CRITICAL
        # UI: info, success, warning, error (debug mapped to info/gray)

        ui_level = "info"
        if level_name == "error" or level_name == "critical":
            ui_level = "error"
        elif level_name == "warning":
            ui_level = "warning"
        elif level_name == "debug":
            ui_level = "debug"  # Special case for gray

        self._append_log(msg, ui_level)

    def _log(self, message, level="info"):
        # type: (str, str) -> None
        """Log message through the logging pipeline for UI + console."""
        if level == "success":
            level = "info"
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        logger.log(
            level_map.get(level, logging.INFO), message, extra={"ui_level": level}
        )

    def _log_level_icon(self, level):
        # type: (str) -> Optional[QtGui.QIcon]
        icon_map = {
            "error": QtWidgets.QStyle.SP_MessageBoxCritical,
            "warning": QtWidgets.QStyle.SP_MessageBoxWarning,
            "info": QtWidgets.QStyle.SP_MessageBoxInformation,
            "success": QtWidgets.QStyle.SP_DialogApplyButton,
            "debug": QtWidgets.QStyle.SP_MessageBoxInformation,
        }
        style = self.app_style
        icon_id = icon_map.get(level)
        if icon_id is None:
            return None
        return style.standardIcon(icon_id)

    def _log_filter_allows(self, level):
        # type: (str) -> bool
        mode = self.log_filter_combo.currentText()
        level = level.lower()
        if mode == "All":
            return True
        if mode == "Errors":
            return level in ("error", "critical")
        if mode == "Warnings":
            return level == "warning"
        if mode == "Info":
            return level == "info"
        if mode == "Debug":
            return level == "debug"
        return True

    def _refresh_log_view(self):
        # type: () -> None
        self.log_table.setRowCount(0)
        self._visible_log_records = []
        for record in self.log_records:
            if self._log_filter_allows(record["level"]):
                self._visible_log_records.append(record)
                self._add_log_item(record, scroll=False)
        self.log_table.scrollToBottom()

    def _append_log(self, message, level="info"):
        # type: (str, str) -> None
        """Append log to widget (internal)."""
        if level == "success":
            level = "info"
        record = {
            "timestamp": QtCore.QDateTime.currentDateTime(),
            "message": message,
            "level": level,
        }
        self.log_records.append(record)
        if not self._log_filter_allows(level):
            return
        self._visible_log_records.append(record)
        self._add_log_item(record, scroll=True)

    def _add_log_item(self, record, scroll):
        # type: (dict, bool) -> None
        row = self.log_table.rowCount()
        self.log_table.insertRow(row)
        timestamp = record["timestamp"].toString("HH:mm:ss.zzz")
        ts_item = QtWidgets.QTableWidgetItem(timestamp)
        ts_item.setFlags(ts_item.flags() & ~QtCore.Qt.ItemIsEditable)
        msg_item = QtWidgets.QTableWidgetItem(record["message"])
        msg_item.setFlags(msg_item.flags() & ~QtCore.Qt.ItemIsEditable)
        msg_item.setToolTip(record["message"])
        icon = self._log_level_icon(record["level"])
        if icon:
            msg_item.setIcon(icon)
        self.log_table.setItem(row, 0, ts_item)
        self.log_table.setItem(row, 1, msg_item)
        if scroll:
            self.log_table.scrollToBottom()

    def _show_log_context_menu(self, pos):
        # type: (QtCore.QPoint) -> None
        selected_rows = self.log_table.selectionModel().selectedRows()
        selected_row = selected_rows[0].row() if selected_rows else -1
        message_item = (
            self.log_table.item(selected_row, 1) if selected_row >= 0 else None
        )

        menu = QtWidgets.QMenu(self)
        copy_message_action = menu.addAction("Copy message")
        copy_message_action.setEnabled(message_item is not None)
        copy_all_action = menu.addAction("Copy all")

        menu_exec = getattr(menu, "exec", None) or getattr(menu, "exec_", None)
        if not menu_exec:
            return
        chosen_action = menu_exec(self.log_table.viewport().mapToGlobal(pos))
        if not chosen_action:
            return

        clipboard = QtWidgets.QApplication.clipboard()
        if chosen_action == copy_message_action and message_item is not None:
            clipboard.setText(message_item.text())
            return

        if chosen_action == copy_all_action:
            rows = []
            for row in range(self.log_table.rowCount()):
                ts_item = self.log_table.item(row, 0)
                msg_item = self.log_table.item(row, 1)
                timestamp = ts_item.text() if ts_item else ""
                message = msg_item.text() if msg_item else ""
                rows.append("{}\t{}".format(timestamp, message))
            clipboard.setText("\n".join(rows))

    def _get_exrmode(self):
        # type: () -> Optional[int]
        text = self.exrmode_combo.currentText()
        if text in ("-1", "0", "1"):
            return int(text)
        return None

    @staticmethod
    def _parse_space_list(text):
        # type: (str) -> Optional[List[str]]
        if not text or not text.strip():
            return None
        parts = re.split(r"[,\s]+", text.strip())
        return [p for p in parts if p] or None


def show():
    # type: () -> BaseWindow
    """Show the denoiser window."""
    window = BaseWindow()
    window.show()
    return window


if __name__ == "__main__":
    show()
