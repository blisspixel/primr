"""
Tests for error handling utilities.
"""

import pytest
import logging
from unittest.mock import patch, MagicMock

from primr.utils.errors import (
    ResearchError,
    ConfigurationError,
    ScrapingError,
    AIError,
    SearchError,
    OutputError,
    ValidationError,
    safe_call,
    retry_on_failure,
    ErrorContext,
)


class TestExceptionHierarchy:
    """Tests for custom exception classes."""
    
    def test_research_error_basic(self):
        """ResearchError should store message."""
        error = ResearchError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.cause is None
    
    def test_research_error_with_cause(self):
        """ResearchError should chain causes."""
        cause = ValueError("Original error")
        error = ResearchError("Wrapped error", cause=cause)
        assert "Wrapped error" in str(error)
        assert "Original error" in str(error)
        assert error.cause is cause
    
    def test_configuration_error(self):
        """ConfigurationError should be a ResearchError."""
        error = ConfigurationError("Missing API key")
        assert isinstance(error, ResearchError)
        assert "Missing API key" in str(error)
    
    def test_scraping_error_with_url(self):
        """ScrapingError should store URL."""
        error = ScrapingError("Failed to scrape", url="https://example.com")
        assert error.url == "https://example.com"
        assert isinstance(error, ResearchError)
    
    def test_ai_error_with_model(self):
        """AIError should store model name."""
        error = AIError("Model failed", model="gemini-pro")
        assert error.model == "gemini-pro"
        assert isinstance(error, ResearchError)
    
    def test_search_error_with_query(self):
        """SearchError should store query."""
        error = SearchError("Search failed", query="test query")
        assert error.query == "test query"
        assert isinstance(error, ResearchError)
    
    def test_all_errors_inherit_from_research_error(self):
        """All custom errors should inherit from ResearchError."""
        errors = [
            ConfigurationError("test"),
            ScrapingError("test"),
            AIError("test"),
            SearchError("test"),
            OutputError("test"),
            ValidationError("test"),
        ]
        for error in errors:
            assert isinstance(error, ResearchError)
            assert isinstance(error, Exception)


class TestSafeCallDecorator:
    """Tests for the safe_call decorator."""
    
    def test_returns_result_on_success(self):
        """Should return function result when no exception."""
        @safe_call(default="default")
        def successful_func():
            return "success"
        
        assert successful_func() == "success"
    
    def test_returns_default_on_exception(self):
        """Should return default value when exception occurs."""
        @safe_call(default="default")
        def failing_func():
            raise ValueError("error")
        
        assert failing_func() == "default"
    
    def test_catches_specific_exceptions(self):
        """Should only catch specified exception types."""
        @safe_call(default="default", exceptions=(ValueError,))
        def func_raises_type_error():
            raise TypeError("wrong type")
        
        with pytest.raises(TypeError):
            func_raises_type_error()
    
    def test_logs_exception(self):
        """Should log caught exceptions."""
        @safe_call(default=None, log_level="warning")
        def failing_func():
            raise ValueError("test error")
        
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            result = failing_func()
            assert result is None
            mock_logger.warning.assert_called_once()
    
    def test_reraise_option(self):
        """Should re-raise exception when reraise=True."""
        @safe_call(default=None, reraise=True)
        def failing_func():
            raise ValueError("test error")
        
        with pytest.raises(ValueError):
            failing_func()
    
    def test_preserves_function_metadata(self):
        """Should preserve function name and docstring."""
        @safe_call(default=None)
        def documented_func():
            """This is a docstring."""
            return "result"
        
        assert documented_func.__name__ == "documented_func"
        assert "docstring" in documented_func.__doc__


