"""
Structured logging configuration for the application.

This module provides:
- Configurable logging setup (file + console)
- Structured log formatting
- Log rotation support
- Context-aware logging
"""

import functools
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# =============================================================================
# LOG FORMATTERS
# =============================================================================


class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Add color to levelname
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """Formatter for structured file logging."""

    def format(self, record: logging.LogRecord) -> str:
        # Add extra context if available
        extra = getattr(record, "extra", {})
        if extra:
            extra_str = " | " + " | ".join(f"{k}={v}" for k, v in extra.items())
        else:
            extra_str = ""

        record.extra_str = extra_str
        return super().format(record)


# =============================================================================
# LOGGING SETUP
# =============================================================================


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    session_id: str | None = None,
    console_level: str = "WARNING",
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Minimum log level for file logging
        log_dir: Directory for log files (None = no file logging)
        session_id: Unique identifier for this session
        console_level: Minimum log level for console output
        max_file_size: Maximum size of each log file
        backup_count: Number of backup files to keep

    Returns:
        Configured root logger for the application
    """
    # Get the root logger for our package
    logger = logging.getLogger("primr")
    logger.setLevel(logging.DEBUG)  # Capture everything, filter at handlers

    # Close and remove existing handlers to avoid resource leaks
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    # Console handler - errors and warnings only by default
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, console_level.upper()))
    console_handler.setFormatter(ColoredFormatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    # File handler - everything
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        session = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"research_{session}.log"

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(
            StructuredFormatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s%(extra_str)s")
        )
        logger.addHandler(file_handler)

        logger.info(f"Logging to {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.

    Args:
        name: Module name (e.g., "scrape", "llm")

    Returns:
        Logger instance

    Example:
        logger = get_logger("scrape")
        logger.info("Starting scrape", extra={"url": url})
    """
    return logging.getLogger(f"primr.{name}")


# =============================================================================
# CONTEXT LOGGING
# =============================================================================


class LogContext:
    """
    Context manager that adds context to all log messages within its scope.

    Example:
        with LogContext(company="Acme Corp", url="https://acme.com"):
            logger.info("Starting research")  # Will include company and url
    """

    _context: dict = {}

    def __init__(self, **context):
        self.context = context
        self.previous = {}

    def __enter__(self):
        self.previous = LogContext._context.copy()
        LogContext._context.update(self.context)
        return self

    def __exit__(self, *args):
        LogContext._context = self.previous


class ContextFilter(logging.Filter):
    """Filter that adds context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.extra = LogContext._context.copy()
        return True


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def log_function_call(logger: logging.Logger) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator that logs function entry and exit.

    Example:
        @log_function_call(logger)
        def process_data(data):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug(f"Entering {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Exiting {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"Exception in {func.__name__}: {e}")
                raise

        return wrapper

    return decorator
