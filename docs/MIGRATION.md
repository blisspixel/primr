# Error Migration Guide

This document describes the migration from legacy error classes to the typed error hierarchy introduced in v1.5.0.

## Overview

Primr v1.5.0 introduces a unified typed error hierarchy that provides:
- Automatic retry classification via `is_retryable` property
- Structured error context with `ErrorContext` dataclass
- Clear categorization (network, API, validation, resource, internal)

## Migration Table

| Legacy Error | New Typed Error | Category |
|-------------|-----------------|----------|
| `ResearchError` | `PrimrError` | Base class |
| `RateLimitError` | `TypedRateLimitError` | API |
| `APIError` | `TypedAPIError` | API |
| `NetworkError` | `TypedNetworkError` | Network |
| `TimeoutError` | `TypedTimeoutError` | Network |
| `ValidationError` | `TypedValidationError` | Validation |
| `ConfigurationError` | `TypedConfigurationError` | Validation |
| `ResourceError` | `TypedResourceError` | Resource |
| `ContentError` | `TypedContentError` | Resource |
| `InternalError` | `TypedInternalError` | Internal |

## Code Examples

### Before (Legacy)

```python
from primr.utils.errors import RateLimitError, APIError

try:
    result = await api_call()
except RateLimitError as e:
    # Manual retry logic
    if should_retry(e):
        await asyncio.sleep(e.retry_after or 60)
        result = await api_call()
except APIError as e:
    logger.error(f"API failed: {e}")
    raise
```

### After (Typed Hierarchy)

```python
from primr.utils.errors import TypedRateLimitError, TypedAPIError

try:
    result = await api_call()
except TypedRateLimitError as e:
    # Automatic retry classification
    if e.is_retryable:
        await asyncio.sleep(e.retry_after or 60)
        result = await api_call()
except TypedAPIError as e:
    # Structured context available
    logger.error(f"API failed: {e.message}", extra={
        "status_code": e.status_code,
        "context": e.context.to_dict() if e.context else None
    })
    raise
```

### Using ErrorContext

```python
from primr.utils.errors import TypedNetworkError, ErrorContext

# Create error with rich context
error = TypedNetworkError(
    message="Connection refused",
    context=ErrorContext(
        operation="fetch_page",
        url="https://example.com",
        attempt=3,
        max_attempts=5,
        metadata={"timeout": 30}
    )
)

# Access context
print(error.context.operation)  # "fetch_page"
print(error.is_retryable)       # True (network errors are retryable)
```

## Gradual Migration Strategy

1. **Phase 1**: Import both old and new errors, catch new errors first
2. **Phase 2**: Update error raising to use typed errors
3. **Phase 3**: Remove legacy error imports

### Phase 1 Example

```python
from primr.utils.errors import (
    # New typed errors (preferred)
    TypedRateLimitError,
    TypedAPIError,
    # Legacy errors (for compatibility)
    RateLimitError,
    APIError,
)

try:
    result = await api_call()
except TypedRateLimitError as e:
    # Handle new typed error
    handle_rate_limit(e)
except RateLimitError as e:
    # Fallback for legacy code paths
    handle_rate_limit_legacy(e)
```

## Deprecation Timeline

- **v1.5.0**: Typed error hierarchy introduced, legacy errors deprecated, warnings enabled by default
- **v2.0.0**: Legacy errors will be removed

To suppress deprecation warnings during migration:

```python
import primr.utils.errors
primr.utils.errors._EMIT_DEPRECATION_WARNINGS = False
```

Or set in your test configuration / conftest.py.

## Benefits of Migration

1. **Automatic Retry Logic**: `is_retryable` property eliminates manual classification
2. **Structured Context**: `ErrorContext` provides consistent error metadata
3. **Type Safety**: Better IDE support and static analysis
4. **Observability**: Errors integrate with telemetry via `to_dict()`
