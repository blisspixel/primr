# Primr Internals

This document explains the internal workings of Primr's key algorithms and prompt engineering strategies.

## Prompt Engineering

### Epistemic Framing

All research prompts include explicit epistemic framing to prevent overconfident AI outputs.

**Key prompt elements:**

```
EPISTEMIC CONTRACT:
This document represents preliminary pattern recognition, not conclusions.
Every strategic observation must be expressed as one of:
- A verified fact (with citation)
- An inference (clearly labeled as such)
- A hypothesis to validate in conversation
```

**Transformation rules:**

```
If a sentence implies inevitability, failure, or urgency, rewrite it as a
question or scenario comparison.

Example transformation:
- Instead of: "X faces an existential threat from Y"
- Write: "One risk worth exploring is whether Y could materially pressure
  X's margins over time"
```

### Subject-Positive Posture

Prompts explicitly instruct the AI to assume competence:

```
Subject-Positive Intent: We assume this company is rational, competent, and
generally successful in its context. Our goal is not to critique from the
outside, but to understand how they create value today and where they might
go further or move faster.
```

This prevents the AI from generating condescending or accusatory analysis.

### Formatting Rules

Every prompt includes explicit formatting rules:

```
FORMATTING RULES (follow these exactly):
- Write in full paragraphs unless bullets genuinely help clarity
- Keep bullets single-level only, no nested sub-bullets
- No em-dashes or en-dashes, use commas or periods instead
- Cite sources at the end of each major section, not inline
```

These rules are repeated because AI models tend to drift toward their default formatting preferences.

### Section Structure

Report sections are defined in YAML configuration files, not hardcoded in Python. This makes the structure:
- **Reviewable**: Sections can be reviewed as standalone artifacts
- **Versionable**: Changes are tracked in version control
- **Customizable**: Users can modify sections without changing code
- **Extensible**: New strategy reports can be added by creating new YAML files

**The Strategic Company Overview uses 23 sections** defined in `src/primr/prompts/company_overview.yaml`:

| Part | Sections |
|------|----------|
| 1 - Foundational | Executive Summary, Products and Services, Target Customers, Competitive Differentiation, Financial Profile, Company History, Leadership and Organization |
| 2 - Industry | Industry Dynamics, Industry Outlook, Competitive Landscape |
| 3 - Strategic | Business Model, SWOT Analysis, Strategic Tensions, Constraints and Degrees of Freedom |
| 4 - Patterns | Narrative Gap Analysis, Fragilities, Patterns Worth Exploring, Discovery Questions, Board Perspective, Engagement Opportunities |
| 5 - Frameworks | Porter's Five Forces, Value Chain Analysis, Strategic Positioning Hypothesis |

**AI Strategy Report** uses 15 sections defined in `src/primr/prompts/strategies/ai_strategy.yaml`. It starts with business strategy and value, then treats Azure, AWS, GCP, private infrastructure, or agnostic selection as an evaluation emphasis rather than a predetermined answer.

The architecture is designed for extensibility - new strategy modules can be added by creating YAML files in `src/primr/prompts/strategies/`.

### Key Metrics Extraction

Prompts specify exact formats for extractable metrics:

```
KEY METRICS FORMAT (use these exact formats so we can extract them):
- Employees: X,XXX (or "Employees: ~X,XXX estimated")
- Revenue: $X.XB or $XXM (or "Revenue: ~$XXM estimated")
- Founded: YYYY
- Headquarters: City, State
```

This enables downstream parsing and structured data extraction.

## Scraping Algorithms

### Tier Selection

The scraping engine escalates through nine tiers, **browser-first** (a real
browser defeats most modern bot defenses; plain HTTP is the last resort, and a
vision tier sits in the middle as a safety net). The canonical order lives in
`src/primr/data/scraping/tier_registry.py`:

```python
def scrape(url):
    tiers = [
        "playwright", "playwright_aggressive", "patchright",   # browser
        "curl_cffi", "drissionpage_stealth", "drissionpage",   # stealth HTTP / browser
        "vision",                                              # screenshot + Gemini extraction
        "httpx", "requests",                                   # plain HTTP fallback
    ]
    for tier in tiers:
        content, error = run_tier(tier, url)
        if content and not is_soft_blocked(content):
            return content
    return None
```

See [ARCHITECTURE](ARCHITECTURE.md) for the full tier table and per-tier costs.

