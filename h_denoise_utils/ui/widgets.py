"""Custom Qt widgets."""

# typing helpers (used only in type comments)

from .qt_compat import QtCore, QtGui, QtWidgets, Signal


class NoWheelComboBox(QtWidgets.QComboBox):
    """ComboBox that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs):
        super(NoWheelComboBox, self).__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        super(NoWheelComboBox, self).wheelEvent(event)


class NoWheelSpinBox(QtWidgets.QSpinBox):
    """SpinBox that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs):
        super(NoWheelSpinBox, self).__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        super(NoWheelSpinBox, self).wheelEvent(event)


class FlowLayout(QtWidgets.QLayout):
    """Simple flow layout that wraps items."""

    def __init__(self, parent=None, margin=0, spacing=-1):
        # type: (Optional[QtWidgets.QWidget], int, int) -> None
        super(FlowLayout, self).__init__(parent)
        self._item_list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        # type: (QtWidgets.QLayoutItem) -> None
        self._item_list.append(item)

    def count(self):
        # type: () -> int
        return len(self._item_list)

    def itemAt(self, index):
        # type: (int) -> Optional[QtWidgets.QLayoutItem]
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        # type: (int) -> Optional[QtWidgets.QLayoutItem]
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        # type: () -> QtCore.Qt.Orientations
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self):
        # type: () -> bool
        return True

    def heightForWidth(self, width):
        # type: (int) -> int
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        # type: (QtCore.QRect) -> None
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        # type: () -> QtCore.QSize
        return self.minimumSize()

    def minimumSize(self):
        # type: () -> QtCore.QSize
        size = QtCore.QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
        return size

    def _do_layout(self, rect, test_only):
        # type: (QtCore.QRect, bool) -> int
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._item_list:
            widget = item.widget()
            space_x = self.spacing()
            space_y = self.spacing()

            if widget is not None:
                if space_x < 0:
                    space_x = widget.style().layoutSpacing(
                        QtWidgets.QSizePolicy.PushButton,
                        QtWidgets.QSizePolicy.PushButton,
                        QtCore.Qt.Horizontal,
                    )
                if space_y < 0:
                    space_y = widget.style().layoutSpacing(
                        QtWidgets.QSizePolicy.PushButton,
                        QtWidgets.QSizePolicy.PushButton,
                        QtCore.Qt.Vertical,
                    )

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class CheckableComboBox(NoWheelComboBox):
    """A combobox with checkable items."""

    def __init__(self, parent=None):
        # type: (QtWidgets.QWidget) -> None
        super(CheckableComboBox, self).__init__(parent)
        self.view().pressed.connect(self.handle_item_pressed)
        self.setModel(QtGui.QStandardItemModel(self))

    def handle_item_pressed(self, index):
        # type: (QtCore.QModelIndex) -> None
        """Toggle the check state of an item when pressed."""
        try:
            item = self.model().itemFromIndex(index)
            item.setCheckState(
                QtCore.Qt.Unchecked
                if item.checkState() == QtCore.Qt.Checked
                else QtCore.Qt.Checked
            )
        except Exception:
            pass


class Chip(QtWidgets.QFrame):
    """Simple removable chip widget."""

    removed = Signal(str)

    def __init__(self, text, parent=None):
        # type: (str, Optional[QtWidgets.QWidget]) -> None
        super(Chip, self).__init__(parent)
        self._text = text
        self.setObjectName("chip")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        label = QtWidgets.QLabel(text)
        close_btn = QtWidgets.QToolButton()
        close_btn.setText("x")
        close_btn.clicked.connect(self._on_remove)
        close_btn.setAutoRaise(True)

        layout.addWidget(label)
        layout.addWidget(close_btn)

    def _on_remove(self):
        # type: () -> None
        self.removed.emit(self._text)


