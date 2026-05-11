"""Entry point for h_denoise_utils GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h_denoise_utils import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="h-denoise")
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the installed h_denoise_utils version and exit.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Validate Qt startup and bundled UI assets without showing the GUI.",
    )
    return parser


def _ui_dir() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "ui",
        here / "h_denoise_utils" / "ui",
    ]

    for candidate in candidates:
        if (candidate / "style.qss").is_file():
            return candidate

    return candidates[0]


def _ui_asset_paths() -> list[Path]:
    ui_dir = _ui_dir()
    return [
        ui_dir / "style.qss",
        ui_dir / "icons" / "logo.ico",
    ]


def _run_smoke_test() -> int:
    from h_denoise_utils.ui.qt_compat import QtWidgets

    missing = [path for path in _ui_asset_paths() if not path.is_file()]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        print(f"Missing bundled UI asset(s): {missing_list}", file=sys.stderr)
        return 1

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(["h-denoise", "--smoke-test"])

    app.processEvents()
    return 0


def _launch_gui(app_args: list[str] | None = None):
    """Launch the denoiser GUI."""
    import logging

    from h_denoise_utils.ui.main_window import BaseWindow
    from h_denoise_utils.ui.qt_compat import QtWidgets, isUIAvailable

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(app_args or sys.argv)

    window = BaseWindow()
    window.show()

    if not isUIAvailable:
        exec_fn = getattr(app, "exec", None) or app.exec_
        return exec_fn()

    return window


def main(argv: list[str] | None = None):
    """Run the command line entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"h_denoise_utils {__version__}")
        return 0

    if args.smoke_test:
        return _run_smoke_test()

    app_args = sys.argv if argv is None else ["h-denoise", *argv]
    return _launch_gui(app_args)


if __name__ == "__main__":
    result = main()
    if isinstance(result, int):
        sys.exit(result)
