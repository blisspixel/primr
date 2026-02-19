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

**As of December 2025, the Strategic Company Overview uses 21 sections** defined in `src/primr/prompts/company_overview.yaml`:

| Part | Sections |
|------|----------|
| 1 - Foundational | Executive Summary, Products and Services, Target Customers, Competitive Differentiation, Financial Profile, Company History, Leadership and Organization |
| 2 - Industry | Industry Dynamics, Competitive Landscape |
| 3 - Strategic | Business Model, SWOT Analysis, Strategic Tensions, Constraints and Degrees of Freedom |
| 4 - Patterns | Narrative Gap Analysis, Fragilities, Patterns Worth Exploring, Discovery Questions, Engagement Opportunities |
| 5 - Frameworks | Porter's Five Forces, Value Chain Analysis, Strategic Positioning Hypothesis |

**AI Strategy Report** uses 17 sections defined in `src/primr/prompts/strategies/ai_strategy.yaml`, including vendor-specific guidance for Azure, AWS, and GCP.

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

The scraping engine uses a simple escalation strategy:

```python
def scrape(url):
    for tier in [requests, httpx, playwright, playwright_aggressive]:
        content, error = tier.scrape(url)
        if content and not is_soft_blocked(content):
            return content
    return None
```

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

Four browser profiles are maintained:

| Profile | User Agent | Platform | Timezone |
|---------|------------|----------|----------|
| Windows Chrome | Chrome/122 on Win10 | Win32 | America/New_York |
| Mac Chrome | Chrome/122 on macOS | MacIntel | America/Los_Angeles |
| Windows Firefox | Firefox/123 on Win10 | Win32 | America/Chicago |
| Mac Safari | Safari/17.2 on macOS | MacIntel | America/Denver |

Each profile includes:
- User agent string
- Platform identifier
- Vendor string
- Timezone
- Screen dimensions
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

Each section is graded on four dimensions:

1. **Clarity & Readability** (0-25): Is the section well-structured?
2. **Completeness** (0-25): Does it cover critical aspects?
3. **Insight Depth** (0-25): Does it provide meaningful business insights?
4. **Accuracy** (0-25): Does it match the company's website information?

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

Sections scoring below the threshold (default: 80) trigger additional research:

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

The Accordion Method produces 30+ page reports by separating research from writing:

```
Phase 1: Deep Research (Lead Researcher)
  - Agent: deep-research-pro-preview-12-2025
  - Role: Gather facts, data, citations
  - Output: ~12 page research dossier

Phase 2: Section Writing (Gemini 3 Flash)
  - Model: gemini-3-flash-preview
  - Role: Write each section with analytical depth
  - Input: Dossier + previous sections in prompt
  - Output: 20 sections × ~1.5 pages = 30+ pages
```

This architecture treats Deep Research as the **researcher** and Gemini 3 Flash as the **writer**.

### Why Not `previous_interaction_id`?

The Gemini docs mention `previous_interaction_id` for follow-up questions. However, testing showed that direct `generate_content()` calls with the dossier in the prompt produce better results:

- More reliable (no interaction state to manage)
- Faster (no interaction lookup overhead)
- More controllable (full prompt visible)

### Model Selection

| Component | Model | Rationale |
|-----------|-------|-----------|
| Research Dossier | `deep-research-pro-preview-12-2025` | Autonomous web research |
| Section Writing | `gemini-3-flash-preview` | Fast, intelligent, cost-effective |
| Stage 1 Analysis | `gemini-3-flash-preview` | Quick section analysis |

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

On startup, pending jobs can be resumed:

```bash
primr --check-jobs
```

### File Search Store

Context from Phase 0 is uploaded to Gemini's File Search Store:

```python
def upload_to_file_search_store(context_file, company_name):
    store = client.file_search_stores.create(
        name=f"primr_{company_name}_{timestamp}"
    )
    client.file_search_stores.upload(
        store_name=store.name,
        file_path=context_file
    )
    return store.name
```

All Phase 2 research nodes reference this store:

```python
tools = [{
    "type": "file_search",
    "file_search_store_names": [store_name]
}]
```

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

Costs are calculated using Gemini pricing:

```python
INPUT_PRICE = 2.00   # per 1M tokens
OUTPUT_PRICE = 12.00  # per 1M tokens

def calculate_cost(input_tokens, output_tokens):
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE
    return input_cost + output_cost
```

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

Models have configured fallbacks:

```python
model_fallbacks = {
    "gemini-3-flash-preview": ["gemini-2.0-flash"],
    "gemini-3-pro-preview": ["gemini-2.0-pro", "gemini-3-flash-preview"]
}
```

On failure, the next model in the chain is tried.


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
    ├── ai_strategy.yaml      # AI strategy module
    ├── cloud_migration.yaml  # Cloud migration (placeholder)
    └── data_strategy.yaml    # Data strategy (placeholder)
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
    cloud_vendor="azure",
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
    cloud_vendor: str = "agnostic"
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
# Data sources for File Search Store
data_sources:
  - name: "vendor_research_azure"
    path: "vendor-research/vendor-research-azure-2025-12.txt"
    description: "Latest Azure AI services"
    vendor: "azure"
    required: false

# Vendor-specific guidance
vendor_guidance:
  azure:
    display_name: "Microsoft Azure"
    key_services:
      productivity_copilots:
        - "Microsoft 365 Copilot"
        - "Copilot Studio"
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

3. Use it via CLI:

```bash
# List registered strategies
primr --list-strategies

# Generate a specific strategy from an existing strategic overview
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type customer_experience
```

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
| `{cloud_vendor}` | `context.cloud_vendor` |
| `{current_date}` | `context.current_date` or auto-generated |

Custom variables can be added via `context.custom_vars`.
