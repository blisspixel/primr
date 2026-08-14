"""Tests for DeepResearchOrchestrator.generate_report — single-call architecture."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from primr.ai.deep_research import (
    DeepResearchOrchestrator,
    ResearchResult,
    ResearchStatus,
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

    o = DeepResearchOrchestrator(api_key="fake-key-1234567890")
    # Patch the store manager to a controllable mock
    o._store_manager = MagicMock()
    return o


@pytest.mark.asyncio
async def test_success_without_stage1_context(orchestrator):
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="report body",
            citations=[{"title": "x", "url": "https://x.example"}],
            interaction_id="iid-1",
            duration_seconds=10.0,
            status=ResearchStatus.COMPLETED,
            search_queries_count=4,
        )
    )
    result = await orchestrator.generate_report(
        company_name="Acme",
        website_url="https://acme.example",
    )
    assert result.success is True
    assert result.content == "report body"
    assert result.search_queries_count == 4
    # No store created since no stage1 context
    orchestrator._store_manager.create_store.assert_not_called()
    orchestrator._store_manager.delete_store.assert_not_called()


@pytest.mark.asyncio
async def test_success_with_stage1_context_creates_and_deletes_store(orchestrator):
    orchestrator._store_manager.create_store.return_value = "stores/research_Acme"
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="report body",
            citations=[],
            interaction_id="iid-1",
            duration_seconds=5.0,
            status=ResearchStatus.COMPLETED,
        )
    )
    result = await orchestrator.generate_report(
        company_name="Acme",
        website_url="https://acme.example",
        stage1_context="some structured context",
    )
    assert result.success is True
    orchestrator._store_manager.create_store.assert_called_once()
    orchestrator._store_manager.upload_context.assert_called_once()
    orchestrator._store_manager.delete_store.assert_called_once()


@pytest.mark.asyncio
async def test_execute_raises_exception_returns_failure(orchestrator):
    orchestrator._execute_with_retry = AsyncMock(side_effect=RuntimeError("API failure"))
    result = await orchestrator.generate_report(
        company_name="Acme",
        website_url="https://acme.example",
    )
    assert result.success is False
    assert "API failure" in (result.error or "")
    assert result.content == ""


@pytest.mark.asyncio
async def test_progress_callback_invoked(orchestrator):
    progress_messages = []
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="report",
            citations=[],
            interaction_id="iid-1",
            duration_seconds=1.0,
            status=ResearchStatus.COMPLETED,
        )
    )
    await orchestrator.generate_report(
        company_name="Acme",
        on_progress=progress_messages.append,
    )
    # Should have emitted at least one progress message
    assert progress_messages


@pytest.mark.asyncio
async def test_failure_from_execute_propagates(orchestrator):
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="",
            status=ResearchStatus.FAILED,
            error="quota exceeded",
        )
    )
    result = await orchestrator.generate_report(company_name="Acme")
    assert result.success is False
    assert result.error == "quota exceeded"


@pytest.mark.asyncio
async def test_store_deleted_on_exception(orchestrator):
    orchestrator._store_manager.create_store.return_value = "stores/abc"
    orchestrator._execute_with_retry = AsyncMock(side_effect=RuntimeError("boom"))
    await orchestrator.generate_report(
        company_name="Acme",
        stage1_context="context",
    )
    # Store cleanup happens in finally regardless of exception
    orchestrator._store_manager.delete_store.assert_called_once_with("stores/abc")


@pytest.mark.asyncio
async def test_pending_interaction_preserves_store_for_recovery(orchestrator):
    orchestrator._store_manager.create_store.return_value = "stores/abc"
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="",
            interaction_id="interaction-123",
            status=ResearchStatus.IN_PROGRESS,
            error="polling state uncertain",
        )
    )

    result = await orchestrator.generate_report(
        company_name="Acme",
        stage1_context="context",
    )

    assert result.success is False
    assert result.interaction_id == "interaction-123"
    orchestrator._store_manager.delete_store.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_after_acceptance_preserves_store(orchestrator):
    orchestrator._store_manager.create_store.return_value = "stores/abc"
    cancelled = asyncio.CancelledError()
    cancelled.interaction_id = "interaction-123"  # type: ignore[attr-defined]
    orchestrator._execute_with_retry = AsyncMock(side_effect=cancelled)

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.generate_report(
            company_name="Acme",
            stage1_context="context",
        )

    orchestrator._store_manager.delete_store.assert_not_called()
