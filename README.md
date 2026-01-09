# Primr

A research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

Primr combines first-party website content (site corpus) with validated external sources (deep research) to produce a structured company brief.

## What It Does

Primr runs company research through a single unified pipeline. Modes control how much of the pipeline runs - they are NOT separate implementations.

### The Pipeline

```
[Build Site Corpus] → [Extract Insights] → [Deep Research] → [Write Report]
         ↓                    ↓                   ↓                ↓
    corpus files         insights.txt        dossier.txt      report.docx
```

**Stage outputs:**
- **Build Site Corpus**: `_raw_scrapes/` (individual page text), `scraped_content.txt` (combined corpus), `_external_links.txt` (discovered external URLs; recorded as metadata, not scraped in scrape mode)
- **Extract Insights**: `insights.txt` (LLM-compressed facts from corpus)
- **Deep Research**: `dossier.txt` (LLM analysis using external sources to validate/augment)
- **Write Report**: `report.docx` (final formatted deliverable)

### Modes (same code, different stopping points)

| Mode | What Runs | Time | Cost |
|------|-----------|------|------|
| `--mode scrape` | Build Site Corpus + Extract Insights | 5-10 min | ~$0.01-0.05 |
| `--mode deep` | Deep Research only (external sources; uses provided URL as research anchor; no site corpus build) | 8-15 min | ~$0.80-1.00 |
| `--mode full` | Full pipeline (default) | 25-40 min | ~$0.80-1.50 |

### Key Point

There is ONE site-to-corpus function: `fetch_web_content()` (aka `build_site_corpus`) in `src/primr/data/scrape.py`. It discovers in-scope URLs, selects pages, scrapes them with tier escalation, and saves results incrementally. All modes that build a corpus use this same function. No other function should implement a site discovery + scrape loop.

Scrape mode stops after insights; full mode continues through deep research and report generation. In all modes, the provided URL is the canonical target identifier (used for domain scoping, deduping, and source attribution).

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
primr "Acme Corp" https://acme.example
```

## Usage

```
primr "<company_label>" <company_website_url> [options]
```

The first argument is a display label used in output paths and headings; scraping scope is determined by the website URL host. The website URL is always required. It defines the research target (canonical domain) and is used for scoping, link discovery, and as a seed for external research.

```bash
# Basic usage
primr "Acme Corp" https://acme.example

# Research modes
primr "Acme Corp" https://acme.example --mode scrape    # Site corpus + insights (multi-page)
primr "Acme Corp" https://acme.example --mode deep      # Deep research only (no site corpus build)
primr "Acme Corp" https://acme.example --mode full      # Full pipeline (default)

# AI strategy with cloud vendor
primr "Acme Corp" https://acme.example --cloud-vendor azure

# Options
primr "Acme Corp" https://acme.example --dry-run    # Cost estimate only
primr "Acme Corp" https://acme.example --verbose    # Detailed output
primr "Acme Corp" https://acme.example --no-qa      # Skip quality assessment

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
