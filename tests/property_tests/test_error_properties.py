"""
Property-based tests for the typed error hierarchy.

This module contains property tests that verify universal correctness properties
of the error hierarchy implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 1.1, 1.10, 1.11**
"""

from datetime import datetime, timedelta
import json
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.utils.errors import (
    AuthenticationError,
    PermanentError,
    PrimrConfigurationError,
    PrimrValidationError,
    QuotaError,
    TransientError,
    TypedNetworkError,
    TypedRateLimitError,
)
from primr.utils.observability import correlation_scope

# =============================================================================
# STRATEGIES FOR GENERATING ERROR INSTANCES
# =============================================================================

# Strategy for generating valid error messages
error_message_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")), min_size=1, max_size=200
).filter(lambda x: x.strip())  # Ensure non-empty after stripping

# Strategy for generating context dictionaries (JSON-serializable)
json_value_strategy = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=50),
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text(min_size=1, max_size=20), children, max_size=5)
    ),
    max_leaves=10,
)

context_strategy = st.dictionaries(
    st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=20),
    json_value_strategy,
    max_size=5,
)

# Strategy for generating retry_after values
retry_after_strategy = st.floats(
    min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False
)

# Strategy for generating host names
host_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=50
).map(lambda x: x.lower() + ".example.com")

# Strategy for generating port numbers
port_strategy = st.integers(min_value=1, max_value=65535)

# Strategy for generating field errors
field_errors_strategy = st.dictionaries(
    st.text(alphabet=st.characters(whitelist_categories=("L",)), min_size=1, max_size=20),
    st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=3),
    min_size=0,
    max_size=5,
)

# Strategy for generating missing keys
missing_keys_strategy = st.lists(
    st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=20),
    min_size=0,
    max_size=5,
)


def generate_transient_error(message: str, context: dict[str, Any]) -> TransientError:
    """Generate a TransientError instance."""
    return TransientError(message=message, context=context)


def generate_permanent_error(message: str, context: dict[str, Any]) -> PermanentError:
    """Generate a PermanentError instance."""
    return PermanentError(message=message, context=context)


def generate_rate_limit_error(
    message: str, retry_after_seconds: float, context: dict[str, Any]
) -> TypedRateLimitError:
    """Generate a TypedRateLimitError instance."""
    return TypedRateLimitError(
        message=message, retry_after_seconds=retry_after_seconds, context=context
    )


def generate_quota_error(
    message: str, hours_until_reset: float, context: dict[str, Any]
) -> QuotaError:
    """Generate a QuotaError instance."""
    reset_time = datetime.now() + timedelta(hours=max(0.01, hours_until_reset))
    return QuotaError(message=message, quota_reset_time=reset_time, context=context)


def generate_network_error(
    message: str, host: str, port: int, context: dict[str, Any]
) -> TypedNetworkError:
    """Generate a TypedNetworkError instance."""
    return TypedNetworkError(message=message, host=host, port=port, context=context)


def generate_validation_error(
    message: str, field_errors: dict[str, list[str]], context: dict[str, Any]
) -> PrimrValidationError:
    """Generate a PrimrValidationError instance."""
    return PrimrValidationError(message=message, field_errors=field_errors, context=context)


def generate_auth_error(
    message: str, auth_method: str, context: dict[str, Any]
) -> AuthenticationError:
    """Generate an AuthenticationError instance."""
    return AuthenticationError(message=message, auth_method=auth_method, context=context)


def generate_config_error(
    message: str, config_path: str, missing_keys: list[str], context: dict[str, Any]
) -> PrimrConfigurationError:
    """Generate a PrimrConfigurationError instance."""
    return PrimrConfigurationError(
        message=message, config_path=config_path, missing_keys=missing_keys, context=context
    )


# =============================================================================
# PROPERTY 1: ERROR STRUCTURE INVARIANT
# =============================================================================


