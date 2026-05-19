"""Tests for DeepResearchClient.research_resilient pre-flight branches.

These exercise the simple pre-flight checks at the top of research_resilient
(lines 1126-1140): empty query, missing API key, missing context file.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import DeepResearchClient
from primr.utils.errors import AIError


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
async def test_empty_query_fails_preflight(client):
    with pytest.raises(AIError) as exc_info:
        await client.research_resilient("")
    assert "Pre-flight" in str(exc_info.value) or "query" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_whitespace_query_fails_preflight(client):
    with pytest.raises(AIError) as exc_info:
        await client.research_resilient("   ")
    assert "Pre-flight" in str(exc_info.value) or "query" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_missing_api_key_fails_preflight(client):
    client._api_key = ""
    with pytest.raises(AIError) as exc_info:
        await client.research_resilient("good query about Acme")
    assert "API key" in str(exc_info.value) or "Pre-flight" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_context_file_fails_preflight(client, tmp_path):
    bogus = tmp_path / "missing.txt"
    with pytest.raises(AIError) as exc_info:
        await client.research_resilient("query", context_files=[str(bogus)])
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_multiple_preflight_errors_all_reported(client):
    client._api_key = ""
    with pytest.raises(AIError) as exc_info:
        await client.research_resilient("")
    msg = str(exc_info.value)
    # Both errors should be in the message
    assert "query" in msg.lower()
    assert "API key" in msg or "api key" in msg
