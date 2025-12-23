# Primr

A research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

## What It Does

Primr runs company research using complementary engines that work together:

**Scrape Mode**: Website-focused research with multi-tier web scraping (requests, httpx, Playwright, aggressive browser), section-by-section AI analysis with quality grading. Useful for deep website analysis and specific data extraction.

**Deep Mode**: Uses the Accordion Method - Deep Research gathers facts, then Gemini Flash writes each section with proper analysis and implications. No website scraping, relies entirely on web research.

**Full Mode** (recommended): Combines both engines:
1. **Data Collection**: Website scraping + Google Search (baseline facts)
2. **Research Dossier**: Deep Research gathers external context
3. **Section Writing**: Gemini Flash writes sections with full context

All modes produce DOCX/PDF reports with optional AI strategy recommendations.

## Quality Assurance

Primr includes an integrated Quality Assurance (QA) system that automatically evaluates report quality:

**Automatic QA Analysis**: Every generated report is automatically assessed for:
- **Citation Accuracy**: Proper attribution and source consistency
- **Logical Consistency**: Internal coherence and reasoning quality  
- **Completeness**: Coverage of expected sections and topics
- **Confidence Assessment**: Reliability of claims and evidence

**Clean CLI Output**: Simple grade display with actionable feedback:
```bash
primr "Tesla" https://tesla.com
# ... research process ...
# Assessing quality...
# Grade: (87/100)
```

**Detailed Analysis**: Comprehensive QA reports saved automatically with:
- Section-by-section scoring
- Specific issue identification and suggestions
- Improvement recommendations
- Historical quality tracking

**QA Commands**:
```bash
primr --qa "Tesla"           # View detailed QA analysis
primr --qa-recent 5          # Show QA summary for recent reports
primr "Tesla" --no-qa        # Skip QA analysis
```

The QA system helps maintain consistent report quality and identifies areas for improvement without disrupting the research workflow.

## Intended Use

Primr outputs are designed for internal research, go-to-market preparation, and strategic sensemaking. They are not written as client-ready deliverables. The goal is to understand how a company creates value and where support could help them move faster, reduce risk, or unlock opportunities.