class TestErrorStructureInvariant:
    """
    **Property 1: Error Structure Invariant**

    For any PrimrError instance (including all subclasses), the error SHALL have
    `category`, `recoverable`, `retry_after`, and `correlation_id` attributes
    with correct types.

    **Validates: Requirements 1.1**
    """

    @given(message=error_message_strategy, context=context_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_transient_error_has_required_attributes(self, message: str, context: dict[str, Any]):
        """TransientError should have all required attributes with correct types."""
        error = generate_transient_error(message, context)

        # Verify required attributes exist
        assert hasattr(error, "category")
        assert hasattr(error, "recoverable")
        assert hasattr(error, "retry_after")
        assert hasattr(error, "correlation_id")
        assert hasattr(error, "timestamp")
        assert hasattr(error, "cause")
        assert hasattr(error, "context")

        # Verify attribute types
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert error.retry_after is None or isinstance(error.retry_after, (int, float))
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.timestamp, datetime)
        assert error.cause is None or isinstance(error.cause, Exception)
        assert isinstance(error.context, dict)

        # Verify TransientError specific values
        assert error.recoverable is True
        assert error.category == "transient"

    @given(message=error_message_strategy, context=context_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_permanent_error_has_required_attributes(self, message: str, context: dict[str, Any]):
        """PermanentError should have all required attributes with correct types."""
        error = generate_permanent_error(message, context)

        # Verify required attributes exist and have correct types
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert error.retry_after is None or isinstance(error.retry_after, (int, float))
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.timestamp, datetime)

        # Verify PermanentError specific values
        assert error.recoverable is False
        assert error.category == "permanent"

    @given(
        message=error_message_strategy, retry_after=retry_after_strategy, context=context_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rate_limit_error_has_required_attributes(
        self, message: str, retry_after: float, context: dict[str, Any]
    ):
        """TypedRateLimitError should have all required attributes with correct types."""
        error = generate_rate_limit_error(message, retry_after, context)

        # Verify required attributes
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert isinstance(error.retry_after, (int, float))
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.retry_after_seconds, (int, float))

        # Verify specific values
        assert error.recoverable is True
        assert error.category == "rate_limit"
        assert error.retry_after == error.retry_after_seconds

    @given(
        message=error_message_strategy,
        hours=st.floats(min_value=0.01, max_value=24.0),
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_quota_error_has_required_attributes(
        self, message: str, hours: float, context: dict[str, Any]
    ):
        """QuotaError should have all required attributes with correct types."""
        error = generate_quota_error(message, hours, context)

        # Verify required attributes
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert isinstance(error.retry_after, (int, float))
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.quota_reset_time, datetime)

        # Verify specific values
        assert error.recoverable is True
        assert error.category == "quota"
        assert error.retry_after >= 0

    @given(
        message=error_message_strategy,
        host=host_strategy,
        port=port_strategy,
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_network_error_has_required_attributes(
        self, message: str, host: str, port: int, context: dict[str, Any]
    ):
        """TypedNetworkError should have all required attributes with correct types."""
        error = generate_network_error(message, host, port, context)

        # Verify required attributes
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.host, str)
        assert isinstance(error.port, int)

        # Verify specific values
        assert error.recoverable is True
        assert error.category == "network"
        assert error.host == host
        assert error.port == port

    @given(
        message=error_message_strategy, field_errors=field_errors_strategy, context=context_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_validation_error_has_required_attributes(
        self, message: str, field_errors: dict[str, list[str]], context: dict[str, Any]
    ):
        """PrimrValidationError should have all required attributes with correct types."""
        error = generate_validation_error(message, field_errors, context)

        # Verify required attributes
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.field_errors, dict)

        # Verify specific values
        assert error.recoverable is False
        assert error.category == "validation"

    @given(
        message=error_message_strategy,
        auth_method=st.sampled_from(["api_key", "oauth2", "basic", "bearer", ""]),
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_auth_error_has_required_attributes(
        self, message: str, auth_method: str, context: dict[str, Any]
    ):
        """AuthenticationError should have all required attributes with correct types."""
        error = generate_auth_error(message, auth_method, context)

        # Verify required attributes
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.auth_method, str)

        # Verify specific values
        assert error.recoverable is False
        assert error.category == "authentication"

    @given(
        message=error_message_strategy,
        config_path=st.text(min_size=0, max_size=100),
        missing_keys=missing_keys_strategy,
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_config_error_has_required_attributes(
        self, message: str, config_path: str, missing_keys: list[str], context: dict[str, Any]
    ):
        """PrimrConfigurationError should have all required attributes with correct types."""
        error = generate_config_error(message, config_path, missing_keys, context)

        # Verify required attributes
        assert isinstance(error.category, str)
        assert isinstance(error.recoverable, bool)
        assert isinstance(error.correlation_id, str)
        assert isinstance(error.config_path, str)
        assert isinstance(error.missing_keys, list)

        # Verify specific values
        assert error.recoverable is False
        assert error.category == "configuration"


# =============================================================================
# PROPERTY 2: CORRELATION ID AUTO-CAPTURE
# =============================================================================


class TestCorrelationIdAutoCapture:
    """
    **Property 2: Correlation ID Auto-Capture**

    For any error raised within a correlation context, the error's `correlation_id`
    attribute SHALL match the current context's correlation ID.

    **Validates: Requirements 1.10**
    """

    @given(
        message=error_message_strategy,
        operation_name=st.text(
            alphabet=st.characters(whitelist_categories=("L",)), min_size=1, max_size=20
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_transient_error_captures_correlation_id(self, message: str, operation_name: str):
        """TransientError should capture correlation ID from context."""
        with correlation_scope(operation_name) as ctx:
            error = TransientError(message=message)
            assert error.correlation_id == ctx.correlation_id

    @given(
        message=error_message_strategy,
        operation_name=st.text(
            alphabet=st.characters(whitelist_categories=("L",)), min_size=1, max_size=20
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_permanent_error_captures_correlation_id(self, message: str, operation_name: str):
        """PermanentError should capture correlation ID from context."""
        with correlation_scope(operation_name) as ctx:
            error = PermanentError(message=message)
            assert error.correlation_id == ctx.correlation_id

    @given(
        message=error_message_strategy,
        retry_after=retry_after_strategy,
        operation_name=st.text(
            alphabet=st.characters(whitelist_categories=("L",)), min_size=1, max_size=20
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rate_limit_error_captures_correlation_id(
        self, message: str, retry_after: float, operation_name: str
    ):
        """TypedRateLimitError should capture correlation ID from context."""
        with correlation_scope(operation_name) as ctx:
            error = TypedRateLimitError(message=message, retry_after_seconds=retry_after)
            assert error.correlation_id == ctx.correlation_id

    @given(
        message=error_message_strategy,
        operation_name=st.text(
            alphabet=st.characters(whitelist_categories=("L",)), min_size=1, max_size=20
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_nested_context_uses_innermost_correlation_id(self, message: str, operation_name: str):
        """Errors in nested contexts should use the innermost correlation ID."""
        with (
            correlation_scope("outer") as outer_ctx,
            correlation_scope(operation_name) as inner_ctx,
        ):
            error = TransientError(message=message)
            # Should use inner context's correlation ID
            assert error.correlation_id == inner_ctx.correlation_id
            # Inner and outer should be different
            assert inner_ctx.correlation_id != outer_ctx.correlation_id

    @given(message=error_message_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_error_without_context_generates_correlation_id(self, message: str):
        """Errors created outside a context should still have a correlation ID."""
        error = TransientError(message=message)

        # Should have a correlation ID
        assert error.correlation_id is not None
        assert isinstance(error.correlation_id, str)
        assert len(error.correlation_id) == 8  # UUID[:8]


# =============================================================================
# PROPERTY 3: ERROR SERIALIZATION ROUND-TRIP
# =============================================================================


class TestErrorSerializationRoundTrip:
    """
    **Property 3: Error Serialization Round-Trip**

    For any PrimrError instance, calling `to_dict()` SHALL produce a JSON-serializable
    dictionary, and the dictionary SHALL contain all error attributes including type,
    message, category, recoverable, retry_after, correlation_id, and timestamp.

    **Validates: Requirements 1.11**
    """

    @given(message=error_message_strategy, context=context_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_transient_error_serialization(self, message: str, context: dict[str, Any]):
        """TransientError.to_dict() should produce JSON-serializable dict with all attributes."""
        error = generate_transient_error(message, context)

        # Get serialized dict
        d = error.to_dict()

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

        # Verify required fields present
        assert "type" in d
        assert "message" in d
        assert "category" in d
        assert "recoverable" in d
        assert "retry_after" in d
        assert "correlation_id" in d
        assert "timestamp" in d
        assert "context" in d

        # Verify field values match error attributes
        assert d["type"] == "TransientError"
        assert d["message"] == error.message
        assert d["category"] == error.category
        assert d["recoverable"] == error.recoverable
        assert d["retry_after"] == error.retry_after
        assert d["correlation_id"] == error.correlation_id
        assert d["context"] == error.context

    @given(message=error_message_strategy, context=context_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_permanent_error_serialization(self, message: str, context: dict[str, Any]):
        """PermanentError.to_dict() should produce JSON-serializable dict with all attributes."""
        error = generate_permanent_error(message, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "PermanentError"
        assert d["recoverable"] is False
        assert d["category"] == "permanent"

    @given(
        message=error_message_strategy, retry_after=retry_after_strategy, context=context_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rate_limit_error_serialization(
        self, message: str, retry_after: float, context: dict[str, Any]
    ):
        """TypedRateLimitError.to_dict() should produce JSON-serializable dict."""
        error = generate_rate_limit_error(message, retry_after, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "TypedRateLimitError"
        assert d["retry_after"] == retry_after
        assert d["category"] == "rate_limit"

    @given(
        message=error_message_strategy,
        hours=st.floats(min_value=0.01, max_value=24.0),
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_quota_error_serialization(self, message: str, hours: float, context: dict[str, Any]):
        """QuotaError.to_dict() should produce JSON-serializable dict."""
        error = generate_quota_error(message, hours, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "QuotaError"
        assert d["category"] == "quota"
        assert isinstance(d["retry_after"], (int, float))

    @given(
        message=error_message_strategy,
        host=host_strategy,
        port=port_strategy,
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_network_error_serialization(
        self, message: str, host: str, port: int, context: dict[str, Any]
    ):
        """TypedNetworkError.to_dict() should produce JSON-serializable dict."""
        error = generate_network_error(message, host, port, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "TypedNetworkError"
        assert d["category"] == "network"

    @given(
        message=error_message_strategy, field_errors=field_errors_strategy, context=context_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_validation_error_serialization(
        self, message: str, field_errors: dict[str, list[str]], context: dict[str, Any]
    ):
        """PrimrValidationError.to_dict() should produce JSON-serializable dict."""
        error = generate_validation_error(message, field_errors, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "PrimrValidationError"
        assert d["category"] == "validation"
        assert d["recoverable"] is False

    @given(
        message=error_message_strategy,
        auth_method=st.sampled_from(["api_key", "oauth2", "basic", "bearer"]),
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_auth_error_serialization(
        self, message: str, auth_method: str, context: dict[str, Any]
    ):
        """AuthenticationError.to_dict() should produce JSON-serializable dict."""
        error = generate_auth_error(message, auth_method, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "AuthenticationError"
        assert d["category"] == "authentication"

    @given(
        message=error_message_strategy,
        config_path=st.text(min_size=0, max_size=50),
        missing_keys=missing_keys_strategy,
        context=context_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_config_error_serialization(
        self, message: str, config_path: str, missing_keys: list[str], context: dict[str, Any]
    ):
        """PrimrConfigurationError.to_dict() should produce JSON-serializable dict."""
        error = generate_config_error(message, config_path, missing_keys, context)

        d = error.to_dict()
        json.dumps(d)

        assert d["type"] == "PrimrConfigurationError"
        assert d["category"] == "configuration"

    @given(message=error_message_strategy, cause_message=error_message_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_error_with_cause_serialization(self, message: str, cause_message: str):
        """Error with cause should serialize cause information."""
        cause = ValueError(cause_message)
        error = TransientError(message=message, cause=cause)

        d = error.to_dict()
        json.dumps(d)

        # Verify cause is serialized
        assert "cause" in d
        assert d["cause"]["type"] == "ValueError"
        assert d["cause"]["message"] == cause_message

    @given(message=error_message_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_timestamp_is_iso_format(self, message: str):
        """Timestamp in to_dict() should be ISO format string."""
        error = TransientError(message=message)

        d = error.to_dict()

        # Verify timestamp is ISO format
        timestamp_str = d["timestamp"]
        assert isinstance(timestamp_str, str)

        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(timestamp_str)
        assert isinstance(parsed, datetime)
