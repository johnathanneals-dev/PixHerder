"""
DupeFinder debug logging configuration.
Provides rotating file handlers for debug and error logs.
Session-only toggle -- resets to off on restart.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


_logging_enabled = False

# Resolve logs directory from config without circular import
_LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup_logging(enable=False):
    """Configure logging handlers. Activates only if enable is True."""
    global _logging_enabled

    os.makedirs(str(_LOGS_DIR), exist_ok=True)

    root = logging.getLogger()

    # Avoid adding duplicate handlers on repeated calls
    if any(getattr(h, "_dupefinder_tag", False) for h in root.handlers):
        return

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Debug log -- 10 MB, 3 backups
    debug_handler = RotatingFileHandler(
        str(_LOGS_DIR / "debug.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(fmt)
    debug_handler._dupefinder_tag = True

    # Error log -- 5 MB, 2 backups
    error_handler = RotatingFileHandler(
        str(_LOGS_DIR / "error.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    error_handler._dupefinder_tag = True

    root.addHandler(debug_handler)
    root.addHandler(error_handler)

    if enable:
        enable_logging()
    else:
        disable_logging()


def enable_logging():
    """Set root logger to DEBUG, activating all handlers."""
    global _logging_enabled
    _logging_enabled = True
    logging.getLogger().setLevel(logging.DEBUG)


def disable_logging():
    """Set root logger to CRITICAL, effectively silencing output."""
    global _logging_enabled
    _logging_enabled = False
    logging.getLogger().setLevel(logging.CRITICAL)


def is_logging_enabled():
    """Return whether verbose logging is currently active."""
    return _logging_enabled
