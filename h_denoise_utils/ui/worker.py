"""Worker thread for background denoising."""

from .qt_compat import QtCore, Signal

from ..core.denoiser import Denoiser


class DenoiseWorker(QtCore.QThread):
    """Background worker for denoising images."""

    # Signals
    progress = Signal(int, int)  # (current, total)
    log_message = Signal(str, str)  # (message, level)
    finished = Signal(dict)  # summary dict

    def __init__(
        self,
        input_path,  # type: str
        denoise_config,  # type: DenoiseConfig
        aov_config,  # type: AOVConfig
        idenoise_path,  # type: str
        extensions=None,  # type: Optional[List[str]]
        file_list=None,  # type: Optional[List[str]]
        parent=None,  # type: Optional[QtCore.QObject]
    ):
        # type: (...) -> None
        super(DenoiseWorker, self).__init__(parent)
        self.input_path = input_path
        self.denoise_config = denoise_config
        self.aov_config = aov_config
        self.idenoise_path = idenoise_path
        self.extensions = extensions
        self.file_list = file_list
        self._stop_requested = False

    def request_stop(self):
        # type: () -> None
        """Request the worker to stop."""
        self._stop_requested = True

    def run(self):
        # type: () -> None
        """Run the denoising process."""
        try:
            # Create denoiser
            denoiser = Denoiser(
                input_path=self.input_path,
                denoise_config=self.denoise_config,
                aov_config=self.aov_config,
                idenoise_path=self.idenoise_path,
                extensions=self.extensions,
                file_list=self.file_list,
            )

            # Prepare
            self.log_message.emit("Preparing denoising...", "info")
            prep_result = denoiser.prepare()

            if prep_result["status"] != "ready":
                self.log_message.emit(
                    "Preparation failed: {}".format(
                        prep_result.get("message", "Unknown error")
                    ),
                    "error",
                )
                self.finished.emit({"processed": 0, "skipped": 0, "failed": []})
                return

            file_count = prep_result["file_count"]
            self.log_message.emit("Processing {} files...".format(file_count), "info")

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
                        "[{}/{}] Denoised: {}".format(
                            i + 1, file_count, denoiser.files[i]
                        ),
                        "success",
                    )
                elif result["status"] == "skipped":
                    skipped += 1
                    prev_output = result.get("output_path") or prev_output
                    self.log_message.emit(
                        "[{}/{}] Skipped: {}".format(
                            i + 1, file_count, denoiser.files[i]
                        ),
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

            # Cleanup
            denoiser.cleanup()

            # Emit summary
            summary = {
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "output_folder": denoiser.dest_folder,
            }
            self.finished.emit(summary)

            if failed:
                self.log_message.emit(
                    "Completed with {} errors".format(len(failed)), "warning"
                )
            else:
                self.log_message.emit(
                    "Successfully processed {} files".format(processed), "success"
                )

        except Exception as e:
            self.log_message.emit("Error: {}".format(str(e)), "error")
            self.finished.emit({"processed": 0, "skipped": 0, "failed": []})
