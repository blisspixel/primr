# Primr

A research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

## What It Does

Primr runs company research using complementary engines that work together:

**Scrape Mode**: Website scraping with intelligent link selection and insight extraction. Uses multi-tier scraping (requests, httpx, Playwright) to handle different site types. Outputs to working folder for downstream use. Fast (2-5 min) and cheap (about $0.01).

**Deep Mode**: Uses the Accordion Method - Deep Research gathers facts, then Gemini Flash writes each section with analysis and implications. No website scraping, relies on web research.

**Full Mode** (default): Combines both engines for the most complete picture:
1. **Data Collection**: Website scraping + Google Search (baseline facts)
2. **Research Dossier**: Deep Research gathers external context
3. **Section Writing**: Gemini Flash writes sections with full context

All modes produce TXT and DOCX reports with optional AI strategy recommendations.

<p align="center">
  <img src="docs/images/primr-demo.png" alt="Primr CLI demo" width="700">
</p>

**Example Output**: See sample reports in [docs/examples/](docs/examples/):
- [Strategic Overview](docs/examples/Softchoice,%20a%20World%20Wide%20Technology%20company_Strategic_Overview_12-23-2025.docx) - Full company research report
- [AI Strategy](docs/examples/Softchoice,%20a%20World%20Wide%20Technology%20company_AI_Strategy_12-23-2025.docx) - Cloud vendor AI recommendations

## Quality Assurance

Primr includes a QA system that evaluates report quality:

**Automatic QA Analysis**: Reports are assessed for:
- **Citation Accuracy**: Proper attribution and source consistency
- **Logical Consistency**: Internal coherence and reasoning quality  
- **Completeness**: Coverage of expected sections and topics
- **Confidence Assessment**: Reliability of claims and evidence

**Clean CLI Output**: Simple grade display:
```bash
primr "Tesla" https://tesla.com
# ... research process ...
# Assessing quality...
# Grade: (87/100)
```

**Detailed Analysis**: QA reports saved to `output/` with:
- Overall assessment and confidence level
- Strengths and areas for improvement  
- Specific recommendations
- Historical quality tracking via monitoring logs

**QA Integration**: Quality assessment runs automatically after each report. Use `--no-qa` to skip or `--verbose` for detailed feedback.

The QA system helps identify areas for improvement. It's not perfect - treat grades as directional, not absolute.

## Intended Use

Primr outputs are designed for internal research, go-to-market preparation, and strategic sensemaking. They're not client-ready deliverables - the goal is to understand how a company creates value and where support could help them move faster.

