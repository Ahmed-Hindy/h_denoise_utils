"""UI section builders for the denoiser window.

These helpers are intentionally plain builder functions instead of QWidget
subclasses. `BaseWindow` passes itself as the first argument so each builder can
create widgets, attach them to layouts, and store the resulting widget
references back onto the window instance (`window.path_edit`,
`window.backend_combo`, etc.). The builders therefore mutate an existing
`BaseWindow` rather than constructing a standalone section object.
"""

import multiprocessing

from ..core.config import PRESETS
from .qt_compat import QtCore, QtWidgets
from .widgets import (
    AovChipsInput,
    FlowLayout,
    NoWheelComboBox,
    NoWheelSpinBox,
)

QWIDGETSIZE_MAX = 16777215


def build_config_scroll(window, top_layout):
    # type: (object, QtWidgets.QVBoxLayout) -> QtWidgets.QVBoxLayout
    window.config_scroll = QtWidgets.QScrollArea()
    window.config_scroll.setObjectName("configScroll")
    window.config_scroll.setWidgetResizable(True)
    window.config_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    window.config_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
    window.config_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    window.config_scroll.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
    )
    window.config_scroll.viewport().setObjectName("configScrollViewport")

    window.config_scroll_body = QtWidgets.QWidget()
    window.config_scroll_body.setObjectName("configScrollBody")
    config_layout = QtWidgets.QVBoxLayout(window.config_scroll_body)
    config_layout.setContentsMargins(0, 0, 0, 0)
    config_layout.setSpacing(6)
    window.config_scroll.setWidget(window.config_scroll_body)
    top_layout.addWidget(window.config_scroll, 1)
    return config_layout


def build_source_section(window, top_layout):
    # type: (object, QtWidgets.QVBoxLayout) -> None
    window.input_section = QtWidgets.QFrame()
    window.input_section.setObjectName("sectionCard")
    window.input_section.setMaximumSize(960, 200)
    input_layout = QtWidgets.QVBoxLayout(window.input_section)
    input_layout.setContentsMargins(8, 4, 8, 4)
    input_layout.setSpacing(4)

    input_header_row = QtWidgets.QHBoxLayout()
    input_header_row.setSpacing(6)
    window._input_header_spacer = QtWidgets.QWidget()
    window._input_header_spacer.setFixedWidth(16)
    input_header_row.addWidget(window._input_header_spacer)
    input_header = QtWidgets.QLabel("Source")
    input_header.setObjectName("sectionTitle")
    input_header_row.addWidget(input_header)

    window.path_edit = NoWheelComboBox()
    window.path_edit.setEditable(True)
    window.path_edit.setInsertPolicy(NoWheelComboBox.NoInsert)
    window.path_edit.lineEdit().setPlaceholderText("Drop file or folder here")
    input_header_row.addWidget(window.path_edit, 1)

    window.browse_btn = QtWidgets.QToolButton()
    window.browse_btn.setIcon(
        window.app_style.standardIcon(QtWidgets.QStyle.SP_DirOpenIcon)
    )
    window.browse_btn.setToolTip("Browse for folder")
    window.browse_btn.setAutoRaise(True)
    window.browse_btn.setIconSize(QtCore.QSize(16, 16))
    window.browse_btn.setFixedSize(26, 26)
    input_header_row.addWidget(window.browse_btn)

    window.scan_btn = QtWidgets.QToolButton()
    window.scan_btn.setIcon(
        window.app_style.standardIcon(QtWidgets.QStyle.SP_BrowserReload)
    )
    window.scan_btn.setToolTip(
        "Scan input folder for AOVs and auto-configure (F5)"
    )
    window.scan_btn.setAutoRaise(True)
    window.scan_btn.setIconSize(QtCore.QSize(16, 16))
    window.scan_btn.setFixedSize(26, 26)
    input_header_row.addWidget(window.scan_btn)

    window.scan_spinner = QtWidgets.QProgressBar()
    window.scan_spinner.setTextVisible(False)
    window.scan_spinner.setFixedHeight(12)
    window.scan_spinner.setFixedWidth(60)
    window.scan_spinner.setRange(0, 0)
    window.scan_spinner.setVisible(False)
    input_header_row.addWidget(window.scan_spinner)
    input_header_row.addStretch(1)

    window.summary_files = QtWidgets.QLabel("Files: -")
    window.summary_files.setObjectName("summaryChip")
    window.summary_planes = QtWidgets.QLabel("AOVs: 0")
    window.summary_planes.setObjectName("summaryChip")
    window.summary_motion = QtWidgets.QLabel("Motion: -")
    window.summary_motion.setObjectName("summaryChip")
    input_header_row.addWidget(window.summary_files)
    input_header_row.addWidget(window.summary_planes)
    input_header_row.addWidget(window.summary_motion)

    input_layout.addLayout(input_header_row)

    window.input_body = QtWidgets.QWidget()
    input_body_layout = QtWidgets.QVBoxLayout(window.input_body)
    input_body_layout.setContentsMargins(0, 0, 0, 0)
    input_body_layout.setSpacing(6)

    window.files_panel = QtWidgets.QWidget()
    files_layout = QtWidgets.QVBoxLayout(window.files_panel)
    files_layout.setSpacing(4)
    files_layout.setContentsMargins(0, 0, 0, 0)
    files_header = QtWidgets.QHBoxLayout()
    window.files_label = QtWidgets.QLabel("Selected files (0)")
    window.files_remove_btn = QtWidgets.QToolButton()
    window.files_remove_btn.setText("Remove")
    window.files_remove_btn.setAutoRaise(True)
    window.files_clear_btn = QtWidgets.QToolButton()
    window.files_clear_btn.setText("Clear")
    window.files_clear_btn.setAutoRaise(True)
    files_header.addWidget(window.files_label)
    files_header.addStretch(1)
    files_header.addWidget(window.files_remove_btn)
    files_header.addWidget(window.files_clear_btn)
    window.files_list = QtWidgets.QListWidget()
    window.files_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    window.files_list.setUniformItemSizes(True)
    window.files_list.setMaximumHeight(96)
    window.files_list.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
    )
    files_layout.addLayout(files_header)
    files_layout.addWidget(window.files_list)
    window.files_panel.setVisible(False)
    input_body_layout.addWidget(window.files_panel)

    window.input_body.setVisible(True)
    input_layout.addWidget(window.input_body)
    window.input_section.setMaximumHeight(QWIDGETSIZE_MAX)

    top_layout.addWidget(window.input_section)


