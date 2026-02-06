# Utils Module

This module provides shared utilities used across all other modules.

## Components

### Async Utilities (`async_utils.py`) - NEW

Unified async/sync boundary handling:

```python
from primr.utils.async_utils import (
    run_sync,
    run_async,
    ensure_async,
    ensure_sync,
    AsyncBridge,
    gather_with_concurrency,
)

# Run async code from sync context
result = run_sync(async_function())

# Run blocking code from async context without blocking event loop
result = await run_async(blocking_function, arg1, arg2)

# Wrap sync function for async use
@ensure_async
def blocking_io():
    return read_file()

result = await blocking_io()

# Wrap async function for sync use
@ensure_sync
async def async_operation():
    return await fetch_data()

result = async_operation()  # Can call from sync code

# Limit concurrent async operations
results = await gather_with_concurrency(
    3,  # Max 3 concurrent
    fetch(url1),
    fetch(url2),
    fetch(url3),
    fetch(url4),
)
```

### Configuration Validation (`config_validation.py`) - NEW

Unified configuration validation with clear error messages:

```python
from primr.utils.config_validation import (
    PrimrConfig,
    load_config,
    validate_config,
    require_valid_config,
    export_schema,
)

# Load and validate configuration
config = load_config()
result = config.validate()

if not result.valid:
    for error in result.errors:
        print(f"{error.field}: {error.message}")
        if error.suggestion:
            print(f"  Suggestion: {error.suggestion}")

# Fail fast at startup
config = require_valid_config()  # Raises if invalid

# Export JSON Schema for documentation
schema = export_schema()
```

### Console Output (`console.py`)

Unified console output with consistent formatting:

```python
from primr.utils.console import console

console.step("Starting research...")
console.ok("Research complete")
console.warn("Some sections had low quality")
console.error("Failed to scrape website")
console.progress(5, 10, "Processing sections")
console.progress_done()
```

### Logging (`logging_config.py`)

Module-specific loggers with consistent configuration:

```python
from primr.utils.logging_config import get_logger, setup_logging

logger = get_logger("my_module")
logger.info("Operation started")
logger.debug("Debug details")

# Configure logging
setup_logging(level="DEBUG", log_file="primr.log")
```

### Error Handling (`errors.py`)

Custom error types and retry utilities:

```python
from primr.utils.errors import (
    # Typed error hierarchy (preferred for new code)
    PrimrError,
    TransientError,
    PermanentError,
    TypedRateLimitError,
    QuotaError,
    
    # Legacy errors (still supported)
    AIError,
    ScrapingError,
    ValidationError,
    
    # Utilities
    retry_on_failure,
    safe_call,
    error_context
)

# Typed errors with automatic retry classification
raise TypedRateLimitError(
    message="Rate limit exceeded",
    retry_after_seconds=60.0
)

# Check if error is retryable
if isinstance(error, TransientError) and error.recoverable:
    await asyncio.sleep(error.retry_after or 1.0)
    retry()

# Legacy errors (deprecated but still work)
raise AIError("Model failed", model="gemini-2.0-flash", cause=original_error)

# Retry decorator
@retry_on_failure(max_retries=3, delay=1.0)
def flaky_operation():
    pass

# Safe call with default
result = safe_call(risky_function, default_value="fallback")

# Error context for debugging
with error_context("processing company", company="Acme Corp"):
    process(data)
```

### File Operations (`files.py`)

Safe file handling utilities:

```python
from primr.utils.files import (
    secure_temp_file,
    secure_temp_dir,
    sanitize_filename,
    get_company_folder,
    get_cache_key
)

# Secure temp file with cleanup
with secure_temp_file(suffix=".txt") as path:
    path.write_text("content")

# Safe filename
safe_name = sanitize_filename("Company/Name: Test")  # "Company_Name_Test"

# Cache key from URL
key = get_cache_key("https://example.com/page")  # SHA-256 hash
```

