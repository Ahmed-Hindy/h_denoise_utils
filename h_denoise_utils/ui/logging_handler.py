"""Custom logging handler integrated with the Qt event loop."""

import logging

from .qt_compat import QtCore, Signal


class _QtLogEmitter(QtCore.QObject):
    """Qt signal container to avoid name clashes with logging.Handler.emit."""

    new_record = Signal(str, str)

    def __init__(self, parent=None):
        # type: (Optional[QtCore.QObject]) -> None
        """Initialize the Qt log emitter.

        Args:
            parent: Optional parent QObject.
        """
        super(_QtLogEmitter, self).__init__(parent)


class QtLogHandler(logging.Handler):
    """Logging handler that emits a signal for each log record."""

    def __init__(self, parent=None):
        # type: (Optional[QtCore.QObject]) -> None
        """Initialize the Qt log handler.

        Args:
            parent: Optional parent QObject for the internal emitter.
        """
        super(QtLogHandler, self).__init__()
        self._emitter = _QtLogEmitter(parent)

    @property
    def new_record(self):
        # type: () -> Signal
        """Get the signal emitted when a new log record is handled.

        Returns:
            Signal: Qt signal emitting (formatted_message, levelname).
        """
        return self._emitter.new_record

    def emit(self, record):
        # type: (logging.LogRecord) -> None
        """Format and emit a log record via the Qt emitter.

        Args:
            record: The logging record to process.
        """
        msg = self.format(record)
        ui_level = getattr(record, "ui_level", record.levelname.lower())
        self._emitter.new_record.emit(msg, ui_level)