def build_destination_section(window, top_layout):
    # type: (object, QtWidgets.QVBoxLayout) -> None
    window.output_section = QtWidgets.QFrame()
    window.output_section.setObjectName("sectionCard")
    window.output_section.setMaximumSize(960, 200)
    output_layout = QtWidgets.QVBoxLayout(window.output_section)
    output_layout.setContentsMargins(8, 4, 8, 4)
    output_layout.setSpacing(4)

    output_header_row = QtWidgets.QHBoxLayout()
    output_header_row.setSpacing(6)
    window.output_toggle = QtWidgets.QToolButton()
    window.output_toggle.setArrowType(QtCore.Qt.RightArrow)
    window.output_toggle.setCheckable(True)
    window.output_toggle.setChecked(False)
    window.output_toggle.setAutoRaise(True)
    output_header_row.addWidget(window.output_toggle)
    if window._input_header_spacer:
        window._input_header_spacer.setFixedWidth(
            window.output_toggle.sizeHint().width()
        )
    output_header = QtWidgets.QLabel("Destination")
    output_header.setObjectName("sectionTitle")
    output_header_row.addWidget(output_header)
    output_header_row.addStretch(1)
    output_layout.addLayout(output_header_row)

    window.output_body = QtWidgets.QWidget()
    output_body_layout = QtWidgets.QVBoxLayout(window.output_body)
    output_body_layout.setContentsMargins(0, 0, 0, 0)
    output_body_layout.setSpacing(6)

    output_form = QtWidgets.QFormLayout()
    output_form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    output_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
    output_form.setContentsMargins(0, 0, 0, 0)
    output_form.setHorizontalSpacing(8)
    output_form.setVerticalSpacing(4)
    output_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

    window.preset_combo = NoWheelComboBox()
    window.preset_combo.addItems(list(PRESETS.keys()) + [window._custom_preset])
    output_form.addRow("Preset:", window.preset_combo)

    window.aovs_input = AovChipsInput()
    output_form.addRow("AOVs to denoise:", window.aovs_input)

    window.overwrite_chk = QtWidgets.QCheckBox()
    window.overwrite_chk.setText("")
    window.overwrite_chk.setToolTip("Overwrite existing outputs")
    window.overwrite_chk.setChecked(False)
    output_form.addRow("Replace Existing:", window.overwrite_chk)

    window.output_path_label = QtWidgets.QLabel("Destination: -")
    window.output_path_label.setObjectName("outputPathLabel")
    window.output_path_label.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
    )
    window.output_path_label.setToolTip("Destination folder")
    window.output_path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    output_form.addRow(window.output_path_label)

    output_body_layout.addLayout(output_form)
    window.output_body.setVisible(False)
    output_layout.addWidget(window.output_body)
    window.output_section.setMaximumHeight(48)

    top_layout.addWidget(window.output_section)


