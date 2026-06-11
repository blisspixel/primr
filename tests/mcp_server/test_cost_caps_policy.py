"""Tests for the tri-state MCP cost-cap enforcement policy (safe-by-default HTTP)."""

import pytest

from primr.mcp_server.cost_caps import is_cost_cap_enforced


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PRIMR_ENFORCE_MCP_COST_CAPS", raising=False)
    monkeypatch.delenv("PRIMR_MCP_TRANSPORT", raising=False)


class TestExplicitOverrides:
    @pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
    def test_explicit_truthy_enforces_everywhere(self, monkeypatch, value):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", value)
        monkeypatch.setenv("PRIMR_MCP_TRANSPORT", "stdio")
        assert is_cost_cap_enforced() is True

    @pytest.mark.parametrize("value", ["0", "false", "No", "OFF"])
    def test_explicit_falsy_disables_even_on_http(self, monkeypatch, value):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", value)
        monkeypatch.setenv("PRIMR_MCP_TRANSPORT", "streamable-http")
        assert is_cost_cap_enforced() is False


class TestTransportDefault:
    def test_unset_on_http_defaults_to_enforced(self, monkeypatch):
        monkeypatch.setenv("PRIMR_MCP_TRANSPORT", "streamable-http")
        assert is_cost_cap_enforced() is True

    def test_unset_on_stdio_defaults_to_unenforced(self, monkeypatch):
        monkeypatch.setenv("PRIMR_MCP_TRANSPORT", "stdio")
        assert is_cost_cap_enforced() is False

    def test_unset_with_no_transport_signal_is_unenforced(self):
        assert is_cost_cap_enforced() is False

    def test_unrecognized_override_value_falls_back_to_transport(self, monkeypatch):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "maybe")
        monkeypatch.setenv("PRIMR_MCP_TRANSPORT", "streamable-http")
        assert is_cost_cap_enforced() is True


class TestServerPublishesTransport:
    def test_http_server_sets_transport_env(self, monkeypatch, tmp_path):
        import os

        from primr.mcp_server.server import PrimrMCPServer

        monkeypatch.delenv("PRIMR_MCP_TRANSPORT", raising=False)
        PrimrMCPServer(
            transport="streamable-http",
            journal_path=str(tmp_path / "journal.json"),
        )
        assert os.environ.get("PRIMR_MCP_TRANSPORT") == "streamable-http"
        assert is_cost_cap_enforced() is True

    def test_stdio_server_sets_transport_env(self, monkeypatch, tmp_path):
        import os

        from primr.mcp_server.server import PrimrMCPServer

        monkeypatch.delenv("PRIMR_MCP_TRANSPORT", raising=False)
        PrimrMCPServer(transport="stdio", journal_path=str(tmp_path / "journal.json"))
        assert os.environ.get("PRIMR_MCP_TRANSPORT") == "stdio"
        assert is_cost_cap_enforced() is False
