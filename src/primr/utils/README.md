# Utils Module

This module provides shared utilities used across all other modules.

## Components

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
    AIError,
    ScrapingError,
    ValidationError,
    retry_on_failure,
    safe_call,
    error_context
)

# Custom errors with context
raise AIError("Model failed", model="gemini-2.0-flash", cause=original_error)

# Retry decorator
@retry_on_failure(max_retries=3, delay=1.0)
def flaky_operation():
    pass

# Safe call with default
result = safe_call(risky_function, default_value="fallback")

# Error context for debugging
with error_context("processing company", company="Tesla"):
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
name = validate_company_name("  Tesla  ")  # "Tesla"
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
with operation_context("research", company="Tesla"):
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

All errors inherit from base types:

```python
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
