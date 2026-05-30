"""Tests for DeepResearchClient.research_stream — async generator over stream chunks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import (
    DeepResearchClient,
    ResearchStatus,
)


def _chunk(event_type: str, **kwargs):
    c = MagicMock()
    c.event_type = event_type
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


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


@pytest.mark.asyncio
async def test_stream_yields_completion(client):
    chunks = [_chunk("interaction.complete")]
    client._start_research_stream = MagicMock(return_value=iter(chunks))
    results = []
    async for prog in client.research_stream("query"):
        results.append(prog)
    assert any(p.status == ResearchStatus.COMPLETED for p in results)


@pytest.mark.asyncio
async def test_stream_yields_text_delta(client):
    text_delta = MagicMock()
    text_delta.type = "text"
    text_delta.text = "hello"
    chunks = [
        _chunk("content.delta", delta=text_delta),
        _chunk("interaction.complete"),
    ]
    client._start_research_stream = MagicMock(return_value=iter(chunks))
    results = []
    async for prog in client.research_stream("query"):
        results.append(prog)
    partial = [p for p in results if p.partial_result]
    assert partial
    assert partial[0].partial_result == "hello"


@pytest.mark.asyncio
async def test_stream_yields_thought_summary(client):
    thought_delta = MagicMock()
    thought_delta.type = "thought_summary"
    thought_delta.content = MagicMock(text="thinking deeply")
    chunks = [
        _chunk("content.delta", delta=thought_delta),
        _chunk("interaction.complete"),
    ]
    client._start_research_stream = MagicMock(return_value=iter(chunks))
    results = []
    async for prog in client.research_stream("query"):
        results.append(prog)
    thoughts = [p for p in results if p.thought]
    assert thoughts
    assert thoughts[0].thought == "thinking deeply"


@pytest.mark.asyncio
async def test_stream_yields_error_chunk(client):
    chunks = [_chunk("error")]
    client._start_research_stream = MagicMock(return_value=iter(chunks))
    results = []
    async for prog in client.research_stream("query"):
        results.append(prog)
    failed = [p for p in results if p.status == ResearchStatus.FAILED]
    assert failed


@pytest.mark.asyncio
async def test_stream_catches_exception(client):
    client._start_research_stream = MagicMock(side_effect=RuntimeError("connection lost"))
    results = []
    async for prog in client.research_stream("query"):
        results.append(prog)
    assert any(p.status == ResearchStatus.FAILED for p in results)
    assert any("Stream error" in (p.message or "") for p in results)


@pytest.mark.asyncio
async def test_stream_ignores_interaction_start(client):
    chunks = [
        _chunk("interaction.start"),
        _chunk("interaction.complete"),
    ]
    client._start_research_stream = MagicMock(return_value=iter(chunks))
    results = []
    async for prog in client.research_stream("query"):
        results.append(prog)
    # Only the completion event yields
    assert len(results) == 1
    assert results[0].status == ResearchStatus.COMPLETED
