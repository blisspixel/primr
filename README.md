# Primr

**Turn a company URL into a cited, analyst-grade intelligence brief.**

Primr extracts primary-source data from company websites using a multi-tier approach that adapts to different site architectures, then synthesizes external research into structured briefs that can be consumed by humans *or* autonomous agents.

Runs as a CLI, an MCP server, an OpenClaw integration, and a Claude Skill.

```
primr "Acme Corp" https://acme.example
```

30 minutes later: competitive positioning, technology stack, strategic initiatives, and external validation—all cited.

## Why This Exists

Company research is tedious. You visit the website, click around, Google the company, read articles, synthesize it all, write it up. Repeat for every prospect, every deal, every meeting.

Primr does that entire workflow autonomously.

## What Makes It Different

- **Adaptive scraping**: 8 retrieval methods from simple HTTP to browser rendering to screenshot+vision extraction, with per-host optimization. Tries the simplest approach first and falls back to more capable methods as needed.
- **Autonomous external research**: Gemini Deep Research plans queries, follows leads, cross-validates sources, and synthesizes findings into a structured brief.
- **Cost controls built in**: `--dry-run` estimates, usage tracking, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills—all first-class.

Manual research takes hours. Primr typically runs in ~30 minutes and costs ~$1–2 in API usage (varies by depth and site behavior).

## Modes

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| `scrape` | Crawls site, extracts insights | ~5 min | ~$0.10 |
| `deep` | Gemini Deep Research on external sources | ~10 min | ~$1.00 |
| `full` | Both combined into comprehensive brief | ~30 min | ~$1.50 |

Costs include Google Search grounding ($0.035/query). Use `--dry-run` for accurate estimates based on your usage history.

## Quick Start

```bash
git clone https://github.com/blisspixel/primr.git
cd primr
python setup_env.py              # Installs deps, creates .env
# Add your API keys to .env (see docs/API_KEYS.md)
primr doctor                     # Verify everything works
primr "Tesla" https://tesla.com  # Run your first research
```

Requires Python 3.11+ and a Gemini API key.

```bash
# More usage
primr "Company" https://company.com --mode scrape   # Site corpus only
primr "Company" https://company.com --mode deep     # External research only
primr "Company" https://company.com --dry-run       # Cost estimate first
```

<!-- TODO: Add sample output screenshot here -->

## Under the Hood

**8-Tier Retrieval Engine** (browser-first for modern JS-heavy sites)
- Browser tiers: Playwright → expanded rendering → DrissionPage (driverless CDP)
- HTTP tiers: curl_cffi → httpx → requests
- Vision tier: Screenshot + LLM extraction for image-heavy or non-standard layouts
- Automatic fallback, per-host optimization, circuit breakers

**Gemini Deep Research**
- Autonomous multi-step search and synthesis
- Plans its own research strategy, follows leads, validates across sources
- Not a wrapper around chat completions—actual agentic research

**Agentic Architecture**
- Hypothesis tracking with confidence levels across sessions
- Subagents for scraping, analysis, writing, and QA
- Hook system for governance (cost limits, quality gates)
- Research memory that persists and evolves

## Configuration

```bash
# Required in .env
GEMINI_API_KEY=       # https://aistudio.google.com/apikey
SEARCH_API_KEY=       # Google Custom Search API  
SEARCH_ENGINE_ID=     # Programmable Search Engine ID
```

→ [Full setup guide](docs/API_KEYS.md)

## Agent Integration

Primr is built for the agentic era. Three ways to plug it in:

**MCP Server** — Claude Desktop, Cursor, and any MCP-compatible client:
```bash
primr-mcp --stdio              # stdio transport
primr-mcp --http --port 8000   # HTTP with JWT auth
```

<details>
<summary><strong>OpenClaw</strong> — Drop-in integration with skills and workflows</summary>

```bash
# openclaw/openclaw.json already configured
# Skills: primr-research, primr-strategy, primr-qa
# Sandboxed Docker execution included
```
</details>

<details>
<summary><strong>Claude Skills</strong> — Anthropic's Agent Skills format</summary>

```
skills/
├── company-research/SKILL.md   # Full pipeline with memory
├── hypothesis-tracking/SKILL.md # Confidence management
├── qa-iteration/SKILL.md       # Section refinement
└── scrape-strategy/SKILL.md    # Tier selection heuristics
```

Skills include hypothesis persistence, cost governance hooks, and QA gates. Agents can pick up where they left off across sessions.
</details>

<details>
<summary><strong>Cloud Deployment</strong> — Serverless on AWS, Azure, or GCP</summary>

Scale-to-zero ephemeral containers, event-driven queues, production observability. See [deployment guide](docs/CLOUD_DEPLOYMENT.md).
</details>

→ [MCP docs](docs/API.md) · [OpenClaw config](openclaw/openclaw.json)

## Development

```bash
python -m pytest tests/ -x --tb=short   # Run tests
ruff check src/                          # Lint
mypy src/primr --ignore-missing-imports  # Type check
```

1,500+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, OpenTelemetry tracing, and typed error hierarchy with automatic retry classification.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, scraping tiers |
| [API.md](docs/API.md) | MCP server, programmatic usage |
| [CONFIG.md](docs/CONFIG.md) | Full configuration reference |
| [API_KEYS.md](docs/API_KEYS.md) | API key setup |
| [CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) | Serverless deployment |
| [SECURITY_OPS.md](docs/SECURITY_OPS.md) | Security operations guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [ROADMAP.md](ROADMAP.md) | What's planned |

## About This Project

Primr is a nights-and-weekends project by a solo developer. I think AI-assisted research workflows are going to be transformative over the next few years, and this is my way of building deeply in the space — learning by shipping something real.

It's not backed by a company or a team. It's an independent project built for personal use.

## Disclaimer

Primr is a research tool. You are responsible for:

- **Web content**: Primr retrieves publicly available web content, similar to a browser or search engine crawler. It does not bypass authentication, access paywalled content, or exploit vulnerabilities. However, some websites restrict automated access in their terms of service — it is your responsibility to check before running Primr against any site.
- **Accuracy**: AI-generated content may contain errors, hallucinations, or outdated information. Verify findings before acting on them.
- **Costs**: API calls to Gemini and other services incur real charges. Use `--dry-run` to estimate costs before running.
- **Use case**: This tool is intended for legitimate research purposes such as due diligence and meeting preparation. Do not use it to violate any website's terms of service or any applicable law.

This software is provided as-is by a solo developer. The author is not liable for how you use this software, the accuracy of its outputs, or any consequences of its use.

## License

MIT