**What makes Primr output useful:**
- Coherent strategic thesis that ties the analysis together
- Hypothesis-driven framing (not declarative pronouncements)
- Specific evidence with citations (not generic observations)
- Framework sections (SWOT, Porter's, Value Chain) applied rigorously
- "Where They're Likely to Say Yes" section connecting analysis to engagement opportunities

**Calibration notes:**
- Observations are framed as hypotheses to validate in conversation
- Numeric claims use appropriate precision (ranges for estimates, exact figures only from filings)
- Competitive comparisons use directional language ("materially faster") not precise multiples
- Each insight lives in one section - no repetition across SWOT, Tensions, Patterns, etc.

Reports may surface aggressive or uncomfortable hypotheses. Treat strong claims as working hypotheses unless explicitly supported by cited sources. Downstream teams should translate insights into materials appropriate for external audiences.

## Quick Start

```bash
# Clone and install (private repo - requires access)
git clone https://github.com/blisspixel/primr.git
cd primr
pip install -e .

# Configure API keys in .env
GEMINI_API_KEY=your_gemini_api_key
SEARCH_API_KEY=your_google_search_api_key
SEARCH_ENGINE_ID=your_google_cse_id

# Check setup
primr doctor

# Run research
primr "Acme Corp" https://acme.com
```

## Usage

```bash
# Basic usage (company name and website required)
primr "Tesla" https://tesla.com
primr "Tesla" tesla.com           # https:// added automatically
primr "Tesla" www.tesla.com       # www. handled correctly

# Research modes
primr "Tesla" https://tesla.com --mode scrape    # Website scraping only
primr "Tesla" https://tesla.com --mode deep      # Autonomous web research
primr "Tesla" https://tesla.com --mode full      # Both sequential (default)

# AI strategy with cloud vendor
primr "Tesla" https://tesla.com --cloud-vendor azure
primr "Tesla" https://tesla.com --cloud-vendor aws
primr "Tesla" https://tesla.com --cloud-vendor gcp
primr "Tesla" https://tesla.com --no-ai-strategy

# Strategy modules (v1.2.6)
primr "Tesla" https://tesla.com --strategy ai              # AI strategy only
primr "Tesla" https://tesla.com --strategy ai,cloud,data   # Multiple strategies
primr "Tesla" https://tesla.com --strategy-only --context-folder output/  # Run on existing research
primr --list-strategies                                     # Show available strategies

# Citation styles
primr "Tesla" https://tesla.com --citation-style numbered  # [1] style (default)
primr "Tesla" https://tesla.com --citation-style inline    # preserve URLs
primr "Tesla" https://tesla.com --citation-style sidecar   # separate sources file

# Batch mode
primr --csv companies.csv

# Options
primr "Tesla" https://tesla.com --confirm    # Ask for confirmation first
primr "Tesla" https://tesla.com --dry-run    # Cost estimate only
primr "Tesla" https://tesla.com --verbose    # Detailed output
primr "Tesla" https://tesla.com --quiet      # Minimal output

# Utility commands
primr doctor            # System check
primr --check-jobs      # Pending Deep Research jobs
primr --check-quota     # API quota status
primr --list-strategies # Available strategy modules
```

### URL Handling

Primr accepts URLs in multiple formats:
- `https://company.com` (full URL)
- `http://company.com` (HTTP URLs accepted)
- `company.com` (bare domain, https:// added)
- `www.company.com` (www prefix handled)

Company names with `.com` in them work fine since the company name and website are separate arguments.

### System Check

```bash
primr doctor
```

Output:
```
Primr - System Check
====================

[pass] Python 3.10+
[pass] GEMINI_API_KEY configured
[pass] SEARCH_API_KEY configured
[pass] SEARCH_ENGINE_ID configured
[pass] Playwright browsers installed
[pass] API quota available
[pass] Output directory writable

All systems ready.
```

### Research Modes

| Mode | Flag | Best For | Duration |
|------|------|----------|----------|
| Full | `--mode full` (default) | Most comprehensive - scraping + Accordion Method | 35-50 min |
| Scrape | `--mode scrape` | Website deep-dives, no Deep Research API | 20-25 min |
| Deep | `--mode deep` | Web research only - Accordion Method | 15-25 min |

## Project Structure

```
primr/
├── src/primr/              # Main package
│   ├── core/               # Research orchestration
│   │   ├── research_agent.py       # Main entry point, backward-compatible API
│   │   ├── workspace.py            # Working folder management
│   │   ├── structured_research.py  # Website scraping pipeline
│   │   ├── vendor_research.py      # Cloud vendor AI research
│   │   ├── ai_strategy.py          # AI strategy generation
│   │   ├── deep_research_runner.py # Deep Research execution
│   │   └── cli.py                  # Command-line interface
│   ├── data/               # Data collection (scraping, search)
│   ├── ai/                 # AI operations (LLM, grading)
│   ├── output/             # Report generation
│   ├── config/             # Configuration
│   └── utils/              # Utilities
├── tests/                  # Test suite
├── pyproject.toml          # Package config
└── requirements.txt        # Dependencies
```

## Configuration

### Required API Keys (.env)
```
GEMINI_API_KEY=       # Google AI API key
SEARCH_API_KEY=       # Google Custom Search API key
SEARCH_ENGINE_ID=     # Google Custom Search Engine ID
```

### Optional Settings
```
AI_RESEARCH_MODEL=gemini-2.0-flash   # Override research model
AI_REPORT_MODEL=gemini-2.0-flash     # Override report model
VERBOSE=true                          # Enable debug output
```

See [docs/CONFIG.md](docs/CONFIG.md) for full configuration reference.

## Output Files

```
output/
├── {Company}_Company_Overview.txt
├── {Company}_Company_Overview.docx
├── {Company}_Company_Overview.pdf
└── {Company}_research_{date}.zip

working/{Company}/
├── scraped_website_summary.txt
├── value_theory.txt
└── {section}.txt
```

Note: Output artifacts are analysis-first. When reusing content externally, teams should reframe conclusions, remove emotionally loaded phrasing, and retain only claims supported by citations.

## Installation

```bash
# From source (private repo - requires access)
git clone https://github.com/blisspixel/primr.git
cd primr
pip install -e .

# Verify
primr doctor
```

## Development

```bash
# Run all tests
pytest tests/ -v

# Run fast tests only (skip slow/integration)
pytest tests/ -v -m "not slow and not integration"

# Run smoke tests (quick CLI validation)
pytest tests/ -v -m smoke

# Run resilience tests (API retry/fallback)
pytest tests/ -v -m resilience
```

## Deep Research API Limitation (December 2025)

Google's Gemini Deep Research Agent (`deep-research-pro-preview-12-2025`) is excellent at autonomous research but compresses output to ~8-12 pages per API call, regardless of prompt instructions. It gathers information thoroughly but writes in a dense, compressed style.

**The Accordion Method:** Primr uses a two-phase approach to produce better-written reports:

1. **Phase 1 - Research Dossier**: Deep Research gathers facts as "Lead Researcher" - thorough research, compressed output (~8-12 pages of dense facts with citations)

2. **Phase 2 - Section Writing**: Gemini Flash takes each section and writes it out properly - with analysis, implications, and strategic connections. Quality over quantity - each section is as long as the content needs, no more.

The key insight: Deep Research is the **researcher** (gathers facts), Gemini Flash is the **writer** (produces prose). The result is naturally longer because it's better written - facts are explained, implications are drawn out, connections are made explicit.

**Quality calibration:**
- Observations use humble, exploratory language ("This suggests...", "Worth validating...")
- Framework sections (SWOT, Porter's, Value Chain) apply structured analysis rigorously
- Each insight lives in ONE section - no repetition across multiple analytical frameworks
- Numeric precision matches source confidence (ranges for estimates, exact figures from filings)

**Resilience:** If Deep Research fails (500 errors, rate limits), the pipeline falls back to Stage 1 context and continues with section writing.

**Mode comparison:**
- `--mode deep`: Accordion Method (web research only, no scraping)
- `--mode scrape`: Website scraping + Gemini Flash (~15-20 pages, no Deep Research API)
- `--mode full`: Stage 1 scraping + Accordion Method (most comprehensive)

## Known Limitations

- Deep Research API produces ~8-12 pages max per call (see above)
- Some sites with aggressive bot protection may not be scrapable
- API rate limits apply (Google Search, Gemini)
- PDF generation requires Microsoft Word on Windows
- Long operations (10-40 minutes) require patience. Progress feedback is provided but operations cannot be paused

## Documentation

- [ROADMAP.md](ROADMAP.md) - Development roadmap and vision
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture and design
- [docs/API.md](docs/API.md) - Programmatic usage reference
- [docs/QA_CONFIGURATION.md](docs/QA_CONFIGURATION.md) - QA system configuration guide
- [docs/QA_USAGE_EXAMPLES.md](docs/QA_USAGE_EXAMPLES.md) - QA usage examples and best practices
- [docs/CONFIG.md](docs/CONFIG.md) - Configuration reference
- [docs/INTERNALS.md](docs/INTERNALS.md) - Prompt engineering and algorithms
- [docs/GLOSSARY.md](docs/GLOSSARY.md) - Term definitions
- [docs/DECISIONS.md](docs/DECISIONS.md) - Design decision records
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) - Contribution guide

## License

MIT
