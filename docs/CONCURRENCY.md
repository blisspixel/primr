# Primr Concurrency Model

This document describes the threading and concurrency model used in Primr, including operation classification, thread pool sizing, shared state management, and deadlock prevention strategies.

## Overview

Primr uses a hybrid concurrency model combining:
- **Async/await** for I/O-bound operations (API calls, network requests)
- **ThreadPoolExecutor** for CPU-bound operations and blocking I/O
- **Synchronous code** for simple sequential operations

The design prioritizes:
1. Responsiveness during long-running operations
2. Efficient use of API rate limits
3. Clean separation between async and sync boundaries

## Operation Classification

### I/O-Bound Operations (Async)

These operations spend most of their time waiting for external resources:

| Operation | Module | Pattern |
|-----------|--------|---------|
| AI API calls | `ai/async_client.py` | `async def` with `await` |
| Deep Research | `ai/deep_research.py` | `async def` with polling |
| URL resolution | `ai/citation_resolver.py` | `async def` with httpx |
| Vendor research | `core/vendor_research.py` | `async def` |
| MCP tool handlers | `mcp_server/tools.py` | `async def` |

### I/O-Bound Operations (Sync with Thread Pool)

These operations use blocking I/O but run in thread pools for parallelism:

| Operation | Module | Thread Pool |
|-----------|--------|-------------|
| Web scraping | `data/parallel_scraper.py` | `ThreadPoolExecutor(max_workers=N)` |
| Link verification | `data/scraping/discovery.py` | `ThreadPoolExecutor(max_workers=10)` |
| Browser automation | `data/scraping/browsers.py` | `ThreadPoolExecutor(max_workers=1)` |

### CPU-Bound Operations (Sync)

These operations are compute-intensive and run synchronously:

| Operation | Module | Notes |
|-----------|--------|-------|
| HTML parsing | `data/scraping/extraction.py` | BeautifulSoup processing |
| Content quality scoring | `data/scraping/quality.py` | Text analysis |
| Report formatting | `output/docx_writer.py` | Document generation |
| Prompt composition | `prompts/loader.py` | String building |

## Thread Pool Sizing

### Parallel Scraper (`data/parallel_scraper.py`)

```python
max_workers = min(10, len(urls))  # Cap at 10 concurrent requests
```

**Rationale:**
- Most websites rate-limit by IP, so more than 10 concurrent requests rarely helps
- 10 workers balance throughput against server-side rate limiting
- Dynamic sizing based on URL count avoids over-provisioning

### Link Verification (`data/scraping/discovery.py`)

```python
max_workers = 10  # Fixed pool for HEAD requests
```

**Rationale:**
- HEAD requests are lightweight and fast
- 10 workers provide good parallelism without overwhelming targets
- Fixed size simplifies resource management

### Browser Automation (`data/scraping/browsers.py`)

```python
max_workers = 1  # Single worker with hard timeout
```

**Rationale:**
- Browser instances are resource-heavy (memory, CPU)
- Single worker prevents resource exhaustion
- Hard timeout (via ThreadPoolExecutor) prevents hangs

### Research Executor (`ai/research_executor.py`)

```python
max_concurrent = 3  # Default for parallel Deep Research
```

**Rationale:**
- Gemini API has rate limits per minute
- 3 concurrent requests balance throughput against rate limits
- Configurable per-instance for different use cases

## Shared State and Synchronization

### Global Singletons

| Singleton | Module | Protection |
|-----------|--------|------------|
| `_executor` | `ai/research_executor.py` | `threading.Lock()` |
| `_master_architect` | `ai/master_architect.py` | `threading.Lock()` |
| `_SCRAPE_CACHE` | `data/scrape.py` | Thread-safe dict operations |
| `_correlation_id` | `utils/telemetry.py` | `contextvars.ContextVar` |

### Thread-Safe Patterns Used

1. **Lock-protected singletons:**
```python
_executor_lock = threading.Lock()

def get_research_executor(...):
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ResearchNodeExecutor(...)
        return _executor
```

2. **Context variables for async state:**
```python
_async_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "async_correlation_id", default=None
)
```

3. **Immutable data structures:**
- Configuration objects are frozen dataclasses
- Prompt configs are loaded once and not modified

### Mutable Shared State

| State | Location | Access Pattern |
|-------|----------|----------------|
| Scrape cache | `data/scrape.py` | Read-heavy, occasional writes |
| Circuit breaker state | `utils/circuit_breaker.py` | RLock-guarded (per-key state); listeners notified outside the lock |
| Job store | `mcp_server/job_store.py` | Single-writer, journal-backed |
| Retry history | `utils/retry.py` | Per-manager instance |

## Async/Sync Boundaries

### Pattern 1: Sync Caller, Async Implementation

Used when sync code needs to call async functions:

```python
# In core/vendor_research.py
def get_vendor_research_sync(vendor: str) -> list[VendorResearchFile]:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(get_or_generate_vendor_research(vendor))
```

### Pattern 2: Async Caller, Sync Implementation

Used when async code needs to call blocking sync functions:

```python
# In core/research_orchestrator.py
async def run_pipeline(self, ...):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,  # Default executor
        lambda: run_research(company_name, website)
    )
```

### Pattern 3: Async Caller, Sync Library

Used when async code calls sync libraries (like google-genai):

```python
# In ai/async_client.py
async def generate_content(self, ...):
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: self._client.models.generate_content(...)
    )
```

## Deadlock Prevention

### Identified Risks

1. **Nested event loops**: Calling `asyncio.run()` from within an async context
2. **Lock ordering**: Multiple locks acquired in different orders
3. **Thread pool exhaustion**: All workers blocked waiting for resources
4. **Sync-in-async blocking**: Blocking calls in async functions

### Mitigations

1. **Event loop detection:**
```python
try:
    loop = asyncio.get_running_loop()
    # Already in async context - use run_in_executor
except RuntimeError:
    # Not in async context - safe to use asyncio.run()
```

2. **Single lock per resource:**
- Each singleton has exactly one lock
- No nested lock acquisition

3. **Timeout on all blocking operations:**
```python
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(blocking_operation)
    try:
        result = future.result(timeout=90)  # Hard timeout
    except TimeoutError:
        # Handle timeout gracefully
```

4. **Async-first design:**
- New code uses `async def` by default
- Sync wrappers only where necessary for backward compatibility

### Testing for Deadlocks

The test suite includes:
- Thread safety tests (`tests/test_thread_safety.py`)
- Concurrent access tests for shared state
- Timeout tests for blocking operations

## Best Practices for Contributors

### DO:
- Use `async def` for new I/O-bound operations
- Use `ThreadPoolExecutor` for blocking I/O that can't be made async
- Use `contextvars` for request-scoped state
- Add timeouts to all blocking operations
- Use frozen dataclasses for configuration

### DON'T:
- Call `asyncio.run()` from within async code
- Hold locks while performing I/O
- Share mutable state between threads without synchronization
- Use global mutable variables without protection
- Block the event loop with sync I/O

## Monitoring and Debugging

### Correlation IDs

All operations are tagged with a correlation ID for tracing:

```python
from primr.utils.telemetry import get_correlation_id, set_async_correlation_id

# In async code
async with propagate_correlation_id("request-123"):
    await some_operation()  # Will have correlation_id="request-123"
```

### Thread Pool Metrics

The telemetry system records:
- Active thread count per pool
- Queue depth for pending tasks
- Task completion times

### Circuit Breaker State

Monitor circuit breaker state for service health:

```python
from primr.utils.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker()
stats = breaker.get_all_stats()
# Returns dict of host -> CircuitStats
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 2026 | Initial documentation |
