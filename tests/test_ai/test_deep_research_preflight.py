"""Tests for DeepResearchClient.research preflight validation branches.

These exercise the pre-API-call validation logic in polling mode (lines 365-441):
empty query, missing API key, missing/empty/unreadable context files, invalid URLs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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
    c = DeepResearchClient(api_key="fake-key-1234567890")
    # Force polling mode by making streaming raise so it falls through.
    c.research_resilient = AsyncMock(side_effect=RuntimeError("streaming disabled"))
    return c


@pytest.mark.asyncio
async def test_empty_query_raises_preflight_error(client):
    with pytest.raises(AIError) as exc_info:
        await client.research("")
    assert "Pre-flight" in str(exc_info.value) or "query" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_whitespace_query_raises_preflight_error(client):
    with pytest.raises(AIError) as exc_info:
        await client.research("   \n   ")
    assert "Pre-flight" in str(exc_info.value) or "query" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_missing_api_key_raises_preflight_error(client):
    client._api_key = ""
    with pytest.raises(AIError) as exc_info:
        await client.research("real query about Acme")
    assert "API key" in str(exc_info.value) or "Pre-flight" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_context_file_raises(client, tmp_path):
    bogus = tmp_path / "no_such.txt"
    with pytest.raises(AIError) as exc_info:
        await client.research("query", context_files=[str(bogus)])
    assert "not found" in str(exc_info.value).lower() or "Pre-flight" in str(exc_info.value)


@pytest.mark.asyncio
async def test_empty_context_file_raises(client, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    with pytest.raises(AIError) as exc_info:
        await client.research("query", context_files=[str(empty)])
    assert "empty" in str(exc_info.value).lower() or "Pre-flight" in str(exc_info.value)


@pytest.mark.asyncio
async def test_directory_as_context_file_raises(client, tmp_path):
    # Pass a directory path (not a file)
    with pytest.raises(AIError) as exc_info:
        await client.research("query", context_files=[str(tmp_path)])
    assert "not a file" in str(exc_info.value).lower() or "Pre-flight" in str(exc_info.value)


@pytest.mark.asyncio
async def test_invalid_priority_url_raises(client):
    with pytest.raises(AIError) as exc_info:
        await client.research(
            "query about Acme",
            priority_urls=["not-a-url.example"],
        )
    assert "URL format" in str(exc_info.value) or "Pre-flight" in str(exc_info.value)
