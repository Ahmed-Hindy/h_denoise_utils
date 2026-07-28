"""Qt compatibility layer for PySide6 and PyQt6."""

import importlib
import os

try:
    import hou  # type: ignore

    isUIAvailable = bool(hou.isUIAvailable())
except (ModuleNotFoundError, NameError):
    isUIAvailable = False

_BACKEND_ORDER = ("pyside6", "pyqt6")
_BACKEND_MODULES = {
    "pyside6": "PySide6",
    "pyqt6": "PyQt6",
}

QT_BACKEND: str | None = os.environ.get("QT_BACKEND", "").lower().strip() or None

if isUIAvailable:
    _backend = "pyside6"
elif QT_BACKEND:
    if QT_BACKEND not in _BACKEND_MODULES:
        raise ValueError(f"Invalid QT_BACKEND: {QT_BACKEND}. Must be one of: pyside6, pyqt6")
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
    raise ImportError("No Qt backend found. Please install one of: PySide6 or PyQt6")

_module = _BACKEND_MODULES[_backend]
QtCore = importlib.import_module(f"{_module}.QtCore")
QtGui = importlib.import_module(f"{_module}.QtGui")
QtWidgets = importlib.import_module(f"{_module}.QtWidgets")

if not hasattr(QtWidgets, "QAction") and hasattr(QtGui, "QAction"):
    QtWidgets.QAction = QtGui.QAction

Signal = QtCore.pyqtSignal if hasattr(QtCore, "pyqtSignal") else QtCore.Signal
Slot = QtCore.pyqtSlot if hasattr(QtCore, "pyqtSlot") else QtCore.Slot
QtAction = QtWidgets.QAction

QT_BACKEND_NAME = _backend


def get_qt_backend() -> str:
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
