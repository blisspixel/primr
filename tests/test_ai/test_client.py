"""
Tests for the unified AI client.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from primr.ai.client import (
    AIClient,
    get_client,
    reset_client,
    llm,
    llm_fast,
)
from primr.utils.errors import AIError
from primr.config.settings import reset_settings


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before and after each test."""
    reset_client()
    yield
    reset_client()


@pytest.fixture
def mock_genai_client():
    """Create a mock genai client."""
    with patch('primr.ai.client.genai.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Setup default response
        mock_response = MagicMock()
        mock_response.text = "Mock AI response"
        mock_client.models.generate_content.return_value = mock_response
        
        yield mock_client


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    with patch('primr.ai.client.get_settings') as mock_get:
        mock_settings = MagicMock()
        mock_settings.api.gemini_key = "test-api-key"
        mock_settings.ai.flash_model = "test-flash-model"
        mock_settings.ai.pro_model = "test-pro-model"
        mock_settings.ai.max_retries = 3
        mock_settings.ai.model_fallbacks = {}
        mock_get.return_value = mock_settings
        yield mock_settings


class TestAIClient:
    """Tests for AIClient class."""
    
    def test_init_with_settings(self, mock_genai_client, mock_settings):
        """Should initialize with settings API key."""
        client = AIClient()
        assert client._api_key == "test-api-key"
    
    def test_init_with_custom_key(self, mock_genai_client, mock_settings):
        """Should use custom API key when provided."""
        client = AIClient(api_key="custom-key")
        assert client._api_key == "custom-key"
    
    def test_generate_success(self, mock_genai_client, mock_settings):
        """Should return generated text on success."""
        client = AIClient()
        result = client.generate("Test prompt")
        
        assert result == "Mock AI response"
        mock_genai_client.models.generate_content.assert_called_once()
    
    def test_generate_uses_research_model(self, mock_genai_client, mock_settings):
        """Should use flash model for research type."""
        client = AIClient()
        client.generate("Test", model_type="research")
        
        call_args = mock_genai_client.models.generate_content.call_args
        assert call_args.kwargs['model'] == "test-flash-model"
    
    def test_generate_uses_report_model(self, mock_genai_client, mock_settings):
        """Should use pro model for report type."""
        client = AIClient()
        client.generate("Test", model_type="report")
        
        call_args = mock_genai_client.models.generate_content.call_args
        assert call_args.kwargs['model'] == "test-pro-model"
    
    def test_generate_retries_on_failure(self, mock_genai_client, mock_settings):
        """Should retry on failure."""
        mock_genai_client.models.generate_content.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            MagicMock(text="Success after retry"),
        ]
        
        client = AIClient()
        with patch('primr.ai.client.time.sleep'):  # Skip delays
            result = client.generate("Test")
        
        assert result == "Success after retry"
        assert mock_genai_client.models.generate_content.call_count == 3
    
    def test_generate_raises_after_max_retries(self, mock_genai_client, mock_settings):
        """Should raise AIError after max retries."""
        mock_genai_client.models.generate_content.side_effect = Exception("Always fails")
        
        client = AIClient()
        with patch('primr.ai.client.time.sleep'):
            with pytest.raises(AIError) as exc_info:
                client.generate("Test")
        
        assert "failed after 3 attempts" in str(exc_info.value)
    
    def test_generate_fast_uses_low_thinking(self, mock_genai_client, mock_settings):
        """generate_fast should use low thinking level."""
        client = AIClient()
        client.generate_fast("Test")
        
        call_args = mock_genai_client.models.generate_content.call_args
        config = call_args.kwargs['config']
        # Compare string value since it might be an enum
        thinking_level = str(config.thinking_config.thinking_level).lower()
        assert "low" in thinking_level
    
    def test_generate_with_context(self, mock_genai_client, mock_settings):
        """Should include context in prompt."""
        client = AIClient()
        client.generate_with_context(
            "Main prompt",
            context={"Company": "Acme Corp", "Industry": "Tech"}
        )
        
        call_args = mock_genai_client.models.generate_content.call_args
        prompt = call_args.kwargs['contents']
        assert "Main prompt" in prompt
        assert "Company" in prompt
        assert "Acme Corp" in prompt

    def test_generate_respects_timeout(self, mock_genai_client, mock_settings):
        """Should raise quickly when timeout is exceeded."""
        mock_settings.ai.max_retries = 1

        def slow_call(*_args, **_kwargs):
            import time as _time

            _time.sleep(0.2)
            return MagicMock(text="late")

        mock_genai_client.models.generate_content.side_effect = slow_call

        client = AIClient()
        with pytest.raises(AIError, match="timed out"):
            client.generate("Test prompt", timeout=0.01)


