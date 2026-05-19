"""Entry point for h_denoise_utils GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h_denoise_utils._version import __version__


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
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
    parser.add_argument(
        "--smoke-runtime",
        choices=("optix", "oidn", "all", "none"),
        default="all",
        help="Runtime bundle to validate during --smoke-test.",
    )
    return parser


def _ui_dir() -> Path:
    """Locate the UI resources directory.

    Returns:
        Path: Path to the UI directory containing assets.
    """
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
    """Retrieve paths to critical UI asset files.

    Returns:
        list[Path]: List of required asset paths.
    """
    ui_dir = _ui_dir()
    return [
        ui_dir / "style.qss",
        ui_dir / "icons" / "logo.ico",
    ]


def _run_smoke_test(runtime: str = "optix") -> int:
    """Perform basic environment verification and Qt startup validation.

    Args:
        runtime: The runtime type to validate ("optix", "oidn", "all", or "none").

    Returns:
        int: 0 if successful, 1 if verification failed.
    """
    from h_denoise_utils.discovery.bundled_denoiser import resolve_bundled_denoiser
    from h_denoise_utils.discovery.bundled_oidn import resolve_bundled_oidn_denoiser
    from h_denoise_utils.ui.qt_compat import QtWidgets

    missing = [path for path in _ui_asset_paths() if not path.is_file()]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        print(f"Missing bundled UI asset(s): {missing_list}", file=sys.stderr)
        return 1
    if runtime in ("optix", "all"):
        try:
            resolve_bundled_denoiser(required=True)
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if runtime in ("oidn", "all"):
        try:
            resolve_bundled_oidn_denoiser(required=True)
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(["h-denoise", "--smoke-test"])

    app.processEvents()
    return 0


def _launch_gui(app_args: list[str] | None = None):
    """Launch the denoiser GUI window.

    Args:
        app_args: Arguments to pass to QApplication. If None, sys.argv is used.

    Returns:
        BaseWindow | int: The window instance if UI is available, or exit code.
    """
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
    """Run the command line entry point.

    Args:
        argv: Optional arguments override.

    Returns:
        int | BaseWindow: Exit code or BaseWindow instance.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"h_denoise_utils {__version__}")
        return 0

    if args.smoke_test:
        return _run_smoke_test(args.smoke_runtime)

    app_args = sys.argv if argv is None else ["h-denoise", *argv]
    return _launch_gui(app_args)


if __name__ == "__main__":
    result = main()
    if isinstance(result, int):
        sys.exit(result)
