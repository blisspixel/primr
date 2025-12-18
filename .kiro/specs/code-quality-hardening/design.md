# Design Document

## Overview

This design document outlines PhD-level code quality improvements for Primr. The focus is on hardening existing code rather than adding features. We'll improve type safety, error handling, resource management, concurrency, observability, and defensive programming.

This spec also includes the rebrand to `primr` CLI with simplified mode names (`scrape`, `deep`, `full`) and a new `primr doctor` diagnostic command.

The architecture remains unchanged; we're adding quality layers to existing components.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Quality Hardening Layers                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Type       │  │   Error      │  │   Resource   │              │
│  │   Guards     │  │   Handlers   │  │   Managers   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Concurrency  │  │ Observability│  │  Defensive   │              │
│  │   Safety     │  │   Layer      │  │   Validators │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Existing Application Code                         │
│  (AIClient, DeepResearchClient, ResearchOrchestrator, etc.)         │
└─────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Type Guards Module (New)

Runtime type validation for critical paths.

```python
# utils/type_guards.py

from typing import TypeVar, Type, Any, Optional, get_type_hints, get_origin, get_args
from dataclasses import fields, is_dataclass

T = TypeVar('T')

class TypeValidationError(ValueError):
    """Raised when runtime type validation fails."""
    def __init__(self, expected: str, actual: str, field: Optional[str] = None):
        self.expected = expected
        self.actual = actual
        self.field = field
        msg = f"Expected {expected}, got {actual}"
        if field:
            msg = f"Field '{field}': {msg}"
        super().__init__(msg)


def validate_type(value: Any, expected_type: Type[T], field_name: Optional[str] = None) -> T:
    """
    Validate that value matches expected type at runtime.
    
    Handles Optional, List, Dict, Union, and dataclass types.
    
    Args:
        value: Value to validate
        expected_type: Expected type
        field_name: Optional field name for error messages
        
    Returns:
        The value if valid
        
    Raises:
        TypeValidationError: If type doesn't match
    """
    pass


def validate_dataclass(instance: Any, cls: Type[T]) -> T:
    """
    Validate all fields of a dataclass instance.
    
    Args:
        instance: Dataclass instance to validate
        cls: Expected dataclass type
        
    Returns:
        The instance if valid
        
    Raises:
        TypeValidationError: If any field is invalid
    """
    pass


def validate_api_response(response: dict, required_fields: list[str]) -> dict:
    """
    Validate API response has required fields.
    
    Args:
        response: API response dict
        required_fields: List of required field names
        
    Returns:
        The response if valid
        
    Raises:
        TypeValidationError: If required fields missing
    """
    pass
```

### Enhanced Error Handling

Consistent error handling patterns across the codebase.

```python
# utils/errors.py (enhanced)

import functools
import random
import time
from typing import TypeVar, Callable, Optional, Type
from contextlib import contextmanager

T = TypeVar('T')

class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 0.1  # 10% jitter


def calculate_backoff_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay with exponential backoff and jitter.
    
    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration
        
    Returns:
        Delay in seconds with jitter applied
    """
    base_delay = config.base_delay * (config.exponential_base ** attempt)
    capped_delay = min(base_delay, config.max_delay)
    jitter_range = capped_delay * config.jitter
    jitter = random.uniform(-jitter_range, jitter_range)
    return max(0, capped_delay + jitter)


@contextmanager
def error_context(operation: str, **context):
    """
    Context manager that enriches exceptions with context.
    
    Usage:
        with error_context("fetching user", user_id=123):
            result = fetch_user(123)
    """
    pass


def async_safe_callback(callback: Callable) -> Callable:
    """
    Wrap callback to be safe for async contexts.
    
    Ensures callback doesn't block and handles exceptions.
    """
    pass
```

### Resource Manager

Guaranteed cleanup for all resource types.

```python
# utils/resources.py

import tempfile
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

@contextmanager
def managed_temp_file(
    suffix: str = ".tmp",
    prefix: str = "company_research_",
    content: Optional[str] = None
) -> Generator[Path, None, None]:
    """
    Context manager for temporary files with guaranteed cleanup.
    
    Args:
        suffix: File suffix
        prefix: File prefix
        content: Optional content to write
        
    Yields:
        Path to temporary file
        
    Note:
        File is deleted even if exception occurs.
    """
    pass


@contextmanager  
def managed_http_client(
    timeout: float = 30.0,
    max_connections: int = 10
) -> Generator:
    """
    Context manager for HTTP client with bounded connection pool.
    
    Args:
        timeout: Request timeout in seconds
        max_connections: Maximum concurrent connections
        
    Yields:
        Configured HTTP client
    """
    pass


class BoundedCache:
    """
    Thread-safe cache with size limits and TTL.
    
    Extends LRUCache with TTL support and metrics.
    """
    
    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: Optional[float] = None,
        name: str = "cache"
    ):
        pass
    
    def get_metrics(self) -> dict:
        """Get cache hit/miss statistics."""
        pass
```

