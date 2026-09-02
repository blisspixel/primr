# Primr Configuration Reference

This document describes all configuration options available in Primr.

## Environment Variables

### Model Provider Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `XAI_API_KEY` | xAI Grok key for standard reasoning, strategy, and the XAI-only writing fallback | Recommended |
| `GEMINI_API_KEY` | Google Gemini key for low-cost writing/utility, premium mode, and Gemini-backed stages | Recommended for the cheapest measured default |
| `OPENAI_API_KEY` | Optional OpenAI GPT/o-series provider for routed utility, reasoning, writing, and registered premium-research candidates; this key alone does not enable full execution | No |
| `ANTHROPIC_API_KEY` | Optional Anthropic Claude provider for reasoning, writing, and pro roles | No |
| `OPENROUTER_API_KEY` | Optional OpenRouter multi-provider gateway key; paid routing also requires `PRIMR_OPENROUTER_ENABLED=1` | No |
| `OLLAMA_API_KEY` | Optional key for Ollama or another local OpenAI-compatible endpoint; Ollama defaults to `ollama` when unset | No |
| `AZURE_OPENAI_API_KEY` | Optional Azure AI Foundry provider (resolves the `foundry`/`azure` provider); set `AZURE_OPENAI_BASE_URL` or `AZURE_OPENAI_ENDPOINT` for the deployment endpoint | No |
| `AWS_BEARER_TOKEN_BEDROCK` | Optional AWS Bedrock provider (resolves the `bedrock`/`aws` provider); the standard AWS credential chain (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_REGION`/`AWS_PROFILE`) also works. Needs `pip install 'primr[bedrock]'` | No |

Run `primr init` for guided first-run setup. Set keys directly with `primr keys set gemini`, `primr keys set xai`, `primr keys set openai`, `primr keys set openrouter`, `primr keys set anthropic`, `primr keys set ollama`, `primr keys set foundry`, or `primr keys set bedrock`; these hidden prompts require a foreground input/output terminal. Shell env vars and local `.env` values are also supported for noninteractive configuration. Run `primr keys path` to see the user-level config file. The measured default remains XAI + Gemini, but a single usable cloud provider key is enough for provider diagnostics. See [OpenRouter Preview](OPENROUTER.md) for its separate opt-in and safeguards.

### Agent Host Authentication

Primr does not define or store agent-host credential variables. Authenticate
inside the official host, and keep its OAuth tokens and session state there.
`primr-zero` keeps the host-assisted workflow inside the selected host. Primr
also has an unpromoted Codex source-relevance adapter. A single-company
experimental run can enable it only with `--inference hybrid` and
`--acknowledge-host-agent-may-bill`, because installed Codex authentication
does not prove whether execution uses plan allowance or metered API-key
billing. Never copy a Claude Code OAuth token, browser cookie, or other
subscription credential into Primr. Direct provider calls still use the
provider API keys listed above.

### Optional Search Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `SEARCH_API_KEY` | Google Custom Search API key, only when `SEARCH_PROVIDER=google` | No |
| `SEARCH_ENGINE_ID` | Google Custom Search Engine ID, only when `SEARCH_PROVIDER=google` | No |

### Optional Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_RESEARCH_MODEL` | Legacy Gemini-backed research model override | `gemini-3-flash-preview` |
| `AI_REPORT_MODEL` | Legacy Gemini-backed report model override | `gemini-3.1-pro-preview` |
| `VERBOSE` | Enable verbose output | `false` |
| `DEBUG` | Enable debug mode | `false` |
| `PRIMR_INFERENCE_PROFILE` | Runtime capability-routing profile for wired stages. Supported values are `cloud` and `hybrid`. `cloud` is the default; `hybrid` enables the current routed utility-stage pilots. Route metadata is recorded in `_run_state.json`. Prefer the `--inference` CLI flag for normal use. Internal enum values used by tests and evals are not supported configuration. | `cloud` |
| `PRIMR_OPENROUTER_ENABLED` | Makes a configured OpenRouter key eligible for Standard paid routing. It does not replace the estimate and approval gate. | `0` |
| `PRIMR_OPENROUTER_ZDR` | Requires zero-data-retention OpenRouter endpoints. Set to `0` only after reviewing the privacy tradeoff; provider data collection remains denied. | `1` |
| `PRIMR_OPENROUTER_MODEL` | Optional custom OpenRouter model slug. Requires explicit input and output price variables below. | unset |
| `PRIMR_OPENROUTER_INPUT_PRICE` | Custom model input price in USD per 1M tokens; also enforced as the provider prompt-price ceiling. | unset |
| `PRIMR_OPENROUTER_OUTPUT_PRICE` | Custom model output price in USD per 1M tokens; also enforced as the provider completion-price ceiling. | unset |
| `PRIMR_OPENROUTER_MAX_INPUT_TOKENS` | Declared custom OpenRouter model input limit. | `128000` |
| `PRIMR_OPENROUTER_MAX_OUTPUT_TOKENS` | Declared custom OpenRouter model output limit. | `16384` |

Note: Legacy Gemini model override variables are still supported for Gemini-backed stages. Provider-aware routing otherwise uses the model registry and configured provider keys. Current Gemini defaults:
- `gemini-3-flash-preview` - Best balance of speed and cost for legacy Gemini paths
- `gemini-3.1-pro-preview` - Maximum Gemini reasoning capability (tiered pricing)

Gemini 3.1 Pro Preview is the default Pro model. It has tiered pricing: $2/$12 per 1M tokens for prompts ≤200k, $4/$18 for >200k. Most Primr calls stay well under 200k tokens. Cost estimates (`--dry-run`) use conservative high-tier pricing; actual costs are typically lower. Model IDs marked deprecated in the registry are not supported override targets.

Gemini 3.7 Flash, Gemini 3.6 Flash, and Gemini 3.5 Flash-Lite are registered
evaluation candidates, not production defaults. Primr omits sampling controls
on these current request paths and keeps thinking levels explicit. The 3.6 and
3.7 registry prices switch from Google's introductory rates to the published
January 1, 2027 rates by pricing date, so future dry-runs do not silently
underquote. Promotion still requires a representative quality/cost evaluation.
See Google's [latest-model migration guide](https://ai.google.dev/gemini-api/docs/latest-model)
and [pricing page](https://ai.google.dev/gemini-api/docs/pricing).

### Scraping Behavior

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_MAX_HEADED_POPUPS` | Total number of visible-browser challenges allowed per run. Shared across the Patchright stealth tier (main-site rescue) and the orchestrator's adaptive Playwright retry. Default is 0 (no popups ever); set to `5` (or any N) to opt in for a run. | `0` |
| `PRIMR_SKIP_HIRING_SIGNALS` | When set to `1` / `true` / `yes`, skips the hiring-signals stage entirely - no ATS/provider probes (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Workable, Recruitee, Jobvite, iCIMS, BambooHR), no careers-page crawl, no DuckDuckGo web-search fallback, no LLM extraction. Use when researching companies where hiring data is irrelevant or when debugging. Note: skill packs treat job postings as their primary input, so packs generated against companies with `PRIMR_SKIP_HIRING_SIGNALS=1` will fall back to recon + research only and may require `--allow-recon-only`. | unset |
| `PRIMR_ALLOW_HEADED_FALLBACK` | Master switch for the visible-browser path in the stealth tier. Set to `0` / `false` / `no` to disable entirely regardless of budget. | `1` |
| `PRIMR_ENABLE_DRISSION` | Include DrissionPage tiers in the external validation orchestrator. | `0` |
| `PRIMR_ENABLE_GROK_SURROGATE` | Experimental opt-in to metered xAI `web_search` synthesis when deterministic blocked-site fallbacks return no content. Governed CLI/MCP/A2A research runs reject this environment-only spend because it is not estimate-bound. | `0` |
| `PRIMR_DISABLE_GROK_SURROGATE` | Emergency override that disables the xAI surrogate even when its enable switch is set. | `0` |
| `PRIMR_BROWSER_HEADED` | Force the Playwright tiers to launch in headed mode for a specific call. Normally set internally by the adaptive-retry path, not by users. | unset |
| `PRIMR_BROWSER_SESSION_MODE` | `persistent` enables a reused browser profile per host (set internally during adaptive retry). | unset |
| `PRIMR_PDF_LLM_MAX_CALLS` | Per-process experimental budget for Gemini-backed PDF extraction during scraping. Default `0` keeps PDF extraction local with PyMuPDF only. Governed CLI/MCP/A2A research runs reject positive values because these calls are not yet estimate-bound. | `0` |
| `PRIMR_PDF_LLM_MAX_TOTAL_MB` | Total PDF bytes that Gemini extraction may receive after `PRIMR_PDF_LLM_MAX_CALLS` is enabled. | `40` |

Provider-backed single-company research prompts for approval by default. JSON
execution never opens an interactive prompt: without `--skip-confirm`, it
returns one `primr.command-error.v1` object with
`error_type: "approval_required"` and starts no provider work. First run the
exact command with `--dry-run --json`, obtain explicit approval for that quote,
then repeat it with `--skip-confirm --json`. Approved JSON execution keeps
stdout to one structured result object.

### Vendor Research Cache

Vendor research (AI news) defaults to a grounded-lite engine: one Gemini call
with Google Search grounding produces live, cited results at roughly $0.30 per
platform. Deep Research (~$2.50/task) is opt-in via `--deep-research`. Results
are shared in the per-user cache and reused when present. Stale or missing cache
files do not trigger a fresh refresh automatically because the run must quote
that extra task before execution. Use the matching explicit control when a
refresh is intentional:

- `primr --generate-vendor-research <vendor> --dry-run`, then repeat without
  `--dry-run` and approve the quoted aggregate estimate
- `primr "Company" https://company.com --refresh-vendor-research`

Integrated research and standalone strategy commands ignore ambient automatic
refresh settings. Their dry-run and budget estimates include one grounded-lite
refresh task per selected platform (or a Deep Research task under
`--deep-research`) only when `--refresh-vendor-research` is present. `PRIMR_ALLOW_VENDOR_REFRESH=1` remains
available to direct library callers that explicitly leave cache policy under
environment control; estimate-bound CLI and MCP paths override it to prevent
unquoted provider work.

The direct cache command accepts `azure`, `aws`, `gcp`, `private`, `agnostic`,
or `all`, plus `--budget <usd>` and `--json`.
It starts no provider work during dry-run, requires confirmation by default,
and treats `--skip-confirm` as explicit noninteractive approval. JSON execution
returns a structured prerequisite error when preflight fails; after preflight
passes, execution without `--skip-confirm` returns an `approval_required`
object. Any failed target produces a nonzero exit code while successful artifact
paths remain in the human or JSON result.

Cache publication uses a same-directory atomic replacement. A completed remote
task is recorded before local publication, linked destination files are
replaced rather than followed, and a failed refresh reuses an existing cache
with a visible warning. A provider or polling exception after submission also
records a conservative task-cost row, while local preflight failure records no
provider usage. Fast multi-platform refresh tasks run serially before parallel
strategy writing because the provider client and usage ledger are shared
process state. Each later refresh budget gate includes earlier submitted tasks.

Explicit refresh execution has a run-local outcome ledger. Provider submission
callbacks record which targets started and which completed, failed, or were
skipped by the budget gate. This avoids attributing work from another concurrent
job to the current run. Partial refresh remains visible even when a cached file
lets strategy generation continue, and causes a nonzero CLI result while
preserving the completed report and successful artifacts.

AI Strategy Deep Research uses the same run-local submission accounting.
Preflight and context-assembly failures do not count as provider spend, while a
task that reaches provider submission remains counted even if publication later
fails. Optional standard-strategy setup errors persist a failed strategy
outcome and preserve the completed base report instead of converting the whole
run into an apparent report failure.

Standalone strategy JSON has separate estimate, refusal, and result contracts.
Use `--dry-run --json` for the one-object estimate. Execution with `--json`
requires `--skip-confirm` and returns one result object containing expected
targets, successful artifact paths, and failed targets. Without that explicit
approval, the command returns one `approval_required` object and starts no
provider work.

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_VENDOR_NEWS_TTL_DAYS` | Freshness threshold for cached vendor research before Primr reports it as stale. Stale files are still reused unless refresh is explicitly enabled. | `7` |
| `PRIMR_ALLOW_VENDOR_REFRESH` | Allows stale or missing vendor research cache to trigger generation only in direct library paths that leave refresh policy environment-controlled. Integrated CLI and MCP strategy paths override it off. | unset |

### Reasoning Topology

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_CONTINUOUS_REASONING` | Controls whether workbook generation (Phase 3) and cross-validation (Phase 5) share one Grok session so the validator inherits the corpus and workbook reasoning the generator produced. FAST and HYBRID use Grok 4.3; MAX uses the version-pinned Grok 4.5 route. FAST differs through lower reasoning effort, not a separate model. Set to `0` / `false` / `no` / `off` to disable. Set to `1` / `true` / `yes` / `on` to force-enable regardless of CLI flags. Unset means use the CLI value, which defaults on. | unset (effectively on via CLI default) |

Notes on continuous reasoning:
- On by default after the n=3 pilot. Pass `--no-continuous-reasoning` on the CLI to disable for a single run.
- Section writing (Phase 4) is intentionally untouched and remains parallel + fresh-call per section. The topology change only affects Phase 3 + Phase 5.
- Cost impact varies by company: an n=3 pilot saw deltas from −3.7% to +32% versus the prior fresh-call topology (average ~+12%). Token accumulation across the shared session is the source of any extra cost.
- Quantified quality benefit: bare leaked-instruction lines in the final report drop from an average of 5.3 (fresh-call) to 1.0 (continuous) - about 81% fewer. Hard count, not LLM-judge opinion.
- Env var precedence: `PRIMR_CONTINUOUS_REASONING` overrides the CLI flag if explicitly set, so you can disable across all runs on a machine without changing CLI invocations.

### Confidence-Label Honesty

A June-2026 calibration pass measured that primr's `(Confirmed)` / `(Reported)`
labels traced to their cited source only ~0-8% of the time: the prose reads
authoritative but the labels overclaim their grounding. The label-honesty pass
closes that gap. It is opt-in, fail-safe, and **not a shipping gate**: it
adjusts content (lowers a label) only on positive evidence of an overclaim, and
never withholds a deliverable.

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_LABEL_HONESTY` | Experimental pre-ship claim-label judge. It remains default-off. Governed CLI/MCP/A2A research runs reject this environment-only switch because its judge calls are not yet part of the estimate and approval shape. Calibration harnesses may still exercise it explicitly. | unset (off) |

### Artifact Shipping Gates

Final reports and strategy documents pass through deterministic ship-time gates
(`primr.output.artifact_validation`). When a blocking gate trips it withholds the
polished DOCX while still writing the Markdown/TXT and a sidecar
`*_validation.txt` report, so you always get the content, just not a deliverable
that looks broken. Blocking gates default to zero tolerance; a malformed or
negative value falls back to `0` so a gate can never be silently disabled by a
bad env value. Scaffolding-leak detection is non-blocking visibility and an eval
metric, not a shipping gate.

| Variable | Description | Default |
|----------|-------------|---------|
| `PRIMR_MAX_SCAFFOLDING_LEAKS` | Max tolerated internal-scaffolding markers before logging a non-blocking warning. This covers bare `[workbook]`, `[cross-ref ...]`, bold `**What to validate:**` lines, and informal `[cite: label]` markers. It never withholds the polished DOCX. | `0` |
| `PRIMR_MAX_DANGLING_CITATIONS` | Max tolerated dangling inline citations, `[cite: N]` references with no matching entry in the `## Sources` appendix. The deterministic backstop behind the upstream LLM citation repair, which keeps the original report when it cannot reach zero. | `0` |
| `PRIMR_MAX_STRUCTURE_DEFECTS` | Max tolerated structural defects: duplicate top-level `##` headings and empty sections. Required-section presence is intentionally not gated here because it is report-type-dependent and stays a QA-scoring signal. | `0` |

Notes on the popup budget:
- The budget is a single shared counter - opt in once with `PRIMR_MAX_HEADED_POPUPS=N` and that N is the total allowance across all trigger points in the run.
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
| `research_model` | str | `gemini-3-flash-preview` | Legacy Gemini-backed research model override |
| `report_model` | str | `gemini-3.1-pro-preview` | Legacy Gemini-backed report model override |
| `max_retries` | int | 3 | Maximum retry attempts |
| `grade_threshold` | int | 70 | Quality threshold (0-100) |
| `default_temperature` | float | 1.0 | Model temperature (0.0-2.0) |
| `default_thinking_level` | str | "high" | Model-supported thinking level |
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

#### Synced folders (OneDrive, Dropbox, Google Drive)

Keep high-churn paths - `working/`, `logs/`, and the scrape cache - outside
cloud-synced folders when possible. Sync clients briefly lock files while
uploading them, which collides with the frequent checkpoint writes a run makes
(`_run_state.json` alone is rewritten on every phase transition). Primr
retries these atomic writes when a lock blocks them (the run-state checkpoint
additionally falls back to a direct overwrite), so a synced folder will not
corrupt state, but runs are slower and noisier there. Run from a plain local
directory (for example `C:\research\` rather than `C:\Users\you\OneDrive\...`),
and let only the final deliverables in `output/` live in a synced location if
you want them backed up. `primr doctor` probes the same atomic write path a
real run uses, so it will surface this contention before a long run does.

### PricingConfig

Controls cost estimation. Prices are per 1 million tokens.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gemini_input_per_million` | float | 2.00 | Input token cost (USD/1M) |
| `gemini_output_per_million` | float | 12.00 | Output token cost (USD/1M) |
| `deep_research_base_cost` | float | 2.50 | Base cost per deep research task |
| `search_cost_per_query` | float | 0.035 | Search API cost per query |

These legacy settings are not the whole estimator for modern routed runs. The
current default estimate comes from provider routing and strategy settings:
with xAI plus Gemini configured, the default Strategic Overview plus one
platform-neutral AI Strategy is typically around `$0.89`; an explicitly
requested two-platform strategy is typically around `$1.01`; and
`--no-ai-strategy` is typically around `$0.76-$0.79`. XAI-only defaults remain
on the higher legacy path.
Always use `primr --dry-run` as the source of truth.

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