Each tier is tried in order. Escalation happens on:
- HTTP errors (4xx, 5xx)
- Connection errors
- Timeouts
- Soft block detection

### Soft Block Detection

Content is analyzed for block indicators:

```python
SOFT_BLOCK_INDICATORS = [
    "captcha", "verify you are human", "access denied", "forbidden",
    "please enable javascript", "browser check", "checking your browser",
    "ddos protection", "cloudflare", "just a moment", "ray id",
    "unusual traffic", "automated access", "bot detected",
    "enable cookies", "login required", "sign in to continue",
    "403 forbidden", "401 unauthorized", "blocked"
]

def detect_soft_block(text, url):
    text_lower = text.lower()
    for indicator in SOFT_BLOCK_INDICATORS:
        if indicator in text_lower:
            # Special cases
            if indicator == "cloudflare" and "cloudflare.com" in url:
                continue  # Cloudflare's own site
            if indicator == "login" and len(text) > 5000:
                continue  # Legitimate page mentioning login
            return True, f"Detected: {indicator}"
    
    if len(text.strip()) < 100:
        return True, "Content too short"
    
    return False, None
```

### Browser Fingerprinting

Five HTTP profiles are maintained in
`src/primr/data/scraping/profiles.py`:

| Profile | User Agent | Platform |
|---------|------------|----------|
| `chrome_131_windows` | Chrome/131 on Win10 | Win32 |
| `chrome_131_mac` | Chrome/131 on macOS | MacIntel |
| `chrome_130_windows` | Chrome/130 on Win10 | Win32 |
| `edge_131_windows` | Edge/131 on Win10 | Win32 |
| `safari_18_mac` | Safari/18.2 on macOS | MacIntel |

Each profile carries a user-agent string, platform and vendor identifiers,
client hints, and screen dimensions. Timezone and viewport are decoupled into a
separate `CONTEXT_PROFILES` set (America/New_York, Los_Angeles, Chicago,
Denver) so a fingerprint and its locale can be varied independently.
- Color depth
- Hardware concurrency
- Device memory
- WebGL vendor/renderer
- Sec-CH-UA headers (for Chrome)

### Stealth Script

Playwright pages are injected with JavaScript to hide automation:

```javascript
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
delete navigator.__proto__.webdriver;

// Add Chrome runtime (for Chrome profiles)
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };

// Spoof permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Spoof plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' }
        ];
        plugins.item = (i) => plugins[i];
        plugins.namedItem = (name) => plugins.find(p => p.name === name);
        plugins.refresh = () => {};
        return plugins;
    }
});

// Spoof WebGL
const getParameterProxyHandler = {
    apply: function(target, thisArg, args) {
        const param = args[0];
        if (param === 37445) return 'Google Inc. (Intel)';  // VENDOR
        if (param === 37446) return 'ANGLE (Intel, ...)';   // RENDERER
        return Reflect.apply(target, thisArg, args);
    }
};
```

## Quality Grading

### Grading Criteria

Each section is graded on four equally-weighted criteria that contribute to a
single **0-100** score (there are no separate per-criterion sub-scores):

1. **Clarity & Readability**: Is the section well-structured?
2. **Completeness**: Does it cover critical aspects?
3. **Insight Depth**: Does it provide meaningful business insights?
4. **Accuracy**: Does it match the company's website information?

### Grading Prompt

```
You are a business analyst grading a research report section.
Provide a single numerical score (0-100) based on the quality of the section.

Company Information:
- Company Name: {company_name}
- Website: {website}
- Section Name: {section_name}

--- SECTION TEXT ---
{section_text}
--- END SECTION TEXT ---

--- SCRAPED WEBSITE INSIGHTS ---
{scraped_insights}
--- END SCRAPED INSIGHTS ---

Respond in this exact format:
```
Grade: X
Reason: [Concise reason why this score was given.]
```
```

### Refinement Trigger

Sections scoring below the threshold (default: 70) trigger additional research:

```python
if score < GRADE_THRESHOLD:
    search_query = f'"{company_name} {section_name}" site:{website}'
    additional_results = search_google(search_query)
    # Re-generate section with additional context
```

## Caching Strategy

### Cache Key Generation

URLs are normalized and hashed:

