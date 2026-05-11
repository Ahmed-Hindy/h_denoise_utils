"""Standalone logging setup for h_denoise_utils.

Configures a standard library logger with console and rotating-file handlers.
Typical usage is to call ``setup_logger("h_denoise_utils")`` once during
application startup and let module loggers use ``logging.getLogger(__name__)``.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


_LOG_DIR_ENV = "H_DENOISE_LOG_DIR"
_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_DEFAULT_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _default_log_dir() -> str:
    """Return a writable directory for log files.

    Prefers the value of H_DENOISE_LOG_DIR env var, falls back to
    <user_data_dir>/h_denoise_utils/logs.
    """
    if os.environ.get(_LOG_DIR_ENV):
        return os.environ[_LOG_DIR_ENV]
    # Cross-platform user data location
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "h_denoise_utils", "logs")


def get_log_dir(log_dir: Optional[str] = None) -> str:
    """Return the effective log directory for a logger setup call."""
    return log_dir or _default_log_dir()


def setup_logger(
    name: str,
    level: int = logging.DEBUG,
    log_dir: Optional[str] = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """Create (or return cached) a logger with console + rotating-file handlers.

    Args:
        name:         Logger name (e.g. ``"h_denoise_utils"``).
        level:        Logging level for both handlers.
        log_dir:      Directory for the rotating log file.
                      Defaults to ``H_DENOISE_LOG_DIR`` env var or the
                      platform user-data directory.
        max_bytes:    Max size of each log file before rotation.
        backup_count: Number of rotated backup files to keep.

    Returns:
        A configured :class:`logging.Logger`.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured by a prior call.
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Rotating file handler (optional — skip if the log dir can't be created)
    target_dir = get_log_dir(log_dir)
    try:
        os.makedirs(target_dir, exist_ok=True)
        log_path = os.path.join(target_dir, "{}.log".format(name))
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Non-fatal: log dir unavailable (read-only fs, restricted env, etc.)
        logger.warning("Could not create log file in: %s", target_dir)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Compatibility wrapper around :func:`logging.getLogger`."""
    return logging.getLogger(name)
