# Design Document: Primr Excellence

## Overview

This design elevates Primr from a functional CLI tool to a reference-grade implementation through two parallel tracks:

1. **Code Quality Track**: Comprehensive type safety, property-based testing, and defensive programming
2. **UX Excellence Track**: Premium CLI experience with intelligent progress feedback and visual hierarchy

The architecture preserves Primr's existing modular structure while adding cross-cutting concerns for validation, observability, and resource management.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Arg Parser  │  │ Validators  │  │ Premium Console         │  │
│  │ + fuzzy     │  │ + preflight │  │ + phase banners         │  │
│  │   suggest   │  │   checks    │  │ + heartbeat             │  │
│  └─────────────┘  └─────────────┘  │ + elapsed time          │  │
│                                     └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Research        │  │ Correlation     │  │ Resource        │  │
│  │ Orchestrator    │  │ Context         │  │ Manager         │  │
│  │ + retry logic   │  │ + trace IDs     │  │ + cleanup       │  │
│  │ + job recovery  │  │ + structured    │  │ + temp files    │  │
│  └─────────────────┘  │   logging       │  │ + connections   │  │
│                       └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Services                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ AI       │  │ Scraper  │  │ Cache    │  │ Document Builder │ │
│  │ Client   │  │          │  │ (thread  │  │ + table render   │ │
│  │ + guards │  │ + guards │  │  safe)   │  │ + citation fmt   │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Foundation Layer                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Type Guards     │  │ Result Monad    │  │ Config          │  │
│  │ + validate_type │  │ + ok/err        │  │ Validator       │  │
│  │ + validate_api  │  │ + unwrap_or     │  │ + env/file      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Enhanced Type Guards (`primr.utils.type_guards`)

Extends existing type guard system with:

```python
@dataclass
class ValidationResult(Generic[T]):
    """Result of validation with detailed error info."""
    value: T | None
    errors: list[ValidationError]
    warnings: list[str]
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

class ValidationError:
    """Structured validation error."""
    field: str
    expected: str
    actual: str
    message: str
    suggestion: str | None

def validate_api_response(
    response: Any,
    schema: type[T],
    strict: bool = True
) -> ValidationResult[T]:
    """Validate API response against expected schema."""
    
def validate_config(
    config: dict[str, Any],
    schema: ConfigSchema
) -> ValidationResult[Config]:
    """Validate configuration with range checks."""
```

### 2. Retry Manager (`primr.utils.retry`)

```python
@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 0.1
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError, TimeoutError, RateLimitError
    )

class RetryManager:
    """Manages retry logic with exponential backoff and jitter."""
    
    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        config: RetryConfig | None = None,
        on_retry: Callable[[int, Exception], None] | None = None
    ) -> T:
        """Execute operation with retry logic."""
```

### 3. Correlation Context (`primr.utils.observability`)

```python
@dataclass
class CorrelationContext:
    """Thread-local correlation context for tracing."""
    correlation_id: str
    operation_name: str
    start_time: float
    metadata: dict[str, Any]
    
    @classmethod
    def create(cls, operation: str) -> 'CorrelationContext':
        """Create new context with generated correlation ID."""

@contextmanager
def correlation_scope(operation: str) -> Generator[CorrelationContext, None, None]:
    """Context manager for correlation tracking."""

def log_structured(
    level: str,
    message: str,
    **fields: Any
) -> None:
    """Log with correlation context and structured fields."""
```

### 4. Premium Console Extensions (`primr.utils.console`)

Extends existing Console class:

```python
class Console:
    # Existing methods...
    
    # New phase management
    def phase_banner(
        self,
        step: int,
        total: int,
        title: str,
        description: str = "",
        expected_duration: str = ""
    ) -> None:
        """Display prominent phase transition banner."""
    
    def phase_complete(
        self,
        title: str,
        stats: list[tuple[str, str]] | None = None
    ) -> None:
        """Display phase completion summary."""
    
    # Enhanced progress
    def progress_with_time(
        self,
        current: int,
        total: int,
        label: str = "",
        start_time: float | None = None
    ) -> None:
        """Progress bar with elapsed time."""
    
    @contextmanager
    def heartbeat(
        self,
        message: str,
        interval: float = 30.0
    ) -> Generator[None, None, None]:
        """Periodic heartbeat during long operations."""
    
    @contextmanager
    def timed_operation(
        self,
        message: str,
        show_spinner: bool = True
    ) -> Generator[None, None, None]:
        """Context manager showing elapsed time on completion."""
```

### 5. Resource Manager (`primr.utils.resources`)

