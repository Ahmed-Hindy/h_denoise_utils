"""AOV scan worker manager for the UI."""

from .qt_compat import QtCore, Signal
from .services.aov_inspector import analyze_aovs


class AovAnalyzeWorker(QtCore.QThread):
    """Background worker for scanning AOVs without blocking the UI."""

    completed = Signal(dict)

    def __init__(self, path, selected_files, parent=None):
        # type: (str, List[str], Optional[QtCore.QObject]) -> None
        super(AovAnalyzeWorker, self).__init__(parent)
        self._path = path
        self._selected_files = list(selected_files or [])

    def run(self):
        # type: () -> None
        if self.isInterruptionRequested():
            return
        result = analyze_aovs(self._path, self._selected_files)
        if self.isInterruptionRequested():
            return
        self.completed.emit(result)


class AovScanManager(QtCore.QObject):
    """Manage AOV scans with timeout and stale-result protection."""

    started = Signal()
    completed = Signal(dict)
    timed_out = Signal()

    def __init__(self, timeout_ms=10000, parent=None):
        # type: (int, Optional[QtCore.QObject]) -> None
        super(AovScanManager, self).__init__(parent)
        self._timeout_ms = timeout_ms
        self._worker = None  # type: Optional[AovAnalyzeWorker]
        self._token = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self, path, selected_files):
        # type: (str, List[str]) -> None
        self._stop_current(invalidate=True)
        token = self._token
        worker = AovAnalyzeWorker(path, selected_files, parent=self)
        worker.completed.connect(lambda result, t=token: self._on_complete(t, result))
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self._timer.start(self._timeout_ms)
        self.started.emit()
        worker.start()

    def cancel(self):
        # type: () -> None
        self._stop_current(invalidate=True)

    def _stop_current(self, invalidate):
        # type: (bool) -> None
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        self._worker = None
        if self._timer.isActive():
            self._timer.stop()
        if invalidate:
            self._token += 1

    def _on_timeout(self):
        # type: () -> None
        if not self._worker or not self._worker.isRunning():
            return
        self._stop_current(invalidate=True)
        self.timed_out.emit()

    def _on_complete(self, token, result):
        # type: (int, dict) -> None
        if token != self._token:
            return
        self._stop_current(invalidate=False)
        self.completed.emit(result)