### Observability Layer

Structured logging and metrics.

```python
# utils/observability.py

import time
import uuid
import functools
from contextlib import contextmanager
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class OperationContext:
    """Context for tracking an operation."""
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    operation: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


_current_context: Optional[OperationContext] = None


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one."""
    if _current_context:
        return _current_context.correlation_id
    return str(uuid.uuid4())[:8]


@contextmanager
def operation_context(operation: str, **metadata):
    """
    Context manager for tracking operations.
    
    Logs entry, exit, duration, and any errors with correlation ID.
    
    Usage:
        with operation_context("research", company="Tesla"):
            perform_research()
    """
    pass


def timed(func: Callable) -> Callable:
    """
    Decorator to log function entry, exit, and duration.
    
    Logs at DEBUG level with correlation ID.
    """
    pass


@dataclass
class Metrics:
    """Structured metrics for research operations."""
    operation: str
    duration_seconds: float
    success: bool
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error_type: Optional[str] = None
    correlation_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/export."""
        pass


def emit_metrics(metrics: Metrics) -> None:
    """
    Emit structured metrics.
    
    Currently logs as JSON. Can be extended for Prometheus, etc.
    """
    pass
```

### Defensive Validators

Input validation and sanitization.

```python
# utils/validators.py

import re
from pathlib import Path
from urllib.parse import urlparse, quote
from typing import Optional

class ValidationError(ValueError):
    """Raised when validation fails."""
    pass


def validate_url(url: str, allowed_schemes: tuple = ('http', 'https')) -> str:
    """
    Validate and normalize URL.
    
    Args:
        url: URL to validate
        allowed_schemes: Allowed URL schemes
        
    Returns:
        Normalized URL
        
    Raises:
        ValidationError: If URL is invalid or uses disallowed scheme
    """
    pass


def validate_company_name(name: str, max_length: int = 200) -> str:
    """
    Validate and sanitize company name.
    
    Args:
        name: Company name to validate
        max_length: Maximum allowed length
        
    Returns:
        Sanitized company name
        
    Raises:
        ValidationError: If name is empty or too long
    """
    pass


def validate_file_path(
    path: str,
    base_dir: Optional[Path] = None,
    must_exist: bool = False
) -> Path:
    """
    Validate file path against traversal attacks.
    
    Args:
        path: Path to validate
        base_dir: If provided, path must be within this directory
        must_exist: If True, path must exist
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is invalid or attempts traversal
    """
    pass


def safe_json_parse(content: str, default: any = None) -> any:
    """
    Safely parse JSON with graceful error handling.
    
    Args:
        content: JSON string to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed JSON or default value
    """
    pass


def sanitize_for_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitize string for use as filename.
    
    Removes/replaces characters that are invalid in filenames.
    
    Args:
        name: String to sanitize
        max_length: Maximum filename length
        
    Returns:
        Safe filename string
    """
    pass
```

## Data Models

### Configuration Models