```python
def get_cache_key(url):
    # Normalize URL
    url = url.split("#")[0]  # Remove fragment
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    
    # Hash to fixed-length key
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
```

### LRU Eviction

Memory cache uses OrderedDict for LRU:

```python
class LRUCache:
    def __init__(self, max_size=100):
        self._cache = OrderedDict()
        self._max_size = max_size
    
    def get(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)  # Mark as recently used
            return self._cache[key]
        return None
    
    def set(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # Evict oldest
        self._cache[key] = value
```

### Disk Cache Format

Each cached URL produces two files:

```
logs/scrape_cache/
├── {hash}.txt   # Content
└── {hash}.meta  # Metadata JSON
```

Metadata structure:
```json
{
    "url": "https://example.com/page",
    "timestamp": "2025-12-18T10:30:00",
    "size": 15234
}
```

## Deep Research Integration

### The Accordion Method

The production Deep/Premium path separates research from sequential writing.
It targets greater evidence breadth and section depth than one Deep Research
response, without promising a fixed page count:

```
Phase 1: Deep Research (Lead Researcher)
  - Agent: deep-research-preview-04-2026
  - Role: Gather facts, data, citations
  - Output: Evidence dossier with citations

Phase 2: Sequential Section Writing (Gemini Flash)
  - Model: PrimrModels.FLASH_MODEL
  - Role: Write each section with analytical depth
  - Input: Dossier plus bounded excerpts from recent sections
  - Output: Configured YAML section plan, sized from an approximate target

Phase 3: Assembly
  - Output: Ordered sections, table of contents, and preserved citations
```

This architecture treats Deep Research as the **researcher** and Gemini Flash
as the **writer**. Section calls use direct generation; they do not continue the
Deep Research interaction.

### Section Writing Context

Each section prompt carries the dossier, bounded Stage 1 evidence, and excerpts
from up to three recent sections. The loop is sequential and uses adaptive
rate-limit pacing. This is continuity-aware context, not an unbounded shared
conversation. See [ARCHITECTURE](ARCHITECTURE.md) for the current end-to-end
pipeline diagram.

### Model Selection

| Component | Model | Rationale |
|-----------|-------|-----------|
| Research Dossier | `deep-research-preview-04-2026` | Autonomous web research |
| Section Writing | `PrimrModels.FLASH_MODEL` | Sequential, cost-controlled synthesis |
| Stage 1 Analysis | `gemini-3-flash-preview` | Quick section analysis |

