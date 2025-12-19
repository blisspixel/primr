# Primr

A research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

## What It Does

Primr runs company research using complementary engines that work together:

**Scrape Mode**: Website-focused research with multi-tier web scraping (requests, httpx, Playwright, aggressive browser), section-by-section AI analysis with quality grading. Useful for deep website analysis and specific data extraction. Produces ~15-20 page reports.

**Deep Mode**: Powered by Gemini Deep Research Agent with autonomous multi-step research and built-in Google Search. Generates a comprehensive company profile. Produces ~12 page reports.

**Full Mode** (recommended): Combines both engines using the "Accordion Method" for comprehensive 30+ page reports:
1. **Data Collection**: Website scraping + Google Search (baseline facts)
2. **Research Dossier**: Deep Research gathers external context (as Lead Researcher, not Writer)
3. **Section Writing**: Gemini 3 Flash writes sections sequentially with context continuity

All modes produce DOCX/PDF reports with optional AI strategy recommendations.

## Intended Use

Primr outputs are designed for internal research, go-to-market preparation, and strategic sensemaking. They are not written as client-ready deliverables. The goal is to understand how a company creates value and where support could help them move faster, reduce risk, or unlock opportunities.

Reports may:
- Surface aggressive or uncomfortable hypotheses
- Compress competitive or regulatory risk into direct language for internal discussion
- Prioritize analytical clarity over diplomatic tone

Treat strong claims as working hypotheses unless explicitly supported by cited sources. Downstream teams should translate insights into materials appropriate for external audiences.

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

| Mode | Flag | Best For | Duration | Output |
|------|------|----------|----------|--------|
| Full | `--mode full` (default) | Most comprehensive - Accordion Method | 35-50 min | 30+ pages |
| Scrape | `--mode scrape` | Website deep-dives, no Deep Research API | 20-25 min | 15-20 pages |
| Deep | `--mode deep` | Quick research via Deep Research API | 10-15 min | ~12 pages |

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
# Run tests
pytest tests/ -v
```

## Deep Research API Limitation (December 2025)

Google's Gemini Deep Research Agent (`deep-research-pro-preview-12-2025`) is excellent at autonomous research but has a practical output limit of ~8-12 pages per API call, regardless of how many pages you request in the prompt.

**Why this matters:** If you ask Deep Research for a "30-page report," it will produce ~8-12 pages of high-quality, well-structured content with citations. It gathers information thoroughly but compresses the output.

**The Accordion Method (Full Mode):** To produce 30+ page reports, Primr uses a multi-phase approach:

1. **Phase 1 - Data Collection**: Website scraping + Google Search + Gemini Flash analysis creates baseline facts (~15-25 min)
2. **Phase 2 - Research Dossier**: Deep Research acts as "Lead Researcher" gathering external context. This produces the ~12 page research dossier with citations.
3. **Phase 3 - Section Writing**: Gemini 3 Flash writes each section one-by-one, passing the dossier and previous sections in each prompt for context continuity.

This architecture treats Deep Research as the **researcher** (gathers facts) and Gemini 3 Flash as the **writer** (produces prose). The result is comprehensive 30+ page reports that avoid the "middle muddle" problem where pages 10-40 become vague and repetitive.

**Resilience:** If Deep Research fails (500 errors, rate limits), the pipeline falls back to using Stage 1 context as the research dossier and continues with section writing.

**Mode comparison:**
- `--mode deep`: Single Deep Research call → ~12 pages (fast, good for quick scans)
- `--mode scrape`: Website scraping + Gemini Flash → ~15-20 pages (no Deep Research API)
- `--mode full`: Accordion Method → 30+ pages (recommended for comprehensive research)

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
- [docs/CONFIG.md](docs/CONFIG.md) - Configuration reference
- [docs/INTERNALS.md](docs/INTERNALS.md) - Prompt engineering and algorithms
- [docs/GLOSSARY.md](docs/GLOSSARY.md) - Term definitions
- [docs/DECISIONS.md](docs/DECISIONS.md) - Design decision records
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) - Contribution guide

## License

MIT