### Formatting (`formatting.py`)

Text formatting utilities:

```python
from primr.utils.formatting import (
    clean_content,
    format_number,
    format_currency,
    remove_emojis,
    remove_em_dashes
)

clean = clean_content(raw_text)
formatted = format_currency(1500000)  # "$1.5M"
no_emoji = remove_emojis(text)
```

### Input Validation (`validators.py`)

Input validation and sanitization:

```python
from primr.utils.validators import (
    validate_url,
    validate_company_name,
    validate_file_path,
    safe_json_parse
)

url = validate_url("example.com")  # "https://example.com"
name = validate_company_name("  Acme Corp  ")  # "Acme Corp"
data = safe_json_parse(json_string, default={})
```

### Type Guards (`type_guards.py`)

Runtime type checking:

```python
from primr.utils.type_guards import (
    validate_type,
    validate_dataclass,
    is_valid_type
)

# Validate and raise if wrong type
validate_type(value, str, "parameter_name")

# Check without raising
if is_valid_type(value, int):
    process(value)
```

### Resource Management (`resources.py`)

Resource lifecycle utilities:

```python
from primr.utils.resources import (
    managed_temp_file,
    managed_http_client,
    BoundedCache,
    ThreadSafeSingleton
)

# Managed resources with cleanup
with managed_temp_file() as path:
    # File is deleted after block

# Bounded cache
cache = BoundedCache(max_size=100)
cache.set("key", "value")
```

### Observability (`observability.py`)

Metrics and tracing:

```python
from primr.utils.observability import (
    operation_context,
    timed,
    Metrics,
    emit_metrics,
    get_correlation_id
)

# Track operation
with operation_context("research", company="Acme Corp"):
    # Operations are tracked with correlation ID
    pass

# Timing decorator
@timed("my_operation")
def slow_function():
    pass

# Emit custom metrics
metrics = Metrics(
    operation="custom",
    duration_seconds=5.0,
    success=True
)
emit_metrics(metrics)
```

### Chat Logging (`chat_logger.py`)

Logs AI interactions for debugging:

```python
from primr.utils.chat_logger import log_chat_interaction

log_chat_interaction(
    prompt=prompt,
    response=response,
    model="gemini-2.0-flash"
)
```

## Key Patterns

### Consistent Error Handling

The codebase uses a typed error hierarchy for automatic retry classification:

```python
# Typed hierarchy (preferred for new code)
class PrimrError(Exception, ABC): pass      # Base with correlation_id, retry_after
class TransientError(PrimrError): pass      # Recoverable errors (retry)
class PermanentError(PrimrError): pass      # Non-recoverable errors (don't retry)
class TypedRateLimitError(TransientError): pass
class QuotaError(TransientError): pass
class TypedNetworkError(TransientError): pass
class PrimrValidationError(PermanentError): pass
class AuthenticationError(PermanentError): pass
class PrimrConfigurationError(PermanentError): pass

# Legacy hierarchy (deprecated, use typed hierarchy for new code)
class ResearchError(Exception): pass
class AIError(ResearchError): pass
class ScrapingError(ResearchError): pass
class ConfigurationError(ResearchError): pass
class ValidationError(ResearchError): pass
class OutputError(ResearchError): pass
```

### Retry with Backoff

Exponential backoff with jitter:

```python
from primr.utils.errors import calculate_backoff_delay

delay = calculate_backoff_delay(
    attempt=2,
    base_delay=1.0,
    max_delay=60.0,
    jitter=True
)
```

### Thread-Safe Singletons

Pattern used across the codebase:

```python
from primr.utils.resources import ThreadSafeSingleton

class MyService(metaclass=ThreadSafeSingleton):
    pass

# Always returns same instance
service = MyService()
```

## Configuration

Utils behavior is configured via environment variables:

- `VERBOSE`: Enable verbose console output
- `DEBUG`: Enable debug logging
- `LOG_FILE`: Path to log file
