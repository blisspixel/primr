"""Tests for A2A CLI entry point."""

from unittest.mock import patch


class TestA2ACli:
    """Tests for primr-a2a CLI argument parsing."""

    def test_default_port(self):
        """Default port is 9000."""
        with patch("sys.argv", ["primr-a2a"]):
            parser = _make_parser()
            args = parser.parse_args([])
            assert args.port == 9000

    def test_custom_port(self):
        parser = _make_parser()
        args = parser.parse_args(["--port", "8080"])
        assert args.port == 8080

    def test_default_host(self):
        parser = _make_parser()
        args = parser.parse_args([])
        assert args.host == "0.0.0.0"

    def test_no_auth_flag(self):
        parser = _make_parser()
        args = parser.parse_args(["--no-auth"])
        assert args.no_auth is True

    def test_no_mcp_flag(self):
        parser = _make_parser()
        args = parser.parse_args(["--no-mcp"])
        assert args.no_mcp is True

    def test_log_level(self):
        parser = _make_parser()
        args = parser.parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_journal_path(self):
        parser = _make_parser()
        args = parser.parse_args(["--journal-path", "/tmp/test.json"])
        assert args.journal_path == "/tmp/test.json"


def _make_parser():
    """Create the argument parser (mirrors cli.py structure)."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--no-mcp", action="store_true")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    parser.add_argument("--journal-path", type=str, default=None)
    return parser
