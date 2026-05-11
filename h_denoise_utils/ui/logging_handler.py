import logging

from .qt_compat import QtCore, Signal


class _QtLogEmitter(QtCore.QObject):
    """Qt signal container to avoid name clashes with logging.Handler.emit."""

    new_record = Signal(str, str)

    def __init__(self, parent=None):
        # type: (Optional[QtCore.QObject]) -> None
        super(_QtLogEmitter, self).__init__(parent)


class QtLogHandler(logging.Handler):
    """Logging handler that emits a signal for each log record."""

    def __init__(self, parent=None):
        # type: (Optional[QtCore.QObject]) -> None
        super(QtLogHandler, self).__init__()
        self._emitter = _QtLogEmitter(parent)

    @property
    def new_record(self):
        # type: () -> Signal
        return self._emitter.new_record

    def emit(self, record):
        # type: (logging.LogRecord) -> None
        msg = self.format(record)
        ui_level = getattr(record, "ui_level", record.levelname.lower())
        self._emitter.new_record.emit(msg, ui_level)
