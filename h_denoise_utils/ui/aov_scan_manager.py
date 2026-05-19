"""AOV scan worker manager for the UI."""

from __future__ import annotations

from .qt_compat import QtCore, Signal
from .services.aov_inspector import analyze_aovs


class AovAnalyzeWorker(QtCore.QThread):
    """Background worker for scanning AOVs without blocking the UI."""

    completed = Signal(dict)

    def __init__(
        self, path: str, selected_files: list[str], parent: QtCore.QObject | None = None
    ) -> None:
        """Initialize the background AOV analysis worker.

        Args:
            path: Target directory or file path to analyze.
            selected_files: List of selected file names.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._path = path
        self._selected_files = list(selected_files or [])

    def run(self) -> None:
        """Execute the AOV analysis in the background thread."""
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

    def __init__(self, timeout_ms: int = 10000, parent: QtCore.QObject | None = None) -> None:
        """Initialize the AOV scan manager.

        Args:
            timeout_ms: Timeout duration in milliseconds for the background scan.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._timeout_ms = timeout_ms
        self._worker: AovAnalyzeWorker | None = None
        self._token = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self, path: str, selected_files: list[str]) -> None:
        """Start a new AOV scan background worker.

        Cancels any ongoing scan and invalidates stale results.

        Args:
            path: Path to target folder or file.
            selected_files: List of selected filenames.
        """
        self._stop_current(invalidate=True)
        token = self._token
        worker = AovAnalyzeWorker(path, selected_files, parent=self)
        worker.completed.connect(lambda result, t=token: self._on_complete(t, result))
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self._timer.start(self._timeout_ms)
        self.started.emit()
        worker.start()

    def cancel(self) -> None:
        """Cancel the current AOV scan."""
        self._stop_current(invalidate=True)

    def _stop_current(self, invalidate: bool) -> None:
        """Stop the currently running background worker and timer.

        Args:
            invalidate: If True, increments the token to ignore any pending
                results from the current worker.
        """
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
        self._worker = None
        if self._timer.isActive():
            self._timer.stop()
        if invalidate:
            self._token += 1

    def _on_timeout(self) -> None:
        """Handle scan timeout by stopping the worker and emitting timed_out."""
        if not self._worker or not self._worker.isRunning():
            return
        self._stop_current(invalidate=True)
        self.timed_out.emit()

    def _on_complete(self, token: int, result: dict) -> None:
        """Handle completion of background scan if token matches.

        Args:
            token: Token associated with the worker.
            result: Analysis result dictionary.
        """
        if token != self._token:
            return
        self._stop_current(invalidate=False)
        self.completed.emit(result)
