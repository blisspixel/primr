# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**Turn any company or organization URL into deep strategic analysis that gets a consultant maximally up to speed.**

Primr extracts primary-source data from company and organization websites using adaptive, org-aware scraping that handles modern site architectures, then synthesizes external research into long-form strategic analysis using AI-powered research and synthesis (Grok 4.1 by default, or Gemini Deep Research via `--premium`).

Runs as a CLI, an MCP server, an OpenClaw integration, and a Claude Skill.

```
primr "ExampleCo" https://example.co
```

About 35-50 minutes later: a deep strategic analysis covering competitive positioning, technology stack, strategic initiatives, likely constraints, and consultant-grade hypotheses, with dense references consolidated at the end. ~$0.75 in API costs.

## Why This Exists

Company research is tedious. You visit the website, click around, search the company, read articles, synthesize it all, write it up. That process easily takes 1-2 hours per company and the output is usually unstructured notes. Primr replaces that entire workflow with a single command.

## What Makes It Different

- **DNS intelligence pre-flight**: Automatic domain reconnaissance detects cloud platforms, SaaS services, email security, and identity providers from DNS records — zero API keys, 2-3 seconds. Strategies are grounded in real tech stack data.
- **Adaptive scraping**: 8 retrieval methods from browser rendering to TLS fingerprinting to screenshot+vision extraction, with per-host optimization. Starts with full browser rendering (what works on 95%+ of modern sites) and falls back through increasingly specialized methods.
- **Org-aware site selection**: Link discovery and prioritization now adapt for commercial companies, government sites, nonprofits, education, and healthcare organizations instead of assuming every site looks like a SaaS company.
- **Fail-fast scrape quality gate**: Full/scrape modes now abort when site extraction is too thin, while still preserving short structured pages like contact, leadership, and org-chart references when they carry useful signal (override with `--skip-scrape-validation`).
- **Autonomous external research**: Gemini Deep Research for comprehensive analysis, Grok 4.1 for fast turnaround — both plan queries, follow leads, cross-validate sources, and synthesize findings.
- **Cost controls built in**: `--dry-run` estimates (including recovery table and stage classifications), usage tracking, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills, all first-class.

## Artifact Model

Primr treats **research artifacts** and **shipping artifacts** as different classes of output. Intermediate research steps such as scrape summaries, gap-analysis notes, source inventories, contradiction findings, and section briefs optimize for consistency, provenance, and parseability. Their formatting matters far less than whether they are complete and structured enough to feed later stages reliably.

Final reports and strategy documents are different. Those artifacts must ship cleanly as Markdown, TXT, DOCX, and eventually PDF, so Primr treats them as a stricter output contract with deterministic cleanup, citation normalization, validation gates, and renderer hardening.

What is already in place:
- Final-document canonicalization before shipping so report/strategy artifacts are normalized into a stable shape before MD/TXT/DOCX rendering
- Typed generated-section normalization at the section-writing seam, including validation-line cleanup, embedded reference stripping, and citation extraction
- Mixed-format parsing resilience so section batches can recover cleanly even if the model blends XML-style section envelopes with legacy `##` headings
- Cleaner artifact validation for rendered DOCX outputs, including reduced false positives from literal `#` content inside tables

Near-term work remains focused on pushing more structure upstream into the long-form writing steps, reducing arbitrary markdown repair before shipping, and strengthening artifact gates against real-world failed artifacts.

## Modes

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| Default | Grok 4.20 hybrid + AI Strategy (recon auto-detects platform) | ~35-50 min | ~$0.75 |
| `--platform ms` | Microsoft Azure + NVIDIA private cloud strategy | ~45-60 min | ~$0.80 |
| Default + multi-platform | Add `--platform aws azure` | ~45-60 min | ~$0.80 |
| Default + strategy type | Add `--strategy-type customer_experience` | ~35-50 min | ~$0.75 |
| `--grok-tier fast` | Grok 4.1 everywhere (cheaper, slightly lower quality) | ~30-45 min | ~$0.47 |
| `--grok-tier max` | Grok 4.20 everywhere (diminishing returns on writing) | ~35-50 min | ~$4.29 |
| `--premium` | Gemini + Deep Research + AI Strategy | 50-75 min | ~$5 |
| `--premium --platform ms` | Premium + Microsoft/NVIDIA | 75-120 min | $6-9 |
| `--premium --lite` | Pro model instead of DR for AI Strategy | 50-80 min | ~$4 |
| `--mode scrape` | Crawl site + extract insights only | 5-10 min | $0.10 |
| `--mode deep` | Gemini Deep Research on external sources only | 10-15 min | $2.50 |
| `primr recon` | DNS intelligence only (no API keys needed) | 2-3 sec | $0.00 |

The default `primr` command auto-detects: when `XAI_API_KEY` is set, it uses the Grok 4.20 hybrid pipeline (4.20 for reasoning-heavy stages, 4.1 for bulk writing) at ~$0.67/run. The standard pipeline includes research deepening, cross-validation, trust-polish, citation normalization, and constrained-evidence reasoning. Strategy types (`ai`, `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`) are YAML-defined and auto-discovered — run `primr --list-strategies` for details. DDG searches are free. Use `--dry-run` for accurate cost estimates.