class TestAIClientFallback:
    """Tests for model fallback functionality."""
    
    def test_uses_fallback_on_failure(self, mock_genai_client, mock_settings):
        """Should try fallback model when primary fails."""
        mock_settings.ai.model_fallbacks = {
            "test-flash-model": ["fallback-model"]
        }
        
        # First call fails, second succeeds
        mock_genai_client.models.generate_content.side_effect = [
            Exception("Primary failed"),
            MagicMock(text="Fallback success"),
        ]
        
        client = AIClient()
        with patch('primr.ai.client.time.sleep'):
            result = client.generate("Test")
        
        assert result == "Fallback success"
        
        # Check that fallback model was used
        calls = mock_genai_client.models.generate_content.call_args_list
        assert calls[1].kwargs['model'] == "fallback-model"


class TestSingletonAccess:
    """Tests for singleton functions."""
    
    def test_get_client_returns_client(self, mock_genai_client, mock_settings):
        """get_client should return AIClient instance."""
        client = get_client()
        assert isinstance(client, AIClient)
    
    def test_get_client_returns_same_instance(self, mock_genai_client, mock_settings):
        """get_client should return same instance."""
        client1 = get_client()
        client2 = get_client()
        assert client1 is client2
    
    def test_reset_client_clears_singleton(self, mock_genai_client, mock_settings):
        """reset_client should clear the singleton."""
        client1 = get_client()
        reset_client()
        client2 = get_client()
        assert client1 is not client2

    def test_reset_client_closes_existing_singleton(self, mock_genai_client, mock_settings):
        """reset_client should close existing client resources."""
        _ = get_client()
        reset_client()
        mock_genai_client.close.assert_called_once()


class TestBackwardCompatibility:
    """Tests for backward-compatible functions."""
    
    def test_llm_function(self, mock_genai_client, mock_settings):
        """llm() should work like before."""
        result = llm("Test prompt")
        assert result == "Mock AI response"
    
    def test_llm_with_model_type(self, mock_genai_client, mock_settings):
        """llm() should accept model_type."""
        llm("Test", model_type="report")
        
        call_args = mock_genai_client.models.generate_content.call_args
        assert call_args.kwargs['model'] == "test-pro-model"
    
    def test_llm_fast_function(self, mock_genai_client, mock_settings):
        """llm_fast() should work like before."""
        result = llm_fast("Test prompt")
        assert result == "Mock AI response"
    
    def test_llm_ignores_streaming_param(self, mock_genai_client, mock_settings):
        """llm() should accept but ignore streaming parameter."""
        result = llm("Test", streaming=True)
        assert result == "Mock AI response"


class TestAIClientErrorHandling:
    """Tests for error handling."""
    
    def test_ai_error_includes_model(self, mock_genai_client, mock_settings):
        """AIError should include model name."""
        mock_genai_client.models.generate_content.side_effect = Exception("Fail")
        
        client = AIClient()
        with patch('primr.ai.client.time.sleep'):
            with pytest.raises(AIError) as exc_info:
                client.generate("Test")
        
        assert exc_info.value.model == "test-flash-model"
    
    def test_ai_error_includes_cause(self, mock_genai_client, mock_settings):
        """AIError should include original exception."""
        original_error = ValueError("Original error")
        mock_genai_client.models.generate_content.side_effect = original_error
        
        client = AIClient()
        with patch('primr.ai.client.time.sleep'):
            with pytest.raises(AIError) as exc_info:
                client.generate("Test")
        
        assert exc_info.value.cause is original_error