def build_extras_section(window, top_layout):
    # type: (object, QtWidgets.QVBoxLayout) -> None
    # Dummy out removed variables so main_window signals don't crash
    window.aov_section = None
    window.aov_body = None
    window.aov_toggle = None
    window.denoise_section = None
    window.denoise_body = None
    window.denoise_toggle = None

    # Keep dummy planes UI objects to avoid breaking main_window logic
    window.planes_toggle = QtWidgets.QToolButton()
    window.planes_preview = QtWidgets.QLabel()
    window.planes_body = QtWidgets.QScrollArea()
    window.planes_flow_container = QtWidgets.QWidget()
    window.planes_flow_layout = FlowLayout(window.planes_flow_container)
    window.planes_body.setWidget(window.planes_flow_container)
    window.planes_toggle.hide()
    window.planes_preview.hide()
    window.planes_body.hide()

    window.advanced_section = QtWidgets.QFrame()
    window.advanced_section.setObjectName("sectionCard")
    window.advanced_section.setMaximumSize(960, 200)
    advanced_layout = QtWidgets.QVBoxLayout(window.advanced_section)
    advanced_layout.setContentsMargins(8, 4, 8, 4)
    advanced_layout.setSpacing(4)

    advanced_header_row = QtWidgets.QHBoxLayout()
    window.advanced_toggle = QtWidgets.QToolButton()
    window.advanced_toggle.setArrowType(QtCore.Qt.RightArrow)
    window.advanced_toggle.setCheckable(True)
    window.advanced_toggle.setChecked(False)
    window.advanced_toggle.setAutoRaise(True)
    advanced_header_row.addWidget(window.advanced_toggle)
    advanced_title = QtWidgets.QLabel("Settings")
    advanced_title.setObjectName("sectionTitle")
    advanced_header_row.addWidget(advanced_title)
    advanced_header_row.addStretch(1)
    advanced_layout.addLayout(advanced_header_row)

    window.advanced_body = QtWidgets.QWidget()
    advanced_body_layout = QtWidgets.QVBoxLayout(window.advanced_body)
    advanced_body_layout.setContentsMargins(0, 8, 0, 0)
    advanced_body_layout.setSpacing(6)

    settings_form = QtWidgets.QFormLayout()
    settings_form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    settings_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
    settings_form.setContentsMargins(0, 0, 0, 0)
    settings_form.setHorizontalSpacing(8)
    settings_form.setVerticalSpacing(4)
    settings_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

    advanced_settings_form = QtWidgets.QFormLayout()
    advanced_settings_form.setLabelAlignment(
        QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
    )
    advanced_settings_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
    advanced_settings_form.setContentsMargins(0, 6, 0, 0)
    advanced_settings_form.setHorizontalSpacing(8)
    advanced_settings_form.setVerticalSpacing(4)
    advanced_settings_form.setFieldGrowthPolicy(
        QtWidgets.QFormLayout.ExpandingFieldsGrow
    )

    window.backend_combo = NoWheelComboBox()
    window.backend_combo.addItems(["Oidn", "Optix"])
    advanced_settings_form.addRow("Backend:", window.backend_combo)

    window.thread_spin = NoWheelSpinBox()
    window.thread_spin.setRange(1, 16)
    window.thread_spin.setValue(min(8, max(1, multiprocessing.cpu_count())))
    advanced_settings_form.addRow("CPU Threads:", window.thread_spin)

    window.albedo_combo = NoWheelComboBox()
    window.albedo_combo.setEditable(True)
    window.albedo_combo.lineEdit().setPlaceholderText("e.g. albedo")
    window.albedo_combo.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
    )

    window.normal_combo = NoWheelComboBox()
    window.normal_combo.setEditable(True)
    window.normal_combo.lineEdit().setPlaceholderText("e.g. N")
    window.normal_combo.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
    )

    window.motion_combo = NoWheelComboBox()
    window.motion_combo.setEditable(True)
    window.motion_combo.lineEdit().setPlaceholderText("e.g. velocity")
    window.motion_combo.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
    )

    window.temporal_chk = QtWidgets.QCheckBox()
    window.temporal_chk.setText("Use Temporal Denoise")
    window.temporal_chk.setToolTip("Requires Optix backend and motion vectors AOV")

    window.prefix_edit = QtWidgets.QLineEdit("den_")
    window.prefix_edit.setMaxLength(32)
    settings_form.addRow("Output Prefix:", window.prefix_edit)
    settings_form.addRow("Albedo (-a):", window.albedo_combo)
    settings_form.addRow("Normal (-n):", window.normal_combo)

    motion_row = QtWidgets.QWidget()
    motion_layout = QtWidgets.QHBoxLayout(motion_row)
    motion_layout.setContentsMargins(0, 0, 0, 0)
    motion_layout.setSpacing(8)
    motion_layout.addWidget(window.temporal_chk)
    window.motion_label = QtWidgets.QLabel("Motion (-m):")
    motion_layout.addWidget(window.motion_label)
    motion_layout.addWidget(window.motion_combo, 1)
    settings_form.addRow(motion_row)

    divider = QtWidgets.QFrame()
    divider.setFrameShape(QtWidgets.QFrame.HLine)
    divider.setFrameShadow(QtWidgets.QFrame.Sunken)
    advanced_settings_form.addRow(divider)

    window.denoiser_combo = NoWheelComboBox()
    for ver, exe in window.houdini_versions.items():
        window.denoiser_combo.addItem(ver, exe)
    if window.houdini_versions:
        window.denoiser_combo.setCurrentIndex(0)

    window.custom_exe_btn = QtWidgets.QPushButton("Custom EXE.")
    idenoise_row = QtWidgets.QWidget()
    idenoise_layout = QtWidgets.QHBoxLayout(idenoise_row)
    idenoise_layout.setContentsMargins(0, 0, 0, 0)
    idenoise_layout.addWidget(window.denoiser_combo, 1)
    idenoise_layout.addWidget(window.custom_exe_btn)
    advanced_settings_form.addRow("idenoise:", idenoise_row)

    window.exrmode_combo = NoWheelComboBox()
    window.exrmode_combo.addItems(["(default HOUDINI_OIIO_EXR)", "-1", "0", "1"])
    advanced_settings_form.addRow("EXR Read Mode:", window.exrmode_combo)

    window.options_edit = QtWidgets.QLineEdit()
    window.options_edit.setPlaceholderText(
        'e.g., {"blendfactor":0.25} or {"auxareclean":true}'
    )
    advanced_settings_form.addRow("Advanced Options (JSON):", window.options_edit)

    window.extra_aovs_edit = QtWidgets.QLineEdit()
    window.extra_aovs_edit.setPlaceholderText("reference AOVs (not denoised)")
    advanced_settings_form.addRow("Optional auxiliary AOVs:", window.extra_aovs_edit)

    advanced_body_layout.addLayout(settings_form)

    window.advanced_settings_section = QtWidgets.QFrame()
    window.advanced_settings_section.setObjectName("nestedSettingsCard")
    advanced_settings_layout = QtWidgets.QVBoxLayout(window.advanced_settings_section)
    advanced_settings_layout.setContentsMargins(0, 4, 0, 0)
    advanced_settings_layout.setSpacing(2)

    advanced_settings_header = QtWidgets.QHBoxLayout()
    window.advanced_settings_toggle = QtWidgets.QToolButton()
    window.advanced_settings_toggle.setArrowType(QtCore.Qt.RightArrow)
    window.advanced_settings_toggle.setCheckable(True)
    window.advanced_settings_toggle.setChecked(False)
    window.advanced_settings_toggle.setAutoRaise(True)
    advanced_settings_header.addWidget(window.advanced_settings_toggle)
    advanced_settings_title = QtWidgets.QLabel("Advanced Settings")
    advanced_settings_title.setObjectName("subsectionTitle")
    advanced_settings_header.addWidget(advanced_settings_title)
    advanced_settings_header.addStretch(1)
    advanced_settings_layout.addLayout(advanced_settings_header)

    window.advanced_settings_body = QtWidgets.QWidget()
    advanced_settings_body_layout = QtWidgets.QVBoxLayout(window.advanced_settings_body)
    advanced_settings_body_layout.setContentsMargins(20, 0, 0, 0)
    advanced_settings_body_layout.setSpacing(0)
    advanced_settings_body_layout.addLayout(advanced_settings_form)
    window.advanced_settings_body.setVisible(False)
    advanced_settings_layout.addWidget(window.advanced_settings_body)
    advanced_body_layout.addWidget(window.advanced_settings_section)

    window.advanced_body.setVisible(False)
    advanced_layout.addWidget(window.advanced_body)
    window.advanced_section.setMaximumHeight(48)

    window.adv_widget = window.advanced_body
    window.adv_scroll = None

    top_layout.addWidget(window.advanced_section)


