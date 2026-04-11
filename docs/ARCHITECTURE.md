# Primr Architecture

This document describes the internal architecture of Primr, a research tool that generates company intelligence briefs using Google's Gemini models.

## Overview

Primr is designed around a core insight: good company research requires both breadth (what's publicly available) and depth (what it means strategically). The architecture reflects this by combining two complementary research engines, each optimized for different aspects of the problem.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI Entry Point                              │
│                      primr "Company" https://...                     │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Research Orchestrator                           │
│                   (Mode Selection & Coordination)                    │
└─────────────────────────────────────────────────────────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
    │   Scrape    │        │    Deep     │        │   Complete  │
    │    Mode     │        │    Mode     │        │    Mode     │
    │  (5-10m)    │        │  (10-15m)   │        │  (30-40m)   │
    └─────────────┘        └─────────────┘        └─────────────┘
           │                       │                       │
           ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Report Generation                             │
│                    (DOCX, PDF, TXT Output)                          │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. Epistemic Humility

Primr distinguishes between facts, inferences, and hypotheses. The system is designed to surface what we know, what we think, and what we should ask. This is encoded in prompts, output formatting, and the separation between data collection and analysis.

### 2. Local-First

All processing happens on the user's machine. No data leaves except API calls to Google (Gemini, Search). This keeps sensitive research private and avoids the complexity of multi-tenant infrastructure.

### 3. Graceful Degradation

Every component has fallbacks. If Playwright fails, try httpx. If httpx fails, try requests. If the AI planning call fails, use default chapter structure. The system should produce useful output even when individual components fail.

### 4. Separation of Concerns

Data collection (scraping, search) is separate from analysis (AI). Analysis is separate from output (document generation). This makes the system testable and allows components to evolve independently.

## Research Modes

### Scrape Mode (Corpus+Insights)

Website-focused research using the `build_site_corpus` workflow with AI-powered insight extraction.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Scrape Mode Pipeline (Corpus+Insights)             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     build_site_corpus (fetch_web_content)            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  1. discover_site_urls → (in_scope_urls, external_urls)      │   │
│  │  2. rank_and_select_urls → selected_urls                     │   │
│  │  3. scrape_pages (using scrape_page primitive with tiers)    │   │
│  │  4. build_corpus → cleaned text                              │   │
│  │  5. save_raw_scrapes, save_external_links                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Outputs: _raw_scrapes/, scraped_content.txt, _external_links.txt   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   scrape_page primitive (8-Tier Orchestrator)        │
│  ┌───────────────┐  ┌───────────────────┐  ┌───────────┐            │
│  │  Playwright   │─▶│Playwright Aggress.│─▶│ curl_cffi │            │
│  │   (browser)   │  │ (content expand)  │  │(TLS spoof)│            │
│  └───────────────┘  └───────────────────┘  └───────────┘            │
│         │                                        │                   │
│         ▼                                        ▼                   │
│  ┌───────────────────┐  ┌───────────────┐  ┌─────────┐  ┌─────────┐ │
│  │DrissionPage Stealt│─▶│ DrissionPage  │─▶│  httpx  │─▶│Requests │ │
│  │ (challenge wait)  │  │  (driverless) │  │ (HTTP/2)│  │ (fast)  │ │
│  └───────────────────┘  └───────────────┘  └─────────┘  └─────────┘ │
│                                                                      │
│  Features: Sticky tier, Circuit breaker, Cookie handoff, Soft block │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     extract_insights (summarize_scraped_content)     │
│              (Extract key facts from corpus - LLM-powered)          │
│                                                                      │
│  Output: insights.txt                                               │
└─────────────────────────────────────────────────────────────────────┘
```

**When to use:** Quick website intel, data collection for downstream use. Fast (5-10 min) and cheap (~$0.01-0.05).

### Deep Mode

Autonomous research using Gemini's Deep Research Agent with built-in Google Search.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Deep Mode Pipeline                            │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Deep Research Agent (Gemini)                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  1. Autonomous Planning: Agent decides what to research      │   │
│  │  2. Web Search: Built-in Google Search integration           │   │
│  │  3. Page Analysis: Reads and synthesizes web content         │   │
│  │  4. Citation Tracking: Automatic source attribution          │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Result Normalization                            │
│              (Convert agent output to section format)               │
└─────────────────────────────────────────────────────────────────────┘
```

**When to use:** Broad market analysis, competitive intelligence, industry trends, when you need information beyond the company's own website.

### Complete Mode (Recommended)

Three-phase "Accordion Method" architecture for comprehensive 30+ page reports. This approach treats Deep Research as a Lead Researcher (gathering facts) and Gemini 3 Pro as the Writer (crafting sections with context continuity).

**Critical API Limitation (December 2025):** Google's Deep Research Agent (`deep-research-pro-preview-12-2025`) produces ~8-12 pages maximum per API call, regardless of prompt instructions. Tested with explicit "30 page" requests, the API consistently returns ~4,000-5,000 words. This is a fundamental output token limit, not a prompt engineering issue. The Accordion Method works around this by using Deep Research for fact-gathering and Gemini 3 Pro for section-by-section writing.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Complete Mode: Accordion Method                   │
│                  (Research → Outline → Write Sections)              │
└─────────────────────────────────────────────────────────────────────┘

Phase 1: Data Collection (10-20 min)
┌─────────────────────────────────────────────────────────────────────┐
│                      Structured Pipeline                             │
│         (Full website scraping + Google search + AI analysis)       │
│                              │                                       │
│                              ▼                                       │
│                    Context File Generation                           │
│              (Baseline facts uploaded to File Search Store)         │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
Phase 2: Research Dossier (10-15 min)
┌─────────────────────────────────────────────────────────────────────┐
│                    Deep Research Agent                               │
│                (deep-research-pro-preview-12-2025)                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Role: Lead Researcher (NOT Writer)                          │   │
│  │  Input: "Compile a research dossier, NOT the final report"   │   │
│  │  Output: Raw facts, data tables, citations, case studies     │   │
│  │  Access: File Search Store with Phase 1 context              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Key insight: Don't ask Deep Research to write 30 pages.            │
│  Ask it to gather the facts that will support 30 pages.             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
Phase 3: Section-by-Section Writing (10-15 min)
┌─────────────────────────────────────────────────────────────────────┐
│                    Sequential Section Writer                         │
│                      (gemini-3-pro-preview)                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Uses: previous_interaction_id from Phase 2                  │   │
│  │  Process: Write one section at a time, sequentially          │   │
│  │  Context: Research dossier + summary of previous sections    │   │
│  │  Output: ~1,000-2,000 words per section                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Section 1 ──▶ Section 2 ──▶ Section 3 ──▶ ... ──▶ Section 10      │
│      │             │             │                      │           │
│      └─────────────┴─────────────┴──────────────────────┘           │
│              Context flows forward for consistency                   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
Phase 4: Assembly (< 1 min)
┌─────────────────────────────────────────────────────────────────────┐
│                      Report Assembler                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  - Combine sections with consistent formatting               │   │
│  │  - Generate table of contents                                │   │
│  │  - Consolidate citations                                     │   │
│  │  - Apply clean header style (no PART headers)                │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Why the Accordion Method?**

A single Deep Research call produces ~12 pages due to output token limits. Asking for "50 pages" causes:
- **Middle Muddle**: Pages 10-40 become vague and repetitive
- **Hallucination Spirals**: Small errors compound as the model consumes its own output

The Accordion Method solves this by:
1. **Expanding** (research): Gather comprehensive facts
2. **Contracting** (outline): Structure into sections with word targets
3. **Expanding** (writing): Write each section with full context

**Model Usage:**
- `deep-research-pro-preview-12-2025`: Autonomous web research (Phase 2)
- `gemini-3-pro-preview`: Section writing with `previous_interaction_id` (Phase 3)

**Rate Limit Strategy:**
- Sequential section writes (not parallel) avoid 429 errors
- 10-20 second delays between sections
- Adaptive backoff on rate limit detection

**Hierarchy of Truth:**
1. Company Facts (from Phase 1 scraping): highest authority
2. Research Dossier (from Phase 2 Deep Research): external context
3. Section Writing (Phase 3): synthesis with consistent voice

## Core Components

### Research Orchestrator

Location: `src/primr/core/research_orchestrator.py`

The central coordinator that routes research requests to the appropriate engine based on mode selection. Handles:
- Mode dispatch (scrape, deep, complete)
- Progress callbacks
- Error aggregation
- Metrics emission

```python
orchestrator = ResearchOrchestrator()
result = await orchestrator.research(
    "Acme Corp",
    "https://acme.example",
    mode=ResearchMode.COMPLETE
)
```

### Core Module Structure

The `src/primr/core/` directory contains the research orchestration logic, decomposed into focused modules:

| Module | Responsibility |
|--------|----------------|
| `research_agent.py` | Main entry point with backward-compatible re-exports |
| `workspace.py` | Working folder creation, file consolidation, section output |
| `structured_research.py` | Website scraping pipeline, section-by-section analysis |
| `vendor_research.py` | Cloud vendor AI capabilities research (major providers) |
| `ai_strategy.py` | AI strategy generation with cloud vendor context |
| `deep_research_runner.py` | Deep Research execution with preflight validation |
| `cli.py` | Command-line interface, argument parsing, utility commands |

### Prompt Architecture

The `src/primr/prompts/` directory contains the externalized prompt system (v1.2.5+):

| Module | Responsibility |
|--------|----------------|
| `composer.py` | PromptComposer class for building prompts from YAML |
| `loader.py` | YAML loading utilities and legacy prompt builders |
| `registry.py` | StrategyModuleRegistry for discovering strategy modules |
| `schema.py` | Dataclass definitions for prompt configs |
| `shared_loader.py` | SharedComponentLoader for epistemic rules, formatting, personas |
| `exceptions.py` | Custom exceptions for prompt configuration errors |

Strategy modules are YAML configs in `src/primr/prompts/strategies/` that define different types of strategic analysis (AI, cloud migration, data strategy, etc.).

Each module exposes dataclasses and functions that can be imported directly:

```python
# Direct imports from specialized modules (preferred for new code)
from primr.core.workspace import create_working_folder, WorkspaceConfig
from primr.core.ai_strategy import generate_ai_strategy_sync, CloudVendor
from primr.core.deep_research_runner import validate_preflight, DeepResearchConfig
from primr.core.cli import parse_args, CLIConfig

# Backward-compatible imports (still work, delegate to new modules)
from primr.core.research_agent import main, run_doctor, create_working_folder
```

### Scraping Conceptual Model

Primr distinguishes between two levels of scraping:

| Level | Conceptual Name | Implementation | Input | Output |
|-------|-----------------|----------------|-------|--------|
| Primitive | `scrape_page` | `ScrapeOrchestrator.scrape_url()` | URL | content + tier + quality + errors |
| Workflow | `build_site_corpus` | `fetch_web_content()` | base domain | corpus + raw scrapes + external links |

**Naming Rules (enforced in docs and code):**
- `scrape_page` always refers to ONE URL (the primitive)
- `build_site_corpus` always refers to multi-page site workflow
- `extract_insights` always refers to corpus → structured facts compression (implemented by `summarize_scraped_content()`)
- `--mode scrape` is "Corpus+Insights mode" (multi-page corpus, not one page)
- Never use "scrape" alone without clarifying page-level or site-level

**Key Principle:** There is ONE site-to-corpus workflow (`build_site_corpus`). All modes that need a corpus call this function. No other function should implement a site discovery + scrape loop.

### 8-Tier Scraping Engine (scrape_page primitive)

Location: `src/primr/data/scraping/orchestrator.py`

The `scrape_page` primitive uses a tiered fallback system for web scraping, designed for 2026 realities where most sites use JavaScript. Browser-first approach ensures reliable scraping of modern sites.

| Tier | Method | Use Case | Speed |
|------|--------|----------|-------|
| 1 | Playwright | JS-rendered content (default) | Medium |
| 2 | Playwright Aggressive | Content expansion (accordions, lazy load) | Medium |
| 3 | curl_cffi | TLS fingerprint impersonation | Fast |
| 4 | DrissionPage Stealth | Maximum stealth with challenge waiting | Slow |
| 5 | DrissionPage | Driverless browser via CDP | Slow |
| 6 | Vision | AI-based extraction (enabled by default) | Slow |
| 7 | httpx | HTTP/2 sites, better headers | Fast |
| 8 | requests | Simple sites, no JS (fallback) | Fast |

**Key Features:**
- **Sticky Tier**: Once a tier works for a host, it's tried first for subsequent pages
- **Circuit Breaker**: Skips failing tiers after 3 consecutive failures per host
- **Cookie Handoff**: Browser-obtained cookies reused by faster HTTP tiers
- **Soft Block Detection**: Checks content, not just HTTP status (catches "200 OK" traps)
- **TLS Fingerprint Impersonation**: curl_cffi mimics real browser TLS signatures
- **Driverless Browsers**: DrissionPage uses CDP directly, bypassing WebDriver detection
- **Content-Type Routing**: Automatic detection (HTML, PDF, binary) via headers and magic bytes — PDFs extracted via Gemini LLM with PyMuPDF fallback
- **Smart Tier Escalation** (v1.2.4+): Stops after 3 consecutive failures of same error type to avoid wasting time on impossible pages
- **Adaptive Timeout**: 45s max per page (reduced to 25s when best_tier is known for the host)

### Link Discovery (Homepage-First, v1.1.0)

Part of the `build_site_corpus` workflow:
1. Render homepage with Playwright (browser-first for JS-heavy sites)
2. Extract navigation links (current and navigable)
3. Expand section pages (news, blog, press, resources) to get actual articles
4. Common URL guessing only if < 20 links found
5. Sitemap only as fallback if still < 20 links (sitemaps often stale)
6. LLM selects most valuable pages for research (leadership, products, news, investors)

**Scope Policy:**
- IN-SCOPE: same domain + subdomains (always scraped)
- OUT-OF-SCOPE: external domains (recorded to `_external_links.txt`, not scraped in scrape mode)

### Deep Research Client

Location: `src/primr/ai/deep_research.py`

Integration with Gemini's Deep Research Agent, which autonomously plans and executes multi-step research.

Key features:
- Adaptive polling (faster initially, slower as research progresses)
- Job persistence for recovery after interruption
- Thinking log capture for transparency
- Pre-flight validation before expensive API calls

```python
client = DeepResearchClient()
result = await client.research(
    "Research Acme Corp's competitive position",
    output_format="company_profile",
    priority_urls=["https://acme.example"]
)
```

### Master Architect

Location: `src/primr/ai/report_architect.py`

Decomposes comprehensive reports into chapters using gemini-3-flash-preview for fast, cost-effective planning.

Default chapter structure (customized per company):
1. Executive Summary & Company Snapshot
2. Products, Services & Value Proposition
3. Leadership, Culture & Organization
4. Financial Position & Business Model
5. Target Markets & Customer Segments
6. Competitive Landscape & Market Position
7. Industry Dynamics & External Forces
8. SWOT Analysis & Strategic Assessment
9. Risk Analysis & Mitigation Strategies
10. Strategic Recommendations & Discovery Questions

### Research Node Executor

Location: `src/primr/ai/research_executor.py`

Executes multiple Deep Research tasks in parallel with rate limiting.

- Semaphore-based concurrency control (default: 3 concurrent)
- Per-chapter timeout (15 minutes)
- Adaptive polling intervals
- Graceful handling of partial failures

### Quality Grading Agent

Location: `src/primr/ai/grading_agent.py`

Grades each section of a report on a 0-100 scale based on:
- Clarity & Readability
- Completeness
- Insight Depth
- Accuracy (vs. scraped website data)

Sections scoring below the threshold (default: 70) trigger additional research refinement.

### AI Client

Location: `src/primr/ai/client.py`

Unified interface for all LLM operations with:
- Automatic retry with exponential backoff
- Model fallback chains
- Token usage tracking
- Quota exhaustion detection (stops immediately, doesn't retry)

```python
client = AIClient()
response = client.generate(
    "Analyze this company",
    model_type="research",
    thinking_level="high"
)
print(client.get_usage_summary())
```

## Data Flow

### Scrape Mode Data Flow

```
URL Input
    │
    ▼
┌─────────────────┐
│  URL Validation │
│  & Normalization│
└─────────────────┘
    │
    ▼
┌─────────────────┐     ┌─────────────────┐
│  Cache Check    │────▶│  Return Cached  │
│  (LRU + Disk)   │     │  Content        │
└─────────────────┘     └─────────────────┘
    │ (miss)
    ▼
┌─────────────────┐
│  Tier 1-4       │
│  Scraping       │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Content        │
│  Extraction     │
│  (BeautifulSoup)│
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Soft Block     │
│  Detection      │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Cache Write    │
│  (LRU + Disk)   │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Link Discovery │
│  & Scoring      │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Section        │
│  Extraction     │
│  (AI-powered)   │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Quality        │
│  Grading        │
└─────────────────┘
    │
    ▼
Section Results
```

### Complete Mode Data Flow (Accordion Method)

```
Company Name + URL
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Structured Pipeline (Data Collection)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Scraping   │─▶│  Section    │─▶│  Context    │             │
│  │  Engine     │  │  Extraction │  │  File Gen   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  File Search Store Upload                                        │
│  (Baseline facts accessible to Deep Research)                   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: Research Dossier (ONE Deep Research call)             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  deep-research-pro-preview-12-2025                       │   │
│  │  Role: Lead Researcher (gather facts, NOT write report)  │   │
│  │  Output: Raw facts, data tables, citations               │   │
│  │  Returns: interaction_id for follow-up calls             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: Sequential Section Writing                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  gemini-3-pro-preview with previous_interaction_id       │   │
│  │                                                          │   │
│  │  Section 1 ──▶ Section 2 ──▶ Section 3 ──▶ ... ──▶ 10   │   │
│  │      │             │             │                       │   │
│  │      └─────────────┴─────────────┘                       │   │
│  │         Context flows forward for consistency            │   │
│  │                                                          │   │
│  │  Each section: ~1,000-2,000 words                        │   │
│  │  Delay: 10-20s between sections (rate limit avoidance)   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: Report Assembly                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Section    │─▶│  TOC        │─▶│  Citation   │             │
│  │  Combine    │  │  Generation │  │  Consolidate│             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Report Generation                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │    TXT      │  │    DOCX     │  │    PDF      │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
src/primr/
├── __init__.py              # Package exports
├── __main__.py              # CLI entry point
├── types.py                 # Type definitions, protocols, type guards
│
├── ai/                      # AI operations
│   ├── client.py            # Unified AI client with retry logic
│   ├── async_client.py      # Async/parallel AI operations
│   ├── deep_research.py     # Gemini Deep Research Agent
│   ├── deep_research_execution.py # Shared deep research polling execution engine
│   ├── deep_research_parsing.py # Shared deep research parsing helpers
│   ├── deep_research_polling.py # Shared deep research polling schedules/phases
│   ├── error_policy.py      # Shared AI error classification and retry policy
│   ├── report_architect.py  # Chapter planning (Master Architect)
│   ├── research_executor.py # Parallel chapter execution
│   ├── report_aggregator.py # Chapter combination
│   ├── grading_agent.py     # Quality grading
│   ├── quality_grader.py    # Grading utilities
│   ├── summarize.py         # Content summarization
│   ├── insight_engine.py    # Strategic insight generation
│   ├── insights.py          # Insight data structures
│   ├── competitive.py       # Competitive analysis
│   ├── ai_strategy.py       # AI strategy generation
│   ├── result_normalizer.py # Deep Research result normalization
│   └── llm.py               # Legacy LLM interface
│
├── data/                    # Data collection
│   ├── scrape.py            # 8-tier scraping engine
│   ├── adaptive_scraper.py  # Domain-learning scraper
│   ├── parallel_scraper.py  # Concurrent scraping
│   ├── http_client.py       # HTTP client wrapper
│   ├── cache.py             # Content caching
│   ├── content_extractor.py # Structured content extraction
│   ├── link_scorer.py       # Link prioritization
│   ├── search_utils.py      # Google Search integration
│   ├── validator.py         # Fact validation
│   ├── sentiment.py         # Sentiment analysis
│   ├── pagination.py        # Pagination detection
│   ├── monitoring.py        # Change monitoring
│   ├── knowledge_graph.py   # Entity extraction
│   └── insights_extractor.py# Insight extraction
│
├── core/                    # Research orchestration
│   ├── research_orchestrator.py  # Mode coordination
│   ├── research_agent.py    # Main entry point, backward-compatible re-exports
│   ├── workspace.py         # Working folder management, file consolidation
│   ├── structured_research.py # Website scraping pipeline, section generation
│   ├── vendor_research.py   # Cloud vendor AI capabilities research
│   ├── ai_strategy.py       # AI strategy generation with cloud vendor context
│   ├── deep_research_runner.py # Deep Research execution, preflight validation
│   ├── cli.py               # Command-line interface, argument parsing
│   ├── report_models.py     # Report data structures
│   └── container.py         # Dependency injection
│
├── pipeline/                # Pipeline resilience layer
│   ├── stages.py            # Stage enum and foreground/background classifier
│   ├── recovery.py          # Recovery table and cost-ordered hierarchies
│   ├── model_breaker.py     # Per-model circuit breaker with fallback chains
│   ├── executor.py          # Recovery executor (retry/fallback/skip orchestration)
│   ├── errors.py            # Error classification (transient/quota/configuration)
│   └── integration.py       # Stage wrappers connecting executor to pipeline
│
├── prompts/                 # Externalized prompt architecture (v1.2.5+)
│   ├── composer.py          # PromptComposer for YAML-based prompts
│   ├── loader.py            # YAML loading and legacy builders
│   ├── registry.py          # StrategyModuleRegistry
│   ├── schema.py            # Dataclass definitions
│   ├── shared_loader.py     # Shared component loading
│   ├── exceptions.py        # Custom exceptions
│   ├── company_overview.yaml # Company research prompt
│   ├── strategic_layer.yaml # Strategic analysis prompt
│   ├── shared/              # Shared components
│   │   ├── epistemic_rules.yaml
│   │   ├── formatting.yaml
│   │   └── personas.yaml
│   └── strategies/          # Strategy modules
│       ├── ai_first_transformation.yaml
│       ├── ai_strategy.yaml
│       ├── cloud_migration.yaml
│       ├── customer_experience.yaml
│       ├── data_fabric_strategy.yaml
│       ├── data_strategy.yaml
│       └── modern_security_compliance.yaml
│
├── output/                  # Report generation
│   ├── document_builder.py  # DOCX generation
│   ├── report_assembler.py  # Report assembly
│   ├── citation_processor.py# Citation handling
│   ├── markdown_converter.py# Markdown to DOCX
│   ├── markdown_parser.py   # Markdown parsing
│   ├── executive_summary.py # Executive summary generation
│   ├── section_writer.py    # Section formatting
│   ├── style_engine.py      # Document styling
│   ├── table_builder.py     # Table generation
│   ├── templates.py         # Report templates
│   └── chapter_config.py    # Chapter configuration
│
├── config/                  # Configuration
│   ├── settings.py          # Settings management
│   └── config.py            # Legacy config
│
└── utils/                   # Utilities
    ├── console.py           # Console output
    ├── logging_config.py    # Logging setup
    ├── errors.py            # Typed error hierarchy with retry policies
    ├── retry.py             # RetryPolicyManager with exponential backoff
    ├── circuit_breaker.py   # Circuit breaker with monitoring
    ├── telemetry.py         # OpenTelemetry integration
    ├── cost_tracker.py      # Cost attribution per operation
    ├── validation.py        # Pydantic configuration validation
    ├── migration.py         # Configuration migration tooling
    ├── state_machine.py     # Generic state machine with transitions
    ├── benchmarks.py        # Performance benchmarking suite
    ├── memory_profiler.py   # Memory profiling and leak detection
    ├── files.py             # File operations
    ├── formatting.py        # Text formatting
    ├── validators.py        # Input validation
    ├── type_guards.py       # Runtime type checking
    ├── resources.py         # Resource management
    ├── observability.py     # Metrics and tracing
    └── chat_logger.py       # Interaction logging
```

## Error Handling Strategy

### Retry with Backoff

All AI operations use exponential backoff with jitter:
- Base delay: 1 second
- Multiplier: 2x per attempt
- Max delay: 60 seconds for rate limits
- Jitter: random variation to avoid thundering herd

### Quota Exhaustion

Daily API quota exhaustion is detected and handled specially:
- Immediate stop (no retries)
- Clear error message with recovery instructions
- Suggestion to check quota status

### Graceful Degradation

| Component | Failure Mode | Fallback |
|-----------|--------------|----------|
| Tier 1 scraping | HTTP error | Try Tier 2 |
| Tier 2 scraping | Connection error | Try Tier 3 |
| Tier 3 scraping | Timeout | Try Tier 4 |
| Tier 4 scraping | All failed | Return partial content |
| Chapter planning | API error | Use default chapters |
| Chapter execution | Timeout | Mark chapter failed, continue |
| Grading | API error | Skip grading, use content as-is |

## Pipeline Resilience Layer

Location: `src/primr/pipeline/`

The pipeline resilience layer formalizes Primr's retry and recovery logic into three interlocking subsystems. Instead of ad-hoc retry loops scattered across AI clients, every pipeline stage declares a **cost-ordered recovery hierarchy** — a sequence of actions ranked cheapest-first (e.g., retry → fallback model → skip). A **stage classifier** labels each stage as *foreground* (must complete) or *background* (bail on API overload or budget stress), so background stages like cross-validation and strategy generation never amplify capacity cascades during batch runs. A **model circuit breaker** tracks consecutive API failures per model and automatically routes to fallback models after 3 failures, with recovery probes after 10 minutes.

The resilience layer sits between the pipeline orchestrator (`research_agent.py`) and the AI clients (`grok_client.py`, `llm.py`). It shares no mutable global state and is fully unit-testable. On successful runs, it adds no observable behavior change (NFR 1).

- **Recovery Table** (`recovery.py`): Declarative mapping from each of the six pipeline stages to its recovery hierarchy. Pure data — serializable to JSON, inspectable via `--dry-run` (`primr --dry-run` includes the full recovery table).
- **Stage Classifier** (`stages.py`): Static foreground/background classification. Foreground: scraping, external search, analysis, section writing. Background: cross-validation, strategy generation.
- **Model Circuit Breaker** (`model_breaker.py`): Per-model health tracking with provider-aware fallback chains (e.g., Grok 4.20 → Grok 4.1 → Gemini Flash). Verifies API key availability before cross-provider fallback.
- **Recovery Executor** (`executor.py`): Integration glue that wraps stage callables, consults the classifier and recovery table on failure, and logs all recovery events to `_run_state.json`.
- **Integration Helpers** (`integration.py`): Thin wrappers connecting the executor to each pipeline stage at the appropriate granularity (per-page for scraping, per-section for writing, per-stage for analysis).

Run `primr --dry-run <company> <url>` to inspect the recovery table and stage classifications without executing any research.

## Security Architecture

Primr underwent comprehensive security review in January 2026. All critical vulnerabilities have been addressed.

### Security Principles

1. **Defense in Depth**: Multiple layers of validation and protection
2. **Fail Secure**: Invalid inputs rejected, not processed
3. **Least Privilege**: Minimal permissions and access
4. **Input Validation**: All external inputs validated before use

### Implemented Protections

#### SSRF (Server-Side Request Forgery) Protection

Location: `src/primr/utils/validators.py`

All HTTP requests are validated before execution to prevent internal network access:

```python
def validate_url_for_request(url: str, allow_private_ips: bool = False) -> tuple[bool, str, str | None]:
    """
    Validate URL for making external HTTP requests (SSRF protection).
    
    Blocks:
    - Internal/private IP addresses (localhost, 10.x, 192.168.x, 169.254.x, 172.16-31.x)
    - Loopback addresses (127.x.x.x, ::1)
    - Link-local addresses (169.254.x.x, fe80::/10)
    - Non-HTTP schemes (file://, ftp://, etc.)
    - Invalid URLs
    - Hostnames that resolve to private IPs (DNS rebinding protection)
    """
```

**Protected Functions** (9 total):
- `src/primr/data/scraping/http_clients.py`: `scrape_with_requests()`, `scrape_with_httpx()`, `scrape_with_curl_cffi()`
- `src/primr/data/scraping/net.py`: `make_request()`, `head_exists()`
- `src/primr/data/scraping/browsers.py`: `scrape_with_playwright()`, `scrape_with_playwright_aggressive()`, `scrape_with_drissionpage()`, `scrape_with_drissionpage_stealth()`

#### XXE (XML External Entity) Protection

Location: `src/primr/data/scraping/discovery.py`

XML parsing uses secure parser with entity expansion disabled:

```python
parser = ET.XMLParser()
parser.entity = {}  # Disable entity expansion
parser.parser.SetParamEntityParsing(0)  # Disable parameter entities
root = ET.fromstring(content, parser=parser)
```

#### Path Traversal Protection

Location: `src/primr/utils/validators.py`

File paths validated to prevent directory traversal:

```python
def validate_file_path(path: str, base_dir: str | None = None) -> tuple[bool, str]:
    """
    Validate file path to prevent directory traversal attacks.
    
    Checks for:
    - Parent directory references (..)
    - Absolute paths outside base directory
    - Invalid characters
    """
```

#### SQL Injection Protection

All database queries use parameterized statements:

```python
# Safe: Uses ? placeholders
cursor.execute("SELECT * FROM cache WHERE url = ?", (url,))

# Never: String concatenation
# cursor.execute(f"SELECT * FROM cache WHERE url = '{url}'")  # UNSAFE
```

#### Secure Hashing

MD5 usage explicitly marked as non-security:

```python
# Safe: MD5 for cache keys only, not security
hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
```

### Security Testing

Location: `tests/test_security.py`

Comprehensive test suite with 22 tests covering:

- **SSRF Protection** (11 tests): Localhost blocking, private IP blocking, link-local blocking, invalid schemes, malformed URLs
- **XXE Protection** (3 tests): Safe parsing, external entity blocking, entity reference handling
- **Path Traversal** (3 tests): Parent directory blocking, safe path validation, absolute path validation
- **Input Validation** (4 tests): Empty strings, whitespace, None handling, URL normalization
- **Security Headers** (1 test): Timeout configuration

All tests passing. Run with:
```bash
python -m pytest tests/test_security.py -v
```

### Automated Security Scanning

#### Bandit (Python Security Linter)

Configuration: `.bandit`

Results (January 2026):
- HIGH severity: 3 issues (MD5 usage) - FIXED
- MEDIUM severity: 5 issues (XML warnings, false positives) - ADDRESSED
- LOW severity: 57 issues (intentional patterns) - SUPPRESSED

#### Safety (Dependency Scanner)

Results (January 2026):
- Core dependencies: CLEAN [OK]
- Development dependencies: Some vulnerabilities (non-critical)
- Production deployment: SECURE [OK]

### Security Best Practices

1. **API Keys**: Never hardcoded, always from environment variables
2. **Secrets**: `.env.example` provided without actual secrets
3. **YAML Loading**: Always uses `yaml.safe_load()`, never `yaml.load()`
4. **File Operations**: Proper encoding, no unsafe file handling
5. **Command Execution**: No `shell=True`, no unsafe subprocess calls
6. **Error Messages**: No system information leakage

### Security Documentation

Complete security audit report: `docs/SECURITY_REVIEW_2026-01-21.md`

Includes:
- Vulnerability findings and fixes
- Security test coverage
- Automated scanning results
- Production readiness assessment
- Ongoing security recommendations

## Caching Strategy

### Memory Cache (LRU)

- Max size: 100 entries
- Thread-safe with locking
- Evicts oldest entries when full

### Disk Cache

- Location: `logs/scrape_cache/`
- TTL: 24 hours
- Format: `.txt` content + `.meta` JSON metadata
- Checked after memory cache miss

### Cache Key Generation

URLs are normalized and hashed to create cache keys:
1. Remove fragments (#)
2. Normalize path (remove trailing slashes)
3. Hash with SHA-256

## Observability

### Structured Logging

All components use the unified logger from `utils/logging_config.py`:
- Module-specific loggers (`ai.client`, `data.scrape`, etc.)
- Configurable log levels
- Structured context (correlation IDs, operation names)

### Metrics

Research operations emit metrics via `utils/observability.py`:
- Operation duration
- Success/failure status
- Section counts
- Citation counts
- Error types

### Token Usage Tracking

The AI client tracks token usage for cost monitoring:
- Input tokens per call
- Output tokens per call
- Cumulative totals
- Estimated cost calculation

## Testing Strategy

### Unit Tests

Location: `tests/`

- Mirror source structure (`test_ai/`, `test_data/`, etc.)
- Mock external dependencies (API calls, file system)
- Focus on edge cases and error handling

### Property-Based Tests

Using Hypothesis for:
- URL normalization
- Cache key generation
- Content extraction
- Type guard validation

### Integration Tests

- End-to-end scraping (with real sites)
- API integration (with mocked responses)
- Report generation pipeline

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `SEARCH_API_KEY` | Yes | Google Custom Search API key |
| `SEARCH_ENGINE_ID` | Yes | Google Custom Search Engine ID |
| `AI_RESEARCH_MODEL` | No | Override research model |
| `AI_REPORT_MODEL` | No | Override report model |
| `VERBOSE` | No | Enable verbose output |
| `DEBUG` | No | Enable debug mode |

### Configuration Classes

See `docs/CONFIG.md` for detailed configuration reference.

## Performance Characteristics

### Typical Durations

| Mode | Duration | Output Size | API Calls |
|------|----------|-------------|-----------|
| Scrape | 2-5 min | 15-20 pages | ~20 Gemini |
| Deep | 8-15 min | ~12 pages | 1 Deep Research |
| Complete | 25-40 min | 30+ pages | 1 Deep Research + 10 Gemini 3 Pro |

### Resource Usage

- Memory: ~200-500MB during scraping (Playwright browser)
- Network: Variable based on site complexity
- API calls: ~10-50 Gemini calls per research run

### Rate Limits

- Deep Research: 3 concurrent tasks (configurable)
- Scraping: Sequential with delays to avoid detection
- Gemini API: Respects 429 responses with backoff

## Future Considerations

The architecture is designed to support future enhancements without major restructuring:

- **Research State Persistence:** The section-based output format can be extended to include confidence levels and hypothesis tracking
- **Iterative Refinement:** The grading loop provides a foundation for incorporating user feedback
- **Centralized Execution:** The orchestrator pattern allows swapping local execution for remote job queues

See `ROADMAP.md` for planned features.


## Under the Hood — Quick Reference

This section provides a quick-reference summary of the retrieval engine, model pricing, and agentic architecture. For full details, see the component sections above.

### 8-Tier Retrieval Engine

Browser-first, falls back automatically:

1. Playwright (JS rendering)
2. Playwright Aggressive (accordions, lazy load)
3. curl_cffi (TLS fingerprint impersonation)
4. DrissionPage Stealth (challenge waiting)
5. DrissionPage (driverless CDP)
6. Vision (screenshot + LLM extraction)
7. httpx (HTTP/2)
8. requests (simple fallback)

Includes sticky tier memory, circuit breakers, cookie handoff, and automatic PDF detection.
Playwright tiers now perform adaptive lazy-load scrolling (up to 20 steps by default, stops early when page height stabilizes).

### Models & Pricing

| Model | Role | Pricing (per 1M tokens) |
|-------|------|-------------------------|
| Grok 4.1 | Default mode: analysis, writing, strategy | $0.20 in / $0.50 out |
| Grok 4.20 | `--grok-tier hybrid/max`: reasoning and/or writing | $2.00 in / $6.00 out |
| Gemini 3 Flash | Scraping, link selection, QA | $0.50 in / $3 out |
| Gemini 3.1 Pro | `--premium` mode: section writing, analysis | $2/$12 (≤200k) · $4/$18 (>200k) |
| Deep Research Agent | `--premium` mode: autonomous research | ~$2.50/task (flat) |

### Why Grok 4.1 is the Default

Primr originally ran everything through Google's Deep Research API + Gemini 3.1 Pro — excellent research quality, but the Deep Research API runs ~$2.50 per task, pushing full runs to ~$5 and 50-75 minutes. When xAI released Grok 4.1, testing showed it handles company research comparably: strong at search-grounded analysis, solid structured output, and reliable citation handling. Switching the default pipeline to Grok 4.1 dropped costs to ~$0.55 (~90% cheaper) and runtime to ~35-50 minutes with similar report quality. Gemini Flash is still used for scraping in both modes. The full Gemini + Deep Research pipeline remains available via `--premium` when maximum research depth justifies the cost.

### Agentic Architecture

- Hypothesis tracking with confidence levels across sessions
- Subagents for scraping, analysis, writing, and QA
- Hook system for governance (cost limits, quality gates)
- Research memory that persists and evolves
