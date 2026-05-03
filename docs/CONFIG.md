# Primr Configuration Reference

This document describes all configuration options available in Primr.

## Environment Variables

### Model Provider Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini key for premium mode, scrape summaries, and Gemini-backed stages | Yes |
| `XAI_API_KEY` | xAI key for the default Grok standard pipeline | Recommended |

Run `primr init` for guided first-run setup. Set keys directly with `primr keys set gemini` and `primr keys set xai`, or provide them as shell env vars / local `.env` values. Run `primr keys path` to see the user-level config file.

### Optional Search Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `SEARCH_API_KEY` | Google Custom Search API key, only when `SEARCH_PROVIDER=google` | No |
| `SEARCH_ENGINE_ID` | Google Custom Search Engine ID, only when `SEARCH_PROVIDER=google` | No |

### Optional Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_RESEARCH_MODEL` | Model for research operations | `gemini-3-flash-preview` |
| `AI_REPORT_MODEL` | Model for report generation | `gemini-3-flash-preview` |
| `VERBOSE` | Enable verbose output | `false` |
| `DEBUG` | Enable debug mode | `false` |

Note: The default models can be overridden via environment variables. Primr is designed to work with the latest Gemini models. Current defaults:
- `gemini-3-flash-preview` - Best balance of speed and cost
- `gemini-3.1-pro-preview` - Maximum reasoning capability (tiered pricing)

Gemini 3.1 Pro Preview is the default Pro model. It has tiered pricing: $2/$12 per 1M tokens for prompts ≤200k, $4/$18 for >200k. Most Primr calls stay well under 200k tokens. Cost estimates (`--dry-run`) use conservative high-tier pricing; actual costs are typically lower.

To revert to Gemini 3.0 Pro (flat $2/$12 pricing):
- Set `AI_REASONING_MODEL=gemini-3-pro-preview` in `.env`

### Scraping Behavior

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_MAX_HEADED_POPUPS` | Total number of visible-browser challenges allowed per run. Shared across the Patchright stealth tier (main-site rescue) and the orchestrator's adaptive Playwright retry. Default is 0 (no popups ever); set to `5` (or any N) to opt in for a run. | `0` |
| `PRIMR_SKIP_HIRING_SIGNALS` | When set to `1` / `true` / `yes`, skips the hiring-signals stage entirely — no ATS probes, no careers-page crawl, no LLM extraction. Use when researching companies where hiring data is irrelevant or when debugging. | unset |
| `PRIMR_ALLOW_HEADED_FALLBACK` | Master switch for the visible-browser path in the stealth tier. Set to `0` / `false` / `no` to disable entirely regardless of budget. | `1` |
| `PRIMR_ENABLE_DRISSION` | Include DrissionPage tiers in the external validation orchestrator. | `0` |
| `PRIMR_BROWSER_HEADED` | Force the Playwright tiers to launch in headed mode for a specific call. Normally set internally by the adaptive-retry path, not by users. | unset |
| `PRIMR_BROWSER_SESSION_MODE` | `persistent` enables a reused browser profile per host (set internally during adaptive retry). | unset |

### Reasoning Topology

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_CONTINUOUS_REASONING` | Controls whether workbook generation (Phase 3) and cross-validation (Phase 5) share a single Grok session (4.3 in HYBRID/MAX tiers, 4.1-fast in FAST tier) so the validator inherits the corpus + workbook reasoning the generator produced. Set to `0` / `false` / `no` / `off` to disable (revert to the fresh-call topology used before the n=3 pilot). Set to `1` / `true` / `yes` / `on` to force-enable regardless of CLI flags. Unset means use whatever the CLI passed (default on). | unset (effectively on via CLI default) |

Notes on continuous reasoning:
- On by default after the n=3 pilot. Pass `--no-continuous-reasoning` on the CLI to disable for a single run.
- Section writing (Phase 4) is intentionally untouched and remains parallel + fresh-call per section. The topology change only affects Phase 3 + Phase 5.
- Cost impact varies by company: an n=3 pilot saw deltas from −3.7% to +32% versus the prior fresh-call topology (average ~+12%). Token accumulation across the shared session is the source of any extra cost.
- Quantified quality benefit: bare leaked-instruction lines in the final report drop from an average of 5.3 (fresh-call) to 1.0 (continuous) — about 81% fewer. Hard count, not LLM-judge opinion.
- Env var precedence: `PRIMR_CONTINUOUS_REASONING` overrides the CLI flag if explicitly set, so you can disable across all runs on a machine without changing CLI invocations.

Notes on the popup budget:
- The budget is a single shared counter — opt in once with `PRIMR_MAX_HEADED_POPUPS=N` and that N is the total allowance across all trigger points in the run.
- External-source validation (web-search results) uses a separate orchestrator that excludes the Patchright stealth tier by design, so validation-pass popups are already impossible even when the budget is set.
- On Linux, the budget is automatically treated as 0 when neither `DISPLAY` nor `WAYLAND_DISPLAY` is set, so SSH sessions, CI runners, and headless containers never attempt a visible-browser launch.

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
| `research_model` | str | `gemini-3-flash-preview` | Model for research |
| `report_model` | str | `gemini-3-flash-preview` | Model for reports |
| `max_retries` | int | 3 | Maximum retry attempts |
| `grade_threshold` | int | 70 | Quality threshold (0-100) |
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
| `deep_research_base_cost` | float | 2.50 | Base cost per deep research task |
| `search_cost_per_query` | float | 0.035 | Search API cost per query |

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

## Prompt Configuration

Prompts are configured via YAML files in `src/primr/prompts/`. See `docs/INTERNALS.md` for the full prompt architecture documentation.

### Prompt Directory Structure

```
src/primr/prompts/
├── company_overview.yaml      # Company research prompt
├── strategic_layer.yaml       # Strategic analysis prompt
├── shared/
│   ├── epistemic_rules.yaml   # Fact/inference/hypothesis rules
│   ├── formatting.yaml        # Formatting standards
│   └── personas.yaml          # Analyst personas
└── strategies/
    ├── ai_strategy.yaml       # AI strategy module
    ├── cloud_migration.yaml   # Cloud migration (placeholder)
    └── data_strategy.yaml     # Data strategy (placeholder)
```

### Adding Custom Strategy Modules

Create a new YAML file in `src/primr/prompts/strategies/`:

```yaml
meta:
  name: "My Strategy"
  version: "1.0.0"
  description: "Description of the strategy"
  status: "active"

persona: "senior_consultant"

document_purpose: |
  Purpose of this strategy document...

sections:
  - id: executive_summary
    name: "Executive Summary"
    part: 1
    purpose: "High-level overview"
    covers:
      - "Key findings"
    depth: "2-3 paragraphs"
```

The strategy is automatically discovered. CLI support is available via `--strategy-type` and discoverable via `--list-strategies`.


## Startup Banner

Primr shows a short startup banner by default in interactive terminals. It is skipped automatically in non-interactive/CI contexts and when `NO_COLOR` disables styling.

```bash
# Show banner only, then exit
primr --banner

# Choose mode explicitly
primr --banner static
primr --banner animated

# Disable once
primr --no-banner

# Disable globally (env)
set PRIMR_NO_BANNER=1
```

Env controls:
- `PRIMR_BANNER=auto|off|static|animated`
- `PRIMR_NO_BANNER=1`
- `PRIMR_BANNER_DURATION_MS=250..3000` (animated mode)
