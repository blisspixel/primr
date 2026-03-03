"""
Tests for the async AI client module.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from primr.ai.async_client import (
    AsyncAIClient,
    BatchResult,
    BatchStats,
    generate_parallel,
    get_batch_stats,
    run_parallel,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.api.gemini_key = "test-api-key"
    settings.ai.flash_model = "gemini-3-flash-preview"
    settings.ai.pro_model = "gemini-3-pro-preview"
    settings.ai.max_retries = 3
    return settings


@pytest.fixture
def mock_genai_client():
    """Mock genai client."""
    client = Mock()
    response = Mock()
    response.text = "Test response"
    client.models.generate_content.return_value = response
    return client


# =============================================================================
# BATCH RESULT TESTS
# =============================================================================

class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_success_with_response(self):
        """Test success property when response exists."""
        result = BatchResult(prompt="test", response="answer")
        assert result.success is True

    def test_failure_with_error(self):
        """Test success property when error exists."""
        result = BatchResult(prompt="test", error=ValueError("fail"))
        assert result.success is False

    def test_failure_with_none_response(self):
        """Test success property when response is None."""
        result = BatchResult(prompt="test", response=None)
        assert result.success is False

    def test_duration_tracking(self):
        """Test duration is tracked."""
        result = BatchResult(prompt="test", response="answer", duration_ms=150.5)
        assert result.duration_ms == 150.5


# =============================================================================
# BATCH STATS TESTS
# =============================================================================

class TestBatchStats:
    """Tests for BatchStats dataclass."""

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        stats = BatchStats(total=10, succeeded=8, failed=2)
        assert stats.success_rate == 80.0

    def test_success_rate_zero_total(self):
        """Test success rate with zero total."""
        stats = BatchStats(total=0, succeeded=0, failed=0)
        assert stats.success_rate == 0.0

    def test_avg_duration_calculation(self):
        """Test average duration calculation."""
        stats = BatchStats(total=4, total_duration_ms=400.0)
        assert stats.avg_duration_ms == 100.0

    def test_avg_duration_zero_total(self):
        """Test average duration with zero total."""
        stats = BatchStats(total=0, total_duration_ms=0.0)
        assert stats.avg_duration_ms == 0.0

    def test_all_succeeded(self):
        """Test 100% success rate."""
        stats = BatchStats(total=5, succeeded=5, failed=0)
        assert stats.success_rate == 100.0

    def test_all_failed(self):
        """Test 0% success rate."""
        stats = BatchStats(total=5, succeeded=0, failed=5)
        assert stats.success_rate == 0.0


# =============================================================================
# GET BATCH STATS TESTS
# =============================================================================

class TestGetBatchStats:
    """Tests for get_batch_stats function."""

    def test_empty_results(self):
        """Test with empty results list."""
        stats = get_batch_stats([])
        assert stats.total == 0
        assert stats.succeeded == 0
        assert stats.failed == 0

    def test_all_successful(self):
        """Test with all successful results."""
        results = [
            BatchResult(prompt="p1", response="r1", duration_ms=100),
            BatchResult(prompt="p2", response="r2", duration_ms=200),
            BatchResult(prompt="p3", response="r3", duration_ms=150),
        ]
        stats = get_batch_stats(results)
        assert stats.total == 3
        assert stats.succeeded == 3
        assert stats.failed == 0
        assert stats.total_duration_ms == 450.0

    def test_mixed_results(self):
        """Test with mixed success/failure."""
        results = [
            BatchResult(prompt="p1", response="r1", duration_ms=100),
            BatchResult(prompt="p2", error=ValueError("fail"), duration_ms=50),
            BatchResult(prompt="p3", response="r3", duration_ms=150),
        ]
        stats = get_batch_stats(results)
        assert stats.total == 3
        assert stats.succeeded == 2
        assert stats.failed == 1
        assert stats.total_duration_ms == 300.0

    def test_all_failed(self):
        """Test with all failed results."""
        results = [
            BatchResult(prompt="p1", error=ValueError("e1"), duration_ms=10),
            BatchResult(prompt="p2", error=ValueError("e2"), duration_ms=20),
        ]
        stats = get_batch_stats(results)
        assert stats.total == 2
        assert stats.succeeded == 0
        assert stats.failed == 2


# =============================================================================
# ASYNC AI CLIENT TESTS
# =============================================================================

class TestAsyncAIClient:
    """Tests for AsyncAIClient class."""

    @patch("primr.ai.async_client.get_settings")
    def test_initialization(self, mock_get_settings, mock_settings):
        """Test client initialization."""
        mock_get_settings.return_value = mock_settings

        client = AsyncAIClient(max_concurrent=3)
        assert client._max_concurrent == 3
        assert client._api_key == "test-api-key"

    @patch("primr.ai.async_client.get_settings")
    def test_custom_api_key(self, mock_get_settings, mock_settings):
        """Test client with custom API key."""
        mock_get_settings.return_value = mock_settings

        client = AsyncAIClient(api_key="custom-key")
        assert client._api_key == "custom-key"

    @patch("primr.ai.async_client.get_settings")
    def test_get_model_research(self, mock_get_settings, mock_settings):
        """Test getting research model."""
        mock_get_settings.return_value = mock_settings

        client = AsyncAIClient()
        assert client._get_model("research") == "gemini-3-flash-preview"

    @patch("primr.ai.async_client.get_settings")
    def test_get_model_report(self, mock_get_settings, mock_settings):
        """Test getting report model."""
        mock_get_settings.return_value = mock_settings

        client = AsyncAIClient()
        assert client._get_model("report") == "gemini-3-pro-preview"

    @patch("primr.ai.async_client.get_settings")
    def test_get_model_unknown_defaults_to_research(self, mock_get_settings, mock_settings):
        """Test unknown model type defaults to research."""
        mock_get_settings.return_value = mock_settings

        client = AsyncAIClient()
        assert client._get_model("unknown") == "gemini-3-flash-preview"


# =============================================================================
# ASYNC CONTEXT MANAGER TESTS
# =============================================================================

class TestAsyncContextManager:
    """Tests for async context manager behavior."""

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_context_manager_entry(self, mock_client_class, mock_get_settings, mock_settings):
        """Test async context manager entry."""
        mock_get_settings.return_value = mock_settings

        async with AsyncAIClient() as client:
            assert client._client is not None
            assert client._semaphore is not None

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_context_manager_exit(self, mock_client_class, mock_get_settings, mock_settings):
        """Test async context manager exit."""
        mock_get_settings.return_value = mock_settings

        client = AsyncAIClient()
        async with client:
            pass

        assert client._client is None
        assert client._semaphore is None

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_context_manager_exit_calls_aclose(self, mock_client_class, mock_get_settings, mock_settings):
        """Exit should close async SDK client when supported."""
        mock_get_settings.return_value = mock_settings
        mock_client = Mock()
        mock_client.aclose = AsyncMock()
        mock_client_class.return_value = mock_client

        client = AsyncAIClient()
        async with client:
            pass

        mock_client.aclose.assert_awaited_once()


# =============================================================================
# GENERATE TESTS
# =============================================================================

class TestGenerate:
    """Tests for generate method."""

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_generate_success(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test successful generation."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        async with AsyncAIClient() as client:
            result = await client.generate("Test prompt")

        assert result == "Test response"

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_generate_fast(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test fast generation."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        async with AsyncAIClient() as client:
            result = await client.generate_fast("Test prompt")

        assert result == "Test response"

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_generate_strips_whitespace(self, mock_client_class, mock_get_settings, mock_settings):
        """Test that response whitespace is stripped."""
        mock_get_settings.return_value = mock_settings

        mock_client = Mock()
        response = Mock()
        response.text = "  Response with whitespace  \n"
        mock_client.models.generate_content.return_value = response
        mock_client_class.return_value = mock_client

        async with AsyncAIClient() as client:
            result = await client.generate("Test")

        assert result == "Response with whitespace"

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_generate_respects_timeout(self, mock_client_class, mock_get_settings, mock_settings):
        """Should raise quickly when timeout is exceeded."""
        mock_get_settings.return_value = mock_settings
        mock_settings.ai.max_retries = 1

        def slow_generate(*_args, **_kwargs):
            import time as _time

            _time.sleep(0.2)
            response = Mock()
            response.text = "late"
            return response

        mock_client = Mock()
        mock_client.models.generate_content.side_effect = slow_generate
        mock_client_class.return_value = mock_client

        async with AsyncAIClient() as client:
            with pytest.raises(Exception, match="timed out"):
                await client.generate("Test", timeout=0.01)


# =============================================================================
# BATCH GENERATION TESTS
# =============================================================================

class TestGenerateBatch:
    """Tests for batch generation."""

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_batch_all_success(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test batch with all successful responses."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        prompts = ["prompt1", "prompt2", "prompt3"]

        async with AsyncAIClient() as client:
            results = await client.generate_batch(prompts)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_batch_progress_callback(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test batch progress callback is called."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        progress_calls = []
        def on_progress(completed, total):
            progress_calls.append((completed, total))

        prompts = ["p1", "p2"]

        async with AsyncAIClient() as client:
            await client.generate_batch(prompts, on_progress=on_progress)

        assert len(progress_calls) == 2
        assert (2, 2) in progress_calls

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_batch_with_context(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test batch with context template."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        items = [
            {"company": "Acme", "industry": "Tech"},
            {"company": "Beta", "industry": "Finance"},
        ]
        template = "Analyze {company} in {industry}"

        async with AsyncAIClient() as client:
            results = await client.generate_batch_with_context(items, template)

        assert len(results) == 2


# =============================================================================
# CONCURRENCY TESTS
# =============================================================================

class TestConcurrency:
    """Tests for concurrency control."""

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_semaphore_limits_concurrency(self, mock_client_class, mock_get_settings, mock_settings):
        """Test that semaphore limits concurrent requests."""
        mock_get_settings.return_value = mock_settings

        concurrent_count = 0
        max_concurrent_seen = 0
        lock = asyncio.Lock()

        def slow_generate(*args, **kwargs):
            # Sync function that simulates work - used with run_in_executor
            import time
            nonlocal concurrent_count, max_concurrent_seen
            concurrent_count += 1
            max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
            time.sleep(0.01)  # Use sync sleep since this runs in executor
            concurrent_count -= 1
            response = Mock()
            response.text = "response"
            return response

        mock_client = Mock()
        mock_client.models.generate_content.side_effect = slow_generate
        mock_client_class.return_value = mock_client

        async with AsyncAIClient(max_concurrent=2) as client:
            prompts = ["p1", "p2", "p3", "p4"]
            await client.generate_batch(prompts)

        assert max_concurrent_seen <= 2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_generate_parallel(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test generate_parallel function."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        results = await generate_parallel(["p1", "p2"])

        assert len(results) == 2
        assert all(r.success for r in results)

    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    def test_run_parallel_sync(self, mock_client_class, mock_get_settings, mock_settings, mock_genai_client):
        """Test run_parallel synchronous wrapper."""
        mock_get_settings.return_value = mock_settings
        mock_client_class.return_value = mock_genai_client

        results = run_parallel(["p1", "p2"])

        assert len(results) == 2
        assert all(r.success for r in results)


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    @patch("primr.ai.async_client.get_settings")
    @patch("primr.ai.async_client.genai.Client")
    async def test_batch_captures_errors(self, mock_client_class, mock_get_settings, mock_settings):
        """Test that batch captures errors without failing."""
        mock_get_settings.return_value = mock_settings
        mock_settings.ai.max_retries = 1

        call_count = 0
        def generate_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Simulated error")
            response = Mock()
            response.text = "success"
            return response

        mock_client = Mock()
        mock_client.models.generate_content.side_effect = generate_with_error
        mock_client_class.return_value = mock_client

        async with AsyncAIClient() as client:
            results = await client.generate_batch(["p1", "p2", "p3"])

        # Should have 2 successes and 1 failure
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        assert len(successes) == 2
        assert len(failures) == 1
        assert failures[0].error is not None