def build_action_bar(window, top_layout):
    # type: (object, QtWidgets.QVBoxLayout) -> None
    action_bar = QtWidgets.QFrame()
    action_bar.setObjectName("actionBar")
    action_bar.setMaximumSize(960, 72)
    btnrow = QtWidgets.QHBoxLayout(action_bar)
    btnrow.setContentsMargins(8, 6, 8, 6)
    btnrow.setSpacing(8)
    window.control_btn = QtWidgets.QPushButton("Denoise")
    window.control_btn.setObjectName("primaryBtn")
    window.play_icon = window.app_style.standardIcon(QtWidgets.QStyle.SP_MediaPlay)
    window.stop_icon = window.app_style.standardIcon(QtWidgets.QStyle.SP_MediaStop)
    window.control_btn.setIcon(window.play_icon)
    btnrow.addWidget(window.control_btn)

    progress_column = QtWidgets.QVBoxLayout()
    progress_column.setContentsMargins(0, 0, 0, 0)
    progress_column.setSpacing(2)

    progress_row = QtWidgets.QHBoxLayout()
    progress_row.setContentsMargins(0, 0, 0, 0)
    progress_row.setSpacing(8)

    window.progress = QtWidgets.QProgressBar()
    window.progress.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
    )
    window.progress.setMinimumHeight(16)
    window.progress_label = QtWidgets.QLabel("File 0 of 0 | ETA --:--")
    window.progress_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    progress_row.addWidget(window.progress)
    progress_row.addWidget(window.progress_label)
    window.open_output_btn = QtWidgets.QToolButton()
    window.open_output_btn.setIcon(
        window.app_style.standardIcon(QtWidgets.QStyle.SP_DirIcon)
    )
    window.open_output_btn.setToolTip("Open destination folder")
    window.open_output_btn.setAutoRaise(True)
    window.open_output_btn.setIconSize(QtCore.QSize(16, 16))
    window.open_output_btn.setFixedSize(26, 26)
    progress_row.addWidget(window.open_output_btn)
    progress_column.addLayout(progress_row)

    window.action_dest_label = QtWidgets.QLabel("→ -")
    window.action_dest_label.setObjectName("outputPathLabel")
    progress_column.addWidget(window.action_dest_label)

    btnrow.addLayout(progress_column, 1)
    top_layout.addWidget(action_bar)


