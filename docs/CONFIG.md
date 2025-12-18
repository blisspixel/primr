# Primr Configuration Reference

This document describes all configuration options available in Primr.

## Environment Variables

### Required API Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key for AI operations | Yes |
| `SEARCH_API_KEY` | Google Custom Search API key | Yes |
| `SEARCH_ENGINE_ID` | Google Custom Search Engine ID | Yes |

### Optional Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_RESEARCH_MODEL` | Model for research operations | `gemini-2.0-flash` |
| `AI_REPORT_MODEL` | Model for report generation | `gemini-2.0-flash` |
| `VERBOSE` | Enable verbose output | `false` |
| `DEBUG` | Enable debug mode | `false` |

Note: The default models can be overridden via environment variables. Primr is designed to work with the latest Gemini models. As of December 2025, the recommended models are:
- `gemini-3-flash-preview` - Best balance of speed and intelligence
- `gemini-3-pro-preview` - Maximum reasoning capability

## Configuration Classes

### TimeoutConfig

Controls timeout behavior for HTTP operations.

```python
from primr.config import TimeoutConfig

config = TimeoutConfig(
    connect=10.0,  # Connection timeout (seconds)
    read=30.0,     # Read timeout (seconds)
    total=60.0,    # Total operation timeout (seconds)
)
config.validate()  # Raises ValueError if invalid
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `connect` | float | 10.0 | Timeout for establishing connection |
| `read` | float | 30.0 | Timeout for reading response data |
| `total` | float | 60.0 | Overall operation timeout |

Validation rules:
- All values must be positive
- `total` must be >= `connect`
- `total` must be >= `read`

### CacheConfig

Controls caching behavior.

```python
from primr.config import CacheConfig

config = CacheConfig(
    max_size=100,       # Maximum cache entries
    ttl_seconds=3600.0, # Time-to-live (None = no expiry)
    name="my_cache",    # Cache name for logging
)
config.validate()
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_size` | int | 100 | Maximum number of cached items |
| `ttl_seconds` | float or None | 3600.0 | Cache entry lifetime (None = no expiry) |
| `name` | str | "default" | Cache identifier for metrics |

Validation rules:
- `max_size` must be positive
- `ttl_seconds` must be positive or None
- `name` must be non-empty

### ScrapingConfig

Controls web scraping behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | int | 2 | Maximum retry attempts |
| `timeout` | int | 15 | Request timeout (seconds) |
| `max_depth` | int | 2 | Maximum crawl depth |
| `cache_ttl_hours` | int | 24 | Cache lifetime (hours) |
| `min_content_length` | int | 100 | Minimum content length |
| `min_html_length` | int | 500 | Minimum HTML length |
| `excluded_sites` | list | [...] | URL patterns to skip |
| `soft_block_indicators` | list | [...] | Block detection keywords |

### AIConfig

Controls AI model behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `research_model` | str | `gemini-2.0-flash` | Model for research |
| `report_model` | str | `gemini-2.0-flash` | Model for reports |
| `max_retries` | int | 3 | Maximum retry attempts |
| `grade_threshold` | int | 80 | Quality threshold (0-100) |
| `default_temperature` | float | 1.0 | Model temperature (0.0-2.0) |
| `default_thinking_level` | str | "high" | Thinking level |
| `model_fallbacks` | dict | {...} | Fallback model chains |

### SearchConfig

Controls search API behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `num_results` | int | 3 | Results per search |
| `parallel_limit` | int | 2 | Concurrent searches |
| `initial_retry_delay` | int | 5 | Initial retry delay (seconds) |
| `excluded_domains` | list | [...] | Domains to exclude |

### PathConfig

Controls file paths.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_root` | Path | cwd | Project root directory |
| `output_dir` | Path | `{root}/output` | Report output directory |
| `working_dir` | Path | `{root}/working` | Working files directory |
| `logs_dir` | Path | `{root}/logs` | Log files directory |
| `cache_dir` | Path | `{root}/logs/scrape_cache` | Scrape cache directory |

### PricingConfig

Controls cost estimation. Prices are per 1 million tokens.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gemini_input_per_million` | float | 2.00 | Input token cost (USD/1M) |
| `gemini_output_per_million` | float | 12.00 | Output token cost (USD/1M) |
| `deep_research_base_cost` | float | 0.50 | Base cost per deep research |
| `search_cost_per_query` | float | 0.00 | Search API cost |

## Usage

### Getting Settings

```python
from primr.config import get_settings

settings = get_settings()

# Access nested config
model = settings.ai.research_model
timeout = settings.scraping.timeout
```

### Validating Configuration

```python
from primr.config import get_settings

settings = get_settings()

# Validate all config values (except API keys)
settings.validate_all()

# Validate including API keys
settings.validate_all(include_api_keys=True)

# Validate API keys only
settings.validate()
```

### Custom Configuration

```python
from primr.config import configure
from pathlib import Path

settings = configure(
    project_root=Path("/custom/path"),
    verbose=True,
    debug=True,
)
```

### Testing

```python
from primr.config import reset_settings

# Reset singleton for test isolation
reset_settings()
```
