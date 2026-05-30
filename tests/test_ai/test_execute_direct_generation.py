"""Unit tests for DeepResearchOrchestrator._execute_direct_generation
and get_deep_research_orchestrator singleton."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import (
    DeepResearchOrchestrator,
    ResearchStatus,
    get_deep_research_orchestrator,
)


@pytest.fixture
def orchestrator(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


class TestExecuteDirectGeneration:
    @pytest.mark.asyncio
    async def test_happy_path_returns_completed(self, orchestrator):
        response = MagicMock()
        response.text = "generated content body"
        orchestrator._client.models.generate_content.return_value = response

        before = orchestrator._api_call_count
        result = await orchestrator._execute_direct_generation("prompt")
        assert result.status == ResearchStatus.COMPLETED
        assert result.content == "generated content body"
        assert orchestrator._api_call_count == before + 1

    @pytest.mark.asyncio
    async def test_extracts_from_parts_when_no_text(self, orchestrator):
        response = MagicMock(spec=["parts"])
        part1 = MagicMock()
        part1.text = "part 1"
        part2 = MagicMock()
        part2.text = "part 2"
        response.parts = [part1, part2]
        orchestrator._client.models.generate_content.return_value = response

        result = await orchestrator._execute_direct_generation("prompt")
        assert "part 1" in result.content
        assert "part 2" in result.content

    @pytest.mark.asyncio
    async def test_empty_content_returns_failed(self, orchestrator):
        response = MagicMock(spec=["text"])
        response.text = ""
        orchestrator._client.models.generate_content.return_value = response

        result = await orchestrator._execute_direct_generation("prompt")
        assert result.status == ResearchStatus.FAILED
        assert "Empty response" in result.error

    @pytest.mark.asyncio
    async def test_rate_limit_marked_specifically(self, orchestrator):
        orchestrator._client.models.generate_content.side_effect = RuntimeError(
            "429 quota exceeded"
        )
        result = await orchestrator._execute_direct_generation("prompt")
        assert result.status == ResearchStatus.FAILED
        assert "Rate limited" in result.error

    @pytest.mark.asyncio
    async def test_generic_failure_propagates_message(self, orchestrator):
        orchestrator._client.models.generate_content.side_effect = RuntimeError("some other error")
        result = await orchestrator._execute_direct_generation("prompt")
        assert result.status == ResearchStatus.FAILED
        assert "some other error" in result.error


class TestGetOrchestratorSingleton:
    def test_returns_same_instance_on_repeated_calls(self, monkeypatch):
        import primr.ai.deep_research as dr

        # Reset the singleton.
        monkeypatch.setattr(dr, "_orchestrator", None)
        mock_genai = MagicMock()
        mock_genai.Client.return_value = MagicMock()
        monkeypatch.setattr(dr, "genai", mock_genai)
        monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)

        first = get_deep_research_orchestrator()
        second = get_deep_research_orchestrator()
        assert first is second
