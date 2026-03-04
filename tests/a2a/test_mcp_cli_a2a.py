"""Tests for --a2a flag in MCP CLI."""

import argparse


class TestMCPCLIA2AFlag:
    """Tests for --a2a and --a2a-port arguments in primr-mcp CLI."""

    def test_a2a_flag_default_false(self):
        """--a2a defaults to False."""
        parser = _make_mcp_parser()
        args = parser.parse_args([])
        assert args.a2a is False

    def test_a2a_flag_true(self):
        parser = _make_mcp_parser()
        args = parser.parse_args(["--a2a"])
        assert args.a2a is True

    def test_a2a_port_default(self):
        parser = _make_mcp_parser()
        args = parser.parse_args([])
        assert args.a2a_port == 9000

    def test_a2a_port_custom(self):
        parser = _make_mcp_parser()
        args = parser.parse_args(["--a2a-port", "8888"])
        assert args.a2a_port == 8888

    def test_a2a_with_http(self):
        """--a2a can be combined with --http."""
        parser = _make_mcp_parser()
        args = parser.parse_args(["--http", "--a2a"])
        assert args.http is True
        assert args.a2a is True

    def test_a2a_with_no_auth(self):
        """--a2a can be combined with --no-auth."""
        parser = _make_mcp_parser()
        args = parser.parse_args(["--a2a", "--no-auth"])
        assert args.a2a is True
        assert args.no_auth is True


def _make_mcp_parser():
    """Create a parser matching primr-mcp CLI structure."""
    parser = argparse.ArgumentParser()

    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument("--stdio", action="store_true", default=True)
    transport_group.add_argument("--http", action="store_true")

    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--allow-plaintext", action="store_true")
    parser.add_argument("--no-auth", action="store_true")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    parser.add_argument("--a2a", action="store_true")
    parser.add_argument("--a2a-port", type=int, default=9000)
    parser.add_argument("--journal-path", type=str, default=None)
    return parser
