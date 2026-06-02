"""Custom logging handler integrated with the Qt event loop."""

from __future__ import annotations

import logging

from .qt_compat import QtCore, Signal


class _QtLogEmitter(QtCore.QObject):
    """Qt signal container to avoid name clashes with logging.Handler.emit."""

    new_record = Signal(str, str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        """Initialize the Qt log emitter.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)


class QtLogHandler(logging.Handler):
    """Logging handler that emits a signal for each log record."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        """Initialize the Qt log handler.

        Args:
            parent: Optional parent QObject for the internal emitter.
        """
        super().__init__()
        self._emitter: _QtLogEmitter | None = _QtLogEmitter(parent)

    @property
    def new_record(self) -> Signal:
        """Get the signal emitted when a new log record is handled.

        Returns:
            Signal: Qt signal emitting (formatted_message, levelname).
        """
        if self._emitter is None:
            raise RuntimeError("Qt log emitter has been closed")
        return self._emitter.new_record

    def emit(self, record: logging.LogRecord) -> None:
        """Format and emit a log record via the Qt emitter.

        Args:
            record: The logging record to process.
        """
        msg = self.format(record)
        ui_level = getattr(record, "ui_level", record.levelname.lower())
        if self._emitter is None:
            return
        try:
            self._emitter.new_record.emit(msg, ui_level)
        except RuntimeError as exc:
            if "deleted" not in str(exc).lower():
                raise
            self._emitter = None

    def close(self) -> None:
        """Detach from the Qt emitter when the logging handler is closed."""
        self._emitter = None
        super().close()
