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
        "input_path",
        nargs="?",
        help="EXR file or folder to denoise. Omit to launch the GUI.",
    )
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
    denoise_group = parser.add_argument_group("batch denoise")
    denoise_group.add_argument(
        "--backend",
        choices=("optix", "oidn"),
        default=None,
        help="Backend to use for a command-line denoise run.",
    )
    denoise_group.add_argument(
        "--optix-version",
        choices=("8.1", "9.0", "9.1"),
        default=None,
        help="Bundled OptiX runtime to use when --backend optix.",
    )
    denoise_group.add_argument(
        "-o",
        "--output-folder",
        default=None,
        help="Destination folder. Defaults to the standard denoised output folder.",
    )
    denoise_group.add_argument(
        "--prefix",
        default=None,
        help="Output filename prefix. Defaults to den_.",
    )
    denoise_group.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output files.",
    )
    denoise_group.add_argument(
        "--beauty",
        "--beauty-name",
        dest="beauty_plane",
        default=None,
        help="Beauty plane name. Defaults to C.",
    )
    denoise_group.add_argument(
        "--albedo",
        "--albedo-name",
        dest="albedo_plane",
        default=None,
        help="Albedo guide plane name.",
    )
    denoise_group.add_argument(
        "--normal",
        "--normal-name",
        dest="normal_plane",
        default=None,
        help="Normal guide plane name.",
    )
    denoise_group.add_argument(
        "--aov",
        "--aov-name",
        dest="aovs_to_denoise",
        action="append",
        default=None,
        help="AOV plane to denoise. Repeat or use comma-separated names.",
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


def _parse_aov_names(values: list[str] | None) -> list[str] | None:
    """Normalize repeated or comma-separated AOV CLI values.

    Args:
        values: Raw AOV option values from argparse.

    Returns:
        list[str] | None: Clean AOV names, or None to trigger auto-detection.
    """
    names = []
    for value in values or []:
        names.extend(part.strip() for part in value.split(",") if part.strip())
    return names or None


def _uses_cli_denoise_options(args: argparse.Namespace) -> bool:
    """Return whether parsed args contain denoise-only options.

    Args:
        args: Parsed command-line arguments.

    Returns:
        bool: True if the user supplied options that require an input path.
    """
    return any(
        (
            args.backend is not None,
            args.optix_version is not None,
            args.output_folder is not None,
            args.prefix is not None,
            args.overwrite,
            args.beauty_plane is not None,
            args.albedo_plane is not None,
            args.normal_plane is not None,
            args.aovs_to_denoise is not None,
        )
    )


def _resolve_cli_runtime(backend: str, optix_version: str) -> str | None:
    """Resolve the bundled executable for a command-line denoise run.

    Args:
        backend: Backend key, either "optix" or "oidn".
        optix_version: OptiX runtime version to use for OptiX runs.

    Returns:
        str | None: Resolved executable path, or None when missing.
    """
    from h_denoise_utils.discovery.bundled_denoiser import resolve_bundled_denoiser
    from h_denoise_utils.discovery.bundled_oidn import resolve_bundled_oidn_denoiser

    if backend == "oidn":
        return resolve_bundled_oidn_denoiser(required=False)
    return resolve_bundled_denoiser(required=False, optix_version=optix_version)


def _create_cli_denoiser(
    *,
    input_path: str,
    backend: str,
    denoiser_path: str,
    output_folder: str | None,
    overwrite: bool,
    prefix: str,
    beauty_plane: str,
    normal_plane: str | None,
    albedo_plane: str | None,
    aovs_to_denoise: list[str] | None,
):
    """Create a Denoiser instance for CLI execution.

    Args:
        input_path: Source EXR file or folder.
        backend: Backend key.
        denoiser_path: Resolved backend executable path.
        output_folder: Optional destination folder.
        overwrite: Whether to replace existing output files.
        prefix: Output filename prefix.
        beauty_plane: Beauty plane name.
        normal_plane: Optional normal guide plane name.
        albedo_plane: Optional albedo guide plane name.
        aovs_to_denoise: Optional explicit AOV list.

    Returns:
        Denoiser: Configured denoiser instance.
    """
    from h_denoise_utils.core.config import AOVConfig, DenoiseConfig
    from h_denoise_utils.core.denoiser import Denoiser

    denoise_config = DenoiseConfig(
        backend=backend,
        overwrite=overwrite,
        prefix=prefix,
    )
    aov_config = AOVConfig(
        beauty_plane=beauty_plane,
        normal_plane=normal_plane,
        albedo_plane=albedo_plane,
        aovs_to_denoise=aovs_to_denoise,
    )
    return Denoiser(
        input_path=input_path,
        denoise_config=denoise_config,
        aov_config=aov_config,
        denoiser_path=denoiser_path,
        output_folder=output_folder,
    )


def _run_cli_denoise(args: argparse.Namespace) -> int:
    """Run command-line batch denoising.

    Args:
        args: Parsed command-line arguments.

    Returns:
        int: Process exit code.
    """
    from h_denoise_utils.discovery.bundled_denoiser import DEFAULT_OPTIX_VERSION

    backend = args.backend or "optix"
    optix_version = args.optix_version or DEFAULT_OPTIX_VERSION
    prefix = args.prefix if args.prefix is not None else "den_"
    beauty_plane = args.beauty_plane if args.beauty_plane is not None else "C"
    aovs_to_denoise = _parse_aov_names(args.aovs_to_denoise)
    denoiser_path = _resolve_cli_runtime(backend, optix_version)
    if not denoiser_path:
        if backend == "oidn":
            print("Bundled OIDN Denoiser.exe was not found.", file=sys.stderr)
        else:
            print(
                f"Bundled OptiX Denoiser.exe was not found for OptiX {optix_version}.",
                file=sys.stderr,
            )
        return 1

    denoiser = None
    try:
        denoiser = _create_cli_denoiser(
            input_path=args.input_path,
            backend=backend,
            denoiser_path=denoiser_path,
            output_folder=args.output_folder,
            overwrite=args.overwrite,
            prefix=prefix,
            beauty_plane=beauty_plane,
            normal_plane=args.normal_plane,
            albedo_plane=args.albedo_plane,
            aovs_to_denoise=aovs_to_denoise,
        )
        prep_result = denoiser.prepare()
        if prep_result.get("status") != "ready":
            print(
                "Preparation failed: {}".format(prep_result.get("message", "Unknown error")),
                file=sys.stderr,
            )
            return 1

        file_count = prep_result["file_count"]
        runtime_label = "OIDN" if backend == "oidn" else f"OptiX {optix_version}"
        print(f"Using {runtime_label} backend: {denoiser_path}")
        print(f"Processing {file_count} file(s)...")

        processed = 0
        skipped = 0
        failed = []
        prev_output = None
        for index in range(file_count):
            result = denoiser.denoise_one(index, prev_output)
            file_name = denoiser.files[index]
            if result["status"] == "success":
                processed += 1
                prev_output = result.get("output_path")
                print(f"[{index + 1}/{file_count}] Denoised: {file_name}")
            elif result["status"] == "skipped":
                skipped += 1
                prev_output = result.get("output_path") or prev_output
                print(f"[{index + 1}/{file_count}] Skipped: {file_name}")
            else:
                failed.append(file_name)
                print(
                    "[{}/{}] Failed: {} - {}".format(
                        index + 1,
                        file_count,
                        file_name,
                        result.get("message", "Unknown error"),
                    ),
                    file=sys.stderr,
                )

        print(f"Finished: {processed} processed, {skipped} skipped, {len(failed)} failed.")
        output_folder = prep_result.get("output_folder")
        if output_folder:
            print(f"Output folder: {output_folder}")
        return 1 if failed else 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if denoiser is not None:
            denoiser.cleanup()


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

    if args.input_path:
        return _run_cli_denoise(args)

    if _uses_cli_denoise_options(args):
        parser.error("an input path is required when using command-line denoise options")

    app_args = sys.argv if argv is None else ["h-denoise", *argv]
    return _launch_gui(app_args)


if __name__ == "__main__":
    result = main()
    if isinstance(result, int):
        sys.exit(result)