```python
# config/settings.py (enhanced)

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path

@dataclass
class TimeoutConfig:
    """Timeout configuration with separate values."""
    connect: float = 10.0
    read: float = 30.0
    total: float = 60.0
    
    def validate(self) -> None:
        """Validate timeout values are positive and sensible."""
        if self.connect <= 0:
            raise ValueError("connect timeout must be positive")
        if self.read <= 0:
            raise ValueError("read timeout must be positive")
        if self.total < self.connect + self.read:
            raise ValueError("total timeout should be >= connect + read")


@dataclass
class CacheConfig:
    """Cache configuration."""
    max_size: int = 100
    ttl_seconds: Optional[float] = 3600.0
    
    def validate(self) -> None:
        """Validate cache configuration."""
        if self.max_size <= 0:
            raise ValueError("max_size must be positive")
        if self.ttl_seconds is not None and self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive or None")


@dataclass
class RetryConfig:
    """Retry configuration with backoff settings."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1
    
    def validate(self) -> None:
        """Validate retry configuration."""
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be positive")
        if self.jitter_factor < 0 or self.jitter_factor > 1:
            raise ValueError("jitter_factor must be between 0 and 1")
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Type Validator Correctness
*For any* value and expected type, the type validator SHALL accept values that match the type and reject values that don't match.
**Validates: Requirements 1.1, 1.2**

### Property 2: API Response Validation
*For any* API response dict and list of required fields, the validator SHALL accept responses containing all required fields and reject responses missing any required field.
**Validates: Requirements 1.5**

### Property 3: Async Error Propagation
*For any* async function that raises an exception, the exception SHALL propagate to the caller without being silently swallowed.
**Validates: Requirements 2.3**

### Property 4: Exponential Backoff with Jitter
*For any* sequence of retry attempts, the delay between attempts SHALL follow exponential growth with bounded jitter, and no two consecutive delays SHALL be identical.
**Validates: Requirements 2.5**

### Property 5: Temp File Cleanup on Exception
*For any* temporary file created within a managed context, the file SHALL be deleted even if an exception occurs within the context.
**Validates: Requirements 3.2**

### Property 6: LRU Cache Eviction
*For any* LRU cache with max_size N, after inserting N+1 items, the cache SHALL contain exactly N items and the oldest item SHALL have been evicted.
**Validates: Requirements 3.4**

### Property 7: Thread-Safe Singleton Access
*For any* number of concurrent threads accessing a singleton, all threads SHALL receive the same instance and no race conditions SHALL occur.
**Validates: Requirements 4.1**

### Property 8: Concurrent State Modification Safety
*For any* shared state protected by locks, concurrent modifications SHALL not corrupt the state or cause data races.
**Validates: Requirements 4.2, 4.3**

### Property 9: Progress Callback Thread Safety
*For any* progress callback invoked from multiple threads, the callback SHALL execute without blocking and handle concurrent invocation safely.
**Validates: Requirements 4.4**

### Property 10: Operation Logging Completeness
*For any* operation executed within an operation_context, the logs SHALL contain entry, exit, duration, and correlation ID.
**Validates: Requirements 5.1, 5.2**

### Property 11: Metrics Emission Completeness
*For any* completed research operation, the emitted metrics SHALL contain duration, token counts, cost, and success status.
**Validates: Requirements 5.3, 5.5**

### Property 12: URL Validation Security
*For any* URL string, the validator SHALL reject URLs with disallowed schemes, invalid format, or potential injection attacks.
**Validates: Requirements 7.2**

### Property 13: Path Traversal Prevention
*For any* file path containing traversal sequences (../, ..\), the validator SHALL reject the path when a base_dir constraint is specified.
**Validates: Requirements 7.3**

### Property 14: JSON Parse Safety
*For any* malformed JSON string, the safe parser SHALL return the default value without raising an exception.
**Validates: Requirements 7.4**

### Property 15: Content Deduplication Effectiveness
*For any* content with duplicate lines, deduplication SHALL reduce the content size, and the deduplicated content SHALL preserve all unique information.
**Validates: Requirements 9.1**

### Property 16: Cache Hit Rate Logging
*For any* cache operation (get/set), the cache SHALL track and log hit/miss statistics.
**Validates: Requirements 9.5**

### Property 17: Configuration Validation
*For any* configuration with invalid values (negative timeouts, zero cache size), the validator SHALL reject the configuration with a descriptive error.
**Validates: Requirements 10.2, 10.3**

## Error Handling

### Type Validation Errors
- Invalid type: Raise TypeValidationError with expected vs actual type
- Missing field: Raise TypeValidationError with field name
- Nested validation failure: Include full path to invalid field

### Resource Cleanup Errors
- Cleanup failure: Log warning but don't raise (cleanup is best-effort)
- Double cleanup: Handle gracefully (idempotent)
- Cleanup timeout: Log and continue

### Concurrency Errors
- Lock acquisition timeout: Raise with context about what was being locked
- Deadlock detection: Log warning with thread info
- Race condition detected: Log error with state snapshot

## Testing Strategy

### Unit Testing
- Test type validators with valid and invalid inputs
- Test error handlers with various exception types
- Test resource managers with normal and exception paths
- Test validators with edge cases and attack patterns

### Property-Based Testing
Using Hypothesis (Python PBT library):
- Generate random types and values for type validation
- Generate random retry sequences for backoff testing
- Generate random concurrent access patterns for thread safety
- Generate random file paths for traversal testing

### Test Configuration
- Property tests: minimum 100 iterations per property
- Each property test tagged with: `**Feature: code-quality-hardening, Property {number}: {property_text}**`
- Use hypothesis profiles for CI (fewer examples) vs local (more examples)

