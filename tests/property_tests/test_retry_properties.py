"""
Property-based tests for the retry policy manager.

This module contains property tests that verify universal correctness properties
of the retry policy implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 2.1-2.8**
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from primr.utils.errors import (
    AuthenticationError,
    PermanentError,
    PrimrValidationError,
    QuotaError,
    TransientError,
    TypedNetworkError,
    TypedRateLimitError,
)
from primr.utils.retry import (
    RetryPolicy,
    RetryPolicyManager,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating valid error messages
error_message_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S', 'Z')),
    min_size=1,
    max_size=100
).filter(lambda x: x.strip())

# Strategy for generating retry policy configurations
retry_policy_strategy = st.builds(
    RetryPolicy,
    max_retries=st.integers(min_value=0, max_value=10),
    base_delay=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    max_delay=st.floats(min_value=1.0, max_value=120.0, allow_nan=False, allow_infinity=False),
    exponential_base=st.floats(min_value=1.1, max_value=4.0, allow_nan=False, allow_infinity=False),
    jitter_factor=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)

# Strategy for generating attempt numbers
attempt_strategy = st.integers(min_value=0, max_value=20)

# Strategy for retry_after values
retry_after_strategy = st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False)

# Strategy for context dictionaries
json_value_strategy = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=50),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=3),
    max_leaves=5
)

context_strategy = st.dictionaries(
    st.text(alphabet=st.characters(whitelist_categories=('L', 'N')), min_size=1, max_size=10),
    json_value_strategy,
    max_size=3
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_transient_error(message: str, context: dict[str, Any] | None = None) -> TransientError:
    """Create a TransientError for testing."""
    return TransientError(message=message, context=context or {})


def create_permanent_error(message: str, context: dict[str, Any] | None = None) -> PermanentError:
    """Create a PermanentError for testing."""
    return PermanentError(message=message, context=context or {})


def create_rate_limit_error(
    message: str,
    retry_after_seconds: float,
    context: dict[str, Any] | None = None
) -> TypedRateLimitError:
    """Create a TypedRateLimitError for testing."""
    return TypedRateLimitError(
        message=message,
        retry_after_seconds=retry_after_seconds,
        context=context or {}
    )


def create_quota_error(
    message: str,
    hours_until_reset: float,
    context: dict[str, Any] | None = None
) -> QuotaError:
    """Create a QuotaError for testing."""
    reset_time = datetime.now() + timedelta(hours=max(0.01, hours_until_reset))
    return QuotaError(
        message=message,
        quota_reset_time=reset_time,
        context=context or {}
    )


def create_network_error(
    message: str,
    host: str = "example.com",
    port: int = 443,
    context: dict[str, Any] | None = None
) -> TypedNetworkError:
    """Create a TypedNetworkError for testing."""
    return TypedNetworkError(
        message=message,
        host=host,
        port=port,
        context=context or {}
    )


def create_validation_error(
    message: str,
    field_errors: dict[str, list[str]] | None = None,
    context: dict[str, Any] | None = None
) -> PrimrValidationError:
    """Create a PrimrValidationError for testing."""
    return PrimrValidationError(
        message=message,
        field_errors=field_errors or {},
        context=context or {}
    )


def create_auth_error(
    message: str,
    auth_method: str = "api_key",
    context: dict[str, Any] | None = None
) -> AuthenticationError:
    """Create an AuthenticationError for testing."""
    return AuthenticationError(
        message=message,
        auth_method=auth_method,
        context=context or {}
    )


# =============================================================================
# PROPERTY 4: RETRY ELIGIBILITY BY ERROR TYPE
# =============================================================================

class TestRetryEligibilityByErrorType:
    """
    **Property 4: Retry Eligibility by Error Type**
    
    For any error, `should_retry()` SHALL return `True` if and only if the error
    is a `TransientError` (or subclass) with `recoverable=True` and attempt count
    is below `max_retries`.
    
    **Validates: Requirements 2.1, 2.2, 2.3**
    """

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_transient_error_is_retryable_when_under_max_retries(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """TransientError should be retryable when attempt < max_retries."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        result = manager.should_retry(error, attempt)

        # Should be True iff attempt < max_retries and category is retryable
        expected = (
            attempt < policy.max_retries and
            error.category in policy.retryable_categories
        )
        assert result == expected

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_permanent_error_is_never_retryable(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """PermanentError should never be retryable regardless of attempt count."""
        manager = RetryPolicyManager(policy)
        error = create_permanent_error(message)

        result = manager.should_retry(error, attempt)

        # PermanentError has recoverable=False, so should never retry
        assert result is False

    @given(
        message=error_message_strategy,
        retry_after=retry_after_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rate_limit_error_is_retryable_when_under_max_retries(
        self, message: str, retry_after: float, policy: RetryPolicy, attempt: int
    ):
        """TypedRateLimitError should be retryable when attempt < max_retries."""
        manager = RetryPolicyManager(policy)
        error = create_rate_limit_error(message, retry_after)

        result = manager.should_retry(error, attempt)

        expected = (
            attempt < policy.max_retries and
            error.category in policy.retryable_categories
        )
        assert result == expected

    @given(
        message=error_message_strategy,
        hours=st.floats(min_value=0.01, max_value=24.0),
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_quota_error_is_retryable_when_under_max_retries(
        self, message: str, hours: float, policy: RetryPolicy, attempt: int
    ):
        """QuotaError should be retryable when attempt < max_retries."""
        manager = RetryPolicyManager(policy)
        error = create_quota_error(message, hours)

        result = manager.should_retry(error, attempt)

        expected = (
            attempt < policy.max_retries and
            error.category in policy.retryable_categories
        )
        assert result == expected

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_network_error_is_retryable_when_under_max_retries(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """TypedNetworkError should be retryable when attempt < max_retries."""
        manager = RetryPolicyManager(policy)
        error = create_network_error(message)

        result = manager.should_retry(error, attempt)

        expected = (
            attempt < policy.max_retries and
            error.category in policy.retryable_categories
        )
        assert result == expected

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_validation_error_is_never_retryable(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """PrimrValidationError should never be retryable."""
        manager = RetryPolicyManager(policy)
        error = create_validation_error(message)

        result = manager.should_retry(error, attempt)

        # ValidationError has recoverable=False
        assert result is False

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_auth_error_is_never_retryable(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """AuthenticationError should never be retryable."""
        manager = RetryPolicyManager(policy)
        error = create_auth_error(message)

        result = manager.should_retry(error, attempt)

        # AuthenticationError has recoverable=False
        assert result is False

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_primr_error_is_never_retryable(
        self, message: str, policy: RetryPolicy
    ):
        """Non-PrimrError exceptions should never be retryable."""
        manager = RetryPolicyManager(policy)
        error = ValueError(message)

        result = manager.should_retry(error, 0)

        assert result is False

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_at_max_retries_is_not_retryable(
        self, message: str, policy: RetryPolicy
    ):
        """Error at exactly max_retries should not be retryable."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        # At max_retries, should not retry
        result = manager.should_retry(error, policy.max_retries)

        assert result is False

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_above_max_retries_is_not_retryable(
        self, message: str, policy: RetryPolicy
    ):
        """Error above max_retries should not be retryable."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        # Above max_retries, should not retry
        result = manager.should_retry(error, policy.max_retries + 1)

        assert result is False


# =============================================================================
# PROPERTY 5: DELAY CALCULATION CORRECTNESS
# =============================================================================

class TestDelayCalculationCorrectness:
    """
    **Property 5: Delay Calculation Correctness**
    
    For any `RateLimitError` with `retry_after_seconds` set, `get_delay()` SHALL
    return exactly that value. For any `QuotaError` with `quota_reset_time` set,
    `get_delay()` SHALL return the time difference to that reset time.
    
    **Validates: Requirements 2.4, 2.5**
    """

    @given(
        message=error_message_strategy,
        retry_after=st.floats(min_value=0.1, max_value=3600.0, allow_nan=False, allow_infinity=False),
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rate_limit_error_uses_retry_after_seconds(
        self, message: str, retry_after: float, policy: RetryPolicy, attempt: int
    ):
        """RateLimitError should use retry_after_seconds for delay."""
        manager = RetryPolicyManager(policy)
        error = create_rate_limit_error(message, retry_after)

        delay = manager.get_delay(error, attempt)

        # Should return exactly retry_after_seconds
        assert delay == retry_after

    @given(
        message=error_message_strategy,
        seconds_until_reset=st.floats(min_value=1.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_quota_error_calculates_time_to_reset(
        self, message: str, seconds_until_reset: float, policy: RetryPolicy, attempt: int
    ):
        """QuotaError should calculate delay based on quota_reset_time."""
        manager = RetryPolicyManager(policy)

        # Create QuotaError with specific reset time
        reset_time = datetime.now() + timedelta(seconds=seconds_until_reset)
        error = QuotaError(message=message, quota_reset_time=reset_time)

        delay = manager.get_delay(error, attempt)

        # Should be approximately the time until reset (within 1 second tolerance)
        assert delay >= 0
        assert abs(delay - seconds_until_reset) < 1.0

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_transient_error_uses_exponential_backoff(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """TransientError without retry_after should use exponential backoff."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        delay = manager.get_delay(error, attempt)

        # Calculate expected delay range
        base_delay = policy.base_delay * (policy.exponential_base ** attempt)
        capped_delay = min(base_delay, policy.max_delay)
        jitter_range = capped_delay * policy.jitter_factor

        # Delay should be within jitter range of expected
        assert delay >= max(0, capped_delay - jitter_range)
        assert delay <= capped_delay + jitter_range

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=attempt_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delay_is_always_non_negative(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """Delay should always be non-negative."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        delay = manager.get_delay(error, attempt)

        assert delay >= 0

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy,
        attempt=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delay_respects_max_delay(
        self, message: str, policy: RetryPolicy, attempt: int
    ):
        """Delay should never exceed max_delay (plus jitter)."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        delay = manager.get_delay(error, attempt)

        # Max possible delay is max_delay + jitter
        max_possible = policy.max_delay * (1 + policy.jitter_factor)
        assert delay <= max_possible

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delay_increases_with_attempt(
        self, message: str, policy: RetryPolicy
    ):
        """Average delay should increase with attempt number (exponential backoff)."""
        manager = RetryPolicyManager(policy)
        error = create_transient_error(message)

        # Get delays for multiple attempts
        delays_0 = [manager.get_delay(error, 0) for _ in range(10)]
        delays_2 = [manager.get_delay(error, 2) for _ in range(10)]

        avg_0 = sum(delays_0) / len(delays_0)
        avg_2 = sum(delays_2) / len(delays_2)

        # Expected base delays
        expected_0 = min(policy.base_delay, policy.max_delay)
        expected_2 = min(policy.base_delay * (policy.exponential_base ** 2), policy.max_delay)

        # Average should be close to expected (within jitter tolerance)
        if expected_2 > expected_0:
            # Only check if expected_2 is actually larger (not capped)
            assert avg_2 >= avg_0 * 0.5  # Allow for jitter variance

    @given(
        message=error_message_strategy,
        policy=retry_policy_strategy
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_quota_error_past_reset_time_returns_zero(
        self, message: str, policy: RetryPolicy
    ):
        """QuotaError with past reset time should return 0 delay."""
        manager = RetryPolicyManager(policy)

        # Create QuotaError with reset time in the past
        reset_time = datetime.now() - timedelta(seconds=10)
        error = QuotaError(message=message, quota_reset_time=reset_time)

        delay = manager.get_delay(error, 0)

        # Should return 0 (or very small positive due to timing)
        assert delay >= 0
        assert delay < 1.0  # Should be essentially 0


# =============================================================================
# PROPERTY 6: RETRY HISTORY ATTACHMENT
# =============================================================================

class TestRetryHistoryAttachment:
    """
    **Property 6: Retry History Attachment**
    
    For any operation that exhausts all retries, the final raised error SHALL
    have a `retry_history` key in its `context` dictionary containing all
    previous attempt details.
    
    **Validates: Requirements 2.8**
    """

    @given(
        message=error_message_strategy,
        max_retries=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_retry_history_attached_on_exhaustion(
        self, message: str, max_retries: int
    ):
        """Retry history should be attached when retries are exhausted."""
        policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=0.001,  # Very short delay for testing
            jitter_factor=0.0
        )
        manager = RetryPolicyManager(policy)

        call_count = 0

        def failing_operation():
            nonlocal call_count
            call_count += 1
            raise create_transient_error(message)

        with pytest.raises(TransientError) as exc_info:
            manager.execute_with_retry_sync(failing_operation)

        error = exc_info.value

        # Should have retry_history in context
        assert "retry_history" in error.context

        # Should have max_retries entries (one for each retry attempt)
        history = error.context["retry_history"]
        assert len(history) == max_retries

        # Each entry should have required fields
        for i, entry in enumerate(history):
            assert "attempt" in entry
            assert "error" in entry
            assert "delay" in entry
            assert "timestamp" in entry
            assert entry["attempt"] == i

    @given(
        message=error_message_strategy,
        max_retries=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_retry_history_attached_on_exhaustion_async(
        self, message: str, max_retries: int
    ):
        """Retry history should be attached when async retries are exhausted."""
        policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=0.001,
            jitter_factor=0.0
        )
        manager = RetryPolicyManager(policy)

        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise create_transient_error(message)

        async def run_test():
            with pytest.raises(TransientError) as exc_info:
                await manager.execute_with_retry(failing_operation)
            return exc_info.value

        error = asyncio.run(run_test())

        # Should have retry_history in context
        assert "retry_history" in error.context
        assert len(error.context["retry_history"]) == max_retries

    @given(message=error_message_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_no_retry_history_on_success(self, message: str):
        """Successful operations should not have retry history."""
        policy = RetryPolicy(max_retries=3, base_delay=0.001)
        manager = RetryPolicyManager(policy)

        def successful_operation():
            return "success"

        result = manager.execute_with_retry_sync(successful_operation)

        assert result == "success"
        # Manager's attempts list should be empty
        assert len(manager.attempts) == 0

    @given(
        message=error_message_strategy,
        max_retries=st.integers(min_value=2, max_value=5),
        succeed_on=st.integers(min_value=1, max_value=4)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_retry_history_tracks_attempts_before_success(
        self, message: str, max_retries: int, succeed_on: int
    ):
        """Retry history should track attempts even when eventually successful."""
        # Ensure succeed_on is within valid range
        assume(succeed_on <= max_retries)

        policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=0.001,
            jitter_factor=0.0
        )
        manager = RetryPolicyManager(policy)

        call_count = 0

        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count <= succeed_on:
                raise create_transient_error(message)
            return "success"

        result = manager.execute_with_retry_sync(eventually_succeeds)

        assert result == "success"
        # Should have tracked the failed attempts
        assert len(manager.attempts) == succeed_on

    @given(message=error_message_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_retry_history_not_attached_for_permanent_error(
        self, message: str
    ):
        """Permanent errors should not have retry history (no retries attempted)."""
        policy = RetryPolicy(max_retries=3, base_delay=0.001)
        manager = RetryPolicyManager(policy)

        def raises_permanent():
            raise create_permanent_error(message)

        with pytest.raises(PermanentError) as exc_info:
            manager.execute_with_retry_sync(raises_permanent)

        error = exc_info.value

        # Should not have retry_history (no retries were attempted)
        assert "retry_history" not in error.context or len(error.context.get("retry_history", [])) == 0

    @given(
        message=error_message_strategy,
        max_retries=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_retry_history_contains_error_type(
        self, message: str, max_retries: int
    ):
        """Retry history entries should contain error type information."""
        policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=0.001,
            jitter_factor=0.0
        )
        manager = RetryPolicyManager(policy)

        def failing_operation():
            raise create_network_error(message)

        with pytest.raises(TypedNetworkError) as exc_info:
            manager.execute_with_retry_sync(failing_operation)

        error = exc_info.value
        history = error.context["retry_history"]

        # Each entry should have error_type
        for entry in history:
            assert "error_type" in entry
            assert entry["error_type"] == "TypedNetworkError"

    @given(
        message=error_message_strategy,
        max_retries=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_retry_history_delays_are_recorded(
        self, message: str, max_retries: int
    ):
        """Retry history should record the actual delays used."""
        base_delay = 0.001
        policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=base_delay,
            exponential_base=2.0,
            jitter_factor=0.0  # No jitter for predictable delays
        )
        manager = RetryPolicyManager(policy)

        def failing_operation():
            raise create_transient_error(message)

        with pytest.raises(TransientError) as exc_info:
            manager.execute_with_retry_sync(failing_operation)

        error = exc_info.value
        history = error.context["retry_history"]

        # Verify delays follow exponential backoff pattern
        for i, entry in enumerate(history):
            expected_delay = base_delay * (2.0 ** i)
            assert abs(entry["delay"] - expected_delay) < 0.0001