For model evaluation and quality comparison, see [Evaluation Guide](docs/EVAL.md).

## Quick Start

```bash
git clone https://github.com/blisspixel/primr.git
cd primr
python setup_env.py              # Installs deps, creates .env
# Add your API keys to .env (see docs/API_KEYS.md)
primr doctor                     # Verify everything works
primr "ExampleCo" https://example.co  # Run your first research
```

Requires Python 3.11+. Set `XAI_API_KEY` for the standard Grok pipeline (recommended), or `GEMINI_API_KEY` for Gemini/premium mode. Web search uses DuckDuckGo (no key needed).

### Platform Support

- Windows
- macOS
- Linux

```bash
# Standard run (auto-detects platform from DNS)
primr "Company" https://company.com

# Microsoft Azure + NVIDIA private cloud strategy
primr "Company" https://company.com --platform ms

# Research modes
primr "Company" https://company.com --mode scrape              # Site corpus only
primr "Company" https://company.com --mode deep                # External research only
primr "Company" https://company.com --dry-run                  # Cost estimate first

# Multi-platform and strategy types
primr "Company" https://company.com --platform aws azure       # Multi-platform AI strategy
primr "Company" https://company.com --strategy-type customer_experience  # CX strategy
primr --list-strategies                                        # See all strategy types

# Premium (Gemini + Deep Research)
primr "Company" https://company.com --premium                  # ~$5, maximum depth
primr "Company" https://company.com --premium --lite           # Cheaper premium strategy

# DNS intelligence (standalone, no API keys needed)
primr recon acme.com                                           # DNS intelligence lookup
primr recon acme.com --json                                    # Structured JSON output
```

For batch processing, see [Batch Guide](docs/BATCH.md). For crash recovery and resume, see [Recovery Guide](docs/RECOVERY.md). For post-generation quality improvement, see [Improve Guide](docs/IMPROVE.md).

### What a run looks like

```
Grok 4.20 hybrid · recon auto-detected Azure

▸ PHASE 0/6 · Recon
✓ 14 services, 8 insights, platform: azure (2s)

▸ PHASE 1/6 · Data Collection
✓ 251 links → 50 selected
✓ 48/50 pages scraped (6m 10s)
✓ 31 external sources (8m 22s)

▸ PHASE 2/6 · Research Deepening
✓ 8 gaps identified, 12 additional sources

▸ PHASE 3/6 · Analysis
✓ Structured workbook built

▸ PHASE 4/6 · Report Writing
  Part 1/5: 7 sections in parallel
  Part 2/5: 3 sections in parallel
  Part 4/5: 7 sections in parallel
✓ 23 sections, 21,500 words

▸ PHASE 5/6 · Cross-Validation
✓ 3 contradictions resolved
  Trust: PASS · cites 12/12 · appendix clean

▸ PHASE 6/6 · AI Strategy (Azure)
✓ Strategy generated

✓ Complete in 38m
  output/ExampleCo_Strategic_Overview_04-10-2026.docx

PASS | 23 chapters | 48 citations | ~$0.74
```

### What the output looks like

From the executive summary of a sample report:

> Northwind Haulage Corp is a mid-market logistics optimization vendor ($180-220M ARR, estimated) that sells route planning and fleet analytics software to regional shipping companies. The company occupies a defensible but narrowing niche: optimizing last-mile delivery for carriers still running legacy dispatch systems.
>
> **Key insights:**
>
> - Northwind's customer concentration is high. Cross-referencing case studies, press releases, and conference presentations, roughly 40% of referenced deployments involve just 3 carrier networks. Loss of any one would be material. *[Confidence: Inferred]*
> - The company has no disclosed AI strategy, but 4 of their last 7 engineering hires have ML/optimization backgrounds. Combined with a patent filing for "autonomous route replanning under disruption," this suggests an unannounced product line. *[Confidence: Inferred]*
> - Pricing has shifted from perpetual licenses to consumption-based billing (per-shipment), visible in public procurement portal RFP responses. *[Confidence: Reported]*

Reports include 23 structured sections, SWOT analysis, competitive landscape, discovery questions, and inline confidence levels on every non-obvious claim.

## Under the Hood

Primr uses an 8-tier browser-first retrieval engine with sticky tier memory, circuit breakers, and cookie handoff. Models range from Grok 4.1 ($0.20/$0.50 per 1M tokens) to Gemini Deep Research (~$2.50/task). The agentic architecture includes hypothesis tracking, subagents for each pipeline stage, governance hooks, and persistent research memory.

For full architecture details, model pricing, and the retrieval tier breakdown, see [System Design](docs/ARCHITECTURE.md).

## Configuration

```bash
# Recommended - for default Grok 4.1 pipeline
XAI_API_KEY=          # https://console.x.ai/

# Required for --premium mode or if XAI_API_KEY not set
GEMINI_API_KEY=       # https://aistudio.google.com/apikey

# Web search uses DuckDuckGo by default - no key needed
```

