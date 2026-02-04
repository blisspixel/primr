# Primr

**Turn any company URL into a strategic intelligence brief for $0.35.**

Primr combines battle-tested web scraping with Gemini's autonomous Deep Research to generate the kind of company intelligence that used to take analysts hours. Point it at a website, get a structured brief with citations.

## Why This Exists

Company research is tedious. You visit the website, click around, Google the company, read articles, synthesize it all, write it up. Repeat for every prospect, every deal, every meeting.

Primr does that entire workflow autonomously:

```
primr "Acme Corp" https://acme.example
```

30 minutes later: a structured brief with competitive positioning, technology stack, strategic initiatives, and external validation—all cited.

## What Makes It Different

**The scraping actually works.** 8 tiers that auto-escalate from simple HTTP to browser automation to screenshot+vision extraction. Beats Cloudflare, detects soft blocks, learns which approach works per host. This isn't `requests.get()`.

**The research is autonomous.** Gemini Deep Research isn't a summarizer—it's an agent that plans searches, follows leads across sources, and synthesizes findings. It researches like a human would, just faster.

**The economics are absurd.** A junior analyst doing this manually? Hours. A research service? Hundreds of dollars. Primr? ~$0.35 and 30 minutes.

**It's composable.** MCP server, OpenClaw integration, and Claude Skills included. AI agents can call Primr, track hypotheses across sessions, and build on prior research.

## Modes

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| `scrape` | Crawls site, extracts insights | ~5 min | ~$0.02 |
| `deep` | Gemini Deep Research on external sources | ~10 min | ~$0.20 |
| `full` | Both combined into comprehensive brief | ~30 min | ~$0.35 |

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

## Usage

```bash
primr "Company" https://company.com                 # Full research (default)
primr "Company" https://company.com --mode scrape   # Site corpus only
primr "Company" https://company.com --mode deep     # External research only
primr "Company" https://company.com --dry-run       # Cost estimate first
```

## Under the Hood

**8-Tier Scraping Engine**
- HTTP tiers: requests → httpx → curl_cffi (TLS fingerprint impersonation)
- Browser tiers: Playwright → aggressive mode → DrissionPage (driverless CDP)
- Vision tier: Screenshot + LLM extraction for the really stubborn pages
- Auto-escalation, sticky tier optimization, circuit breakers, soft block detection

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

**OpenClaw** — Drop-in integration with skills and workflows:
```bash
# openclaw/openclaw.json already configured
# Skills: primr-research, primr-strategy, primr-qa
# Sandboxed Docker execution included
```

**Claude Skills** — Anthropic's Agent Skills format:
```
skills/
├── company-research/SKILL.md   # Full pipeline with memory
├── hypothesis-tracking/SKILL.md # Confidence management
├── qa-iteration/SKILL.md       # Section refinement
└── scrape-strategy/SKILL.md    # Tier selection heuristics
```

The skills include hypothesis persistence, cost governance hooks, and QA gates. Agents can pick up where they left off across sessions.

→ [MCP docs](docs/API.md) · [OpenClaw config](openclaw/openclaw.json)

## Cloud Deployment

Scale to zero serverless deployment on AWS, Azure, or GCP. Job-based ephemeral containers, event-driven queues, production observability. → [Deployment guide](docs/CLOUD_DEPLOYMENT.md)

## Documentation

| Doc | What's in it |
|-----|--------------|
| [API_KEYS.md](docs/API_KEYS.md) | API key setup |
| [CONFIG.md](docs/CONFIG.md) | Full configuration reference |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, scraping tiers |
| [API.md](docs/API.md) | MCP server, programmatic usage |
| [CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) | Serverless deployment |
| [ROADMAP.md](ROADMAP.md) | What's next |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

Primr is a research tool. You are responsible for:

- **Compliance**: Respecting robots.txt, terms of service, and applicable laws when scraping websites. Some sites prohibit automated access.
- **Accuracy**: AI-generated content may contain errors, hallucinations, or outdated information. Verify findings before acting on them.
- **Costs**: API calls to Gemini and other services incur real charges. Use `--dry-run` to estimate costs before running.
- **Use case**: This tool is intended for legitimate research purposes. Don't use it for anything sketchy.

The authors are not liable for how you use this software or the accuracy of its outputs.

## License

MIT
