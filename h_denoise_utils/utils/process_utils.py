"""Process execution utilities."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping

from ..constants import DEFAULT_DENOISER_TIMEOUT_SECONDS


def get_subprocess_config() -> tuple[subprocess.STARTUPINFO | None, int]:
    """Get subprocess configuration to hide console on Windows.

    Returns:
        Tuple of (startupinfo, creation_flags) for subprocess.run()
    """
    startupinfo: subprocess.STARTUPINFO | None = None
    creation_flags = 0

    import os

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = subprocess.CREATE_NO_WINDOW

    return startupinfo, creation_flags


def run_subprocess(
    cmd: list[str],
    timeout: int = DEFAULT_DENOISER_TIMEOUT_SECONDS,
    env: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    """Run a subprocess and return success status and error message.

    Args:
        cmd: Command list to execute.
        timeout: Timeout in seconds.
        env: Optional subprocess environment override.

    Returns:
        Tuple of (success, error_message)
    """
    startupinfo, creation_flags = get_subprocess_config()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=creation_flags,
            timeout=timeout,
            env=env,
        )
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return False, f"Process timeout after {timeout}s"
    except Exception as e:
        return False, f"Execution error: {e}"
