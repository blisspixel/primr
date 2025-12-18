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
    │  (20-25m)   │        │  (10-15m)   │        │  (30-40m)   │
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

### Scrape Mode

Website-focused research using a 4-tier scraping strategy with AI-powered section extraction.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Scrape Mode Pipeline                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     4-Tier Scraping Engine                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │Requests │─▶│  httpx  │─▶│ Playwright  │─▶│Playwright Aggress.│  │
│  │ (fast)  │  │ (HTTP/2)│  │  (stealth)  │  │   (full evasion)  │  │
│  └─────────┘  └─────────┘  └─────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Link Discovery & Scoring                        │
│              (Prioritize high-value pages: /about, /team, etc.)     │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Section-by-Section Extraction                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Company    │  │   Products   │  │  Leadership  │  ... (18)    │
│  │   Overview   │  │  & Services  │  │   & Team     │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Quality Grading Loop                          │
│         (Grade each section, trigger refinement if < 80/100)        │
└─────────────────────────────────────────────────────────────────────┘
```

**When to use:** Deep website analysis, specific data extraction, when the company website is the primary source of truth.

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

Two-phase architecture combining both engines for comprehensive 40+ page reports.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Complete Mode: Recursive Hierarchical             │
│                         Research Architecture                        │
└─────────────────────────────────────────────────────────────────────┘

Phase 0: Data Collection (15-25 min)
┌─────────────────────────────────────────────────────────────────────┐
│                      Structured Pipeline                             │
│         (Full website scraping + Google search + AI analysis)       │
│                              │                                       │
│                              ▼                                       │
│                    Context File Generation                           │
│              (Baseline facts for all subsequent phases)             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
Phase 1: Planning (1-2 min)
┌─────────────────────────────────────────────────────────────────────┐
│                       Master Architect                               │
│                    (gemini-2.0-flash)                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Input: Context summary from Phase 0                         │   │
│  │  Output: 10-chapter plan with research prompts               │   │
│  │  Each chapter: title, detailed instructions, expected pages  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
Phase 2: Parallel Execution (15-20 min)
┌─────────────────────────────────────────────────────────────────────┐
│                   Research Node Executor                             │
│              (Max 3 concurrent Deep Research tasks)                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                             │
│  │ Ch 1-3  │  │ Ch 4-6  │  │ Ch 7-10 │  (batched by concurrency)   │
│  │ parallel│  │ parallel│  │ parallel│                             │
│  └─────────┘  └─────────┘  └─────────┘                             │
│                              │                                       │
│                    File Search Store                                 │
│         (Shared context from Phase 0, accessible to all nodes)      │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
Phase 3: Aggregation (1-2 min)
┌─────────────────────────────────────────────────────────────────────┐
│                      Report Aggregator                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  - Concatenate chapters in order                             │   │
│  │  - Generate table of contents                                │   │
│  │  - Consolidate citations                                     │   │
│  │  - Handle missing chapters gracefully                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Hierarchy of Truth:** The Complete Mode establishes a clear precedence for information:
1. Company Facts (from Phase 0 scraping): highest authority
2. External Context (from Phase 2 web search): market conditions, competitive intel
3. Synthesis: integrated analysis combining both sources

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
    "Tesla",
    "https://tesla.com",
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
| `vendor_research.py` | Cloud vendor AI capabilities research (AWS, Azure, GCP) |
| `ai_strategy.py` | AI strategy generation with cloud vendor context |
| `deep_research_runner.py` | Deep Research execution with preflight validation |
| `cli.py` | Command-line interface, argument parsing, utility commands |

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

### 4-Tier Scraping Engine

Location: `src/primr/data/scrape.py`

A tiered fallback system for web scraping, designed to handle increasingly aggressive bot protection.

| Tier | Method | Use Case | Speed |
|------|--------|----------|-------|
| 1 | requests | Simple sites, no JS | Fast |
| 2 | httpx | HTTP/2 sites, better headers | Fast |
| 3 | Playwright | JS-rendered content | Medium |
| 4 | Playwright Aggressive | Bot-protected sites | Slow |

Each tier includes:
- Randomized browser fingerprints (4 profiles: Windows Chrome, Mac Chrome, Windows Firefox, Mac Safari)
- Stealth scripts to evade detection
- Cookie banner dismissal
- Soft block detection

**Soft Block Detection:** The scraper identifies when a site has blocked the request without returning an error (captchas, "please enable JavaScript", Cloudflare challenges). When detected, it escalates to the next tier.

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
    "Research Tesla's competitive position",
    output_format="company_profile",
    priority_urls=["https://tesla.com"]
)
```

### Master Architect

Location: `src/primr/ai/report_architect.py`

Decomposes comprehensive reports into chapters using gemini-2.0-flash for fast, cost-effective planning.

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

Sections scoring below the threshold (default: 80) trigger additional research refinement.

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

### Complete Mode Data Flow

```
Company Name + URL
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 0: Structured Pipeline                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Scraping   │─▶│  Section    │─▶│  Context    │             │
│  │  Engine     │  │  Extraction │  │  File Gen   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  File Search Store Upload                                        │
│  (Context accessible to all Deep Research nodes)                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: Master Architect                                       │
│  ┌─────────────┐  ┌─────────────┐                               │
│  │  Context    │─▶│  Chapter    │                               │
│  │  Summary    │  │  Plan (10)  │                               │
│  └─────────────┘  └─────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: Parallel Execution                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ... (10 chapters)      │
│  │ Deep    │  │ Deep    │  │ Deep    │                          │
│  │Research │  │Research │  │Research │  (3 concurrent max)      │
│  └─────────┘  └─────────┘  └─────────┘                          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: Aggregation                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Chapter    │─▶│  TOC        │─▶│  Citation   │             │
│  │  Concat     │  │  Generation │  │  Consolidate│             │
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
│   ├── scrape.py            # 4-tier scraping engine
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
    ├── errors.py            # Error types and retry logic
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

| Mode | Duration | Output Size |
|------|----------|-------------|
| Scrape | 20-25 min | 15-20 pages |
| Deep | 10-15 min | 8-12 pages |
| Complete | 30-40 min | 40-50 pages |

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