class TestUsageTracking:
    """Tests for token usage tracking."""
    
    def test_usage_tracking_enabled_by_default(self, mock_genai_client, mock_settings):
        """Usage tracking should be enabled by default."""
        client = AIClient()
        assert client._track_usage is True
        assert client.total_input_tokens == 0
        assert client.total_output_tokens == 0
        assert client.call_count == 0
    
    def test_usage_tracking_can_be_disabled(self, mock_genai_client, mock_settings):
        """Usage tracking can be disabled."""
        client = AIClient(track_usage=False)
        assert client._track_usage is False
    
    def test_extract_usage_with_valid_metadata(self, mock_genai_client, mock_settings):
        """Should extract usage from response with valid metadata."""
        client = AIClient()
        
        # Create mock response with usage metadata
        mock_response = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50
        
        usage = client._extract_usage(mock_response)
        
        assert usage is not None
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150
    
    def test_extract_usage_returns_none_without_metadata(self, mock_genai_client, mock_settings):
        """Should return None when no usage metadata available."""
        client = AIClient()
        
        mock_response = MagicMock()
        mock_response.usage_metadata = None
        
        usage = client._extract_usage(mock_response)
        assert usage is None
    
    def test_get_usage_summary(self, mock_genai_client, mock_settings):
        """Should return usage summary with cost calculation."""
        client = AIClient()
        client.total_input_tokens = 1_000_000  # 1M tokens
        client.total_output_tokens = 500_000   # 0.5M tokens
        client.call_count = 10
        
        summary = client.get_usage_summary()
        
        assert summary["call_count"] == 10
        assert summary["total_input_tokens"] == 1_000_000
        assert summary["total_output_tokens"] == 500_000
        assert summary["total_tokens"] == 1_500_000
        assert summary["input_cost"] == 2.00  # $2 per 1M input
        assert summary["output_cost"] == 6.00  # $12 per 1M output * 0.5M
        assert summary["total_cost"] == 8.00
    
    def test_get_usage_summary_with_per_call_cost(self, mock_genai_client, mock_settings):
        """Per-call accumulated cost should be used when available."""
        client = AIClient()
        # Simulate per-call cost accumulation
        client.usage_by_model = {
            "gemini-3-flash-preview": {
                "input_tokens": 500_000,
                "output_tokens": 200_000,
                "calls": 5,
                "cost": 0.85,  # Pre-calculated per-call cost
            },
            "gemini-3.1-pro-preview": {
                "input_tokens": 100_000,
                "output_tokens": 50_000,
                "calls": 3,
                "cost": 0.80,  # Pre-calculated per-call cost
            },
        }
        client.total_input_tokens = 600_000
        client.total_output_tokens = 250_000
        client.call_count = 8

        summary = client.get_usage_summary()

        # total_cost should use pre-calculated per-call costs
        assert abs(summary["total_cost"] - 1.65) < 0.001  # $0.85 + $0.80

    def test_reset_usage(self, mock_genai_client, mock_settings):
        """Should reset all usage counters."""
        client = AIClient()
        client.total_input_tokens = 1000
        client.total_output_tokens = 500
        client.call_count = 5

        client.reset_usage()

        assert client.total_input_tokens == 0
        assert client.total_output_tokens == 0
        assert client.call_count == 0
    
    def test_usage_accumulates_across_calls(self, mock_genai_client, mock_settings):
        """Usage should accumulate across multiple generate calls."""
        # Create mock response with usage metadata
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50
        mock_genai_client.models.generate_content.return_value = mock_response
        
        client = AIClient()
        client.generate("Test 1")
        client.generate("Test 2")
        
        assert client.call_count == 2
        assert client.total_input_tokens == 200
        assert client.total_output_tokens == 100


class TestAIClientThreadSafety:
    """Tests for thread safety of AIClient singleton."""
    
    def test_singleton_thread_safe(self, mock_genai_client, mock_settings):
        """Test that get_client() is thread safe under concurrent access."""
        import threading
        
        clients = []
        errors = []
        
        def get_client_thread():
            try:
                client = get_client()
                clients.append(client)
            except Exception as e:
                errors.append(e)
        
        # Create many threads to stress test
        threads = [threading.Thread(target=get_client_thread) for _ in range(20)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
        # All should be the same instance
        assert len(clients) == 20
        assert all(c is clients[0] for c in clients), "Not all clients are the same instance"
    
    def test_reset_client_thread_safe(self, mock_genai_client, mock_settings):
        """Test that reset_client() is thread safe."""
        import threading
        
        errors = []
        
        def reset_and_get():
            try:
                reset_client()
                get_client()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=reset_and_get) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors during concurrent reset: {errors}"
