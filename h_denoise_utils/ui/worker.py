"""Worker thread for background denoising."""

from __future__ import annotations

from ..core.config import AOVConfig, DenoiseConfig
from ..core.denoiser import Denoiser
from .qt_compat import QtCore, Signal


class DenoiseWorker(QtCore.QThread):
    """Background worker for denoising images."""

    # Signals
    progress = Signal(int, int)  # (current, total)
    log_message = Signal(str, str)  # (message, level)
    completed = Signal(dict)  # summary dict

    def __init__(
        self,
        input_path: str,
        denoise_config: DenoiseConfig,
        aov_config: AOVConfig,
        denoiser_path: str,
        extensions: list[str] | None = None,
        file_list: list[str] | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.input_path = input_path
        self.denoise_config = denoise_config
        self.aov_config = aov_config
        self.denoiser_path = denoiser_path
        self.extensions = extensions
        self.file_list = file_list
        self._stop_requested = False

    def request_stop(self) -> None:
        """Request the worker to stop."""
        self._stop_requested = True

    def run(self) -> None:
        """Run the denoising process."""
        denoiser = None
        try:
            # Create denoiser
            denoiser = Denoiser(
                input_path=self.input_path,
                denoise_config=self.denoise_config,
                aov_config=self.aov_config,
                denoiser_path=self.denoiser_path,
                extensions=self.extensions,
                file_list=self.file_list,
            )

            # Prepare
            self.log_message.emit("Preparing denoising...", "info")
            prep_result = denoiser.prepare()

            if prep_result["status"] != "ready":
                self.log_message.emit(
                    "Preparation failed: {}".format(prep_result.get("message", "Unknown error")),
                    "error",
                )
                self.completed.emit({"processed": 0, "skipped": 0, "failed": []})
                return

            file_count = prep_result["file_count"]
            self.log_message.emit(f"Processing {file_count} files...", "info")

            # Process files
            processed = 0
            skipped = 0
            failed = []
            prev_output = None

            for i in range(file_count):
                if self._stop_requested:
                    self.log_message.emit("Cancelled by user", "warning")
                    break

                self.progress.emit(i + 1, file_count)
                result = denoiser.denoise_one(i, prev_output)

                if result["status"] == "success":
                    processed += 1
                    prev_output = result.get("output_path")
                    self.log_message.emit(
                        f"[{i + 1}/{file_count}] Denoised: {denoiser.files[i]}",
                        "success",
                    )
                elif result["status"] == "skipped":
                    skipped += 1
                    prev_output = result.get("output_path") or prev_output
                    self.log_message.emit(
                        f"[{i + 1}/{file_count}] Skipped: {denoiser.files[i]}",
                        "info",
                    )
                else:
                    failed.append(denoiser.files[i])
                    self.log_message.emit(
                        "[{}/{}] Failed: {} - {}".format(
                            i + 1,
                            file_count,
                            denoiser.files[i],
                            result.get("message", "Unknown error"),
                        ),
                        "error",
                    )

            # Emit summary
            summary = {
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "output_folder": denoiser.dest_folder,
            }
            self.completed.emit(summary)

            if failed:
                self.log_message.emit(f"Completed with {len(failed)} errors", "warning")
            else:
                self.log_message.emit(f"Successfully processed {processed} files", "success")

        except Exception as e:
            self.log_message.emit(f"Error: {str(e)}", "error")
            self.completed.emit({"processed": 0, "skipped": 0, "failed": []})
        finally:
            if denoiser is not None:
                denoiser.cleanup()
