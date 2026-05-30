"""
Structured logging configuration for the application.

This module provides:
- Configurable logging setup (file + console)
- Structured log formatting
- Log rotation support
- Context-aware logging
"""

import contextvars
import functools
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from primr.utils.security import mask_sensitive_data

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
    console_handler.addFilter(SecretMaskingFilter())
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
        # Wire up ContextFilter so LogContext data appears in structured log output
        file_handler.addFilter(ContextFilter())
        # Redact secrets before anything is written to the persistent log file
        file_handler.addFilter(SecretMaskingFilter())
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


# Thread-local and async-safe context storage
_log_context_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "log_context", default=None
)


def _get_log_context() -> dict:
    """Return the current log context, initializing if needed."""
    ctx = _log_context_var.get()
    if ctx is None:
        return {}
    return ctx


class LogContext:
    """
    Context manager that adds context to all log messages within its scope.

    Thread-safe and async-safe via contextvars. Each thread and each async
    task gets its own isolated context, so parallel ThreadPoolExecutor
    workers (section writing, search queries) cannot corrupt each other.

    Example:
        with LogContext(company="Acme Corp", url="https://acme.com"):
            logger.info("Starting research")  # Will include company and url
    """

    def __init__(self, **context):
        self.context = context
        self._token: contextvars.Token | None = None

    def __enter__(self):
        previous = _get_log_context()
        merged = {**previous, **self.context}
        self._token = _log_context_var.set(merged)
        return self

    def __exit__(self, *args):
        if self._token is not None:
            _log_context_var.reset(self._token)

    @staticmethod
    def get_current() -> dict:
        """Return the current context dict (safe from any thread/task)."""
        return _get_log_context()


class ContextFilter(logging.Filter):
    """Filter that adds context to log records (thread-safe via contextvars)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.extra = _get_log_context().copy()
        return True


class SecretMaskingFilter(logging.Filter):
    """Redacts secrets (API keys, tokens, passwords) from every log record.

    Defense-in-depth at the logging sink: even if a caller accidentally logs a
    secret (e.g. ``logger.info("key=%s", api_key)``), it is masked before the
    record reaches any handler, regardless of caller discipline. Renders the
    record's message (applying %-args) and runs it through
    ``mask_sensitive_data``; only rewrites the record when something changed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            # Never let masking break logging — emit the record untouched.
            return True
        masked = mask_sensitive_data(rendered)
        if masked != rendered:
            record.msg = masked
            record.args = None  # already interpolated into masked text

        # The message alone is not enough: a secret inside an exception (e.g.
        # `logger.error("call failed", exc_info=True)` where the exception text
        # contains an API key) reaches the log via the formatted traceback, not
        # getMessage(). Pre-format the traceback, mask it, and cache it on the
        # record so the handler's formatter uses the redacted version.
        if record.exc_info:
            try:
                if record.exc_text is None:
                    record.exc_text = logging.Formatter().formatException(record.exc_info)
                record.exc_text = mask_sensitive_data(record.exc_text)
            except Exception:
                # Masking the traceback must never break logging.
                pass
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