def build_logs_section(window, logs_layout):
    # type: (object, QtWidgets.QVBoxLayout) -> None
    logs_section = QtWidgets.QFrame()
    logs_section.setObjectName("sectionCard")
    logs_section.setMaximumSize(960, 260)
    logs_section_layout = QtWidgets.QVBoxLayout(logs_section)
    logs_section_layout.setContentsMargins(8, 6, 8, 8)
    logs_section_layout.setSpacing(6)
    logs_header = QtWidgets.QLabel("Logs")
    logs_header.setObjectName("sectionTitle")
    logs_section_layout.addWidget(logs_header)

    log_controls = QtWidgets.QHBoxLayout()
    log_controls.setContentsMargins(0, 0, 0, 0)
    log_controls.setSpacing(6)
    log_controls.addWidget(QtWidgets.QLabel("Log:"))
    window.log_filter_combo = NoWheelComboBox()
    window.log_filter_combo.addItems(["All", "Errors", "Warnings", "Info", "Debug"])
    log_controls.addWidget(window.log_filter_combo)
    log_controls.addStretch(1)
    logs_section_layout.addLayout(log_controls)

    window.log_table = QtWidgets.QTableWidget()
    window.log_table.setColumnCount(2)
    window.log_table.setHorizontalHeaderLabels(["Timestamp", "Message"])
    window.log_table.horizontalHeader().setStretchLastSection(True)
    window.log_table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)
    header = window.log_table.horizontalHeader()
    if hasattr(header, "setSectionResizeMode"):
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
    else:
        header.setResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
    window.log_table.verticalHeader().setVisible(False)
    window.log_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    window.log_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    window.log_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    window.log_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
    window.log_table.setShowGrid(False)
    window.log_table.setAlternatingRowColors(True)
    window.log_table.setMaximumHeight(220)
    log_font = window.log_table.font()
    log_font.setPointSize(max(8, log_font.pointSize() - 1))
    window.log_table.setFont(log_font)
    window.log_table.verticalHeader().setDefaultSectionSize(18)
    logs_section_layout.addWidget(window.log_table)
    window.log_table.installEventFilter(window)

    logs_layout.addWidget(logs_section)
