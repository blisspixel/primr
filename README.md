# Primr

A research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

## What It Does

Primr runs company research using two complementary engines:

**Scrape Mode**: Website-focused research with multi-tier web scraping (requests, httpx, Playwright, aggressive browser), section-by-section AI analysis with quality grading. Useful for deep website analysis and specific data extraction.

**Deep Mode**: Powered by Gemini Deep Research Agent with autonomous multi-step research and built-in Google Search. Useful for broad market analysis, competitive intelligence, and industry trends.

Both engines produce DOCX/PDF reports with optional AI strategy recommendations.

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
primr doctor          # System check
primr --check-jobs    # Pending Deep Research jobs
primr --check-quota   # API quota status
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
| Full | `--mode full` (default) | Most comprehensive | 30-40 min |
| Scrape | `--mode scrape` | Website deep-dives | 20-25 min |
| Deep | `--mode deep` | Market analysis | 10-15 min |

## Project Structure

```
primr/
├── src/primr/              # Main package
│   ├── core/               # Research orchestration
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

# Current test count: 1900+ tests
```

## Known Limitations

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