class ChipListWidget(QtWidgets.QScrollArea):
    """Scrollable list of removable chips."""

    chip_removed = Signal(str)

    def __init__(self, parent=None):
        # type: (Optional[QtWidgets.QWidget]) -> None
        super(ChipListWidget, self).__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        self._chips = []  # type: List[str]
        self._chip_map = {}  # type: Dict[str, str]
        self._chip_widgets = {}  # type: Dict[str, Chip]
        self._available = None  # type: Optional[Set[str]]

        self._container = QtWidgets.QWidget()
        self._layout = FlowLayout(self._container, margin=4, spacing=6)

        self.setWidget(self._container)

    def set_available(self, planes):
        # type: (Optional[List[str]]) -> None
        if planes is None:
            self._available = None
        else:
            self._available = {p.lower() for p in planes if p}

    def chips(self):
        # type: () -> List[str]
        return [self._chip_map[key] for key in self._chips]

    def clear_chips(self):
        # type: () -> None
        for key in list(self._chip_widgets.keys()):
            self._remove_chip_by_key(key, emit=False)

    def add_chip(self, text):
        # type: (str) -> None
        if not text:
            return
        value = str(text).strip()
        if not value:
            return
        key = value.lower()
        if self._available is not None and key not in self._available:
            return
        if key in self._chip_map:
            return

        chip = Chip(value, self._container)
        chip.removed.connect(self._on_chip_removed)
        self._layout.addWidget(chip)

        self._chip_map[key] = value
        self._chip_widgets[key] = chip
        self._chips.append(key)

    def remove_chip(self, text):
        # type: (str) -> None
        if not text:
            return
        key = str(text).strip().lower()
        self._remove_chip_by_key(key, emit=True)

    def prune_unavailable(self):
        # type: () -> None
        if self._available is None:
            return
        for key in list(self._chip_map.keys()):
            if key not in self._available:
                self._remove_chip_by_key(key, emit=False)

    def _on_chip_removed(self, text):
        # type: (str) -> None
        self.remove_chip(text)

    def _remove_chip_by_key(self, key, emit):
        # type: (str, bool) -> None
        if key not in self._chip_widgets:
            return
        widget = self._chip_widgets.pop(key)
        self._chip_map.pop(key, None)
        if key in self._chips:
            self._chips.remove(key)
        widget.setParent(None)
        widget.deleteLater()
        if emit:
            self.chip_removed.emit(key)


class AovChipsInput(QtWidgets.QWidget):
    """AOV picker with checkable chips for selected planes."""

    def __init__(self, parent=None):
        # type: (Optional[QtWidgets.QWidget]) -> None
        super(AovChipsInput, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._container = QtWidgets.QWidget()
        self._container.setObjectName("aovChipContainer")
        self._flow = FlowLayout(self._container, margin=0, spacing=6)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setWidget(self._container)
        self.scroll.setMaximumHeight(80)
        self.scroll.setMinimumHeight(32)

        self.custom_input = QtWidgets.QLineEdit()
        self.custom_input.setPlaceholderText("Add custom AOV (comma separated)")

        layout.addWidget(self.scroll)
        layout.addWidget(self.custom_input)

        self._buttons = []  # type: List[QtWidgets.QPushButton]
        self._available_planes = []

    def set_available_planes(self, planes):
        # type: (List[str]) -> None
        # Preserve currently checked planes
        checked = set(self.selected_chips())
        self._available_planes = planes[:]

        # Clear existing buttons
        while self._flow.count():
            item = self._flow.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._buttons = []

        if not planes:
            label = QtWidgets.QLabel("No AOVs detected.")
            label.setObjectName("aovChipEmptyHint")
            self._flow.addWidget(label)
            return

        for p in planes:
            btn = QtWidgets.QPushButton(p)
            btn.setObjectName("aovChipBtn")
            btn.setCheckable(True)
            if p in checked:
                btn.setChecked(True)
            self._flow.addWidget(btn)
            self._buttons.append(btn)

    def set_chips(self, planes):
        # type: (List[str]) -> None
        # This acts as setting the strictly selected ones from an external preset
        selected_set = set(planes)
        for btn in self._buttons:
            btn.setChecked(btn.text() in selected_set)

    def selected_chips(self):
        # type: () -> List[str]
        selected = [btn.text() for btn in self._buttons if btn.isChecked()]
        custom_text = self.custom_input.text().strip()
        if custom_text:
            selected.extend([x.strip() for x in custom_text.split(",") if x.strip()])
        return selected

    def clear(self):
        # type: () -> None
        for btn in self._buttons:
            btn.setChecked(False)
        self.custom_input.clear()
