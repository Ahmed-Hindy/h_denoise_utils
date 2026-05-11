"""Process execution utilities."""

import subprocess


def get_subprocess_config():
    # type: () -> Tuple[Optional[subprocess.STARTUPINFO], int]
    """Get subprocess configuration to hide console on Windows.

    Returns:
        Tuple of (startupinfo, creation_flags) for subprocess.run()
    """
    startupinfo = None  # type: Optional[subprocess.STARTUPINFO]
    creation_flags = 0

    import os

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = subprocess.CREATE_NO_WINDOW

    return startupinfo, creation_flags


def run_subprocess(cmd, timeout=300):
    # type: (list, int) -> Tuple[bool, str]
    """Run a subprocess and return success status and error message.

    Args:
        cmd: Command list to execute
        timeout: Timeout in seconds (default 5 minutes)

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
        )
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return False, "Process timeout after {}s".format(timeout)
    except Exception as e:
        return False, "Execution error: {}".format(e)
