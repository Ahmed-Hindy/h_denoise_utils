"""Main window for the bundled OptiX denoiser GUI."""

from __future__ import annotations

import logging
import os
import re
import time

from .. import __version__
from ..core.config import (
    PRESETS,
    AOVConfig,
    DenoiseConfig,
)
from ..discovery.bundled_denoiser import (
    DEFAULT_OPTIX_VERSION,
    SUPPORTED_OPTIX_VERSIONS,
    resolve_bundled_denoiser,
)
from ..discovery.bundled_oidn import resolve_bundled_oidn_denoiser
from ..logger import get_log_dir, setup_logger
from ..utils.file_utils import compute_output_folder
from . import tooltips
from .aov_scan_manager import AovScanManager
from .logging_handler import QtLogHandler
from .qt_compat import (
    QtAction,
    QtCore,
    QtGui,
    QtWidgets,
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
from .worker import DenoiseWorker

logger = logging.getLogger(__name__)


class BaseWindow(QtWidgets.QMainWindow):
    """Main UI widget for bundled OptiX denoising."""

    # Standard AOV names for heuristics
    BEAUTY_NAMES = {"C", "beauty", "Beauty", "RGBA", "rgb"}
    NORMAL_NAMES = {"N", "normal", "normals", "Normal"}
    ALBEDO_NAMES = {"albedo", "Albedo", "diffuse_albedo"}

    def __init__(
        self, parent: QtWidgets.QWidget | None = None, initial_path: str | None = None
    ) -> None:
        """Initialize the base window instance and UI elements.

        Args:
            parent: Optional parent widget.
            initial_path: Optional initial path to load on startup.
        """
        super().__init__(parent)
        self.app_style = self.style()
        self.setAcceptDrops(True)
        self.worker: DenoiseWorker | None = None
        self._settings = QtCore.QSettings("h_denoise_utils", "h_denoise_utils")
        self._recent_paths: list[str] = []
        self._input_state = InputState()
        self._aov_state = AovState()
        self._last_aov_scan_key = None
        self._ui_state = UiState()
        self._denoise_state = DenoiseState()
        self.log_records: list[dict] = []
        self._visible_log_records: list[dict] = []
        self._run_start: float | None = None
        self._custom_preset = "Custom"
        self._auto_preset_enabled = True
        self._suppress_custom_changes = False
        self.drop_overlay: QtWidgets.QLabel | None = None
        self.log_table: QtWidgets.QTableWidget | None = None
        self.output_path_label: QtWidgets.QLabel | None = None
        self.action_dest_label: QtWidgets.QLabel | None = None
        self._package_logger: logging.Logger | None = None
        self._aov_timeout_ms = 10000
        self._aov_scan = AovScanManager(timeout_ms=self._aov_timeout_ms, parent=self)
        self.scan_spinner: QtWidgets.QProgressBar | None = None
        self.summary_files: QtWidgets.QLabel | None = None
        self.summary_planes: QtWidgets.QLabel | None = None
        self.summary_motion: QtWidgets.QLabel | None = None
        self.input_section: QtWidgets.QFrame | None = None
        self.input_body: QtWidgets.QWidget | None = None
        self.output_section: QtWidgets.QFrame | None = None
        self.output_body: QtWidgets.QWidget | None = None
        self.output_toggle: QtWidgets.QToolButton | None = None
        self.config_scroll: QtWidgets.QScrollArea | None = None
        self.config_scroll_body: QtWidgets.QWidget | None = None
        self._input_header_spacer: QtWidgets.QWidget | None = None
        self.denoise_section: QtWidgets.QFrame | None = None
        self.denoise_body: QtWidgets.QWidget | None = None
        self.denoise_toggle: QtWidgets.QToolButton | None = None
        self.adv_scroll: QtWidgets.QScrollArea | None = None
        self.advanced_section: QtWidgets.QFrame | None = None
        self.advanced_body: QtWidgets.QWidget | None = None
        self.advanced_toggle: QtWidgets.QToolButton | None = None
        self.advanced_settings_section: QtWidgets.QFrame | None = None
        self.advanced_settings_body: QtWidgets.QWidget | None = None
        self.advanced_settings_toggle: QtWidgets.QToolButton | None = None
        self.beauty_combo: QtWidgets.QComboBox | None = None
        self.backend_combo: QtWidgets.QComboBox | None = None
        self.optix_version_combo: QtWidgets.QComboBox | None = None
        self.denoiser_status_label: QtWidgets.QLabel | None = None
        self.motion_label: QtWidgets.QLabel | None = None
        self._path_analysis_timer = QtCore.QTimer(self)
        self._path_analysis_timer.setSingleShot(True)
        self._path_analysis_timer.setInterval(500)
        self._path_analysis_timer.timeout.connect(self._analyze_input)
        self._summary_planes_flash_timer = QtCore.QTimer(self)
        self._summary_planes_flash_timer.setSingleShot(True)
        self._summary_planes_flash_timer.timeout.connect(self._clear_summary_planes_flash)
        self._summary_planes_flash_original_style: str | None = None
        self._control_shortcut_enter: object | None = None
        self._scan_shortcut_f5: object | None = None
        self.main_splitter: QtWidgets.QSplitter | None = None
        self._pre_run_enabled: dict = {}

        self.supported_optix_versions = SUPPORTED_OPTIX_VERSIONS
        self.selected_backend = "optix"
        self.selected_optix_version = self._initial_optix_version()
        self.bundled_denoiser_path = self._resolve_selected_denoiser_path()
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

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Clean up active resources and save settings when the window is closed.

        Args:
            event: The window close event payload.
        """
        if self._package_logger and self.log_handler:
            self._package_logger.removeHandler(self.log_handler)
            self.log_handler.close()
        if self._aov_scan:
            self._aov_scan.cancel()
        self._save_splitter_state()
        super().closeEvent(event)

    def _load_stylesheet(self) -> None:
        """Load and apply the CSS/QSS stylesheet for window styling."""
        ui_dir = os.path.dirname(__file__)
        icons_dir = os.path.join(ui_dir, "icons")
        if os.path.isdir(icons_dir):
            # Stable QSS path prefix, independent of launch cwd.
            QtCore.QDir.addSearchPath("hdui", os.path.normpath(icons_dir))
        style_path = os.path.join(ui_dir, "style.qss")
        if os.path.exists(style_path):
            with open(style_path) as stream:
                self.setStyleSheet(stream.read())

    # --- Menu & window setup ---
    def _setup_menus(self) -> None:
        """Initialize and build the menu bar actions and help menus."""
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

    def _show_about(self) -> None:
        """Display the About dialog containing app name, version, and details."""
        QtWidgets.QMessageBox.about(
            self,
            "About Denoiser",
            (
                f"<b>Denoiser</b><br>Version {__version__}<br><br>"
                "Denoises multipart EXRs with bundled OptiX or OIDN denoisers, "
                "with smart AOV detection and source metadata preservation."
            ),
        )

    def _show_shortcuts(self) -> None:
        """Display a dialog box listing the available keyboard shortcuts."""
        message = "Shortcuts:\n\nCtrl+Enter: Denoise / Stop\nF5: Scan AOVs\nCtrl+Q: Quit"
        QtWidgets.QMessageBox.information(self, "Shortcuts", message)

    def _log_folder_path(self) -> str:
        """Get the directory path where log files are stored.

        Returns:
            str: Path to the logs folder.
        """
        return get_log_dir()

    def _open_logs_folder(self) -> None:
        """Open the application logs folder in the system file explorer."""
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
            QtWidgets.QMessageBox.warning(self, "Logs Folder", "Unable to open the logs folder.")

    def _setup_ui(self) -> None:
        """Construct and arrange all sections, layout frames, and widgets."""
        ENV_IS_DEV = str(os.environ.get("ENV_IS_DEV", "")).lower() == "true"
        title = (
            "Denoiser {} {}".format("(DEV)" if ENV_IS_DEV else "", __version__)
            .replace("  ", " ")
            .strip()
        )
        self.setWindowTitle(title)
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
            "QLabel{border:2px dashed #4a7ab5;border-radius:8px;"
            "background-color: rgba(58,95,138,72);color:#dfdfdf;}"
        )
        self.drop_overlay.setVisible(False)
        self.drop_overlay.installEventFilter(self)

        # Load stylesheet
        self._load_stylesheet()

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter = self.main_splitter
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
        self._restore_splitter_state()

        self._build_source_section(top_layout)
        config_layout = self._build_config_scroll(top_layout)
        self._build_destination_section(config_layout)
        self._build_extras_section(config_layout)
        config_layout.addStretch(1)
        self._build_action_bar(top_layout)
        self._build_logs_section(logs_layout)

    def _build_source_section(self, top_layout: QtWidgets.QVBoxLayout) -> None:
        """Add the Source section widgets to the main vertical layout.

        Args:
            top_layout: The top-level QVBoxLayout of the main window.
        """
        build_source_section(self, top_layout)

    def _build_config_scroll(self, top_layout: QtWidgets.QVBoxLayout) -> QtWidgets.QVBoxLayout:
        """Create the configuration scroll area and append to top layout.

        Args:
            top_layout: The top-level QVBoxLayout of the main window.

        Returns:
            QtWidgets.QVBoxLayout: The internal body layout inside the scroll area.
        """
        return build_config_scroll(self, top_layout)

    def _build_destination_section(self, top_layout: QtWidgets.QVBoxLayout) -> None:
        """Add the Destination configuration card to the scroll layout.

        Args:
            top_layout: The scroll area's configuration QVBoxLayout.
        """
        build_destination_section(self, top_layout)

    def _build_extras_section(self, top_layout: QtWidgets.QVBoxLayout) -> None:
        """Add settings and runtime selection cards to the scroll layout.

        Args:
            top_layout: The scroll area's configuration QVBoxLayout.
        """
        build_extras_section(self, top_layout)

    def _build_action_bar(self, top_layout: QtWidgets.QVBoxLayout) -> None:
        """Add execution triggers, progress bar, and path labels to layout.

        Args:
            top_layout: The top-level QVBoxLayout of the main window.
        """
        build_action_bar(self, top_layout)

    def _build_logs_section(self, logs_layout: QtWidgets.QVBoxLayout) -> None:
        """Add log table and level filtering combo box to the layout.

        Args:
            logs_layout: The QVBoxLayout of the logs pane widget.
        """
        build_logs_section(self, logs_layout)

    def _set_init_widget_values(self) -> None:
        """Set initial values and preset selections for widgets on launch."""
        self.preset_combo.setCurrentText("Beauty")
        self._apply_preset("Beauty")
        self._update_output_label()

    def _lockable_widgets(self) -> list[QtWidgets.QWidget]:
        """Return the ordered list of interactive widgets to lock during a run."""
        widgets = [
            self.path_edit,
            self.browse_btn,
            self.scan_btn,
            self.files_remove_btn,
            self.files_clear_btn,
            self.preset_combo,
            self.aovs_input,
            self.overwrite_chk,
            self.output_toggle,
            self.advanced_toggle,
            self.advanced_settings_toggle,
            self.prefix_edit,
            self.beauty_combo,
            self.albedo_combo,
            self.normal_combo,
            self.backend_combo,
            self.optix_version_combo,
            self.log_filter_combo,
        ]
        return [w for w in widgets if w is not None]

    def _apply_ui_lock(self, locked: bool) -> None:
        """Enable or disable interaction with UI widgets during denoiser execution.

        Args:
            locked: Whether to lock the widgets (True) or restore them (False).
        """
        if locked:
            self._pre_run_enabled = {w: w.isEnabled() for w in self._lockable_widgets()}
            for w in self._lockable_widgets():
                self._set_lockable_enabled(w, False)
        else:
            for w, was_enabled in (self._pre_run_enabled or {}).items():
                self._set_lockable_enabled(w, was_enabled)
            self._pre_run_enabled = {}

    def _set_lockable_enabled(self, widget: QtWidgets.QWidget, enabled: bool) -> None:
        """Set enabled state without allowing lockable widgets to unlock mid-run."""
        if self._ui_state.is_running and enabled and widget in self._lockable_widgets():
            enabled = False
        widget.setEnabled(enabled)

    def _initial_optix_version(self) -> str:
        """Determine the initial OptiX runtime version from environment variable or default.

        Returns:
            str: Selected initial OptiX version string.
        """
        return DEFAULT_OPTIX_VERSION

    def _optix_version_key(self) -> str:
        """Retrieve the selected OptiX version identifier from combo box data.

        Returns:
            str: OptiX version key identifier.
        """
        if self.optix_version_combo:
            data = self.optix_version_combo.currentData()
            if data:
                return str(data)
        return self.selected_optix_version or DEFAULT_OPTIX_VERSION

    def _resolve_selected_denoiser_path(self) -> str:
        """Locate the executable path of the selected backend denoiser runtime.

        Returns:
            str: Path to the executable binary, or empty string if missing.
        """
        try:
            if self._backend_key() == "oidn":
                return resolve_bundled_oidn_denoiser(required=False) or ""
            return (
                resolve_bundled_denoiser(
                    required=False,
                    optix_version=self.selected_optix_version,
                )
                or ""
            )
        except ValueError:
            return ""

    def _runtime_missing_text(self) -> str:
        """Construct appropriate warning text for missing backend executables.

        Returns:
            str: Path resolution failure alert string.
        """
        if self._backend_key() == "oidn":
            return "Missing bundled OIDN Denoiser.exe"
        return f"Missing bundled Denoiser.exe for OptiX {self.selected_optix_version}"

    def _sync_backend_controls(self) -> None:
        """Enable or disable options based on the chosen backend (OptiX vs OIDN)."""
        is_optix = self._backend_key() == "optix"
        if self.optix_version_combo:
            self.optix_version_combo.setEnabled(is_optix)
        self._refresh_denoiser_status()
        self._update_summary_strip()

    def _refresh_denoiser_status(self) -> None:
        """Update the Status label with the resolved path of the denoiser binary."""
        if self.denoiser_status_label:
            self.denoiser_status_label.setText(
                self.bundled_denoiser_path or self._runtime_missing_text()
            )

    def _on_optix_version_changed(self, _text: str) -> None:
        """Trigger path resolution and UI updates when the OptiX version changes.

        Args:
            _text: The new selected text value from the combo box.
        """
        self.selected_optix_version = self._optix_version_key()
        self.bundled_denoiser_path = self._resolve_selected_denoiser_path()
        self._sync_backend_controls()

    # --- Signal wiring ---
    def _connect_signals(self) -> None:
        """Connect signals of all interactive controls to their corresponding slots."""
        self.browse_btn.clicked.connect(self._browse)
        self.scan_btn.clicked.connect(self._on_scan_requested)
        self.open_output_btn.clicked.connect(self._open_output_folder)
        self.path_edit.currentTextChanged.connect(self._on_path_text_changed)
        self.path_edit.lineEdit().editingFinished.connect(self._analyze_input)
        self.path_edit.activated.connect(self._on_path_selected)
        self.files_remove_btn.clicked.connect(self._remove_selected_files)
        self.files_clear_btn.clicked.connect(self._clear_selected_files)

        if self.output_toggle:
            self.output_toggle.toggled.connect(self._toggle_output_body)
        if self.denoise_toggle:
            self.denoise_toggle.toggled.connect(self._toggle_denoise_body)
        if self.aov_toggle:
            self.aov_toggle.toggled.connect(self._toggle_aov_body)
        if self.advanced_toggle:
            self.advanced_toggle.toggled.connect(self._toggle_advanced)
        if self.advanced_settings_toggle:
            self.advanced_settings_toggle.toggled.connect(self._toggle_advanced_settings)
        self.control_btn.clicked.connect(self._on_control)
        self.beauty_combo.currentTextChanged.connect(self._mark_custom)
        self.normal_combo.currentTextChanged.connect(self._mark_custom)
        self.albedo_combo.currentTextChanged.connect(self._mark_custom)
        if self.optix_version_combo:
            self.optix_version_combo.currentTextChanged.connect(self._on_optix_version_changed)
        if self.backend_combo:
            self.backend_combo.currentTextChanged.connect(self._on_backend_changed)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self.log_filter_combo.currentTextChanged.connect(self._refresh_log_view)
        self.log_table.customContextMenuRequested.connect(self._show_log_context_menu)
        shortcut_cls = getattr(QtWidgets, "QShortcut", None) or getattr(QtGui, "QShortcut", None)
        if shortcut_cls:
            self._control_shortcut_enter = shortcut_cls(QtGui.QKeySequence("Ctrl+Return"), self)
            self._control_shortcut_enter.activated.connect(self._on_control)
            self._scan_shortcut_f5 = shortcut_cls(QtGui.QKeySequence("F5"), self)
            self._scan_shortcut_f5.activated.connect(self._on_scan_requested)

    def _connect_aov_scan(self) -> None:
        """Connect signals of the background AovScanManager instance to slot methods."""
        if not self._aov_scan:
            return
        self._aov_scan.started.connect(self._on_aov_scan_started)
        self._aov_scan.completed.connect(self._on_aov_analysis_complete)
        self._aov_scan.timed_out.connect(self._on_aov_analysis_timeout)

    def _set_tooltips(self) -> None:
        """Apply tooltip text descriptions to all control elements."""
        self.path_edit.setToolTip(tooltips.PATH_EDIT)
        self.browse_btn.setToolTip(tooltips.BROWSE_BTN)
        self.scan_btn.setToolTip(tooltips.SCAN_BTN)
        self.files_list.setToolTip(tooltips.FILES_LIST)
        self.files_remove_btn.setToolTip(tooltips.FILES_REMOVE_BTN)
        self.files_clear_btn.setToolTip(tooltips.FILES_CLEAR_BTN)
        if self.summary_files:
            self.summary_files.setToolTip(tooltips.SUMMARY_FILES)
        if self.summary_planes:
            self.summary_planes.setToolTip(tooltips.SUMMARY_PLANES)
        if self.summary_motion:
            self.summary_motion.setToolTip(tooltips.SUMMARY_MOTION)
        if self.scan_spinner:
            self.scan_spinner.setToolTip(tooltips.SCAN_SPINNER)

        self.output_toggle.setToolTip(tooltips.OUTPUT_TOGGLE)
        self.preset_combo.setToolTip(tooltips.PRESET_COMBO)
        self.aovs_input.setToolTip(tooltips.AOVS_INPUT)
        self.aovs_input.custom_input.setToolTip(tooltips.AOVS_CUSTOM_INPUT)
        self.overwrite_chk.setToolTip(tooltips.OVERWRITE_CHK)

        self.advanced_toggle.setToolTip(tooltips.ADVANCED_TOGGLE)
        self.advanced_settings_toggle.setToolTip(tooltips.ADVANCED_SETTINGS_TOGGLE)
        self.prefix_edit.setToolTip(tooltips.PREFIX_EDIT)
        self.beauty_combo.setToolTip(tooltips.BEAUTY_COMBO)
        self.albedo_combo.setToolTip(tooltips.ALBEDO_COMBO)
        self.normal_combo.setToolTip(tooltips.NORMAL_COMBO)
        if self.optix_version_combo:
            self.optix_version_combo.setToolTip(tooltips.OPTIX_VERSION_COMBO)
        if self.backend_combo:
            self.backend_combo.setToolTip(tooltips.BACKEND_COMBO)
        if self.denoiser_status_label:
            self.denoiser_status_label.setToolTip(tooltips.DENOISER_COMBO)

        self.control_btn.setToolTip(tooltips.CONTROL_BTN_START)
        self.progress.setToolTip(tooltips.PROGRESS)
        self.progress_label.setToolTip(tooltips.PROGRESS_LABEL)
        self.open_output_btn.setToolTip(tooltips.OPEN_OUTPUT_BTN)

        self.log_filter_combo.setToolTip(tooltips.LOG_FILTER_COMBO)

        self._update_output_label()

    def _browse(self) -> None:
        """Open a QFileDialog directory selector to populate the path input."""
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")
        if path:
            self._set_path_text(path, analyze=True, clear_selected=True)

    def _open_output_folder(self) -> None:
        """Open the destination folder of the active input path in file manager."""
        path = self._effective_input_path()
        if not path:
            QtWidgets.QMessageBox.information(
                self, "Destination Folder", "Select an input path first."
            )
            return
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Destination Folder", "Input path does not exist.")
            return
        output_folder = compute_output_folder(path, [])
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(output_folder))

    def _update_drop_overlay_geometry(self) -> None:
        """Match the size of the drag-and-drop overlay to its parent widget."""
        if self.drop_overlay:
            parent = self.drop_overlay.parentWidget()
            if parent:
                self.drop_overlay.setGeometry(parent.rect())

    def _set_drop_overlay_visible(self, visible: bool) -> None:
        """Toggle visual visibility of the drag-and-drop landing helper.

        Args:
            visible: Whether the overlay should be shown.
        """
        if visible and self._ui_state.is_running:
            visible = False
        if self.drop_overlay:
            if visible:
                self._update_drop_overlay_geometry()
                self.drop_overlay.raise_()
            self.drop_overlay.setVisible(visible)

    def _set_path_from_drop(self, urls: list[QtCore.QUrl]) -> None:
        """Receive dropped URLs, classify paths, and populate the input field.

        Args:
            urls: List of QUrl objects dropped on the UI.
        """
        if self._ui_state.is_running:
            return
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
                f"Multiple folders detected. Using files from: {first_dir}",
            )
        self._set_selected_files(sorted(same_dir))
        self._set_path_text(first_dir, analyze=True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """Filter and accept drag event if content matches files or folders.

        Args:
            event: The QDragEnterEvent object.
        """
        if not self._ui_state.is_running and event.mimeData().hasUrls():
            self._set_drop_overlay_visible(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        """Accept drag move event to maintain drop overlay state.

        Args:
            event: The QDragMoveEvent object.
        """
        if not self._ui_state.is_running and event.mimeData().hasUrls():
            self._set_drop_overlay_visible(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent) -> None:
        """Hide the drop overlay when the drag cursor leaves window area.

        Args:
            event: The QDragLeaveEvent object.
        """
        self._set_drop_overlay_visible(False)
        event.accept()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Retrieve URLs from the drop payload and parse them into the input state.

        Args:
            event: The QDropEvent object.
        """
        if self._ui_state.is_running:
            self._set_drop_overlay_visible(False)
            event.ignore()
            return
        self._set_path_from_drop(event.mimeData().urls())
        self._set_drop_overlay_visible(False)
        event.acceptProposedAction()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Handle resize and drag action monitoring on central container widgets.

        Args:
            obj: The monitored object.
            event: The event payload.

        Returns:
            bool: True if event was captured and consumed, False to propagate.
        """
        if obj in (self.centralWidget(), self.drop_overlay):
            if self._ui_state.is_running and event.type() in (
                QtCore.QEvent.DragEnter,
                QtCore.QEvent.DragMove,
                QtCore.QEvent.Drop,
            ):
                self._set_drop_overlay_visible(False)
                event.ignore()
                return True
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
        return super().eventFilter(obj, event)

    def _restore_splitter_state(self) -> None:
        """Restore splitter layout dimensions from persistent settings storage."""
        if not self.main_splitter:
            return
        state = self._settings.value("ui/main_splitter_state")
        if state:
            self.main_splitter.restoreState(state)

    def _save_splitter_state(self) -> None:
        """Persist the splitter layout dimensions to settings storage."""
        if not self.main_splitter:
            return
        self._settings.setValue("ui/main_splitter_state", self.main_splitter.saveState())

    def _load_recent_paths(self) -> None:
        """Load the list of recently loaded paths from QSettings."""
        self._recent_paths = load_recent_paths(self._settings)
        self._refresh_recent_paths()

    def _save_recent_paths(self) -> None:
        """Save the list of recently loaded paths to QSettings."""
        save_recent_paths(self._settings, self._recent_paths)

    # --- Input/path state ---
    def _refresh_recent_paths(self) -> None:
        """Populate the path combo box dropdown selection with history items."""
        current = self.path_edit.currentText()
        self.path_edit.blockSignals(True)
        self.path_edit.clear()
        for path in self._recent_paths:
            self.path_edit.addItem(path)
        self.path_edit.blockSignals(False)
        self._set_path_text(current)

    def _set_input_path_state(self, path: str) -> None:
        """Update the internal input state value and update summary fields.

        Args:
            path: The source path string value.
        """
        self._input_state.path = (path or "").strip()
        self._update_output_label()
        self._update_summary_strip()

    def _set_path_text(
        self, path: str, analyze: bool = False, clear_selected: bool = False
    ) -> None:
        """Set path edit text and optionally trigger asynchronous analysis.

        Args:
            path: The path string.
            analyze: Whether to run an AOV scan.
            clear_selected: Whether to empty individual file selections.
        """
        if clear_selected:
            self._clear_selected_files()
        self.path_edit.blockSignals(True)
        self.path_edit.setCurrentText(path)
        self.path_edit.blockSignals(False)
        self._set_input_path_state(path)
        if analyze:
            self._analyze_input(force=True)

    def _on_scan_requested(self, _checked: bool = False) -> None:
        """Force trigger a re-analysis scan of the effective input path.

        Args:
            _checked: The checked state if triggered from action button.
        """
        if self._ui_state.is_running:
            return
        self._analyze_input(force=True)

    def _on_path_text_changed(self, text: str) -> None:
        """Respond to changes in input text by triggering a deferred path scan.

        Args:
            text: The new input path string.
        """
        self._set_input_path_state(text)
        path = (text or "").strip()
        if path and os.path.isdir(path):
            self._path_analysis_timer.start()
        else:
            self._path_analysis_timer.stop()

    def _current_input_path(self) -> str:
        """Get the current string text of the input path field.

        Returns:
            str: The current text value.
        """
        return self._input_state.path.strip()

    def _effective_input_path(self) -> str:
        """Get the absolute folder or selected file path to run commands against.

        Returns:
            str: The path to denoise.
        """
        path = self._current_input_path()
        if self._input_state.selected_files:
            return self._input_state.selected_root or path
        return path

    def _remember_path(self, path: str) -> None:
        """Add path to history and save persistent settings.

        Args:
            path: The directory path to add.
        """
        self._recent_paths = remember_path(self._recent_paths, path, max_items=10)
        self._save_recent_paths()
        self._refresh_recent_paths()

    def _set_selected_files(self, files: list[str]) -> None:
        """Populate individual files panel and update file list selection.

        Args:
            files: List of selected file path strings.
        """
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
            self.files_label.setText(f"Selected file: {os.path.basename(selected_files[0])}")
            self.files_list.setVisible(False)
            self.files_remove_btn.setVisible(False)
        else:
            for f in selected_files:
                item = QtWidgets.QListWidgetItem(os.path.basename(f))
                item.setToolTip(f)
                self.files_list.addItem(item)
            self.files_label.setText(f"Selected files ({len(selected_files)})")
            self.files_list.setVisible(True)
            self.files_remove_btn.setVisible(True)

        self.files_panel.setVisible(True)
        self.files_clear_btn.setVisible(True)
        self._update_output_label()
        self._update_summary_strip()

    def _clear_selected_files(self) -> None:
        """Clear all files from manual selection with user confirmation."""
        selected_count = len(self._input_state.selected_files)
        if selected_count > 3 and self.sender() is self.files_clear_btn:
            response = QtWidgets.QMessageBox.question(
                self,
                "Clear Selected Files",
                f"Clear {selected_count} selected files?",
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

    def _remove_selected_files(self) -> None:
        """Remove specific selected file rows from the file list widget."""
        selected_rows = {item.row() for item in self.files_list.selectedIndexes()}
        if not selected_rows:
            return
        remaining = [
            f for i, f in enumerate(self._input_state.selected_files) if i not in selected_rows
        ]
        self._set_selected_files(remaining)

    def _on_path_selected(self, index: int) -> None:
        """Respond to history item selection in combo box.

        Args:
            index: The chosen combo box index.
        """
        path = self.path_edit.itemText(index)
        if path:
            self._set_path_text(path, analyze=True, clear_selected=True)

    def _set_scan_busy(self, busy: bool) -> None:
        """Show or hide the scanning spinner and disable refresh triggers.

        Args:
            busy: Whether a scan is in progress.
        """
        self._ui_state.scan_busy = busy
        if self.scan_spinner:
            self.scan_spinner.setVisible(busy)
        if self.scan_btn:
            self._set_lockable_enabled(self.scan_btn, not busy)

    # --- AOV scan lifecycle ---
    def _on_aov_scan_started(self) -> None:
        """Handle the start of an AOV scan by setting busy state."""
        self._set_scan_busy(True)

    def _on_aov_analysis_timeout(self) -> None:
        """Handle scan timeouts by resetting state and clearing results."""
        self._set_scan_busy(False)
        self._log("AOV analysis timed out.", "warning")
        self._apply_planes([])

    def _on_aov_analysis_complete(self, result: dict) -> None:
        """Handle completed scans and apply detected channels to UI widgets.

        Args:
            result: Analysis result dictionary from the scan thread.
        """
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
            self._log("No valid AOVs found in EXR.", "warning")
            self._apply_planes([])
            return
        if status == "error":
            self._log("Failed to list AOVs: {}".format(result.get("error")), "error")
            self._apply_planes([])
            return

        if exr_file:
            self._log(f"Analyzing AOVs from: {os.path.basename(exr_file)}", "info")
        planes = result.get("planes") or []
        self._log(f"AOVs detected: {planes}", "info")
        self._apply_planes(planes)
        self._flash_summary_planes()

    def _aov_scan_key(self, path: str) -> tuple:
        """Construct cache signature for folder and selected file parameters.

        Args:
            path: The directory path.

        Returns:
            tuple: Cache signature containing path metadata.
        """

        def normalize(value: str) -> str:
            """Normalize a path for caching consistency.

            Args:
                value: A folder or file path string.

            Returns:
                str: Normalized path string.
            """
            return os.path.normcase(os.path.abspath(os.path.normpath(value)))

        return (
            normalize(path),
            tuple(normalize(f) for f in self._input_state.selected_files),
        )

    def _analyze_input(self, force=False):
        """Analyze input files to populate AOVs and configure settings."""
        path = self._effective_input_path()
        self._update_output_label()
        if not path or not os.path.exists(path):
            self._last_aov_scan_key = None
            self._aov_state.last_error = None
            if self._aov_scan:
                self._aov_scan.cancel()
            self._set_scan_busy(False)
            self._apply_planes([])
            self._update_summary_strip()
            return
        scan_key = self._aov_scan_key(path)
        if not force and scan_key == self._last_aov_scan_key:
            return
        self._remember_path(path)
        if self._aov_scan:
            self._last_aov_scan_key = scan_key
            self._aov_scan.start(path, self._input_state.selected_files)

    def _auto_select_preset(self, planes: list[str]) -> None:
        """Apply basic presets automatically based on detected channel names.

        Args:
            planes: List of available channel/AOV names.
        """
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

    def _apply_planes(self, planes: list[str]) -> None:
        """Configure available channel list dropdowns and target controls.

        Args:
            planes: List of available channel/AOV names.
        """
        if not planes:
            self._aov_state.planes = []
            self._update_planes_panel([])
            self._update_summary_strip()
            return

        self._aov_state.last_error = None
        available_planes = list(planes)
        self._aov_state.planes = available_planes
        self._update_planes_panel(available_planes)
        self._auto_select_preset(available_planes)

        self._suppress_custom_changes = True
        try:
            for combo in [
                self.beauty_combo,
                self.albedo_combo,
                self.normal_combo,
            ]:
                current = combo.currentText()
                combo.clear()
                combo.addItems([""] + available_planes)
                combo.setCurrentText(current)

            self.aovs_input.set_available_planes(available_planes)

            self._set_smart_selection(self.beauty_combo, self.BEAUTY_NAMES, available_planes)
            self._set_smart_selection(self.albedo_combo, self.ALBEDO_NAMES, available_planes)
            self._set_smart_selection(self.normal_combo, self.NORMAL_NAMES, available_planes)
        finally:
            self._suppress_custom_changes = False

        self._log("AOVs updated from analysis.", "success")

    def _update_planes_panel(self, planes: list[str]) -> None:
        """Populate detected AOV labels and layout chips.

        Args:
            planes: List of AOV channel names.
        """
        self._clear_planes_flow()
        for plane in planes:
            chip = QtWidgets.QLabel(plane)
            chip.setObjectName("aovPlaneChip")
            self.planes_flow_layout.addWidget(chip)
        timestamp = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.planes_toggle.setText(f"Detected AOVs ({len(planes)})")
        self.planes_toggle.setToolTip(tooltips.planes_toggle(len(planes), timestamp))
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

    def _toggle_planes_panel(self, checked: bool) -> None:
        """Toggle display layout showing detected AOV chips.

        Args:
            checked: True to show, False to hide.
        """
        self.planes_body.setVisible(checked)
        self.planes_toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        has_planes = bool(self._aov_state.planes)
        self.planes_body.setMaximumHeight(120 if checked and has_planes else 24)

    def _toggle_output_body(self, checked: bool) -> None:
        """Toggle visibility of destination setup controls.

        Args:
            checked: True to show, False to hide.
        """
        if not self.output_body or not self.output_section:
            return
        self.output_body.setVisible(checked)
        if self.output_toggle:
            self.output_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.output_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _toggle_denoise_body(self, checked: bool) -> None:
        """Toggle visibility of denoise setup controls.

        Args:
            checked: True to show, False to hide.
        """
        if not self.denoise_body or not self.denoise_section:
            return
        self.denoise_body.setVisible(checked)
        if self.denoise_toggle:
            self.denoise_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.denoise_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _toggle_advanced(self, checked: bool) -> None:
        """Toggle visibility of options settings panel.

        Args:
            checked: True to show, False to hide.
        """
        if not self.advanced_section or not self.advanced_body:
            return
        self.advanced_body.setVisible(checked)
        if self.advanced_toggle:
            self.advanced_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )
        self.advanced_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _toggle_advanced_settings(self, checked: bool) -> None:
        """Toggle visibility of runtime selection controls.

        Args:
            checked: True to show, False to hide.
        """
        if not self.advanced_settings_body:
            return
        self.advanced_settings_body.setVisible(checked)
        if self.advanced_settings_toggle:
            self.advanced_settings_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )

    def _toggle_aov_body(self, checked: bool) -> None:
        """Toggle visibility of AOV scan panel controls.

        Args:
            checked: True to show, False to hide.
        """
        if not self.aov_body or not self.aov_section:
            return
        self.aov_body.setVisible(checked)
        if self.aov_toggle:
            self.aov_toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        self.aov_section.setMaximumHeight(QWIDGETSIZE_MAX if checked else 48)

    def _clear_planes_flow(self) -> None:
        """Remove all AOV chip labels from layout widgets."""
        while self.planes_flow_layout.count():
            item = self.planes_flow_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _output_preview_path(self) -> str:
        """Obtain output path template for filename display.

        Returns:
            str: The output path template preview.
        """
        selected_root = self._input_state.selected_root
        return preview_output_path(self._current_input_path(), selected_root)

    def _update_output_label(self) -> None:
        """Refresh all destination path preview labels."""
        if not self.output_path_label:
            return
        preview = self._output_preview_path()
        text = tooltips.output_destination_label(preview)
        self.output_path_label.setText(text)
        self.output_path_label.setToolTip(text)
        if self.action_dest_label:
            action_text = tooltips.action_destination_label(preview)
            self.action_dest_label.setText(action_text)
            self.action_dest_label.setToolTip(action_text)
        self._update_summary_strip()

    def _update_summary_strip(self) -> None:
        """Evaluate values and adjust chip background status colors."""
        if not self.summary_files or not self.summary_planes or not self.summary_motion:
            return

        def _apply_chip_state(chip: QtWidgets.QLabel, object_name: str) -> None:
            """Update the stylesheet property class of a summary label chip.

            Args:
                chip: The label chip widget.
                object_name: Target style class name.
            """
            if chip.objectName() == object_name:
                return
            chip.setObjectName(object_name)
            chip_style = chip.style()
            chip_style.unpolish(chip)
            chip_style.polish(chip)

        selected_files = self._input_state.selected_files
        path = self._effective_input_path()
        if selected_files:
            files_text = f"Files: {len(selected_files)}"
        elif path and os.path.isfile(path):
            files_text = "Files: 1"
        elif path and os.path.isdir(path):
            files_text = "Files: folder"
        else:
            files_text = "Files: -"

        path_text = self._current_input_path()
        has_files = bool(selected_files) or bool(
            path and (os.path.isfile(path) or os.path.isdir(path))
        )
        path_invalid = bool(path_text) and not has_files
        planes_count = len(self._aov_state.planes)
        path_ready = has_files or bool(path_text and os.path.exists(path_text))

        self.summary_files.setText(files_text)
        self.summary_planes.setText(f"AOVs: {planes_count}")
        if self._backend_key() == "oidn":
            self.summary_motion.setText("Mode: OIDN")
        else:
            self.summary_motion.setText(f"Mode: OptiX {self.selected_optix_version}")

        if has_files:
            files_chip = "summaryChipOk"
        elif path_invalid:
            files_chip = "summaryChipBad"
        else:
            files_chip = "summaryChip"

        if self._aov_state.last_error:
            planes_chip = "summaryChipBad"
        elif planes_count >= 1:
            planes_chip = "summaryChipOk"
        elif path_ready:
            planes_chip = "summaryChipWarn"
        else:
            planes_chip = "summaryChip"

        _apply_chip_state(self.summary_files, files_chip)
        _apply_chip_state(self.summary_planes, planes_chip)
        _apply_chip_state(self.summary_motion, "summaryChipOk")

    def _flash_summary_planes(self) -> None:
        """Briefly change colors of AOV summary chip to highlight refresh."""
        if not self.summary_planes:
            return
        if not self._summary_planes_flash_timer.isActive():
            self._summary_planes_flash_original_style = self.summary_planes.styleSheet()
        self.summary_planes.setStyleSheet("QLabel { background-color: #3a5f8a; }")
        self._summary_planes_flash_timer.start(400)

    def _clear_summary_planes_flash(self) -> None:
        """Restore original stylesheet of AOV summary chip."""
        if not self.summary_planes:
            return
        self.summary_planes.setStyleSheet(self._summary_planes_flash_original_style or "")
        self._summary_planes_flash_original_style = None
        chip_style = self.summary_planes.style()
        chip_style.unpolish(self.summary_planes)
        chip_style.polish(self.summary_planes)

    def _set_planes_preview(self, planes: list[str]) -> None:
        """Set text preview containing names of detected AOVs.

        Args:
            planes: List of channel name strings.
        """
        if not planes:
            self.planes_preview.setText("")
            return
        preview = ", ".join(planes[:4])
        if len(planes) > 4:
            preview += ", ..."
        self.planes_preview.setText(preview)

    def _set_smart_selection(
        self, combo: QtWidgets.QComboBox, candidates: set[str], available_planes: list[str]
    ) -> bool:
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

    def _set_preset_text(self, preset_name: str) -> None:
        """Set preset combo text while blocking recursive signal fires.

        Args:
            preset_name: Preset value string.
        """
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(preset_name)
        self.preset_combo.blockSignals(False)

    @staticmethod
    def _backend_display(backend_key: str) -> str:
        """Convert backend identifier strings to clean titles.

        Args:
            backend_key: Backend key (optix or oidn).

        Returns:
            str: Human-readable backend name.
        """
        key = (backend_key or "").strip().lower()
        if key == "oidn":
            return "OIDN"
        if key == "optix":
            return "OptiX"
        return backend_key

    def _backend_key(self) -> str:
        """Get normalized lowercase backend selection.

        Returns:
            str: Active backend identifier.
        """
        if self.backend_combo:
            data = self.backend_combo.currentData()
            if data:
                return str(data).strip().lower()
        return self.selected_backend or "optix"

    def _apply_preset(self, preset_name: str) -> None:
        """Configure UI settings and combo defaults configured by preset.

        Args:
            preset_name: Preset name value.
        """
        if preset_name not in PRESETS:
            return
        preset = PRESETS[preset_name]
        self._suppress_custom_changes = True
        try:
            self._apply_preset_plane(self.beauty_combo, preset.get("beauty", "C"))
            self._apply_preset_plane(self.normal_combo, preset.get("normal", "N"))
            self._apply_preset_plane(self.albedo_combo, preset.get("albedo", "albedo"))
        finally:
            self._suppress_custom_changes = False

    def _apply_preset_plane(self, combo: QtWidgets.QComboBox, preset_value: str | None) -> None:
        """Auto-select the best matching channel suffix in target combo box.

        Args:
            combo: Combo box widget.
            preset_value: Expected channel suffix.
        """
        if not preset_value:
            combo.setCurrentText("")
            return
        available_planes = self._aov_state.planes
        if not available_planes:
            combo.setCurrentText(str(preset_value))
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

    def _mark_custom(self) -> None:
        """De-activate preset flags and mark active configuration as Custom."""
        if self._suppress_custom_changes:
            return
        self._auto_preset_enabled = False
        if self.preset_combo.currentText() != self._custom_preset:
            self._set_preset_text(self._custom_preset)

    def _motion_vectors_available(self) -> bool:
        """Check if temporal inputs are present.

        Returns:
            bool: Always False.
        """
        return False

    def _update_temporal_state(self, desired_checked: bool | None = None) -> bool:
        """Evaluate temporal parameters and adjust configurations.

        Args:
            desired_checked: Optional override value.

        Returns:
            bool: Always False.
        """
        self._update_summary_strip()
        return False

    def _pick_custom_exe(self) -> None:
        """Open selection dialog for custom runtime binaries."""
        return

    def _on_backend_changed(self, backend: str) -> None:
        """Sync backend configs and paths when backend changes.

        Args:
            backend: Selected backend identifier.
        """
        self.selected_backend = self._backend_key()
        self.bundled_denoiser_path = self._resolve_selected_denoiser_path()
        self._sync_backend_controls()
        self._update_temporal_state()

    def _on_motion_changed(self, _: str) -> None:
        """Update configs when temporal checkbox selection changes.

        Args:
            _: Checkbox state value.
        """
        self._update_temporal_state()
        self._mark_custom()

    def _on_preset_changed(self, preset_name: str) -> None:
        """Switch preset profiles and update channel combobox options.

        Args:
            preset_name: Selected preset option name.
        """
        if preset_name == self._custom_preset:
            self._auto_preset_enabled = False
            return
        if preset_name not in PRESETS:
            return
        self._auto_preset_enabled = False
        self._apply_preset(preset_name)

    def _on_control(self) -> None:
        """Respond to Primary Action Button execution clicks (Start/Stop)."""
        if self._ui_state.is_running:
            self._stop_denoise()
        else:
            self._start_denoise()

    def _on_options_edit_finished(self) -> None:
        """Validate manual configuration JSON modifications."""
        self._validate_options_json(show_message=False)

    def _validate_options_json(self, show_message: bool = False) -> bool:
        """Verify formatting of configuration inputs.

        Args:
            show_message: Whether to display warning dialogs.

        Returns:
            bool: Always True.
        """
        return True

    # --- Denoise workflow ---
    def _start_denoise(self) -> None:
        """Resolve execution details and spin up background worker thread."""
        input_path = self._effective_input_path()
        selected_files = self._input_state.selected_files
        if selected_files and not input_path:
            input_path = selected_files[0]
        if not input_path or not os.path.exists(input_path):
            QtWidgets.QMessageBox.warning(self, "Error", "Invalid input path")
            return

        self.selected_backend = self._backend_key()
        self.selected_optix_version = self._optix_version_key()
        if self.selected_backend == "oidn":
            denoiser_path = resolve_bundled_oidn_denoiser(required=False)
        else:
            denoiser_path = resolve_bundled_denoiser(
                required=False,
                optix_version=self.selected_optix_version,
            )
        if not denoiser_path:
            if self.selected_backend == "oidn":
                message = (
                    "Bundled OIDN Denoiser.exe was not found. Reinstall the bundled "
                    "runtime package."
                )
            else:
                message = (
                    f"Bundled OptiX Denoiser.exe was not found for OptiX "
                    f"{self.selected_optix_version}. "
                    "Reinstall the bundled runtime package."
                )
            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                message,
            )
            return

        self.bundled_denoiser_path = denoiser_path
        self._refresh_denoiser_status()
        self._denoise_state.backend = self.selected_backend
        self._denoise_state.denoiser_path = denoiser_path
        self._denoise_state.threads = 0
        self._denoise_state.overwrite = self.overwrite_chk.isChecked()
        self._denoise_state.prefix = self.prefix_edit.text()
        self._denoise_state.options_json = ""
        self._denoise_state.temporal = False

        # Collect settings
        denoise_config = DenoiseConfig(
            backend=self._denoise_state.backend,
            temporal=False,
            overwrite=self._denoise_state.overwrite,
            prefix=self._denoise_state.prefix,
        )

        aov_config = AOVConfig(
            beauty_plane=self.beauty_combo.currentText().strip() or "C",
            normal_plane=self.normal_combo.currentText().strip() or None,
            albedo_plane=self.albedo_combo.currentText().strip() or None,
            aovs_to_denoise=self.aovs_input.selected_chips() or None,
        )

        # Start worker
        self.worker = DenoiseWorker(
            input_path,
            denoise_config,
            aov_config,
            denoiser_path,
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
        self.control_btn.setToolTip(tooltips.CONTROL_BTN_STOP)
        button_style = self.control_btn.style()
        button_style.unpolish(self.control_btn)
        button_style.polish(self.control_btn)
        self.log_table.setRowCount(0)
        self.log_records = []
        self._visible_log_records = []

        self.progress.setValue(0)
        self._run_start = time.time()
        self.progress_label.setText("File 0 of 0 | ETA --:--")

        self._apply_ui_lock(True)
        self.worker.start()

    def _stop_denoise(self) -> None:
        """Signal background execution thread to abort execution."""
        if self.worker:
            self.worker.request_stop()
            self._log("Stopping...", "warning")

    def _on_progress(self, current: int, total: int) -> None:
        """Update progress indicators with current worker stats.

        Args:
            current: Current file index.
            total: Total files count.
        """
        self._ui_state.progress_current = current
        self._ui_state.progress_total = total
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self._update_progress_label(current, total)

    def _on_finished(self, summary: dict) -> None:
        """Handle completion of the background processing thread.

        Args:
            summary: Metrics dictionary with processing results.
        """
        self._ui_state.is_running = False
        self._apply_ui_lock(False)
        self.control_btn.setText("Denoise")
        self.control_btn.setIcon(self.play_icon)
        self.control_btn.setObjectName("primaryBtn")
        self.control_btn.setToolTip(tooltips.CONTROL_BTN_START)
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
            self.progress_label.setText(f"Completed in {self._format_eta(elapsed)}")
        self._run_start = None

    def _update_progress_label(self, current: int, total: int) -> None:
        """Compute ETA values and update progress display text.

        Args:
            current: Processed file index.
            total: Total files count.
        """
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
        self.progress_label.setText(f"File {current}/{total} | ETA {eta_text}")

    @staticmethod
    def _format_eta(seconds: float) -> str:
        """Convert integer duration in seconds to descriptive timestamp.

        Args:
            seconds: Duration in seconds.

        Returns:
            str: Descriptive timestamp representation.
        """
        secs = max(0, int(seconds + 0.5))
        mins, sec = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours:d}:{mins:02d}:{sec:02d}"
        return f"{mins:02d}:{sec:02d}"

    def _log_from_handler(self, msg: str, level_name: str) -> None:
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

    def _log(self, message: str, level: str = "info") -> None:
        """Log message through the logging pipeline for UI + console."""
        if level == "success":
            level = "info"
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        logger.log(level_map.get(level, logging.INFO), message, extra={"ui_level": level})

    def _log_level_icon(self, level: str) -> QtGui.QIcon | None:
        """Resolve system icons matching specific message severities.

        Args:
            level: Severity value string.

        Returns:
            Optional[QtGui.QIcon]: Status icon object, or None.
        """
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

    def _log_filter_allows(self, level: str) -> bool:
        """Filter logs based on severity levels.

        Args:
            level: Severity value string.

        Returns:
            bool: True if allowed to be logged.
        """
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

    def _refresh_log_view(self) -> None:
        """Rebuild log console table content using active level filters."""
        self.log_table.setRowCount(0)
        self._visible_log_records = []
        for record in self.log_records:
            if self._log_filter_allows(record["level"]):
                self._visible_log_records.append(record)
                self._add_log_item(record, scroll=False)
        self.log_table.scrollToBottom()

    def _append_log(self, message: str, level: str = "info") -> None:
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

    def _add_log_item(self, record: dict, scroll: bool) -> None:
        """Add a single log record row to the table layout.

        Args:
            record: Log record dictionary.
            scroll: True to scroll to bottom.
        """
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

    def _show_log_context_menu(self, pos: QtCore.QPoint) -> None:
        """Render the context menu for copying logs.

        Args:
            pos: Trigger mouse coordinate point.
        """
        selected_rows = self.log_table.selectionModel().selectedRows()
        selected_row = selected_rows[0].row() if selected_rows else -1
        message_item = self.log_table.item(selected_row, 1) if selected_row >= 0 else None

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
                rows.append(f"{timestamp}\t{message}")
            clipboard.setText("\n".join(rows))

    def _get_exrmode(self) -> int | None:
        """Read target EXR output specifications.

        Returns:
            Optional[int]: Always None.
        """
        return None

    @staticmethod
    def _parse_space_list(text: str) -> list[str] | None:
        """Tokenize a string by comma or white space.

        Args:
            text: Raw text to split.

        Returns:
            Optional[List[str]]: List of tokens, or None.
        """
        if not text or not text.strip():
            return None
        parts = re.split(r"[,\s]+", text.strip())
        return [p for p in parts if p] or None


def show() -> BaseWindow:
    """Show the denoiser window."""
    window = BaseWindow()
    window.show()
    return window


if __name__ == "__main__":
    show()
