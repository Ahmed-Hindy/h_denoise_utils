"""Qt compatibility layer for Houdini/PySide2, PySide6, PyQt6, and PyQt5."""

import importlib
import os
from typing import Optional

try:
    import hou  # type: ignore

    isUIAvailable = bool(hou.isUIAvailable())
except (ModuleNotFoundError, NameError):
    isUIAvailable = False

_BACKEND_ORDER = ("pyside6", "pyside2", "pyqt6", "pyqt5")
_BACKEND_MODULES = {
    "pyside6": "PySide6",
    "pyside2": "PySide2",
    "pyqt6": "PyQt6",
    "pyqt5": "PyQt5",
}

QT_BACKEND: Optional[str] = os.environ.get("QT_BACKEND", "").lower().strip() or None

if isUIAvailable:
    _backend = "pyside2"
elif QT_BACKEND:
    if QT_BACKEND not in _BACKEND_MODULES:
        raise ValueError(
            "Invalid QT_BACKEND: {}. Must be one of: pyside6, pyside2, pyqt6, pyqt5".format(
                QT_BACKEND
            )
        )
    _backend = QT_BACKEND
else:
    _backend = None
    for backend in _BACKEND_ORDER:
        try:
            importlib.import_module(_BACKEND_MODULES[backend])
        except ImportError:
            continue
        _backend = backend
        break

if _backend is None:
    raise ImportError(
        "No Qt backend found. Please install one of: PySide6, PySide2, PyQt6, or PyQt5"
    )

_module = _BACKEND_MODULES[_backend]
QtCore = importlib.import_module("{}.QtCore".format(_module))
QtGui = importlib.import_module("{}.QtGui".format(_module))
QtWidgets = importlib.import_module("{}.QtWidgets".format(_module))

if not hasattr(QtWidgets, "QAction") and hasattr(QtGui, "QAction"):
    QtWidgets.QAction = QtGui.QAction

Signal = QtCore.pyqtSignal if hasattr(QtCore, "pyqtSignal") else QtCore.Signal
Slot = QtCore.pyqtSlot if hasattr(QtCore, "pyqtSlot") else QtCore.Slot
QtAction = QtWidgets.QAction

QT_BACKEND_NAME = _backend


def get_qt_backend():
    # type: () -> str
    """Get the active Qt backend name."""
    return QT_BACKEND_NAME


__all__ = [
    "QtCore",
    "QtGui",
    "QtWidgets",
    "Signal",
    "Slot",
    "QtAction",
    "QT_BACKEND_NAME",
    "get_qt_backend",
    "isUIAvailable",
]
