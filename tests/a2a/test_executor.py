"""Tests for A2A agent executor."""

import json
from unittest.mock import MagicMock, patch

import pytest

a2a = pytest.importorskip("a2a")

from primr.a2a.executor import (
    PrimrAgentExecutor,
    _extract_skill_id,
    _extract_text,
    _parse_research_params,
)
from primr.a2a.task_store import PrimrTaskStore


class TestExtractSkillId:
    """Tests for _extract_skill_id helper."""

    def test_from_dict_message(self):
        msg = {"metadata": {"skillId": "research_company"}}
        assert _extract_skill_id(msg) == "research_company"

    def test_from_dict_no_metadata(self):
        msg = {"parts": [{"kind": "text", "text": "hello"}]}
        assert _extract_skill_id(msg) is None

    def test_from_object_with_metadata(self):
        msg = MagicMock()
        msg.metadata = {"skillId": "check_jobs"}
        assert _extract_skill_id(msg) == "check_jobs"

    def test_from_none_metadata(self):
        msg = MagicMock()
        msg.metadata = None
        assert _extract_skill_id(msg) is None


class TestExtractText:
    """Tests for _extract_text helper."""

    def test_from_dict_parts(self):
        msg = {"parts": [{"kind": "text", "text": "hello world"}]}
        assert _extract_text(msg) == "hello world"

    def test_multiple_parts(self):
        msg = {
            "parts": [
                {"kind": "text", "text": "hello"},
                {"kind": "text", "text": "world"},
            ]
        }
        assert _extract_text(msg) == "hello world"

    def test_ignores_non_text_parts(self):
        msg = {
            "parts": [
                {"kind": "file", "uri": "data:..."},
                {"kind": "text", "text": "text only"},
            ]
        }
        assert _extract_text(msg) == "text only"

    def test_empty_message(self):
        assert _extract_text({}) == ""
        assert _extract_text("not a dict") == ""


class TestParseResearchParams:
    """Tests for _parse_research_params helper."""

    def test_json_params(self):
        text = json.dumps({"url": "http://example.com", "mode": "deep"})
        params = _parse_research_params(text)
        assert params["url"] == "http://example.com"
        assert params["mode"] == "deep"

    def test_url_extraction(self):
        text = "Research Acme at https://acme.com please"
        params = _parse_research_params(text)
        assert params["url"] == "https://acme.com"

    def test_mode_extraction(self):
        text = "Run deep research on https://example.com"
        params = _parse_research_params(text)
        assert params["mode"] == "deep"

    def test_no_url(self):
        text = "What is the status?"
        params = _parse_research_params(text)
        assert "url" not in params

    def test_empty_text(self):
        params = _parse_research_params("")
        assert params == {}


class TestPrimrAgentExecutor:
    """Tests for PrimrAgentExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with mocked MCP server."""
        from primr.mcp_server.server import create_mcp_server

        journal_path = str(tmp_path / "journal.json")
        mcp_server = create_mcp_server(
            journal_path=journal_path,
            skip_background_tasks=True,
        )

        task_store = PrimrTaskStore(mcp_server.job_store)
        executor = PrimrAgentExecutor(mcp_server, task_store)
        return executor

    @pytest.fixture
    def event_queue(self):
        """Create a mock EventQueue."""
        queue = MagicMock()
        queue.enqueue_event = MagicMock()
        return queue

    @pytest.fixture
    def context(self):
        """Create a mock RequestContext."""
        ctx = MagicMock()
        ctx.message = {
            "parts": [{"kind": "text", "text": "test"}],
            "messageId": "msg-1",
        }
        ctx.task_id = None
        return ctx

    @pytest.mark.asyncio
    async def test_handle_unknown_skill(self, executor, event_queue, context):
        """Unknown skill returns available skills list."""
        context.message["metadata"] = {"skillId": "unknown_skill"}
        await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_handle_check_jobs_no_active(self, executor, event_queue, context):
        """check_jobs with no active job returns idle."""
        context.message["metadata"] = {"skillId": "check_jobs"}
        await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_handle_doctor(self, executor, event_queue, context):
        """system_health dispatches to doctor."""
        context.message["metadata"] = {"skillId": "system_health"}
        with patch("primr.a2a.executor.get_doctor_status", return_value={"healthy": True}):
            await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_handle_estimate_no_url(self, executor, event_queue, context):
        """estimate_research without URL asks for one."""
        context.message = {
            "parts": [{"kind": "text", "text": "estimate something"}],
            "metadata": {"skillId": "estimate_research"},
        }
        await executor.execute(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_no_task(self, executor, event_queue, context):
        """Cancel with no task_id returns message."""
        context.task_id = None
        await executor.cancel(context, event_queue)
        event_queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_unknown_task(self, executor, event_queue, context):
        """Cancel with unknown task returns message."""
        context.task_id = "nonexistent-task"
        await executor.cancel(context, event_queue)
        event_queue.enqueue_event.assert_called()
