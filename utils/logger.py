"""
Enhanced logger: writes to debug_logs folder with proper formatting and rotation.
Call setup_debug_logging() from main on startup to enable file logging.
"""
import logging
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler
import os

# Project root: app/utils/logger.py -> app -> project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEBUG_LOGS_DIR = _PROJECT_ROOT / "debug_logs"
DEBUG_LOG_FILE = DEBUG_LOGS_DIR / "app_debug.log"

_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_debug_file_handler: Optional[logging.FileHandler] = None


def setup_debug_logging() -> None:
    """
    Create debug_logs folder and add file handler with rotation.
    Call once from main on startup to enable file logging.
    All logs (INFO, DEBUG, WARNING, ERROR) will be saved to debug_logs/app_debug.log
    """
    global _debug_file_handler
    try:
        # Get root logger FIRST and set level IMMEDIATELY
        root_logger = logging.getLogger()

        # Set root logger level to DEBUG to capture everything
        root_logger.setLevel(logging.DEBUG)

        # Create debug_logs directory
        DEBUG_LOGS_DIR.mkdir(parents=True, exist_ok=True)

        # Don't add handler if already exists
        if _debug_file_handler is not None:
            return

        # Use RotatingFileHandler to prevent log files from growing too large
        # Max file size: 10MB, keep 5 backup files
        _debug_file_handler = RotatingFileHandler(
            DEBUG_LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )

        # Set level to DEBUG to capture all log levels
        _debug_file_handler.setLevel(logging.DEBUG)

        # Set formatter
        _debug_file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

        # Add handler to root logger
        root_logger.addHandler(_debug_file_handler)

        # Also add console handler to show logs in terminal
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
        root_logger.addHandler(console_handler)

        # Log success message
        root_logger.info("=" * 80)
        root_logger.info("Debug logging initialized")
        root_logger.info(f"Log file: {DEBUG_LOG_FILE}")
        root_logger.info(f"Console output: ENABLED")
        root_logger.info(f"All events will be logged to: {DEBUG_LOG_FILE}")
        root_logger.info("=" * 80)

    except Exception as e:
        # Use basic logging if file handler fails
        logging.getLogger(__name__).warning(f"Could not setup debug file logging: {e}", exc_info=True)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with proper level. Use: log = get_logger(__name__); log.info(...)"""
    logger = logging.getLogger(name)
    # Ensure the logger level is set to DEBUG to capture all messages
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.DEBUG)
    return logger


# Simple functions you can use anywhere: info(), error(), debug(), warning()
_default_logger = logging.getLogger("app")


def info(msg: str, *args, **kwargs) -> None:
    _default_logger.info(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs) -> None:
    _default_logger.error(msg, *args, **kwargs)


def debug(msg: str, *args, **kwargs) -> None:
    _default_logger.debug(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs) -> None:
    _default_logger.warning(msg, *args, **kwargs)