**What makes output useful:**
- Coherent strategic thesis tying the analysis together
- Hypothesis-driven framing (not declarative pronouncements)
- Specific evidence with citations (not generic observations)
- Framework sections (SWOT, Porter's, Value Chain) applied with structure
- "Where They're Likely to Say Yes" section connecting analysis to engagement opportunities

**Calibration notes:**
- Observations are framed as hypotheses to validate in conversation
- Numeric claims use appropriate precision (ranges for estimates, exact figures only from filings)
- Competitive comparisons use directional language ("materially faster") not precise multiples
- Each insight lives in one section - no repetition across SWOT, Tensions, Patterns, etc.

Reports may surface aggressive or uncomfortable hypotheses. Treat strong claims as working hypotheses unless explicitly supported by cited sources. Downstream teams should translate insights into materials appropriate for external audiences.

## Quick Start

```bash
# Clone the repo
git clone <repo-url>
cd primr

# Run setup (installs everything, configures API keys, verifies)
python setup_env.py

# Run research
primr "Acme Corp" https://acme.com
```

On Windows, if `primr` isn't recognized, use `python -m primr` instead (or run `primr.cmd` from the repo directory).

The setup script walks you through getting the required API keys from Google.

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
primr "Tesla" https://tesla.com --verbose    # Detailed output (includes QA details)
primr "Tesla" https://tesla.com --quiet      # Minimal output
primr "Tesla" https://tesla.com --no-qa      # Skip quality assessment

# Utility commands
primr doctor            # System check
primr --check-jobs      # Pending Deep Research jobs
primr --check-quota     # API quota status
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

| Mode | Flag | Best For | Duration | Cost |
|------|------|----------|----------|------|
| Scrape | `--mode scrape` | Quick website intel, data collection | 2-5 min | about $0.01 |
| Deep | `--mode deep` | Web research only, Accordion Method | 8-15 min | about $0.80-1.00 |
| Full | `--mode full` (default) | Most comprehensive, scraping + Accordion | 25-40 min | about $0.80-1.50 |

Duration and cost vary based on website size and content complexity. Costs assume current free search grounding (ends Jan 5, 2026). After that date, add ~$0.35-$1.05 per report for search queries. Use `--dry-run` for estimates.

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
AI_FAST_MODEL=gemini-3-flash-preview     # Override Flash model (cheap, fast)
AI_REASONING_MODEL=gemini-3-pro-preview  # Override Pro model (expensive, smart)
VERBOSE=true                              # Enable debug output
```

### AI Models and Pricing

Primr uses Gemini 3 models via Vertex AI. Model assignments are centralized in `src/primr/config/models.py`.

**Model Pricing (December 2025)**

| Model | Role | Input | Output |
|-------|------|-------|--------|
| `gemini-3-flash-preview` | Scraping, QA, link selection | $0.50/1M tokens | $3.00/1M tokens |
| `gemini-3-pro-preview` | Section writing, analysis | $2.00/1M tokens | $12.00/1M tokens |
| `deep-research-pro-preview` | Autonomous web research | $2.00/1M tokens | $12.00/1M tokens |

**Why reports are cheap right now (about $0.80-1.50 each)**

The Accordion Method keeps costs low:
- Deep Research phase: about $0.70-0.80 (reading web pages + generating dossier)
- Writer phase (Flash): about $0.10 (reading dossier + writing 50 pages)

Search grounding is currently free until January 5, 2026. After that date, Google charges $35 per 1,000 search queries ($0.035/query). Typical reports trigger 10-30 searches, adding $0.35-$1.05 per report. Actual search counts are visible in the API response via `groundingMetadata.webSearchQueries` - don't confuse "thinking steps" (billed as output tokens) with "search queries" (billed separately).

**Task-specific model assignments:**
- `SCRAPING_MODEL` = Flash (summarizing scraped content)
- `LINK_SELECTION_MODEL` = Flash (intelligent link prioritization)
- `QA_MODEL` = Flash (quality checks)
- `SECTION_WRITING_MODEL` = Pro (writing report sections)
- `ANALYSIS_MODEL` = Pro (complex reasoning)

When new models release, update `src/primr/config/models.py` once and all code uses the new models.

See [docs/CONFIG.md](docs/CONFIG.md) for full configuration reference.

## Output Files

```
output/
├── {Company}_Strategic_Overview.txt
├── {Company}_Strategic_Overview.docx
├── {Company}_QA_Report_{timestamp}.txt     # Quality assessment details
└── {Company}_research_{date}.zip

working/{Company}/
├── scraped_website_summary.txt
├── value_theory.txt
└── {section}.txt

logs/qa/                                    # QA monitoring logs
├── qa_metrics.json                         # Performance metrics
└── qa_assessments.jsonl                    # Assessment history
```

Note: Output artifacts are analysis-first. When reusing content externally, teams should reframe conclusions, remove emotionally loaded phrasing, and retain only claims supported by citations.

## Installation

```bash
# From source (private repo - requires access)
git clone <repo-url>
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

Google's Gemini Deep Research Agent (`deep-research-pro-preview-12-2025`) does autonomous research but compresses output to 8-12 pages per API call, regardless of prompt instructions. It gathers information but writes in a dense, compressed style.

**The Accordion Method:** Primr uses a two-phase approach to work around this:

1. **Phase 1 - Research Dossier**: Deep Research gathers facts as "Lead Researcher" - compressed output (8-12 pages of dense facts with citations)

2. **Phase 2 - Section Writing**: Gemini Flash takes each section and writes it out - with analysis, implications, and strategic connections.

The idea: Deep Research is the **researcher** (gathers facts), Gemini Flash is the **writer** (produces prose). The result is longer because facts are explained, implications drawn out, connections made explicit.

**Quality calibration:**
- Observations use exploratory language ("This suggests...", "Worth validating...")
- Framework sections (SWOT, Porter's, Value Chain) apply structured analysis
- Each insight lives in ONE section - no repetition across frameworks
- Numeric precision matches source confidence (ranges for estimates, exact figures from filings)

**Resilience:** If Deep Research fails (500 errors, rate limits), the pipeline falls back to Stage 1 context and continues with section writing.

**Mode comparison:**
- `--mode scrape`: Website scraping + insight extraction (about 2-5 min, about $0.01)
- `--mode deep`: Accordion Method, web research only (about 8-15 min, about $0.80-1.00)
- `--mode full`: Stage 1 scraping + Accordion Method (about 25-40 min, about $0.80-1.50)

## Known Limitations

- Deep Research API produces ~8-12 pages max per call (see above)
- Some sites with aggressive bot protection may not be scrapable
- API rate limits apply (Google Search, Gemini)
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
