"""Tests for the tri-state MCP cost-cap enforcement policy (safe-by-default HTTP)."""

import pytest

from primr.mcp_server.cost_caps import is_cost_cap_enforced, set_active_transport


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("PRIMR_ENFORCE_MCP_COST_CAPS", raising=False)
    monkeypatch.delenv("PRIMR_MCP_TRANSPORT", raising=False)
    set_active_transport(None)
    yield
    set_active_transport(None)


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


class TestTransportPublication:
    def test_active_transport_http_enforces(self):
        set_active_transport("streamable-http")
        assert is_cost_cap_enforced() is True

    def test_active_transport_stdio_does_not_enforce(self):
        set_active_transport("stdio")
        assert is_cost_cap_enforced() is False

    def test_env_transport_fallback_when_no_server(self, monkeypatch):
        # Deploy manifests can still signal transport via env when policy is
        # checked without an in-process server having called run().
        monkeypatch.setenv("PRIMR_MCP_TRANSPORT", "streamable-http")
        assert is_cost_cap_enforced() is True

    def test_constructing_a_server_does_not_change_policy(self, tmp_path):
        # Construction must be side-effect free: only run() publishes the
        # transport. Tests across the suite construct servers freely; that
        # must never flip process-wide enforcement.
        from primr.mcp_server.server import PrimrMCPServer

        PrimrMCPServer(
            transport="streamable-http",
            journal_path=str(tmp_path / "journal.json"),
        )
        assert is_cost_cap_enforced() is False

    @pytest.mark.asyncio
    async def test_run_publishes_transport(self, tmp_path, monkeypatch):
        from primr.mcp_server.server import PrimrMCPServer

        server = PrimrMCPServer(
            transport="streamable-http",
            journal_path=str(tmp_path / "journal.json"),
        )

        async def fake_http(self):
            return None

        monkeypatch.setattr(PrimrMCPServer, "run_http", fake_http)
        await server.run()
        assert is_cost_cap_enforced() is True
