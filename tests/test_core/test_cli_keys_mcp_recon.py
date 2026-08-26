"""Unit tests for primr.core.cli — keys / mcp / recon command dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.cli import (
    _is_keys_command,
    _is_recon_command,
)
from primr.core.cli_dispatch import is_mcp_command, run_mcp
from primr.core.cli_keys import run_keys

# ---------------------------------------------------------------------------
# Command predicates
# ---------------------------------------------------------------------------


class TestCommandPredicates:
    def test_keys_command_accepts_keys(self):
        assert _is_keys_command(["keys", "list"]) is True

    def test_keys_command_accepts_key_singular(self):
        assert _is_keys_command(["key", "list"]) is True

    def test_keys_command_rejects_other(self):
        assert _is_keys_command(["doctor"]) is False

    def test_keys_command_rejects_empty(self):
        assert _is_keys_command([]) is False

    def test_mcp_command_accepts_mcp(self):
        assert is_mcp_command(["mcp"]) is True

    def test_mcp_command_rejects_other(self):
        assert is_mcp_command(["other"]) is False

    def test_recon_command_accepts_recon(self):
        assert _is_recon_command(["recon", "acme.com"]) is True

    def test_recon_command_rejects_other(self):
        assert _is_recon_command(["doctor"]) is False


# ---------------------------------------------------------------------------
# _run_keys
# ---------------------------------------------------------------------------


class TestRunKeys:
    def test_path_action_returns_zero(self, monkeypatch):
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: "/user/.env")
        monkeypatch.setattr("primr.config.env.get_local_env_path", lambda: None)
        assert run_keys(["keys", "path"]) == 0

    def test_path_with_local_override(self, monkeypatch):
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: "/user/.env")
        monkeypatch.setattr("primr.config.env.get_local_env_path", lambda: "/project/.env")
        assert run_keys(["keys", "path"]) == 0

    def test_list_action_returns_zero(self, monkeypatch):
        monkeypatch.setattr("primr.config.env.get_user_env_path", lambda: "/user/.env")
        monkeypatch.setattr("primr.config.env.get_local_env_path", lambda: None)
        monkeypatch.setattr("primr.config.env.load_primr_env", lambda: None)
        monkeypatch.setattr("primr.config.env.mask_secret", lambda x: "***")
        monkeypatch.setattr(
            "primr.config.env.KEY_HELP",
            {"GEMINI_API_KEY": "Premium pipeline"},
        )
        assert run_keys(["keys", "list"]) == 0

    def test_set_with_explicit_value(self, monkeypatch):
        monkeypatch.setattr("primr.config.env.normalize_key_name", lambda p: f"{p.upper()}_API_KEY")
        monkeypatch.setattr(
            "primr.config.env.set_user_key",
            lambda p, v: (f"{p.upper()}_API_KEY", "/path/.env"),
        )
        monkeypatch.setattr("primr.config.env.mask_secret", lambda x: "***")
        result = run_keys(["keys", "set", "gemini", "AI" + "x" * 30])
        assert result == 0

    def test_set_with_empty_value_returns_1(self, monkeypatch):
        monkeypatch.setattr("primr.config.env.normalize_key_name", lambda p: f"{p.upper()}_API_KEY")
        result = run_keys(["keys", "set", "gemini", ""])
        assert result == 1

    def test_set_non_interactive_no_value_returns_1(self, monkeypatch):
        monkeypatch.setattr("primr.config.env.normalize_key_name", lambda p: f"{p.upper()}_API_KEY")
        monkeypatch.setattr("primr.core.cli_keys.can_prompt_for_input", lambda: False)
        result = run_keys(["keys", "set", "gemini"])
        assert result == 1

    @pytest.mark.parametrize("prompt_error", [EOFError(), OSError("closed"), ValueError("closed")])
    def test_set_handles_secret_prompt_failure(self, monkeypatch, prompt_error):
        monkeypatch.setattr("primr.config.env.normalize_key_name", lambda p: f"{p.upper()}_API_KEY")
        monkeypatch.setattr("primr.core.cli_keys.can_prompt_for_input", lambda: True)
        monkeypatch.setattr("getpass.getpass", MagicMock(side_effect=prompt_error))
        monkeypatch.setattr(
            "primr.config.env.set_user_key",
            lambda *_args, **_kwargs: pytest.fail("key must not be saved"),
        )

        assert run_keys(["keys", "set", "gemini"]) == 1

    def test_unset_removes_key(self, monkeypatch):
        monkeypatch.setattr(
            "primr.config.env.unset_user_key",
            lambda p: (f"{p.upper()}_API_KEY", "/path/.env", True),
        )
        result = run_keys(["keys", "unset", "gemini"])
        assert result == 0

    def test_unset_when_not_present(self, monkeypatch):
        monkeypatch.setattr(
            "primr.config.env.unset_user_key",
            lambda p: (f"{p.upper()}_API_KEY", "/path/.env", False),
        )
        result = run_keys(["keys", "unset", "gemini"])
        assert result == 0


# ---------------------------------------------------------------------------
# run_mcp
# ---------------------------------------------------------------------------


class TestRunMcp:
    def test_defaults_to_stdio_when_no_args(self, monkeypatch):
        mcp_main = MagicMock()
        # Patch the import target
        import primr.mcp_server.cli

        monkeypatch.setattr(primr.mcp_server.cli, "main", mcp_main)
        result = run_mcp(["mcp"])
        assert result == 0
        # sys.argv should have been temporarily set to include --stdio
        mcp_main.assert_called_once()

    def test_passes_through_extra_args(self, monkeypatch):
        mcp_main = MagicMock()
        import primr.mcp_server.cli

        monkeypatch.setattr(primr.mcp_server.cli, "main", mcp_main)
        result = run_mcp(["mcp", "--http", "--port", "8000"])
        assert result == 0

    def test_handles_sys_exit_with_code(self, monkeypatch):
        def main_raises():
            raise SystemExit(42)

        import primr.mcp_server.cli

        monkeypatch.setattr(primr.mcp_server.cli, "main", main_raises)
        result = run_mcp(["mcp"])
        assert result == 42

    def test_handles_sys_exit_with_none(self, monkeypatch):
        def main_raises():
            raise SystemExit(None)

        import primr.mcp_server.cli

        monkeypatch.setattr(primr.mcp_server.cli, "main", main_raises)
        result = run_mcp(["mcp"])
        assert result == 0