[Full config reference](docs/CONFIG.md) | [API key setup](docs/API_KEYS.md)

## Agent Integration

Primr is built for the agentic era. Four ways to plug it in:
**MCP Server** - Claude Desktop, Cursor, and any MCP-compatible client:
```bash
primr-mcp --stdio              # stdio transport
primr-mcp --http --port 8000   # HTTP with JWT auth
```

**A2A Protocol** - Agent-to-Agent communication with any A2A-compatible agent:
```bash
pip install primr[a2a]                     # install optional A2A support
primr-a2a --no-auth                        # standalone A2A server on port 9000
primr-mcp --http --a2a                     # co-hosted with MCP server
curl localhost:9000/.well-known/agent.json  # discover agent capabilities
```

<details>
<summary><strong>OpenClaw</strong> - Packaged skills, governed workflows, and sandbox config</summary>

```bash
# openclaw/openclaw.json wires Primr MCP into OpenClaw
# Skills: primr-research, primr-strategy, primr-qa
# Workflows: research-pipeline, strategy-pipeline
```

The packaged workflows estimate cost, require approval, and propagate approved cost caps into spend calls.
See `docs/OPENCLAW.md` for setup and troubleshooting.
</details>

<details>
<summary><strong>Claude Skills</strong> - MCP-first skill packages</summary>

```text
skills/
├── company-research/SKILL.md
├── hypothesis-tracking/SKILL.md
├── qa-iteration/SKILL.md
└── scrape-strategy/SKILL.md
```

These skills are thin intent routers over Primr MCP rather than separate product definitions. Generic MCP clients can also use `primr://agent/governance`, `primr://research/next-actions`, and the `governed_execution` prompt to follow the same estimate/approval/monitor pattern.
</details>

[MCP docs](docs/API.md) | [A2A protocol](https://github.com/a2aproject/a2a-python) | [OpenClaw config](openclaw/openclaw.json) | [OpenClaw guide](docs/OPENCLAW.md)

## Cloud Deployment

Primr is CLI-first, local-first. Cloud deployment is optional for teams needing shared access or always-on availability.

| Tier | What it is | Idle cost |
|------|-----------|-----------|
| Solo (default) | CLI on your machine | $0 |
| Team | Azure Container Apps, scale-to-zero | < $5/month |
| Organization | Entra ID, budget tracking, observability, M365 Agent Store | < $15/month |

See the [Deployment Guide](docs/CLOUD_DEPLOYMENT.md) or [Azure Quickstart](docs/AZURE_QUICKSTART.md).

## Development

```bash
python -m pytest tests/ -x --tb=short       # Run tests
ruff check .                                 # Lint
mypy src/primr --ignore-missing-imports     # Type check
```

5,700+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, and OpenTelemetry tracing. CI runs lint, type check, and tests on every push.

## Learn More

| Topic | Guide |
|-------|-------|
| Batch processing | [Batch Guide](docs/BATCH.md) |
| Model evaluation | [Evaluation Guide](docs/EVAL.md) |
| Crash recovery | [Recovery Guide](docs/RECOVERY.md) |
| Output improvement | [Improve Guide](docs/IMPROVE.md) |
| Configuration | [Full Config Reference](docs/CONFIG.md) |
| Architecture | [System Design](docs/ARCHITECTURE.md) |
| Cloud deployment | [Deployment Guide](docs/CLOUD_DEPLOYMENT.md) |
| Agent integration | [MCP & A2A API](docs/API.md) |
| API key setup | [API Keys](docs/API_KEYS.md) |
| Azure quickstart | [Azure Quickstart](docs/AZURE_QUICKSTART.md) |
| OpenClaw | [Setup & Troubleshooting](docs/OPENCLAW.md) |
| Security ops | [Security Operations](docs/SECURITY_OPS.md) |
| Contributing | [Contribution Guidelines](CONTRIBUTING.md) |
| Vulnerability reporting | [Security](SECURITY.md) |
| Roadmap | [What's Planned](ROADMAP.md) |

## About This Project

Primr is a nights-and-weekends project by a solo developer. The time-to-insight ratio for company research was terrible, and most of the work was mechanical. That's exactly what AI should be doing. So I built the tool I wanted.

It's not backed by a company or a team. It's an independent project built for personal use.

## Disclaimer

Primr is a research tool. You are responsible for:

- **Web content**: Primr retrieves publicly available web content, similar to a browser or search engine crawler. It does not bypass authentication, access paywalled content, or exploit vulnerabilities. However, some websites restrict automated access in their terms of service - it is your responsibility to check before running Primr against any site.
- **Accuracy**: AI-generated content may contain errors, hallucinations, or outdated information. Verify findings before acting on them.
- **Costs**: API calls to AI services (Gemini, Grok) incur real charges. Use `--dry-run` to estimate costs before running.
- **Use case**: This tool is intended for legitimate research purposes. Do not use it to violate any website's terms of service or any applicable law.

This software is provided as-is by a solo developer. The author is not liable for how you use this software, the accuracy of its outputs, or any consequences of its use.

## License

MIT
