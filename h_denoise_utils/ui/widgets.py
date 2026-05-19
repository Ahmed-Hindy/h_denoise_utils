"""Custom Qt widgets."""

from __future__ import annotations

from .qt_compat import QtCore, QtGui, QtWidgets, Signal


class NoWheelComboBox(QtWidgets.QComboBox):
    """ComboBox that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs):
        """Initialize the combobox.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def wheelEvent(self, event):
        """Ignore wheel events unless the widget has keyboard focus.

        Args:
            event: The QWheelEvent.
        """
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class NoWheelSpinBox(QtWidgets.QSpinBox):
    """SpinBox that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs):
        """Initialize the spinbox.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def wheelEvent(self, event):
        """Ignore wheel events unless the widget has keyboard focus.

        Args:
            event: The QWheelEvent.
        """
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FlowLayout(QtWidgets.QLayout):
    """Simple flow layout that wraps items."""

    def __init__(
        self, parent: QtWidgets.QWidget | None = None, margin: int = 0, spacing: int = -1
    ) -> None:
        """Initialize the flow layout.

        Args:
            parent: Optional parent QWidget.
            margin: Outer margin size.
            spacing: Layout spacing between elements.
        """
        super().__init__(parent)
        self._item_list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        """Add a layout item to the flow list.

        Args:
            item: The QLayoutItem to add.
        """
        self._item_list.append(item)

    def count(self) -> int:
        """Retrieve the number of items in the layout.

        Returns:
            int: The count of layout items.
        """
        return len(self._item_list)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        """Get the layout item at the specified index.

        Args:
            index: The index of the item.

        Returns:
            Optional[QLayoutItem]: The layout item, or None if index is out of bounds.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        """Remove and return the layout item at the specified index.

        Args:
            index: The index of the item to remove.

        Returns:
            Optional[QLayoutItem]: The removed item, or None if index is out of bounds.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> QtCore.Qt.Orientations:
        """Get the expanding directions of the layout.

        Returns:
            Orientations: Empty orientations (0) since flow layout wraps instead.
        """
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        """Determine if height depends on width.

        Returns:
            bool: True, as height increases when items wrap.
        """
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate the height for the given layout width.

        Args:
            width: The constraint width.

        Returns:
            int: The required height.
        """
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        """Arrange elements inside the layout rectangle.

        Args:
            rect: The bounding rectangle geometry.
        """
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        """Get the size hint for the layout.

        Returns:
            QSize: Minimum size required by the layout.
        """
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        """Calculate the minimum bounding size of the layout.

        Returns:
            QSize: Bounding size of all elements.
        """
        size = QtCore.QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        """Calculate wrapping layout positions or perform the actual layout.

        Args:
            rect: The bounding rectangle.
            test_only: If True, only calculate height without moving widgets.

        Returns:
            int: Total height of the flow layout.
        """
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

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        """Initialize the checkable combobox.

        Args:
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
        self.view().pressed.connect(self.handle_item_pressed)
        self.setModel(QtGui.QStandardItemModel(self))

    def handle_item_pressed(self, index: QtCore.QModelIndex) -> None:
        """Toggle the check state of an item when pressed.

        Args:
            index: The index of the clicked item.
        """
        try:
            item = self.model().itemFromIndex(index)
            item.setCheckState(
                QtCore.Qt.Unchecked if item.checkState() == QtCore.Qt.Checked else QtCore.Qt.Checked
            )
        except Exception:
            pass


class Chip(QtWidgets.QFrame):
    """Simple removable chip widget."""

    removed = Signal(str)

    def __init__(self, text: str, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the chip widget.

        Args:
            text: Display text for the chip.
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
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

    def _on_remove(self) -> None:
        """Emit the removed signal containing the chip's text."""
        self.removed.emit(self._text)


class ChipListWidget(QtWidgets.QScrollArea):
    """Scrollable list of removable chips."""

    chip_removed = Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the chip list container.

        Args:
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        self._chips: list[str] = []
        self._chip_map: dict[str, str] = {}
        self._chip_widgets: dict[str, Chip] = {}
        self._available: set[str] | None = None

        self._container = QtWidgets.QWidget()
        self._layout = FlowLayout(self._container, margin=4, spacing=6)

        self.setWidget(self._container)

    def set_available(self, planes: list[str] | None) -> None:
        """Configure the set of available/allowed plane names for the list.

        Args:
            planes: List of strings or None to disable restriction.
        """
        if planes is None:
            self._available = None
        else:
            self._available = {p.lower() for p in planes if p}

    def chips(self) -> list[str]:
        """Get list of active chip labels.

        Returns:
            List[str]: Display labels of the chips.
        """
        return [self._chip_map[key] for key in self._chips]

    def clear_chips(self) -> None:
        """Remove all chips from the list."""
        for key in list(self._chip_widgets.keys()):
            self._remove_chip_by_key(key, emit=False)

    def add_chip(self, text: str) -> None:
        """Create and add a new chip to the layout.

        Args:
            text: Label for the new chip.
        """
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

    def remove_chip(self, text: str) -> None:
        """Remove a chip matching the text identifier.

        Args:
            text: Chip label to remove.
        """
        if not text:
            return
        key = str(text).strip().lower()
        self._remove_chip_by_key(key, emit=True)

    def prune_unavailable(self) -> None:
        """Remove chips whose names are no longer in the set of available planes."""
        if self._available is None:
            return
        for key in list(self._chip_map.keys()):
            if key not in self._available:
                self._remove_chip_by_key(key, emit=False)

    def _on_chip_removed(self, text: str) -> None:
        """Callback triggered when a child Chip is closed.

        Args:
            text: Text label of the removed chip.
        """
        self.remove_chip(text)

    def _remove_chip_by_key(self, key: str, emit: bool) -> None:
        """Internal helper to remove chip by lowercase key and clean up.

        Args:
            key: Lowercase chip identifier.
            emit: Whether to emit the chip_removed signal.
        """
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

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the AOV chips selector widget.

        Args:
            parent: Optional parent QWidget.
        """
        super().__init__(parent)
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

        self._buttons: list[QtWidgets.QPushButton] = []
        self._available_planes = []

    def set_available_planes(self, planes: list[str]) -> None:
        """Set the selectable AOV planes in the flow layout.

        Args:
            planes: List of discovered plane name strings.
        """
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

    def set_chips(self, planes: list[str]) -> None:
        """Check buttons matching the provided plane names.

        Args:
            planes: List of plane names to check.
        """
        selected_set = set(planes)
        for btn in self._buttons:
            btn.setChecked(btn.text() in selected_set)

    def selected_chips(self) -> list[str]:
        """Get the names of all selected AOV planes (standard chips + custom input).

        Returns:
            List[str]: List of selected plane names.
        """
        selected = [btn.text() for btn in self._buttons if btn.isChecked()]
        custom_text = self.custom_input.text().strip()
        if custom_text:
            selected.extend([x.strip() for x in custom_text.split(",") if x.strip()])
        return selected

    def clear(self) -> None:
        """Clear all checked chips and custom input field."""
        for btn in self._buttons:
            btn.setChecked(False)
        self.custom_input.clear()
