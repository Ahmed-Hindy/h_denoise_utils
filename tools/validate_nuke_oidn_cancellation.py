"""Cancel a Nuke OIDN render with Ctrl+Break and verify bridge cleanup."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

TEMP_ROOT = Path(tempfile.gettempdir()) / "hdu-oidn-nuke"
OUTPUT = Path(tempfile.gettempdir()) / "hdu-oidn-cancel-acceptance.exr"


def _bridge_running() -> bool:
    """Return whether an OIDN bridge process is active."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq HOidnBridge.exe", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "HOidnBridge.exe" in result.stdout


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nuke", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Start a render, interrupt it while the bridge runs, and verify cleanup."""
    args = _parse_args()
    render_script = Path(__file__).with_name("nuke_oidn_long_render.py")
    OUTPUT.unlink(missing_ok=True)
    before = set(TEMP_ROOT.glob("*")) if TEMP_ROOT.exists() else set()

    environment = os.environ.copy()
    environment["NUKE_PATH"] = str(args.plugin.resolve())
    environment.pop("CUDA_CACHE_MAXSIZE", None)
    process = subprocess.Popen(
        [str(args.nuke.resolve()), "-t", str(render_script.resolve())],
        cwd=Path.cwd(),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    bridge_seen = False
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline and process.poll() is None:
        if _bridge_running():
            bridge_seen = True
            time.sleep(0.2)
            process.send_signal(signal.CTRL_BREAK_EVENT)
            break
        time.sleep(0.05)

    try:
        output, _ = process.communicate(timeout=20.0)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate(timeout=5.0)
        raise RuntimeError("Nuke did not exit after Ctrl+Break cancellation") from error

    time.sleep(0.75)
    after = set(TEMP_ROOT.glob("*")) if TEMP_ROOT.exists() else set()
    leaked = sorted(path.as_posix() for path in after - before)

    print(output)
    print(f"bridge_seen={bridge_seen}")
    print(f"nuke_exit_code={process.returncode}")
    print(f"output_exists={OUTPUT.exists()}")
    print(f"leaked_exchange_files={leaked}")

    if not bridge_seen:
        raise RuntimeError("HOidnBridge.exe did not start before Nuke exited")
    if _bridge_running():
        raise RuntimeError("HOidnBridge.exe is still running after cancellation")
    if leaked:
        raise RuntimeError(f"OIDN exchange files leaked after cancellation: {leaked}")
    if "cancel" not in output.lower() and "interrupt" not in output.lower():
        raise RuntimeError("Nuke output did not report cancellation or interruption")

    print("OIDN Ctrl+Break cancellation acceptance passed")


if __name__ == "__main__":
    main()