Deep Research responses are parsed from the current Interactions shape:
`steps[*].model_output.content`. A deliberate legacy `outputs` fallback remains
for persisted jobs created under older response shapes. Background interactions
set `store=True` because Google requires storage for background execution. See
Google's [Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview)
and [Deep Research guide](https://ai.google.dev/gemini-api/docs/deep-research).

### Adaptive Polling

Polling interval increases over time:

```python
def get_poll_interval(elapsed_seconds):
    if elapsed_seconds < 60:
        return 5.0   # Fast initially
    elif elapsed_seconds < 300:
        return 10.0  # Normal
    else:
        return 20.0  # Slow for long tasks
```

### Job Recovery

Pending jobs are saved to disk:

```python
def save_pending_job(interaction_id, job_type, description):
    jobs_file = "logs/pending_research_jobs.json"
    jobs = load_existing_jobs()
    jobs[interaction_id] = {
        "type": job_type,
        "description": description,
        "started": datetime.now().isoformat(),
        "status": "pending"
    }
    save_jobs(jobs)
```

Status inspection is read-only. Completed jobs are finalized explicitly:

```bash
primr --check-jobs
primr --resume-latest
```

The pending record is removed only after recovered outputs are saved. Provider-terminal jobs are acknowledged by explicit resume; transient status-check errors remain pending.

### File Search Store

Context from Stage 1 is uploaded to a Gemini File Search store. Upload returns a
long-running operation, so Primr waits with a bounded timeout and backoff before
submitting the research interaction:

```python
def upload_to_file_search_store(context_file, company_name):
    store = client.file_search_stores.create(
        config={"display_name": f"primr-{company_name}-{timestamp}"}
    )
    operation = client.file_search_stores.upload_to_file_search_store(
        file=context_file,
        file_search_store_name=store.name,
    )
    wait_for_file_search_operation(client, operation)
    return store.name
```

The dossier interaction references this store:

```python
tools = [{
    "type": "file_search",
    "file_search_store_names": [store_name]
}]
```

Google documents that imported File Search data and its embeddings persist
until the store is manually deleted. The temporary raw File API object is
deleted after 48 hours. Primr deletes its owned store after terminal work, but
does not delete a store while an accepted background interaction may still use
it. Storage and query-time embeddings are free; indexing embeddings are billed.
See Google's [File Search storage and pricing notes](https://ai.google.dev/gemini-api/docs/file-search#pricing).

## Token Usage Tracking

### Extraction

Token counts are extracted from API responses:

```python
def extract_usage(response):
    if not hasattr(response, 'usage_metadata'):
        return None
    
    metadata = response.usage_metadata
    return TokenUsage(
        input_tokens=metadata.prompt_token_count,
        output_tokens=metadata.candidates_token_count
    )
```

### Cost Calculation

Token fallback costs come from the selected entry in `ModelRegistry`, including
published cached-input and long-context tiers. They are not calculated from one
global Gemini price. xAI responses may additionally return
`usage.cost_in_usd_ticks`; Primr records that exact billed amount when present
and retains registry pricing as the conservative fallback. One US dollar is
10,000,000,000 ticks. See xAI's
[cost-tracking contract](https://docs.x.ai/developers/cost-tracking).

## Error Recovery

### Retry Strategy

Exponential backoff with jitter:

```python
def calculate_backoff_delay(attempt, base_delay=1.0, max_delay=60.0):
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter
```

### Quota Detection

Daily quota exhaustion is detected and handled specially:

```python
error_str = str(e).lower()
is_quota_exhausted = (
    "resource_exhausted" in error_str and
    ("per_day" in error_str or "quota" in error_str)
)

if is_quota_exhausted:
    # Stop immediately, don't retry
    raise AIError("Daily API quota exhausted")
```

### Fallback Chains

Runtime failover uses explicit provider-aware chains. The legacy
`PrimrModels.FALLBACK_MODELS` mapping is intentionally empty so individual
model calls cannot silently substitute an arbitrary model.

```python
from primr.pipeline.model_breaker import (
    ANALYSIS_FALLBACK_CHAIN,
    PREMIUM_FALLBACK_CHAIN,
    UTILITY_FALLBACK_CHAIN,
)

fallback_chains = {
    "analysis": ANALYSIS_FALLBACK_CHAIN.models,
    "utility": UTILITY_FALLBACK_CHAIN.models,
    "premium": PREMIUM_FALLBACK_CHAIN.models,
}
```

The circuit breaker filters each chain to configured providers and tries the
next eligible model for quota and other failover-eligible failures. See
`src/primr/pipeline/model_breaker.py` for the current ordered chains.


## Prompt Architecture

### Overview

Primr uses an externalized prompt architecture where prompts are defined in YAML configuration files rather than hardcoded Python strings. This makes prompts:

- **Reviewable**: Prompts can be reviewed as standalone artifacts
- **Versionable**: Changes to prompts are tracked in version control
- **Customizable**: Users can modify prompts without changing code
- **Composable**: Shared components are reused across prompts

### Directory Structure

```
src/primr/prompts/
├── __init__.py           # Public API exports
├── composer.py           # PromptComposer class
├── loader.py             # Legacy loader functions
├── registry.py           # StrategyModuleRegistry
├── schema.py             # Dataclass definitions
├── shared_loader.py      # SharedComponentLoader
├── exceptions.py         # Custom exceptions
├── company_overview.yaml # Company research prompt
├── strategic_layer.yaml  # Strategic analysis prompt
├── shared/
│   ├── epistemic_rules.yaml  # Epistemic standards
│   ├── formatting.yaml       # Formatting rules
│   └── personas.yaml         # Analyst personas
└── strategies/
    ├── ai_strategy.yaml              # AI strategy module (default)
    ├── ai_first_transformation.yaml  # Historical / non-selectable
    ├── customer_experience.yaml      # Active strategy module
    ├── data_fabric_strategy.yaml     # Active strategy module
    ├── modern_security_compliance.yaml
    ├── skills.yaml                   # Skills-pack strategy
    ├── cloud_migration.yaml          # Placeholder
    └── data_strategy.yaml            # Placeholder
```

### Core Components

#### PromptComposer

The central class for composing prompts from YAML configurations:

```python
from primr.prompts import PromptComposer, PromptContext

composer = PromptComposer()
context = PromptContext(
    company_name="Acme Corp",
    website_url="https://acme.com",
    platform="azure",
)

# Compose a standard prompt
result = composer.compose("company_overview", context)
print(result.content)

# Compose a strategy prompt
result = composer.compose_strategy("ai", context)
print(result.content)
```

#### PromptContext

Runtime context for variable substitution:

```python
@dataclass
class PromptContext:
    company_name: str
    website_url: str | None = None
    platform: str = "agnostic"
    current_date: str | None = None
    has_stage1_context: bool = False
    custom_vars: dict[str, str] = field(default_factory=dict)
```

#### StrategyModuleRegistry

Discovers and manages strategy modules:

```python
from primr.prompts import get_registry

registry = get_registry()

# List available strategies
for name in registry.list_names():
    print(name)

# Get a specific strategy
strategy = registry.get("ai")
print(strategy.display_name)

# Get context files for a strategy
files = registry.get_context_files("ai", vendor="azure")
```

### YAML Schema

#### Prompt Configuration

```yaml
meta:
  name: "Strategic Company Overview"
  version: "1.1.0"
  description: "Comprehensive company research"
  output_format: "markdown"
  expected_pages: "20-70"

document_purpose: |
  This is INTERNAL PREP to understand the company...

epistemic_rules:
  fact_inference_hypothesis: |
    Distinguish facts (with citations) from inferences...

formatting:
  paragraphs: "Write in full paragraphs..."
  bullets: "Use bullets only when they genuinely help..."

sections:
  - id: executive_summary
    name: "Executive Summary"
    part: 1
    purpose: "The 'so what' for the reader"
    covers:
      - "Key findings"
      - "Strategic implications"
    depth: "2-3 paragraphs. Concise and actionable."
```

#### Strategy Module

Strategy modules extend the base schema with:

```yaml
# Current vendor evidence is resolved at run time rather than pinned here.
data_sources: []

# Platform evaluation guidance
vendor_guidance:
  azure:
    display_name: "Microsoft ecosystem emphasis"
    guidance: "Start with business fit, preserve other observed ecosystems, and verify current product claims against official evidence."
```

### Creating a New Strategy Module

1. Create a new YAML file in `src/primr/prompts/strategies/`:

```yaml
# my_strategy.yaml
meta:
  name: "My Strategy"
  version: "1.0.0"
  description: "Description of the strategy"
  status: "active"  # or "placeholder"

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

2. The strategy is automatically discovered by the registry.

3. Use it through the normal estimated research pipeline:

```bash
# List registered strategies
primr --list-strategies

# Generate a specific strategy with the Strategic Overview
primr "Company" https://company.example --strategy-type customer_experience
```

Standalone `--ai-strategy-only` generation now defaults to the ~$1 lite (Pro
reasoning) engine, emits a full estimate, and is budget-gated with a `--dry-run`
preview and a `--deep-research` opt-in, so it is safe for agent workflows behind
the standard estimate/approval gate.

### Error Handling

Custom exceptions provide helpful error messages:

```python
from primr.prompts import (
    PromptConfigNotFoundError,
    PromptConfigValidationError,
    StrategyModuleNotFoundError,
)

try:
    composer.compose("nonexistent", context)
except PromptConfigNotFoundError as e:
    print(f"Not found: {e.prompt_name}")
    print(f"Available: {e.available_prompts}")
```

### Shared Components

Shared components are loaded from `shared/` and merged into prompts:

- **epistemic_rules.yaml**: Standards for distinguishing facts, inferences, and hypotheses
- **formatting.yaml**: Formatting rules (paragraphs, bullets, citations)
- **personas.yaml**: Analyst personas (senior_consultant, ai_strategist, technical_architect)

Prompts can override shared components:

```yaml
# In a prompt YAML
epistemic_rules_override:
  confidence_labeling: |
    Custom confidence labeling rule...
```

### Variable Substitution

Variables in prompts are substituted at runtime:

| Variable | Source |
|----------|--------|
| `{company_name}` | `context.company_name` |
| `{website_url}` | `context.website_url` |
| `{platform}` | `context.platform` |
| `{cloud_vendor}` | Legacy alias for `context.platform` |
| `{current_date}` | `context.current_date` or auto-generated |

Custom variables can be added via `context.custom_vars`.