```python
class ResourceManager:
    """Manages cleanup of resources on exit."""
    
    _temp_files: set[Path]
    _open_handles: set[IO]
    _browser_processes: set[int]
    
    def register_temp_file(self, path: Path) -> None:
        """Register temp file for cleanup."""
    
    def register_handle(self, handle: IO) -> None:
        """Register file handle for cleanup."""
    
    def cleanup(self) -> None:
        """Clean up all registered resources."""
    
    def __enter__(self) -> 'ResourceManager':
        """Context manager entry."""
    
    def __exit__(self, *args) -> None:
        """Cleanup on exit."""

# Global instance with atexit registration
resource_manager = ResourceManager()
atexit.register(resource_manager.cleanup)
```

### 6. CLI Validator (`primr.utils.validators`)

```python
@dataclass
class CLIValidationResult:
    """Result of CLI argument validation."""
    valid: bool
    normalized_args: dict[str, Any]
    errors: list[str]
    suggestions: list[str]

def validate_url(url: str) -> tuple[bool, str, str | None]:
    """Validate and normalize URL. Returns (valid, normalized, error)."""

def validate_cli_args(args: argparse.Namespace) -> CLIValidationResult:
    """Comprehensive CLI argument validation."""

def suggest_similar(unknown: str, valid_options: list[str]) -> list[str]:
    """Fuzzy match unknown option to valid options."""
```

### 7. Thread-Safe Cache (`primr.data.cache`)

Enhance existing cache with thread safety:

```python
class ThreadSafeCache:
    """Thread-safe cache with size limits and eviction."""
    
    _lock: threading.RLock
    _max_size: int
    _eviction_policy: Literal["lru", "fifo"]
    
    def get(self, key: str) -> str | None:
        """Thread-safe get."""
    
    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Thread-safe set with optional TTL."""
    
    def _evict_if_needed(self) -> None:
        """Evict oldest entries if over size limit."""
```

## Data Models

### Validation Models

```python
@dataclass
class ConfigSchema:
    """Schema for configuration validation."""
    required_keys: list[str]
    optional_keys: dict[str, Any]  # key -> default
    type_hints: dict[str, type]
    validators: dict[str, Callable[[Any], bool]]
    ranges: dict[str, tuple[Any, Any]]  # key -> (min, max)

@dataclass  
class APIResponseSchema:
    """Schema for API response validation."""
    required_fields: list[str]
    field_types: dict[str, type]
    nested_schemas: dict[str, 'APIResponseSchema']
```

### Observability Models

