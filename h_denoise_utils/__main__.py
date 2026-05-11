"""Entry point for h_denoise_utils GUI."""

import sys

from .ui.qt_compat import QtWidgets, isUIAvailable

from .ui.main_window import BaseWindow


def main():
    """Launch the denoiser GUI."""
    # Configure logging
    import logging

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Create QApplication if needed
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Create and show window
    window = BaseWindow()
    window.show()

    # Run event loop if not in Houdini
    if not isUIAvailable:
        exec_fn = getattr(app, "exec", None) or app.exec_
        sys.exit(exec_fn())

    return window


if __name__ == "__main__":
    main()
