# Primr

A research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

## What It Does

Primr runs company research using complementary engines:

**Scrape Mode**: Website scraping with LLM-powered link selection. Browser-first discovery handles JS-heavy sites, then the LLM picks the most valuable pages (leadership, products, news, investors). Reader-mode extraction pulls clean content, with quality validation to catch garbage pages. Vision tier fallback uses screenshots + LLM for image-heavy pages. 5-10 min, ~$0.01-0.05.

**Deep Mode**: Uses the Accordion Method - Deep Research gathers facts, then Gemini Flash writes each section with analysis. No website scraping, relies on web research. 8-15 min, ~$0.80-1.00.

**Full Mode** (default): Combines both for the most complete picture. 25-40 min, ~$0.80-1.50.

All modes produce TXT and DOCX reports with optional AI strategy recommendations.

<p align="center">
  <img src="docs/images/primr-demo.png" alt="Primr CLI demo" width="700">
</p>

**Example Output**: See sample reports in [docs/examples/](docs/examples/)

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd primr
python setup_env.py

# Run research
primr "Acme Corp" https://acme.com
```

## Usage

```bash
# Basic usage
primr "Tesla" https://tesla.com

# Research modes
primr "Tesla" https://tesla.com --mode scrape    # Website only
primr "Tesla" https://tesla.com --mode deep      # Web research only
primr "Tesla" https://tesla.com --mode full      # Both (default)

# AI strategy with cloud vendor
primr "Tesla" https://tesla.com --cloud-vendor azure

# Options
primr "Tesla" https://tesla.com --dry-run    # Cost estimate only
primr "Tesla" https://tesla.com --verbose    # Detailed output
primr "Tesla" https://tesla.com --no-qa      # Skip quality assessment

# Batch mode
primr --csv companies.csv

# System check
primr doctor
```

## Configuration

Required API keys in `.env`:
```
GEMINI_API_KEY=       # Google AI API key
SEARCH_API_KEY=       # Google Custom Search API key
SEARCH_ENGINE_ID=     # Google Custom Search Engine ID
```

See [docs/CONFIG.md](docs/CONFIG.md) for full configuration reference.

## Intended Use

Primr outputs are for internal research and go-to-market preparation - not client-ready deliverables. The goal is understanding how a company creates value and where support could help them move faster.

Reports surface hypotheses to validate in conversation. Treat strong claims as working hypotheses unless explicitly supported by cited sources.

## Known Limitations

- Deep Research API produces ~8-12 pages max per call (worked around with Accordion Method)
- Some sites with aggressive WAF block all automated access - use Deep Mode for coverage
- Deep Research occasionally hangs - if it exceeds 20 minutes, cancel and retry
- Vision tier uses LLM API calls for extraction (~$0.01-0.02 per page)

## Documentation

- [ROADMAP.md](ROADMAP.md) - Development roadmap
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture, scraping tiers, resilience features
- [docs/API.md](docs/API.md) - Programmatic usage
- [docs/CONFIG.md](docs/CONFIG.md) - Configuration reference
- [docs/INTERNALS.md](docs/INTERNALS.md) - Prompt engineering and algorithms

## License

MIT
