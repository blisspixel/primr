# Contributing to Primr

This guide explains how to contribute to Primr, including development setup, code standards, and the pull request process.

## Development Setup

### Prerequisites

- Python 3.10+
- pip or uv package manager
- Playwright browsers (for scraping tests)

### Installation

```bash
# Clone the repository
git clone https://github.com/blisspixel/primr.git
cd primr

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

### Verify Setup

```bash
# Run the doctor command
primr doctor

# Run tests
pytest tests/ -v

# Run type checking
mypy src/primr

# Run linting
ruff check src/primr
```

## Project Structure

```
primr/
├── src/primr/           # Main package
│   ├── ai/              # AI operations (LLM, grading, deep research)
│   ├── api/             # REST API (if applicable)
│   ├── config/          # Configuration management
│   ├── core/            # Research orchestration
│   ├── data/            # Data collection (scraping, search)
│   ├── output/          # Report generation
│   └── utils/           # Utilities (logging, errors, files)
├── tests/               # Test suite (mirrors src structure)
├── docs/                # Documentation
└── working/             # Runtime working directory (gitignored)
```

## Code Standards

### Type Hints

All code must have type hints. Use the types defined in `src/primr/types.py` where applicable.

```python
# Good
def process_url(url: str, timeout: float = 30.0) -> str | None:
    ...

# Bad
def process_url(url, timeout=30.0):
    ...
```

### Docstrings

All public functions and classes must have docstrings following Google style.

```python
def scrape_url(url: str, tier: int = 1) -> tuple[str | None, str | None]:
    """
    Scrape content from a URL using the specified tier.
    
    Args:
        url: The URL to scrape
        tier: Scraping tier (1-4), higher = more aggressive
        
    Returns:
        Tuple of (content, error). Content is None if scraping failed,
        error is None if scraping succeeded.
        
    Raises:
        ValueError: If tier is not 1-4
        
    Example:
        content, error = scrape_url("https://example.com", tier=2)
        if content:
            print(f"Got {len(content)} characters")
    """
```

### Error Handling

Use the error types from `src/primr/utils/errors.py`:

```python
from primr.utils.errors import AIError, ScrapingError, ValidationError

# Raise specific errors
raise AIError("Model returned empty response", model="gemini-2.0-flash")

# Use error context for debugging
from primr.utils.errors import error_context

with error_context("processing company", company=company_name):
    result = process(data)
```

### Logging

Use the module logger pattern:

```python
from primr.utils.logging_config import get_logger

logger = get_logger("module_name")

logger.debug("Detailed info for debugging")
logger.info("Normal operation info")
logger.warning("Something unexpected but handled")
logger.error("Something failed")
```

### Configuration

Access configuration through the settings singleton:

```python
from primr.config import get_settings

settings = get_settings()
model = settings.ai.research_model
timeout = settings.scraping.timeout
```

### Singleton Pattern

For components that should have a single instance, use the thread-safe singleton pattern:

```python
import threading

_instance: MyClass | None = None
_lock = threading.Lock()

def get_instance() -> MyClass:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MyClass()
    return _instance

def reset_instance() -> None:
    global _instance
    with _lock:
        _instance = None
```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_ai/test_client.py -v

# Run with coverage
pytest tests/ --cov=src/primr --cov-report=html

# Run only fast tests (skip integration)
pytest tests/ -v -m "not integration"
```

### Test Structure

Tests mirror the source structure:

```
tests/
├── test_ai/
│   ├── test_client.py
│   ├── test_deep_research.py
│   └── ...
├── test_data/
│   ├── test_scrape.py
│   └── ...
├── conftest.py          # Shared fixtures
└── utils/               # Test utilities
```

### Writing Tests

```python
import pytest
from unittest.mock import Mock, patch

from primr.ai.client import AIClient

class TestAIClient:
    """Tests for AIClient."""
    
    def test_generate_returns_string(self):
        """generate() should return a string response."""
        with patch.object(AIClient, '_client') as mock_client:
            mock_client.models.generate_content.return_value = Mock(text="response")
            
            client = AIClient()
            result = client.generate("test prompt")
            
            assert isinstance(result, str)
            assert result == "response"
    
    def test_generate_retries_on_failure(self):
        """generate() should retry on transient failures."""
        # Test implementation
        pass
    
    @pytest.mark.integration
    def test_generate_with_real_api(self):
        """Integration test with real API (requires API key)."""
        # Skip if no API key
        pass
```

### Property-Based Tests

Use Hypothesis for property-based testing:

```python
from hypothesis import given, strategies as st

from primr.data.scrape import normalize_url

@given(st.text())
def test_normalize_url_idempotent(url):
    """Normalizing a URL twice should give the same result."""
    if url.startswith(('http://', 'https://')):
        result1 = normalize_url(url)
        result2 = normalize_url(result1)
        assert result1 == result2
```

