"""
Coverage tests for agentic tool handlers (agentic_tools.py).

These tests exercise query_roadmap, get_hypotheses, and save_hypothesis
handlers through the public dispatcher, using a temp memory path so no
real LLM/network calls occur.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from primr.mcp_server.agentic_tools import (
    handle_agentic_tool,
    register_agentic_tools,
)


@pytest.fixture
def mcp_server_stub():
    """Minimal mcp_server stub with a temp memory path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        stub = MagicMock()
        stub._memory_path = Path(tmpdir) / "research_memory"
        yield stub


def _text(result):
    return json.loads(result[0].text)


class TestRegisterAgenticTools:
    def test_register_returns_three_tools(self):
        tools = register_agentic_tools(MagicMock(), MagicMock())
        names = [t.name for t in tools]
        assert "query_roadmap" in names
        assert "get_hypotheses" in names
        assert "save_hypothesis" in names


class TestDispatch:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_none(self, mcp_server_stub):
        result = await handle_agentic_tool("not_an_agentic_tool", {}, mcp_server_stub)
        assert result is None


class TestQueryRoadmap:
    @pytest.mark.asyncio
    async def test_query_roadmap_default_summary(self, mcp_server_stub):
        """Empty query returns full roadmap JSON summary."""
        result = await handle_agentic_tool("query_roadmap", {}, mcp_server_stub)
        # Should be valid JSON (roadmap summary)
        data = json.loads(result[0].text)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_query_roadmap_specific_version_not_found(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "query_roadmap", {"version": "v99.99.99"}, mcp_server_stub
        )
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "version_not_found"

    @pytest.mark.asyncio
    async def test_query_roadmap_in_progress(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "query_roadmap", {"query": "what is in progress"}, mcp_server_stub
        )
        data = _text(result)
        assert data["status"] == "in_progress"
        assert "versions" in data

    @pytest.mark.asyncio
    async def test_query_roadmap_planned(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "query_roadmap", {"query": "what is planned"}, mcp_server_stub
        )
        data = _text(result)
        assert data["status"] == "planned"

    @pytest.mark.asyncio
    async def test_query_roadmap_completed(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "query_roadmap", {"query": "what is completed"}, mcp_server_stub
        )
        data = _text(result)
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_query_roadmap_blockers_with_version(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "query_roadmap", {"query": "what is blocking v1.x"}, mcp_server_stub
        )
        data = _text(result)
        assert data == {"version": "1.x", "blockers": []}

    @pytest.mark.asyncio
    async def test_query_roadmap_handles_exception(self, mcp_server_stub, monkeypatch):
        """A failure inside RoadmapAPI is captured as a structured error."""
        import primr.agentic.roadmap_api as roadmap_api

        class BoomAPI:
            def __init__(self, *a, **k):
                raise RuntimeError("boom")

        monkeypatch.setattr(roadmap_api, "RoadmapAPI", BoomAPI)
        result = await handle_agentic_tool("query_roadmap", {}, mcp_server_stub)
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "roadmap_query_failed"


class TestGetHypotheses:
    @pytest.mark.asyncio
    async def test_get_hypotheses_empty(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "get_hypotheses", {"company": "Acme Corp"}, mcp_server_stub
        )
        data = _text(result)
        assert data["company"] == "Acme Corp"
        assert data["count"] == 0
        assert data["hypotheses"] == []

    @pytest.mark.asyncio
    async def test_get_hypotheses_invalid_confidence(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "get_hypotheses",
            {"company": "Acme Corp", "confidence": "bogus"},
            mcp_server_stub,
        )
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_confidence"

    @pytest.mark.asyncio
    async def test_get_hypotheses_with_confidence_filter(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "get_hypotheses",
            {"company": "Acme Corp", "confidence": "validated", "topic": "tech"},
            mcp_server_stub,
        )
        data = _text(result)
        assert data["company"] == "Acme Corp"
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_hypotheses_default_memory_path(self, monkeypatch, tmp_path):
        """When _memory_path is absent, the default path is used."""
        stub = MagicMock(spec=[])  # no _memory_path attribute
        monkeypatch.setenv("PRIMR_DATA_DIR", str(tmp_path / "data"))
        result = await handle_agentic_tool("get_hypotheses", {"company": "X"}, stub)
        data = _text(result)
        assert data["company"] == "X"

    @pytest.mark.asyncio
    async def test_get_hypotheses_handles_exception(self, mcp_server_stub, monkeypatch):
        import primr.agentic.memory as memory_mod

        class BoomMemory:
            def __init__(self, *a, **k):
                raise RuntimeError("kaboom")

        monkeypatch.setattr(memory_mod, "ResearchMemory", BoomMemory)
        result = await handle_agentic_tool("get_hypotheses", {"company": "Acme"}, mcp_server_stub)
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "get_hypotheses_failed"