class TestRetryOnFailure:
    """Tests for the retry_on_failure decorator."""
    
    def test_returns_on_first_success(self):
        """Should return immediately on success."""
        call_count = 0
        
        @retry_on_failure(max_retries=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_func()
        assert result == "success"
        assert call_count == 1
    
    def test_retries_on_failure(self):
        """Should retry specified number of times."""
        call_count = 0
        
        @retry_on_failure(max_retries=3, delay=0.01)
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")
        
        with pytest.raises(ValueError):
            failing_func()
        
        assert call_count == 3
    
    def test_succeeds_after_retry(self):
        """Should succeed if function works on retry."""
        call_count = 0
        
        @retry_on_failure(max_retries=3, delay=0.01)
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "success"
        
        result = eventually_succeeds()
        assert result == "success"
        assert call_count == 3
    
    def test_only_catches_specified_exceptions(self):
        """Should only retry on specified exception types."""
        @retry_on_failure(max_retries=3, exceptions=(ValueError,), delay=0.01)
        def raises_type_error():
            raise TypeError("wrong type")
        
        with pytest.raises(TypeError):
            raises_type_error()
    
    def test_exponential_backoff(self):
        """Should use exponential backoff between retries."""
        import time
        
        call_times = []
        
        @retry_on_failure(max_retries=3, delay=0.1, backoff=2.0)
        def track_timing():
            call_times.append(time.time())
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            track_timing()
        
        # Check delays increase
        if len(call_times) >= 3:
            delay1 = call_times[1] - call_times[0]
            delay2 = call_times[2] - call_times[1]
            assert delay2 > delay1  # Second delay should be longer


class TestErrorContext:
    """Tests for ErrorContext context manager."""
    
    def test_logs_on_exception(self):
        """Should log error with context on exception."""
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            try:
                with ErrorContext("test operation", key="value"):
                    raise ValueError("test error")
            except ValueError:
                pass
            
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "test operation" in call_args
            assert "key=value" in call_args
    
    def test_no_log_on_success(self):
        """Should not log when no exception occurs."""
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            with ErrorContext("test operation"):
                pass  # No exception
            
            mock_logger.error.assert_not_called()
    
    def test_does_not_suppress_exception(self):
        """Should not suppress the exception."""
        with pytest.raises(ValueError):
            with ErrorContext("test"):
                raise ValueError("should propagate")


from hypothesis import given, strategies as st, settings, HealthCheck

from primr.utils.errors import (
    RetryConfig,
    calculate_backoff_delay,
    error_context,
    async_safe_callback,
)


# =============================================================================
# UNIT TESTS - RetryConfig
# =============================================================================

class TestRetryConfig:
    """Tests for RetryConfig dataclass."""
    
    def test_default_values(self):
        """Should have sensible defaults."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter_factor == 0.1
    
    def test_custom_values(self):
        """Should accept custom values."""
        config = RetryConfig(
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter_factor=0.2
        )
        assert config.max_retries == 5
        assert config.base_delay == 0.5
    
    def test_validate_rejects_negative_retries(self):
        """Should reject negative max_retries."""
        config = RetryConfig(max_retries=-1)
        with pytest.raises(ValueError, match="max_retries"):
            config.validate()
    
    def test_validate_rejects_zero_base_delay(self):
        """Should reject zero base_delay."""
        config = RetryConfig(base_delay=0)
        with pytest.raises(ValueError, match="base_delay"):
            config.validate()
    
    def test_validate_rejects_invalid_jitter(self):
        """Should reject jitter outside 0-1 range."""
        config = RetryConfig(jitter_factor=1.5)
        with pytest.raises(ValueError, match="jitter_factor"):
            config.validate()
    
    def test_validate_accepts_valid_config(self):
        """Should accept valid configuration."""
        config = RetryConfig()
        config.validate()  # Should not raise


class TestCalculateBackoffDelay:
    """Tests for calculate_backoff_delay function."""
    
    def test_first_attempt_uses_base_delay(self):
        """First attempt should use approximately base_delay."""
        config = RetryConfig(base_delay=1.0, jitter_factor=0)
        delay = calculate_backoff_delay(0, config)
        assert delay == 1.0
    
    def test_exponential_growth(self):
        """Delay should grow exponentially."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter_factor=0)
        assert calculate_backoff_delay(0, config) == 1.0
        assert calculate_backoff_delay(1, config) == 2.0
        assert calculate_backoff_delay(2, config) == 4.0
        assert calculate_backoff_delay(3, config) == 8.0
    
    def test_respects_max_delay(self):
        """Delay should be capped at max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter_factor=0)
        delay = calculate_backoff_delay(10, config)  # Would be 1024 without cap
        assert delay == 5.0
    
    def test_jitter_adds_variation(self):
        """Jitter should add variation to delays."""
        config = RetryConfig(base_delay=10.0, jitter_factor=0.1)
        delays = [calculate_backoff_delay(0, config) for _ in range(100)]
        # With 10% jitter on base 10, delays should be in range [9, 11]
        assert all(9.0 <= d <= 11.0 for d in delays)
        # Should have some variation (not all identical)
        assert len(set(delays)) > 1
    
    def test_never_negative(self):
        """Delay should never be negative."""
        config = RetryConfig(base_delay=0.1, jitter_factor=1.0)  # Max jitter
        for _ in range(100):
            delay = calculate_backoff_delay(0, config)
            assert delay >= 0


class TestErrorContextFunction:
    """Tests for error_context context manager function."""
    
    def test_logs_on_exception(self):
        """Should log error with context on exception."""
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            try:
                with error_context("test operation", key="value"):
                    raise ValueError("test error")
            except ValueError:
                pass
            
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "test operation" in call_args
            assert "key=value" in call_args
    
    def test_no_log_on_success(self):
        """Should not log when no exception occurs."""
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            with error_context("test operation"):
                pass
            mock_logger.error.assert_not_called()
    
    def test_reraises_exception(self):
        """Should re-raise the exception."""
        with pytest.raises(ValueError, match="test error"):
            with error_context("test"):
                raise ValueError("test error")
    
    def test_handles_no_metadata(self):
        """Should work without metadata."""
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            try:
                with error_context("simple operation"):
                    raise ValueError("error")
            except ValueError:
                pass
            
            call_args = mock_logger.error.call_args[0][0]
            assert "simple operation" in call_args


class TestAsyncSafeCallback:
    """Tests for async_safe_callback wrapper."""
    
    def test_wraps_successful_callback(self):
        """Should pass through successful callback results."""
        def callback(x):
            return x * 2
        
        safe = async_safe_callback(callback)
        assert safe(5) == 10
    
    def test_handles_none_callback(self):
        """Should handle None callback gracefully."""
        safe = async_safe_callback(None)
        result = safe("anything")
        assert result is None
    
    def test_catches_callback_exceptions(self):
        """Should catch and log callback exceptions."""
        def failing_callback():
            raise ValueError("callback failed")
        
        safe = async_safe_callback(failing_callback)
        with patch('primr.utils.errors.decorators.logger') as mock_logger:
            result = safe()
            assert result is None
            mock_logger.warning.assert_called_once()
    
    def test_preserves_function_name(self):
        """Should preserve original function name."""
        def my_callback():
            pass
        
        safe = async_safe_callback(my_callback)
        assert safe.__name__ == "my_callback"


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================

class TestExponentialBackoffProperty:
    """
    Property-based tests for exponential backoff with jitter.
    
    **Feature: code-quality-hardening, Property 4: Exponential Backoff with Jitter**
    **Validates: Requirements 2.5**
    
    For any sequence of retry attempts, the delay between attempts SHALL follow
    exponential growth with bounded jitter, and no two consecutive delays SHALL
    be identical (due to jitter).
    """
    
    @given(
        attempt=st.integers(min_value=0, max_value=10),
        base_delay_cents=st.integers(min_value=10, max_value=1000),  # 0.1 to 10.0
        exp_base_tenths=st.integers(min_value=11, max_value=50),     # 1.1 to 5.0
        jitter_percent=st.integers(min_value=1, max_value=50)        # 0.01 to 0.5
    )
    @settings(max_examples=100)
    def test_delay_is_non_negative(
        self,
        attempt: int,
        base_delay_cents: int,
        exp_base_tenths: int,
        jitter_percent: int
    ):
        """Delay should always be non-negative."""
        # Convert integers to floats for cleaner generation
        base_delay = base_delay_cents / 100.0
        exponential_base = exp_base_tenths / 10.0
        jitter_factor = jitter_percent / 100.0
        
        config = RetryConfig(
            base_delay=base_delay,
            exponential_base=exponential_base,
            jitter_factor=jitter_factor,
            max_delay=1000.0
        )
        delay = calculate_backoff_delay(attempt, config)
        assert delay >= 0
    
    @given(
        attempt=st.integers(min_value=0, max_value=5),
        base_delay_cents=st.integers(min_value=10, max_value=500),   # 0.1 to 5.0
        max_delay_int=st.integers(min_value=10, max_value=100)       # 10.0 to 100.0
    )
    @settings(max_examples=100)
    def test_delay_respects_max(
        self,
        attempt: int,
        base_delay_cents: int,
        max_delay_int: int
    ):
        """Delay should never exceed max_delay (plus jitter)."""
        base_delay = base_delay_cents / 100.0
        max_delay = float(max_delay_int)
        
        config = RetryConfig(
            base_delay=base_delay,
            max_delay=max_delay,
            jitter_factor=0.1
        )
        delay = calculate_backoff_delay(attempt, config)
        # With 10% jitter, max possible is max_delay * 1.1
        assert delay <= max_delay * 1.1
    
    @given(st.integers(min_value=0, max_value=5))
    @settings(max_examples=100)
    def test_exponential_growth_without_jitter(self, attempt: int):
        """Without jitter, delay should follow exact exponential formula."""
        config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            jitter_factor=0,
            max_delay=1000.0
        )
        delay = calculate_backoff_delay(attempt, config)
        expected = 1.0 * (2.0 ** attempt)
        assert delay == expected
    
    @given(st.integers(min_value=0, max_value=3))
    @settings(max_examples=100)
    def test_jitter_produces_variation(self, attempt: int):
        """With jitter, consecutive calls should produce different values."""
        config = RetryConfig(
            base_delay=10.0,
            jitter_factor=0.2,
            max_delay=1000.0
        )
        delays = [calculate_backoff_delay(attempt, config) for _ in range(20)]
        # Should have variation (not all identical)
        unique_delays = set(delays)
        assert len(unique_delays) > 1, "Jitter should produce variation"
    
    @given(
        st.integers(min_value=0, max_value=4),
        st.floats(min_value=0.1, max_value=5.0),
        st.floats(min_value=0.01, max_value=0.3)
    )
    @settings(max_examples=100)
    def test_delay_within_jitter_bounds(
        self,
        attempt: int,
        base_delay: float,
        jitter_factor: float
    ):
        """Delay should be within expected jitter bounds."""
        config = RetryConfig(
            base_delay=base_delay,
            exponential_base=2.0,
            jitter_factor=jitter_factor,
            max_delay=1000.0
        )
        
        expected_base = base_delay * (2.0 ** attempt)
        expected_base = min(expected_base, 1000.0)  # Cap
        
        delay = calculate_backoff_delay(attempt, config)
        
        min_expected = expected_base * (1 - jitter_factor)
        max_expected = expected_base * (1 + jitter_factor)
        
        # Allow small floating point tolerance
        assert delay >= min_expected - 0.001
        assert delay <= max_expected + 0.001


class TestAsyncErrorPropagationProperty:
    """
    Property-based tests for async error propagation.
    
    **Feature: code-quality-hardening, Property 3: Async Error Propagation**
    **Validates: Requirements 2.3**
    
    For any async function that raises an exception, the exception SHALL
    propagate to the caller without being silently swallowed.
    """
    
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_error_context_propagates_exceptions(self, error_message: str):
        """error_context should always propagate exceptions."""
        with pytest.raises(ValueError) as exc_info:
            with error_context("test operation"):
                raise ValueError(error_message)
        
        assert error_message in str(exc_info.value)
    
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_safe_callback_never_raises(self, error_message: str):
        """async_safe_callback should never raise exceptions."""
        def failing_callback():
            raise ValueError(error_message)
        
        safe = async_safe_callback(failing_callback)
        
        # Should not raise
        result = safe()
        assert result is None


# =============================================================================
# TESTS FOR RETRY MANAGER
# =============================================================================

from primr.utils.errors import RetryManager


class TestRetryManager:
    """Tests for RetryManager class."""
    
    def test_succeeds_on_first_try(self):
        """Should return result on first successful call."""
        manager = RetryManager(RetryConfig(max_retries=3))
        
        result = manager.execute_sync(lambda: "success")
        
        assert result == "success"
        assert manager.last_attempt_count == 1
        assert manager.last_total_delay == 0.0
    
    def test_retries_on_failure(self):
        """Should retry on retryable exceptions."""
        manager = RetryManager(
            RetryConfig(max_retries=3, base_delay=0.01),
            retryable_exceptions=(ValueError,)
        )
        
        call_count = 0
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            manager.execute_sync(failing_func)
        
        assert call_count == 4  # Initial + 3 retries
        assert manager.last_attempt_count == 4
    
    def test_succeeds_after_retry(self):
        """Should succeed if function works on retry."""
        manager = RetryManager(
            RetryConfig(max_retries=3, base_delay=0.01),
            retryable_exceptions=(ValueError,)
        )
        
        call_count = 0
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "success"
        
        result = manager.execute_sync(eventually_succeeds)
        
        assert result == "success"
        assert call_count == 3
        assert manager.last_attempt_count == 3
    
    def test_only_retries_specified_exceptions(self):
        """Should not retry on non-retryable exceptions."""
        manager = RetryManager(
            RetryConfig(max_retries=3, base_delay=0.01),
            retryable_exceptions=(ValueError,)
        )
        
        call_count = 0
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")
        
        with pytest.raises(TypeError):
            manager.execute_sync(raises_type_error)
        
        assert call_count == 1  # No retries
    
    def test_on_retry_callback(self):
        """Should call on_retry callback on each retry."""
        manager = RetryManager(
            RetryConfig(max_retries=3, base_delay=0.01),
            retryable_exceptions=(ValueError,)
        )
        
        retry_events = []
        def on_retry(attempt, error):
            retry_events.append((attempt, str(error)))
        
        call_count = 0
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"fail {call_count}")
            return "success"
        
        result = manager.execute_sync(failing_func, on_retry=on_retry)
        
        assert result == "success"
        assert len(retry_events) == 2
        assert retry_events[0][0] == 1
        assert retry_events[1][0] == 2
    
    def test_callback_errors_dont_affect_retry(self):
        """Callback errors should not prevent retries."""
        manager = RetryManager(
            RetryConfig(max_retries=3, base_delay=0.01),
            retryable_exceptions=(ValueError,)
        )
        
        def bad_callback(attempt, error):
            raise RuntimeError("callback failed")
        
        call_count = 0
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("not yet")
            return "success"
        
        # Should still succeed despite callback errors
        result = manager.execute_sync(eventually_succeeds, on_retry=bad_callback)
        assert result == "success"
    
    def test_tracks_total_delay(self):
        """Should track total delay time."""
        manager = RetryManager(
            RetryConfig(max_retries=2, base_delay=0.05, jitter_factor=0),
            retryable_exceptions=(ValueError,)
        )
        
        call_count = 0
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")
        
        with pytest.raises(ValueError):
            manager.execute_sync(failing_func)
        
        # With base_delay=0.05, exp_base=2.0, jitter=0:
        # Delay 0: 0.05, Delay 1: 0.10 = 0.15 total
        assert manager.last_total_delay == pytest.approx(0.15, rel=0.1)


@pytest.mark.asyncio
class TestRetryManagerAsync:
    """Async tests for RetryManager."""
    
    async def test_async_succeeds_on_first_try(self):
        """Should return result on first successful async call."""
        manager = RetryManager(RetryConfig(max_retries=3))
        
        async def async_success():
            return "async success"
        
        result = await manager.execute(async_success)
        
        assert result == "async success"
        assert manager.last_attempt_count == 1
    
    async def test_async_retries_on_failure(self):
        """Should retry async operations on failure."""
        manager = RetryManager(
            RetryConfig(max_retries=2, base_delay=0.01),
            retryable_exceptions=(ValueError,)
        )
        
        call_count = 0
        async def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("not yet")
            return "success"
        
        result = await manager.execute(eventually_succeeds)
        
        assert result == "success"
        assert call_count == 2


class TestRetryManagerProperty:
    """
    **Feature: primr-excellence, Property 2: Retry Backoff Pattern**
    **Validates: Requirements 2.1**
    
    For any sequence of N consecutive failures followed by success,
    the retry manager SHALL make exactly min(N+1, max_attempts) attempts.
    """
    
    @given(
        max_retries=st.integers(min_value=1, max_value=5),
        failures_before_success=st.integers(min_value=0, max_value=7)
    )
    @settings(max_examples=50)
    def test_attempt_count_property(self, max_retries: int, failures_before_success: int):
        """Attempt count should match expected based on failures and max_retries."""
        manager = RetryManager(
            RetryConfig(max_retries=max_retries, base_delay=0.001, jitter_factor=0),
            retryable_exceptions=(ValueError,)
        )
        
        call_count = 0
        def controlled_func():
            nonlocal call_count
            call_count += 1
            if call_count <= failures_before_success:
                raise ValueError("controlled failure")
            return "success"
        
        if failures_before_success <= max_retries:
            # Should eventually succeed
            result = manager.execute_sync(controlled_func)
            assert result == "success"
            assert manager.last_attempt_count == failures_before_success + 1
        else:
            # Should exhaust retries
            with pytest.raises(ValueError):
                manager.execute_sync(controlled_func)
            assert manager.last_attempt_count == max_retries + 1


# =============================================================================
# TESTS FOR ERROR FORMATTING
# =============================================================================

from primr.utils.errors import (
    format_error_for_user,
    get_error_guidance,
    is_recoverable_error,
    RateLimitError,
)


class TestErrorFormatting:
    """Tests for error formatting utilities."""
    
    def test_user_message_hides_cause(self):
        """User message should not expose internal exception details."""
        cause = RuntimeError("internal details")
        error = AIError("AI request failed", cause=cause)
        
        user_msg = error.user_message()
        
        assert "AI request failed" in user_msg
        assert "internal details" not in user_msg
        assert "RuntimeError" not in user_msg
    
    def test_user_message_includes_guidance(self):
        """User message should include guidance."""
        error = ConfigurationError("Missing API key")
        
        user_msg = error.user_message()
        
        assert "Missing API key" in user_msg
        assert ".env" in user_msg  # Default guidance mentions .env
    
    def test_debug_message_includes_cause(self):
        """Debug message should include cause chain."""
        cause = RuntimeError("internal details")
        error = AIError("AI request failed", model="gemini-pro", cause=cause)
        
        debug_msg = error.debug_message()
        
        assert "AI request failed" in debug_msg
        assert "RuntimeError" in debug_msg
        assert "internal details" in debug_msg
        assert "gemini-pro" in debug_msg
    
    def test_format_error_for_user_verbose(self):
        """format_error_for_user with verbose=True should show debug info."""
        error = ScrapingError("Failed to scrape", url="https://example.com")
        
        formatted = format_error_for_user(error, verbose=True)
        
        assert "https://example.com" in formatted
    
    def test_format_error_for_user_non_verbose(self):
        """format_error_for_user with verbose=False should hide details."""
        cause = RuntimeError("internal")
        error = ScrapingError("Failed to scrape", cause=cause)
        
        formatted = format_error_for_user(error, verbose=False)
        
        assert "Failed to scrape" in formatted
        assert "internal" not in formatted
    
    def test_format_non_research_error(self):
        """Should handle non-ResearchError exceptions."""
        error = ValueError("bad value")
        
        formatted = format_error_for_user(error, verbose=False)
        
        assert "bad value" in formatted


class TestErrorGuidance:
    """Tests for error guidance utilities."""
    
    def test_research_error_guidance(self):
        """Should return guidance from ResearchError."""
        error = ConfigurationError("Missing key")
        
        guidance = get_error_guidance(error)
        
        assert guidance is not None
        assert ".env" in guidance
    
    def test_custom_guidance(self):
        """Should use custom guidance when provided."""
        error = AIError("Failed", guidance="Custom guidance here")
        
        guidance = get_error_guidance(error)
        
        assert guidance == "Custom guidance here"
    
    def test_common_error_guidance(self):
        """Should provide guidance for common error types."""
        error = ConnectionError("Connection refused")
        
        guidance = get_error_guidance(error)
        
        assert guidance is not None
        assert "internet" in guidance.lower() or "connection" in guidance.lower()
    
    def test_unknown_error_no_guidance(self):
        """Should return None for unknown error types."""
        class CustomError(Exception):
            pass
        
        error = CustomError("unknown")
        
        guidance = get_error_guidance(error)
        
        assert guidance is None


class TestRecoverableErrors:
    """Tests for recoverable error detection."""
    
    def test_recoverable_research_error(self):
        """Should detect recoverable ResearchErrors."""
        assert is_recoverable_error(AIError("failed")) is True
        assert is_recoverable_error(ScrapingError("failed")) is True
        assert is_recoverable_error(RateLimitError()) is True
    
    def test_non_recoverable_research_error(self):
        """Should detect non-recoverable ResearchErrors."""
        assert is_recoverable_error(ConfigurationError("missing")) is False
        assert is_recoverable_error(ValidationError("invalid")) is False
    
    def test_recoverable_builtin_errors(self):
        """Should detect recoverable builtin errors."""
        assert is_recoverable_error(ConnectionError()) is True
        assert is_recoverable_error(TimeoutError()) is True
    
    def test_non_recoverable_builtin_errors(self):
        """Should detect non-recoverable builtin errors."""
        assert is_recoverable_error(ValueError("bad")) is False
        assert is_recoverable_error(TypeError("wrong")) is False


class TestRateLimitError:
    """Tests for RateLimitError."""
    
    def test_default_message(self):
        """Should have default message."""
        error = RateLimitError()
        assert "rate limit" in str(error).lower()
    
    def test_retry_after_in_guidance(self):
        """Should include retry_after in guidance."""
        error = RateLimitError(retry_after=60)
        
        guidance = error.guidance
        
        assert "60" in guidance
        assert "seconds" in guidance.lower()
    
    def test_is_recoverable(self):
        """Should be marked as recoverable."""
        error = RateLimitError()
        assert error.recoverable is True
        assert is_recoverable_error(error) is True


class TestStructuredErrorLoggingProperty:
    """
    **Feature: primr-excellence, Property 3: Structured Error Logging**
    **Validates: Requirements 2.3, 2.4**
    
    For any error that occurs, the log entry SHALL contain required fields
    and user-facing output SHALL NOT contain stack traces.
    """
    
    @given(
        message=st.text(min_size=1, max_size=100),
        url=st.text(min_size=0, max_size=50)
    )
    @settings(max_examples=50)
    def test_user_message_never_contains_traceback(self, message: str, url: str):
        """User message should never contain traceback indicators."""
        # Create error with a cause that has traceback-like content
        cause = RuntimeError("Traceback (most recent call last):\n  File...")
        error = ScrapingError(message, url=url, cause=cause)
        
        user_msg = error.user_message()
        
        # Should not contain traceback indicators
        assert "Traceback" not in user_msg
        assert "File" not in user_msg or "File" in message  # Unless in original message
        assert "most recent call" not in user_msg
    
    @given(error_type=st.sampled_from([
        ConfigurationError,
        ScrapingError,
        AIError,
        SearchError,
        OutputError,
        ValidationError,
    ]))
    @settings(max_examples=20)
    def test_all_error_types_have_category(self, error_type):
        """All error types should have a category."""
        error = error_type("test message")
        
        assert hasattr(error, 'category')
        assert error.category is not None
        assert len(error.category) > 0
    
    @given(error_type=st.sampled_from([
        ConfigurationError,
        ScrapingError,
        AIError,
        SearchError,
        OutputError,
        ValidationError,
    ]))
    @settings(max_examples=20)
    def test_debug_message_includes_category(self, error_type):
        """Debug message should include error category."""
        error = error_type("test message")
        
        debug_msg = error.debug_message()
        
        assert error.category in debug_msg
