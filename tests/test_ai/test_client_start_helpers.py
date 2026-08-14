"""Unit tests for DeepResearchClient._start_research and _start_research_stream."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import DeepResearchClient


@pytest.fixture
def client(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchClient(api_key="fake-key-1234567890")


class TestStartResearch:
    def test_minimal_call_without_file_store(self, client):
        client._client.interactions.create.return_value = MagicMock(id="iid-1")
        client._start_research("research prompt")
        kwargs = client._client.interactions.create.call_args.kwargs
        assert kwargs["input"] == "research prompt"
        assert kwargs["agent"] == client.AGENT_ID
        assert kwargs["background"] is True
        assert kwargs["store"] is True
        assert "tools" not in kwargs

    def test_with_file_store_adds_tool(self, client):
        client._client.interactions.create.return_value = MagicMock(id="iid-1")
        client._start_research("prompt", file_store_name="stores/abc")
        kwargs = client._client.interactions.create.call_args.kwargs
        assert "tools" in kwargs
        tools = kwargs["tools"]
        assert tools[0]["type"] == "file_search"
        assert tools[0]["file_search_store_names"] == ["stores/abc"]

    def test_disable_model_calls_blocks_start(self, client):
        from primr.utils.model_policy import ModelCallsDisabledError, disable_model_calls

        with disable_model_calls(), pytest.raises(ModelCallsDisabledError, match="deep research"):
            client._start_research("research prompt")
        client._client.interactions.create.assert_not_called()


class TestStartResearchStream:
    def test_includes_stream_and_thinking_summaries(self, client):
        client._client.interactions.create.return_value = MagicMock()
        client._start_research_stream("research prompt")
        kwargs = client._client.interactions.create.call_args.kwargs
        assert kwargs["stream"] is True
        assert kwargs["agent"] == client.AGENT_ID
        assert kwargs["background"] is True
        assert kwargs["store"] is True
        assert kwargs["agent_config"]["type"] == "deep-research"
        assert kwargs["agent_config"]["thinking_summaries"] == "auto"

    def test_disable_model_calls_blocks_stream_start(self, client):
        from primr.utils.model_policy import ModelCallsDisabledError, disable_model_calls

        with disable_model_calls(), pytest.raises(ModelCallsDisabledError, match="deep research"):
            client._start_research_stream("research prompt")
        client._client.interactions.create.assert_not_called()
