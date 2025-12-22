# Design Document: Test Coverage Hardening

## Overview

This design specifies the implementation of comprehensive test coverage improvements for Primr, focusing on end-to-end integration tests, API resilience validation, and output quality assurance. The design leverages pytest's fixture system, Hypothesis for property-based testing, and subprocess-based CLI testing to achieve production-grade reliability.

## Architecture

The test hardening follows a layered approach:

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Integration Tests                     │
│         (CLI smoke tests, full pipeline validation)          │
├─────────────────────────────────────────────────────────────┤
│                   Component Integration Tests                │
│    (API resilience, File Search lifecycle, cost tracking)    │
├─────────────────────────────────────────────────────────────┤
│                    Unit & Property Tests                     │
│  (sections_written, citation resolution, YAML validation)    │
├─────────────────────────────────────────────────────────────┤
│                      Test Infrastructure                     │
│        (pytest marks, fixtures, mock factories)              │
└─────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Pytest Configuration (pytest.ini)

Register custom marks to eliminate warnings and enable selective test execution:

```ini
[pytest]
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests requiring external services
    smoke: marks CLI smoke tests
    resilience: marks API resilience tests
```

### 2. CLI Smoke Test Module (tests/test_cli_smoke.py)

Uses `subprocess.run()` to execute CLI commands and validate exit codes/output:

```python
def test_doctor_runs():
    result = subprocess.run(["primr", "doctor"], capture_output=True, timeout=30)
    assert result.returncode == 0

def test_dry_run_no_api_calls():
    result = subprocess.run(
        ["primr", "Test", "https://test.com", "--dry-run"],
        capture_output=True, timeout=30
    )
    assert result.returncode == 0
    assert "Estimated" in result.stdout.decode()
```

### 3. API Resilience Test Module (tests/test_ai/test_api_resilience.py)

Uses mocking to inject failures and validate retry/fallback behavior:

```python
@pytest.fixture
def mock_api_429():
    """Simulates rate limit errors."""
    with patch('primr.ai.deep_research.client') as mock:
        mock.interactions.create.side_effect = RateLimitError("429")
        yield mock

def test_retry_on_429(mock_api_429):
    orchestrator = DeepResearchOrchestrator()
    # Verify exponential backoff is applied
```

### 4. Sections Written Test Module (tests/test_core/test_sections_written.py)

Validates the new `sections_written` field propagates correctly:

```python
def test_sections_written_matches_actual():
    result = DeepResearchOrchestratorResult(
        company_name="Test",
        content="...",
        sections_written=20,
        ...
    )
    assert result.sections_written == 20

def test_orchestrator_result_propagates_sections_written():
    # Verify OrchestratorResult.sections_written matches source
```

### 5. Citation Resolution Property Tests (tests/test_ai/test_citation_properties.py)

Uses Hypothesis to test URL resolution across many inputs:

```python
@given(url=st.from_regex(r'https://www\.google\.com/url\?.*', fullmatch=True))
def test_google_redirect_resolved(url):
    resolver = CitationResolver()
    result = resolver.resolve(url)
    assert not result.startswith("https://www.google.com/url")
```

### 6. YAML Validation Tests (tests/test_prompts/test_yaml_validation.py)

Validates configuration completeness and correctness:

```python
def test_all_sections_have_position():
    config = load_config("company_overview")
    for section in config.sections:
        assert section.position in {"opening", "middle", "closing", "framework"}

def test_accordion_prompts_have_placeholders():
    prompts = load_accordion_prompts()
    assert "{company_name}" in prompts["research_dossier_prompt"]
```

### 7. Output Format Tests (tests/test_output/test_format_consistency.py)

Validates report structure across modes:

```python
def test_report_has_all_sections():
    report = generate_mock_report()
    for section_id in EXPECTED_SECTION_IDS:
        assert f"## {section_id}" in report or section_id in report
```

### 8. Concurrent Access Tests (tests/test_utils/test_thread_safety.py)

Validates thread safety in console and file operations:

```python
def test_console_output_not_interleaved():
    console = Console()
    threads = [Thread(target=console.info, args=(f"Message {i}",)) for i in range(10)]
    # Verify output lines are complete
```

## Data Models

### Test Result Tracking

```python
@dataclass
class TestCoverageMetrics:
    total_tests: int
    property_tests: int
    integration_tests: int
    smoke_tests: int
    resilience_tests: int
    coverage_percentage: float
```

### Mock Factories

