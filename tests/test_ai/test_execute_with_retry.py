"""Unit tests for DeepResearchOrchestrator._execute_with_retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.ai.deep_research import (
    DeepResearchOrchestrator,
    ResearchResult,
    ResearchStatus,
)
from primr.utils.errors import AIError


@pytest.fixture
def orchestrator(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    # Reset module-level singletons so real-API tests downstream don't see mock state.
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


class TestExecuteWithRetry:
    @pytest.mark.asyncio
    async def test_returns_immediately_on_success(self, orchestrator):
        ok_result = ResearchResult(
            content="body", status=ResearchStatus.COMPLETED
        )
        with patch.object(
            orchestrator,
            "_execute_single",
            new=AsyncMock(return_value=ok_result),
        ) as exec_mock:
            result = await orchestrator._execute_with_retry("prompt")
        assert result is ok_result
        exec_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_429_and_succeeds(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(
                    side_effect=[
                        AIError("429 rate limited", model="dr"),
                        ok,
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await orchestrator._execute_with_retry("prompt")
        assert result is ok

    @pytest.mark.asyncio
    async def test_retries_on_500(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(
                    side_effect=[
                        AIError("500 internal server error", model="dr"),
                        ok,
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await orchestrator._execute_with_retry("prompt")
        assert result is ok

    @pytest.mark.asyncio
    async def test_retries_on_503(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(
                    side_effect=[
                        AIError("503 service unavailable", model="dr"),
                        ok,
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await orchestrator._execute_with_retry("prompt")
        assert result is ok

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(
                    side_effect=[
                        AIError("connection refused", model="dr"),
                        ok,
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await orchestrator._execute_with_retry("prompt")
        assert result is ok

    @pytest.mark.asyncio
    async def test_non_retryable_aierror_propagates(self, orchestrator):
        with patch.object(
            orchestrator,
            "_execute_single",
            new=AsyncMock(
                side_effect=AIError("validation failure - not retryable", model="dr")
            ),
        ), pytest.raises(AIError):
            await orchestrator._execute_with_retry("prompt")

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises(self, orchestrator, monkeypatch):
        # Force MAX_RETRIES to 2 for fast test
        monkeypatch.setattr(orchestrator, "MAX_RETRIES", 2)
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(side_effect=AIError("429 rate limit", model="dr")),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
            pytest.raises(AIError),
        ):
            await orchestrator._execute_with_retry("prompt")

    @pytest.mark.asyncio
    async def test_generic_exception_retried_when_transient(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(
                    side_effect=[
                        RuntimeError("connection lost"),
                        ok,
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await orchestrator._execute_with_retry("prompt")
        assert result is ok

    @pytest.mark.asyncio
    async def test_generic_exception_non_retryable_propagates(self, orchestrator):
        with patch.object(
            orchestrator,
            "_execute_single",
            new=AsyncMock(side_effect=ValueError("bad input")),
        ), pytest.raises(ValueError):
            await orchestrator._execute_with_retry("prompt")

    @pytest.mark.asyncio
    async def test_progress_callback_invoked_on_retry(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        progress = MagicMock()
        with (
            patch.object(
                orchestrator,
                "_execute_single",
                new=AsyncMock(
                    side_effect=[
                        AIError("429 rate limit", model="dr"),
                        ok,
                    ]
                ),
            ),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            await orchestrator._execute_with_retry(
                "prompt", on_progress=progress
            )
        # Should have been called for the retry message
        assert progress.called

    @pytest.mark.asyncio
    async def test_increments_api_call_count(self, orchestrator):
        ok = ResearchResult(content="ok", status=ResearchStatus.COMPLETED)
        with patch.object(
            orchestrator,
            "_execute_single",
            new=AsyncMock(return_value=ok),
        ):
            before = orchestrator._api_call_count
            await orchestrator._execute_with_retry("prompt")
            assert orchestrator._api_call_count == before + 1
