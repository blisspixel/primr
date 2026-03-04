"""Edge case and validation tests for A2A module."""

from unittest.mock import MagicMock, patch

import pytest

from primr.a2a.client import A2AClient, A2AError
from primr.a2a.hooks import DELEGATE_TOOL_NAME, A2AExternalAgentHook
from primr.a2a.types import A2ATaskMapping, ExternalAgentConfig
from primr.agentic.hooks import HookContext, HookResult, HookType


class TestExternalAgentConfigValidation:
    """Edge cases for ExternalAgentConfig."""

    def test_whitespace_only_url_raises(self):
        with pytest.raises(ValueError):
            ExternalAgentConfig(url="   ", name="Test")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValueError):
            ExternalAgentConfig(url="http://example.com", name="   ")

    def test_negative_timeout(self):
        """Negative timeout is accepted (no validation, httpx will handle)."""
        config = ExternalAgentConfig(url="http://example.com", name="Test", timeout=-1.0)
        assert config.timeout == -1.0

    def test_skills_is_independent_list(self):
        """Skills list is independent per instance."""
        c1 = ExternalAgentConfig(url="http://a.com", name="A")
        c2 = ExternalAgentConfig(url="http://b.com", name="B")
        c1.skills.append("research")
        assert c2.skills == []


class TestA2ATaskMappingEdgeCases:
    """Edge cases for A2ATaskMapping."""

    def test_from_dict_with_string_created_at(self):
        mapping = A2ATaskMapping.from_dict({
            "task_id": "t-1",
            "job_id": "j-1",
            "skill_id": "check",
            "created_at": "2026-01-15T10:30:00+00:00",
        })
        assert mapping.created_at.year == 2026

    def test_from_dict_preserves_timezone(self):
        mapping = A2ATaskMapping.from_dict({
            "task_id": "t-1",
            "job_id": "j-1",
            "skill_id": "check",
            "created_at": "2026-01-15T10:30:00+05:00",
        })
        assert mapping.created_at.utcoffset() is not None

    def test_to_dict_created_at_is_iso(self):
        mapping = A2ATaskMapping(task_id="t-1", job_id="j-1", skill_id="check")
        d = mapping.to_dict()
        # Should be valid ISO format
        from datetime import datetime
        datetime.fromisoformat(d["created_at"])


class TestA2AClientEdgeCases:
    """Edge cases for A2AClient."""

    def test_url_without_trailing_slash(self):
        client = A2AClient(agent_url="http://example.com")
        assert client.agent_url == "http://example.com"

    def test_url_with_path(self):
        client = A2AClient(agent_url="http://example.com/api/v1/")
        assert client.agent_url == "http://example.com/api/v1"

    def test_auth_header_included(self):
        """Auth token sets Bearer header on client creation."""
        client = A2AClient(agent_url="http://example.com", auth_token="my-token")
        assert client.auth_token == "my-token"

    def test_jsonrpc_ids_are_unique(self):
        """Each JSON-RPC message gets a unique ID."""
        client = A2AClient(agent_url="http://example.com")
        ids = [client._build_jsonrpc("test", {})["id"] for _ in range(100)]
        assert len(set(ids)) == 100

    def test_jsonrpc_method_preserved(self):
        client = A2AClient(agent_url="http://example.com")
        for method in ["message/send", "message/stream", "tasks/get", "tasks/cancel"]:
            msg = client._build_jsonrpc(method, {})
            assert msg["method"] == method


class TestA2AHookEdgeCases:
    """Edge cases for A2A hooks."""

    @pytest.mark.asyncio
    async def test_empty_agent_url(self):
        """Empty agent URL is caught by SSRF check."""
        hook = A2AExternalAgentHook()
        ctx = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=DELEGATE_TOOL_NAME,
            arguments={"agent_url": ""},
        )
        result = await hook.execute(ctx)
        assert result.result == HookResult.BLOCK

    @pytest.mark.asyncio
    async def test_missing_agent_url_key(self):
        """Missing agent_url defaults to empty string, caught by SSRF."""
        hook = A2AExternalAgentHook()
        ctx = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=DELEGATE_TOOL_NAME,
            arguments={},
        )
        result = await hook.execute(ctx)
        assert result.result == HookResult.BLOCK

    @pytest.mark.asyncio
    async def test_ftp_scheme_blocked(self):
        """Non-HTTP schemes are blocked."""
        hook = A2AExternalAgentHook()
        ctx = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=DELEGATE_TOOL_NAME,
            arguments={"agent_url": "ftp://evil.com/agent"},
        )
        result = await hook.execute(ctx)
        assert result.result == HookResult.BLOCK

    @pytest.mark.asyncio
    async def test_metadata_endpoint_blocked(self):
        """Cloud metadata endpoints are blocked."""
        hook = A2AExternalAgentHook()
        for url in [
            "http://169.254.169.254/",
            "http://metadata.google.internal/",
        ]:
            ctx = HookContext(
                hook_type=HookType.PRE_TOOL_USE,
                tool_name=DELEGATE_TOOL_NAME,
                arguments={"agent_url": url},
            )
            result = await hook.execute(ctx)
            assert result.result == HookResult.BLOCK, f"Expected BLOCK for {url}"

    @pytest.mark.asyncio
    async def test_budget_exactly_at_limit(self):
        """Budget check blocks at exactly the limit (spent >= max)."""
        hook = A2AExternalAgentHook(max_cost_usd=5.0)
        hook.record_cost(5.0)

        ctx = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=DELEGATE_TOOL_NAME,
            arguments={"agent_url": "https://agent.example.com"},
        )
        with patch("primr.a2a.hooks.URLValidator") as MockValidator:
            MockValidator.return_value.validate.return_value = MagicMock(valid=True)
            result = await hook.execute(ctx)
        assert result.result == HookResult.BLOCK

    @pytest.mark.asyncio
    async def test_budget_just_under_limit(self):
        """Budget check allows when just under limit."""
        hook = A2AExternalAgentHook(max_cost_usd=5.0)
        hook.record_cost(4.99)

        ctx = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=DELEGATE_TOOL_NAME,
            arguments={"agent_url": "https://agent.example.com"},
        )
        with patch("primr.a2a.hooks.URLValidator") as MockValidator:
            MockValidator.return_value.validate.return_value = MagicMock(valid=True)
            result = await hook.execute(ctx)
        assert result.result == HookResult.ALLOW

    def test_cost_accumulates(self):
        """Multiple record_cost calls accumulate."""
        hook = A2AExternalAgentHook(max_cost_usd=10.0)
        for _ in range(10):
            hook.record_cost(0.5)
        assert hook.spent == pytest.approx(5.0)
        assert hook.remaining == pytest.approx(5.0)


class TestA2AErrorClass:
    """Tests for A2AError exception."""

    def test_basic_error(self):
        err = A2AError("test error")
        assert str(err) == "test error"
        assert err.code is None
        assert err.data is None

    def test_error_with_code(self):
        err = A2AError("bad request", code=-32600)
        assert err.code == -32600

    def test_error_with_data(self):
        err = A2AError("error", data={"detail": "info"})
        assert err.data == {"detail": "info"}

    def test_error_is_exception(self):
        with pytest.raises(A2AError, match="test"):
            raise A2AError("test")