```python
def create_mock_orchestrator_result(
    sections_written: int = 20,
    success: bool = True,
    error: str | None = None
) -> OrchestratorResult:
    """Factory for creating test OrchestratorResult instances."""
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following properties have been identified. Redundant properties have been consolidated where one subsumes another.

### Property 1: Invalid CLI arguments return non-zero exit code
*For any* invalid CLI argument combination, the system should return a non-zero exit code and include an error message in stderr.
**Validates: Requirements 2.5**

### Property 2: Retryable errors trigger exponential backoff
*For any* retryable error (429, 500, timeout), the system should retry with delays that increase exponentially up to MAX_RETRIES attempts.
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 3: Deep Research fallback on exhausted retries
*For any* Deep Research task that fails after MAX_RETRIES attempts, the system should fall back to Stage 1 context and continue section writing.
**Validates: Requirements 3.4**

### Property 4: Consecutive failure threshold stops processing
*For any* sequence of 3 consecutive section write failures, the system should stop processing and return partial results with sections_written reflecting only successful sections.
**Validates: Requirements 3.5, 4.4**

### Property 5: sections_written accuracy and propagation
*For any* Accordion Method execution, sections_written should equal the count of successfully written sections, and this value should propagate unchanged through OrchestratorResult to CLI display.
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 6: Google redirect URL resolution
*For any* citation URL matching the Google redirect pattern, the resolver should return the final destination URL (not the redirect URL). Direct URLs should pass through unchanged.
**Validates: Requirements 5.1, 5.2**

### Property 7: URL resolution graceful degradation
*For any* URL resolution failure, the system should preserve the original URL and log a warning rather than losing the citation.
**Validates: Requirements 5.3**

### Property 8: Citation deduplication
*For any* set of citations containing duplicate URLs, the sources list should contain each unique URL exactly once.
**Validates: Requirements 5.4**

### Property 9: Malformed YAML raises descriptive error
*For any* malformed strategy module YAML, the system should raise an exception with a message identifying the configuration issue.
**Validates: Requirements 6.3**

### Property 10: Markdown table to DOCX preservation
*For any* markdown content containing tables, the DOCX conversion should produce corresponding Word tables with matching row/column structure.
**Validates: Requirements 7.4**

### Property 11: Heading hierarchy preservation
*For any* markdown content with heading levels (H1-H4), the DOCX conversion should preserve the relative hierarchy.
**Validates: Requirements 7.5**

### Property 12: Console thread safety
*For any* concurrent console writes from multiple threads, output lines should be complete (not interleaved mid-line).
**Validates: Requirements 8.1, 8.2**

### Property 13: File write thread safety
*For any* concurrent section saves to the working folder, files should not be corrupted by race conditions.
**Validates: Requirements 8.3**

### Property 14: Cost estimate accuracy
*For any* cost estimate for deep mode, the estimate should be within 50% of typical actual costs based on historical usage data.
**Validates: Requirements 9.1**

### Property 15: File Search Store cleanup
*For any* research task (successful or failed), the File Search Store should be deleted in the finally block to prevent data leakage.
**Validates: Requirements 10.1, 10.2**

### Property 16: Context upload ordering
*For any* research task using Stage 1 context, the file upload and indexing must complete before Deep Research begins.
**Validates: Requirements 10.3**

## Error Handling

### API Errors
- **429 Rate Limit**: Exponential backoff starting at BASE_RETRY_DELAY (60s), doubling each retry
- **500 Server Error**: Same retry pattern as 429
- **Timeout**: Log error, attempt reconnection using interaction_id for stream resumption
- **Authentication Error**: Fail fast with descriptive error message

### Configuration Errors
- **Missing YAML**: Raise `ConfigurationError` with file path
- **Malformed YAML**: Raise `ConfigurationError` with parse error details
- **Missing Required Fields**: Raise `ValidationError` listing missing fields

### File System Errors
- **Permission Denied**: Log warning, attempt alternative path
- **Disk Full**: Fail with clear error message about disk space

## Testing Strategy

### Dual Testing Approach

**Unit Tests**: Verify specific examples and edge cases
- CLI argument parsing
- YAML configuration loading
- Section counting logic
- URL resolution patterns

**Property-Based Tests**: Verify universal properties using Hypothesis
- Retry behavior across error types
- URL resolution across URL patterns
- Thread safety across concurrent access patterns
- Format conversion across markdown structures

### Testing Framework

- **Framework**: pytest with pytest-asyncio for async tests
- **Property Testing**: Hypothesis (already in use, 100+ iterations per property)
- **Mocking**: unittest.mock for API injection
- **CLI Testing**: subprocess.run for smoke tests

### Test Organization

```
tests/
├── test_cli_smoke.py              # Requirement 2 (smoke tests)
├── test_ai/
│   ├── test_api_resilience.py     # Requirement 3 (resilience)
│   └── test_citation_properties.py # Requirement 5 (citations)
├── test_core/
│   └── test_sections_written.py   # Requirement 4 (sections_written)
├── test_prompts/
│   └── test_yaml_validation.py    # Requirement 6 (YAML)
├── test_output/
│   └── test_format_consistency.py # Requirement 7 (output format)
├── test_utils/
│   └── test_thread_safety.py      # Requirement 8 (concurrency)
│   └── test_cost_accuracy.py      # Requirement 9 (cost)
└── test_lifecycle/
    └── test_file_search_store.py  # Requirement 10 (cleanup)
```

### Property Test Annotations

Each property-based test MUST include:
```python
# **Feature: test-coverage-hardening, Property {number}: {property_text}**
# **Validates: Requirements X.Y**
```

### Test Execution

```bash
# Run all tests
pytest tests/ -v

# Run only fast tests (exclude slow/integration)
pytest tests/ -m "not slow and not integration"

# Run smoke tests only
pytest tests/ -m smoke

# Run resilience tests only
pytest tests/ -m resilience
```