class TestSaveHypothesis:
    @pytest.mark.asyncio
    async def test_create_new_hypothesis(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "save_hypothesis",
            {
                "company": "Acme Corp",
                "hypothesis_id": "h_001",
                "claim": "Acme uses microservices",
                "confidence": "untested",
                "topic": "technology",
            },
            mcp_server_stub,
        )
        data = _text(result)
        assert data["success"] is True
        assert data["action"] == "created"
        assert data["hypothesis_id"] == "h_001"

    @pytest.mark.asyncio
    async def test_create_new_hypothesis_requires_claim(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "save_hypothesis",
            {"company": "Acme Corp", "hypothesis_id": "h_no_claim"},
            mcp_server_stub,
        )
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "claim_required"

    @pytest.mark.asyncio
    async def test_invalid_confidence(self, mcp_server_stub):
        result = await handle_agentic_tool(
            "save_hypothesis",
            {
                "company": "Acme Corp",
                "hypothesis_id": "h_002",
                "claim": "test",
                "confidence": "nonsense",
            },
            mcp_server_stub,
        )
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_confidence"

    @pytest.mark.asyncio
    async def test_update_existing_with_evidence(self, mcp_server_stub):
        # First create
        await handle_agentic_tool(
            "save_hypothesis",
            {
                "company": "Acme Corp",
                "hypothesis_id": "h_update",
                "claim": "Acme is profitable",
                "confidence": "untested",
            },
            mcp_server_stub,
        )
        # Then update with evidence
        result = await handle_agentic_tool(
            "save_hypothesis",
            {
                "company": "Acme Corp",
                "hypothesis_id": "h_update",
                "confidence": "validated",
                "evidence": "Q4 earnings positive",
            },
            mcp_server_stub,
        )
        data = _text(result)
        assert data["success"] is True
        assert data["action"] == "updated"
        assert data["confidence"] == "validated"

    @pytest.mark.asyncio
    async def test_update_existing_without_evidence(self, mcp_server_stub):
        await handle_agentic_tool(
            "save_hypothesis",
            {
                "company": "Acme Corp",
                "hypothesis_id": "h_noev",
                "claim": "claim text",
                "confidence": "untested",
            },
            mcp_server_stub,
        )
        result = await handle_agentic_tool(
            "save_hypothesis",
            {
                "company": "Acme Corp",
                "hypothesis_id": "h_noev",
                "confidence": "validated",
            },
            mcp_server_stub,
        )
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "evidence_required"

    @pytest.mark.asyncio
    async def test_save_hypothesis_handles_exception(self, mcp_server_stub, monkeypatch):
        import primr.agentic.memory as memory_mod

        class BoomMemory:
            def __init__(self, *a, **k):
                raise RuntimeError("explode")

        monkeypatch.setattr(memory_mod, "ResearchMemory", BoomMemory)
        result = await handle_agentic_tool(
            "save_hypothesis",
            {"company": "Acme", "hypothesis_id": "h_x", "claim": "c"},
            mcp_server_stub,
        )
        data = _text(result)
        assert data["error"] is True
        assert data["error_type"] == "save_hypothesis_failed"