```python
@dataclass
class APICallLog:
    """Structured log entry for API calls."""
    correlation_id: str
    timestamp: str
    operation: str
    request_params: dict[str, Any]
    response_status: int | str
    duration_ms: float
    tokens_used: int | None
    error: str | None

@dataclass
class JobSummary:
    """Summary of completed research job."""
    correlation_id: str
    company: str
    mode: str
    duration_seconds: float
    api_calls: int
    total_tokens: int
    sections_generated: int
    errors: list[str]
    warnings: list[str]
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Type Guard Correctness

*For any* input value and expected type, the type guard SHALL either:
- Return the value unchanged if it matches the type
- Raise TypeValidationError with field, expected, and actual if it doesn't match

This property combines validation of API responses (1.2), configuration (1.3), and error structure (1.5).

**Validates: Requirements 1.2, 1.3, 1.5**

### Property 2: Retry Backoff Pattern

*For any* sequence of N consecutive failures followed by success, the retry manager SHALL:
- Make exactly min(N+1, max_attempts) attempts
- Apply delays following exponential backoff with jitter
- Return the successful result or raise after max_attempts

**Validates: Requirements 2.1**

### Property 3: Structured Error Logging

*For any* error that occurs within a correlation scope, the log entry SHALL contain:
- correlation_id matching the scope
- operation name
- error type and message
- No internal stack traces in user-facing output

**Validates: Requirements 2.3, 2.4**

### Property 4: Markdown Round-Trip

*For any* valid markdown AST, parsing the rendered output SHALL produce a semantically equivalent AST. Specifically:
- Heading levels preserved
- Bullet/numbered list structure preserved
- Bold/italic formatting preserved
- Table structure preserved

**Validates: Requirements 3.1**

### Property 5: Citation Count Invariant

*For any* document with N unique source URLs, citation processing SHALL produce exactly N citations in the output, regardless of how many times each source is referenced.

**Validates: Requirements 3.3**

### Property 6: URL Normalization Idempotence

*For any* URL string, `normalize(normalize(url)) == normalize(url)`. The normalized form is stable under repeated normalization.

**Validates: Requirements 3.4**

### Property 7: Cost Estimation Monotonicity

*For any* two research configurations A and B where A has more sections, longer content, or AI strategy enabled, `estimate_cost(A) >= estimate_cost(B)`.

**Validates: Requirements 3.5**

### Property 8: Parser Graceful Degradation

*For any* string input (including empty, malformed, or adversarial), all parsers SHALL return a valid result type without raising exceptions.

**Validates: Requirements 3.6**

### Property 9: Phase Banner Completeness

*For any* phase_banner call with step, total, and title, the output SHALL contain all three elements in a visually distinct format.

**Validates: Requirements 4.1**

### Property 10: Progress Time Display

*For any* progress_with_time call with a start_time, the output SHALL include elapsed time in human-readable format (Xs or Xm Ys).

**Validates: Requirements 4.2, 5.4**

### Property 11: Heading Hierarchy Validity

*For any* document with headings, the heading levels SHALL form a valid hierarchy where no heading skips more than one level (e.g., H1 → H3 without H2 is invalid).

**Validates: Requirements 7.3**

### Property 12: Serialization Round-Trip

*For any* serializable object (research state, usage history, cache entry, configuration), `deserialize(serialize(obj))` SHALL produce an object equal to the original.

**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

### Property 13: Concurrent Cache Safety

*For any* sequence of concurrent cache operations (reads and writes), the cache SHALL:
- Never return corrupted data
- Maintain size invariant (size <= max_size)
- Not deadlock

**Validates: Requirements 12.1**

### Property 14: Concurrent Console Safety

*For any* sequence of concurrent console outputs, each line SHALL be complete (not interleaved with other lines).

**Validates: Requirements 12.2**

### Property 15: Rate Limit Enforcement

*For any* burst of N concurrent requests with limit L, at most L requests SHALL be in-flight simultaneously.

**Validates: Requirements 12.4**

### Property 16: Resource Cleanup Completeness

*For any* operation that creates temporary files, those files SHALL not exist after the operation completes (success or failure).

**Validates: Requirements 9.3**

### Property 17: API Log Completeness

*For any* API call, the log entry SHALL contain: correlation_id, request params, response status, and duration.

**Validates: Requirements 8.2**

### Property 18: Fuzzy Suggestion Quality

*For any* unknown CLI option that is within edit distance 2 of a valid option, the system SHALL suggest that valid option.

**Validates: Requirements 6.4**

## Error Handling

### Error Categories

1. **Recoverable Errors**: Network timeouts, rate limits, transient API failures
   - Strategy: Retry with backoff, then surface user-friendly message
   
2. **Configuration Errors**: Missing API keys, invalid settings
   - Strategy: Fail fast with specific guidance
   
3. **Validation Errors**: Invalid input, malformed data
   - Strategy: Return structured error with field-level details
   
4. **Fatal Errors**: Out of memory, disk full, unrecoverable state
   - Strategy: Log, cleanup resources, exit with clear message

### Error Display

```
User-facing errors:
  x Research failed: API rate limit exceeded
    Try again in 60 seconds, or reduce --max-pages

Debug mode errors (--verbose):
  x Research failed: API rate limit exceeded
    [correlation: abc123] RateLimitError at ai.client.generate
    Retry 3/3 failed after 45.2s
    Request: model=gemini-2.0-flash, tokens=1500
```

## Testing Strategy

### Dual Testing Approach

This design uses both unit tests and property-based tests:

- **Unit tests**: Verify specific examples, edge cases, integration points
- **Property-based tests**: Verify universal properties across all valid inputs

### Property-Based Testing Framework

**Library**: Hypothesis (already in dev dependencies)

**Configuration**:
```python
from hypothesis import settings, HealthCheck

# Default settings for property tests
settings.register_profile("default", max_examples=100)
settings.register_profile("ci", max_examples=500)
settings.register_profile("thorough", max_examples=1000)
```

**Test Organization**:
- Property tests in `tests/test_*/test_*_properties.py`
- Each property test tagged with feature and requirement reference
- Minimum 100 iterations per property

### Test Annotation Format

```python
class TestTypeGuardProperties:
    """
    **Feature: primr-excellence, Property 1: Type Guard Correctness**
    **Validates: Requirements 1.2, 1.3, 1.5**
    """
    
    @settings(max_examples=100)
    @given(value=st.from_type(dict), expected_type=st.sampled_from([str, int, list]))
    def test_type_guard_returns_or_raises(self, value, expected_type):
        """Type guard either returns value or raises TypeValidationError."""
        # ...
```

### Coverage Targets

- Line coverage: 90%+
- Branch coverage: 85%+
- Property coverage: All 18 properties implemented
- Mutation testing: 80%+ mutation score on core modules

