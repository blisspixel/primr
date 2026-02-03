# Error Migration Guide

This document describes the typed error hierarchy in Primr v1.5.0.

## Overview

Primr v1.5.0 uses a unified typed error hierarchy that provides:
- Automatic retry classification via `recoverable` property
- Structured error context with correlation IDs
- Clear categorization (ai, scraping, search, configuration, validation, etc.)
- Backward-compatible aliases for existing code

## Error Classes

| Error Class | Category | Recoverable | Use Case |
|-------------|----------|-------------|----------|
| `PrimrError` | general | No | Base class for all errors |
| `TransientError` | transient | Yes | Base for retryable errors |
| `PermanentError` | permanent | No | Base for non-retryable errors |
| `AIError` | ai | Yes | AI/LLM operation failures |
| `ScrapingError` | scraping | Yes | Web scraping failures |
| `SearchError` | search | Yes | Search API failures |
| `RateLimitError` | rate_limit | Yes | API rate limit exceeded |
| `ConfigurationError` | configuration | No | Invalid/missing configuration |
| `ValidationError` | validation | No | Input validation failures |
| `OutputError` | output | No | Report generation failures |
| `NetworkError` | network | Yes | Network connectivity issues |

## Usage Examples

### Basic Error Handling

```python
from primr.utils.errors import AIError, ScrapingError, ConfigurationError

try:
    result = await api_call()
except AIError as e:
    if e.recoverable:
        # Safe to retry
        await asyncio.sleep(e.retry_after or 1.0)
        result = await api_call()
    else:
        raise
except ConfigurationError as e:
    # Not recoverable - fix configuration
    print(f"Configuration error: {e.message}")
    print(f"Guidance: {e.guidance}")
```

### Error with Context

```python
from primr.utils.errors import ScrapingError

# Create error with context
error = ScrapingError(
    message="Failed to scrape page",
    url="https://example.com",
    status_code=403,
    tier="playwright",
    cause=original_exception
)

# Access attributes
print(error.url)           # "https://example.com"
print(error.status_code)   # 403
print(error.recoverable)   # True
print(error.category)      # "scraping"

# User-friendly output
print(error.user_message())   # Message + guidance
print(error.debug_message())  # Full details including cause
```

### Rate Limit Handling

```python
from primr.utils.errors import RateLimitError

try:
    response = api.call()
except RateLimitError as e:
    # retry_after is automatically set
    await asyncio.sleep(e.retry_after)
    response = api.call()
```

## Error Formatting Utilities

```python
from primr.utils.errors import (
    format_error_for_user,
    get_error_guidance,
    is_recoverable_error,
)

# Format for display
user_msg = format_error_for_user(error, verbose=False)
debug_msg = format_error_for_user(error, verbose=True)

# Get guidance
guidance = get_error_guidance(error)

# Check recoverability
if is_recoverable_error(error):
    # Safe to retry
    pass
```

## Typed Error Hierarchy

All errors inherit from `PrimrError`, which provides:

- `message`: Human-readable error description
- `category`: Error category for classification
- `recoverable`: Whether the error can be retried
- `retry_after`: Suggested delay before retry (seconds)
- `correlation_id`: Unique ID for tracing
- `timestamp`: When the error occurred
- `cause`: The underlying exception
- `context`: Additional context data
- `guidance`: User-friendly resolution guidance

Methods:
- `user_message()`: Clean message for users (no stack traces)
- `debug_message()`: Detailed message for debugging
- `to_dict()`: JSON-serializable dictionary

## Backward Compatibility

The following aliases are provided for backward compatibility:

```python
# These all work and point to the typed error classes
from primr.utils.errors import (
    ResearchError,      # -> PrimrError
    AIError,            # -> PrimrAIError
    ScrapingError,      # -> PrimrScrapingError
    SearchError,        # -> PrimrSearchError
    ConfigurationError, # -> PrimrConfigurationError
    ValidationError,    # -> PrimrValidationError
    OutputError,        # -> PrimrOutputError
    RateLimitError,     # -> TypedRateLimitError (with wrapper)
    NetworkError,       # -> TypedNetworkError
)
```

Existing code using these names will continue to work without changes.