### Fixtures

Common fixtures are in `tests/conftest.py`:

```python
import pytest
from primr.config import reset_settings
from primr.ai import reset_client

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons before each test."""
    yield
    reset_settings()
    reset_client()

@pytest.fixture
def mock_ai_response():
    """Fixture providing a mock AI response."""
    return Mock(text="Test response", usage_metadata=None)
```

## Adding New Features

### 1. Start with Types

Define types in `src/primr/types.py` if needed:

```python
class NewFeatureResult(TypedDict):
    """Result from the new feature."""
    data: str
    metadata: dict[str, Any]
```

### 2. Write Tests First

Create test file in the appropriate location:

```python
# tests/test_module/test_new_feature.py

class TestNewFeature:
    def test_basic_functionality(self):
        # Test the happy path
        pass
    
    def test_error_handling(self):
        # Test error cases
        pass
```

### 3. Implement the Feature

Create the implementation:

```python
# src/primr/module/new_feature.py

from primr.utils.logging_config import get_logger
from primr.utils.errors import ValidationError

logger = get_logger("module.new_feature")

def new_feature(input: str) -> NewFeatureResult:
    """
    Description of what this does.
    
    Args:
        input: Description
        
    Returns:
        NewFeatureResult with data and metadata
        
    Raises:
        ValidationError: If input is invalid
    """
    logger.debug(f"Processing input: {input[:50]}...")
    
    if not input:
        raise ValidationError("Input cannot be empty")
    
    # Implementation
    return {"data": result, "metadata": {}}
```

### 4. Export from __init__.py

Add to the module's `__init__.py`:

```python
from primr.module.new_feature import new_feature, NewFeatureResult

__all__ = [
    # ... existing exports
    "new_feature",
    "NewFeatureResult",
]
```

### 5. Update Documentation

- Add to relevant docs (API.md, ARCHITECTURE.md)
- Add terms to GLOSSARY.md if needed
- Update README.md if user-facing

## Pull Request Process

### Before Submitting

1. Run all tests: `pytest tests/ -v`
2. Run type checking: `mypy src/primr`
3. Run linting: `ruff check src/primr`
4. Update documentation if needed
5. Add tests for new functionality

### PR Description Template

```markdown
## Summary
Brief description of changes.

## Changes
- Change 1
- Change 2

## Testing
How was this tested?

## Documentation
- [ ] Updated relevant docs
- [ ] Added to GLOSSARY if new terms
- [ ] Updated ARCHITECTURE if structural changes

## Checklist
- [ ] Tests pass
- [ ] Type hints added
- [ ] Docstrings added
- [ ] No new linting errors
```

### Review Process

1. All PRs require at least one review
2. CI must pass (tests, types, linting)
3. Documentation must be updated for user-facing changes
4. Breaking changes require discussion first

## Code Style

### Formatting

- Line length: 100 characters
- Use ruff for formatting: `ruff format src/primr`

### Imports

Order imports as:
1. Standard library
2. Third-party packages
3. Local imports

```python
import asyncio
import json
from pathlib import Path

import httpx
from google import genai

from primr.config import get_settings
from primr.utils.errors import AIError
```

### Naming Conventions

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Module-level loggers: `logger = get_logger("module_name")`

### Async Code

Use async/await for I/O-bound operations:

```python
async def fetch_data(url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
```

For sync code that needs to call async:

```python
import asyncio

def sync_wrapper():
    return asyncio.run(async_function())
```

## Common Patterns

### Graceful Degradation

Always provide fallbacks:

```python
def get_data(url: str) -> str | None:
    # Try primary method
    result = try_primary(url)
    if result:
        return result
    
    # Fallback to secondary
    result = try_secondary(url)
    if result:
        return result
    
    # Log and return None rather than raising
    logger.warning(f"All methods failed for {url}")
    return None
```

### Progress Callbacks

Support optional progress callbacks:

```python
from collections.abc import Callable

def long_operation(
    data: list[str],
    on_progress: Callable[[int, int, str], None] | None = None
) -> list[str]:
    results = []
    for i, item in enumerate(data):
        result = process(item)
        results.append(result)
        
        if on_progress:
            on_progress(i + 1, len(data), f"Processed {item}")
    
    return results
```

### Resource Cleanup

Use context managers for resources:

```python
from contextlib import contextmanager

@contextmanager
def managed_browser():
    browser = launch_browser()
    try:
        yield browser
    finally:
        browser.close()

# Usage
with managed_browser() as browser:
    page = browser.new_page()
    # ...
```

## Getting Help

- Check existing documentation in `docs/`
- Look at similar code in the codebase
- Open an issue for discussion before large changes
- Ask questions in PR comments
