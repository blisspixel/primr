"""
Logging configuration for MCP server.

This module provides logging isolation for stdio transport mode,
ensuring all logs go to stderr to preserve stdout for JSON-RPC framing.

Requirements: 14.1, 14.2, 14.4
"""

import logging
import sys
import warnings
from contextlib import contextmanager
from typing import Iterator, TextIO


class StdioSafeHandler(logging.Handler):
    """
    Logging handler that writes only to stderr.

    Used in stdio mode to prevent log output from corrupting JSON-RPC framing.
    """

    def __init__(self, stream: TextIO = None):
        super().__init__()
        self.stream = stream or sys.stderr

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.stream.write(msg + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)


def configure_stdio_logging(level: str = "INFO") -> None:
    """
    Configure logging for stdio mode.

    Routes all logs and warnings to stderr to preserve stdout for JSON-RPC.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Requirements: 14.1, 14.4
    """
    # Get numeric level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add stderr handler
    handler = StdioSafeHandler(sys.stderr)
    handler.setLevel(numeric_level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Redirect warnings to stderr
    warnings.filterwarnings("default")
    logging.captureWarnings(True)

    # Configure specific loggers
    for logger_name in ["primr", "mcp", "httpx", "httpcore"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(numeric_level)


def configure_http_logging(level: str = "INFO", log_file: str = None) -> None:
    """
    Configure logging for HTTP mode.

    Logs to stderr by default, or to a file if specified.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file

    Requirements: 14.2
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler
    if log_file:
        handler = logging.FileHandler(log_file)
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setLevel(numeric_level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Capture warnings
    warnings.filterwarnings("default")
    logging.captureWarnings(True)


@contextmanager
def suppress_stdout() -> Iterator[None]:
    """
    Context manager to suppress stdout output.

    Used to wrap library calls that might print to stdout in stdio mode.

    Requirements: 1.9
    """
    old_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr  # Redirect to stderr
        yield
    finally:
        sys.stdout = old_stdout


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the given name.

    Args:
        name: Logger name (typically module name)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
