"""
Tests for logging configuration.
"""

import logging

from primr.utils.logging_config import (
    ColoredFormatter,
    LogContext,
    StructuredFormatter,
    get_logger,
    setup_logging,
)


class TestSetupLogging:
    """Tests for logging setup."""

    def test_returns_logger(self):
        """setup_logging() should return a logger."""
        logger = setup_logging(level="INFO")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "primr"

    def test_sets_log_level(self):
        """Should set the specified log level."""
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_creates_console_handler(self):
        """Should create a console handler."""
        logger = setup_logging(level="INFO")
        handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(handlers) >= 1

    def test_creates_file_handler(self, tmp_path):
        """Should create file handler when log_dir specified."""
        setup_logging(level="INFO", log_dir=tmp_path)

        # Check that a log file was created
        log_files = list(tmp_path.glob("research_*.log"))
        assert len(log_files) == 1

    def test_uses_session_id_in_filename(self, tmp_path):
        """Should use session_id in log filename."""
        setup_logging(level="INFO", log_dir=tmp_path, session_id="test_session")

        log_file = tmp_path / "research_test_session.log"
        assert log_file.exists()

    def test_clears_existing_handlers(self):
        """Should clear existing handlers on setup."""
        logger = setup_logging(level="INFO")
        initial_count = len(logger.handlers)

        # Setup again
        logger = setup_logging(level="DEBUG")

        # Should not accumulate handlers
        assert len(logger.handlers) <= initial_count + 1


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_child_logger(self):
        """get_logger() should return a child logger."""
        logger = get_logger("test_module")
        assert logger.name == "primr.test_module"

    def test_different_modules_get_different_loggers(self):
        """Different module names should get different loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        assert logger1 is not logger2
        assert logger1.name != logger2.name


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_sets_context(self):
        """LogContext should set context variables."""
        with LogContext(company="Acme", url="https://acme.com"):
            assert LogContext._context.get("company") == "Acme"
            assert LogContext._context.get("url") == "https://acme.com"

    def test_clears_context_on_exit(self):
        """LogContext should clear context on exit."""
        with LogContext(company="Acme"):
            pass
        assert "company" not in LogContext._context

    def test_nested_contexts(self):
        """Nested LogContexts should work correctly."""
        with LogContext(outer="value1"):
            assert LogContext._context.get("outer") == "value1"

            with LogContext(inner="value2"):
                assert LogContext._context.get("outer") == "value1"
                assert LogContext._context.get("inner") == "value2"

            # Inner context should be cleared
            assert "inner" not in LogContext._context
            assert LogContext._context.get("outer") == "value1"

    def test_restores_previous_context(self):
        """Should restore previous context values."""
        LogContext._context = {"existing": "value"}

        with LogContext(new="context"):
            assert LogContext._context.get("existing") == "value"
            assert LogContext._context.get("new") == "context"

        assert LogContext._context.get("existing") == "value"
        assert "new" not in LogContext._context

        # Cleanup
        LogContext._context = {}


class TestColoredFormatter:
    """Tests for ColoredFormatter."""

    def test_adds_color_to_levelname(self):
        """Should add ANSI color codes to level name."""
        formatter = ColoredFormatter("%(levelname)s: %(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        # Should contain ANSI escape codes
        assert "\033[" in formatted
        assert "Test message" in formatted


class TestStructuredFormatter:
    """Tests for StructuredFormatter."""

    def test_formats_basic_message(self):
        """Should format basic log message."""
        formatter = StructuredFormatter("%(asctime)s | %(levelname)s | %(message)s%(extra_str)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        assert "Test message" in formatted

    def test_includes_extra_context(self):
        """Should include extra context in output."""
        formatter = StructuredFormatter("%(message)s%(extra_str)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra = {"key": "value"}

        formatted = formatter.format(record)
        assert "key=value" in formatted


class TestLoggingIntegration:
    """Integration tests for logging."""

    def test_log_to_file(self, tmp_path):
        """Should write logs to file."""
        logger = setup_logging(level="DEBUG", log_dir=tmp_path, session_id="integration_test")

        logger.info("Test log message")

        log_file = tmp_path / "research_integration_test.log"
        content = log_file.read_text()
        assert "Test log message" in content

    def test_child_logger_writes_to_same_file(self, tmp_path):
        """Child loggers should write to same file."""
        setup_logging(level="DEBUG", log_dir=tmp_path, session_id="child_test")

        child = get_logger("child_module")
        child.info("Child log message")

        log_file = tmp_path / "research_child_test.log"
        content = log_file.read_text()
        assert "Child log message" in content
        assert "child_module" in content
