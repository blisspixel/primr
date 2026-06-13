# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

**Point it at a company's website. It reads their DNS records, their job postings, and fifty pages of their site, then drafts a strategic brief: what they appear to be building, where they look constrained, and which questions are worth asking.**

Summaries of published articles are a commodity; any chat assistant's deep-research mode produces one. Primr is built for the layer underneath: primary-source signals that aren't in the articles. DNS records reveal the real tech stack. Job postings reveal what a company is actually building right now. The site corpus, external research, and that signal layer get triangulated into a long-form strategic analysis covering competitive positioning, likely economics, operating constraints, and working hypotheses, with confidence labels distinguishing what's confirmed, what's reported, and what's inference. The labels are model-applied and spot-audited for traceability (`primr calibrate`); treat them as editorial discipline, not ground truth.

```
primr "ExampleCo" https://example.co
```

About 23-35 minutes later: a 23-section strategic analysis as Markdown and DOCX, with dense references consolidated at the end. **~$0.79 in API costs** when both `GEMINI_API_KEY` and `XAI_API_KEY` are set (Grok 4.3 for reasoning with cached input, Gemini 3.1 Flash-Lite for bulk writing; the v1.24.0 default after a cross-provider eval). XAI-only setups stay on the legacy Grok-NR writing path at ~$4.27/run.

Primr is local-first and CLI-first; it also runs as an MCP server and a Claude Skill so agents can drive it ([details below](#use-primr-from-your-ai-tool)).

> **Not a developer?** You (or whoever sets up your machine) need three things: Python, `pip install primr`, and API keys from one or two AI providers. `primr init` walks through all of it. Everything from [Agent Integration](#agent-integration-advanced) down is for developers and agent builders; you never need it to run research.

## Why This Exists

Company research is tedious. You visit the website, click around, search the company, read articles, synthesize it all, write it up. That process easily takes 1-2 hours per company and the output is usually unstructured notes. Primr compresses most of that into a single command: you get a structured, sourced draft instead of a blank page. You should still read it critically; it's a head start, not a finished judgment.

## What Makes It Different

- **DNS intelligence pre-flight**: Automatic domain reconnaissance detects cloud platforms, SaaS services, email security, and identity providers from DNS records. Zero API keys, 2-3 seconds. Strategies are grounded in real tech stack data.
- **Hiring-signal gathering**: After the main scrape, Primr discovers open job postings across eight ATS providers (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Workable, Recruitee, Jobvite) plus a corpus-driven Workday URL discovery path, an HTML careers-page fallback, and a DuckDuckGo web-search fallback that sweeps LinkedIn / Indeed / Glassdoor / job-board hosts when every other path comes up empty. The pipeline LLM-triages the most signal-rich postings and extracts tech-stack frequency, strategic initiatives, culture cues, and notable absences. Job posts are the most honest statement of what a company is actually building right now; they feed every downstream phase from gap analysis to final strategy and are the primary input to the skill pack subsystem. Skip with `PRIMR_SKIP_HIRING_SIGNALS=1`.
- **Adaptive scraping**: 9 retrieval methods from browser rendering to TLS fingerprinting to screenshot+vision extraction, with per-host optimization. Starts with full browser rendering and falls back through increasingly specialized methods. Some heavily protected sites still win; access is evidence-validated, so a blocked site is reported as blocked rather than silently summarized from nothing.
- **Org-aware site selection**: Link discovery and prioritization now adapt for commercial companies, government sites, nonprofits, education, and healthcare organizations instead of assuming every site looks like a SaaS company.
- **Fail-fast scrape quality gate**: Full/scrape modes now abort when site extraction is too thin, while still preserving short structured pages like contact, leadership, and org-chart references when they carry useful signal (override with `--skip-scrape-validation`).
- **Autonomous external research**: Gemini Deep Research for comprehensive analysis, Grok 4.3 for fast turnaround. Both plan queries, follow leads, cross-validate sources, and synthesize findings.
- **Cost controls built in**: `--dry-run` estimates (including recovery table and stage classifications), `--budget $N` per-run cost ceiling (refuses to start over budget, skips optional stages once actual spend reaches it), usage tracking with per-run cache hit rates in `primr show-usage`, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills, all first-class.
- **Skill pack generation**: `primr skills "<Company>" <url>` produces a QA-refined Agent Skills pack of up to 15 roles × M skills, grounded in DNS recon + actual job postings + strategic research. Internal pipeline: a two-call role planning step that emits an inspectable `role_plan.md` / `role_plan.json` (observed roles backed by posting citations + plausible roles inferred from research and industry classification, with provenance preserved end-to-end), archetype-grounded authoring with provenance-aware prompts, deterministic ASKILL-* validation, capped refinement loop, and pack-level coherence pass. Emits both an unpacked Claude/Cursor/VS Code tree AND a Microsoft 365 Copilot Cowork sideload `.zip` from the same byte-identical SKILL.md files. Full **operator roster curation**: `--plan-only` to inspect, `--from-plan` to author from a saved plan, `--roles-add` to augment the discovered roster, `--roles-skip` to prune from it (composes with `--from-plan`), `--roles-override` for full control.

## Artifact Model

Primr treats **research artifacts** and **shipping artifacts** as different classes of output. Intermediate research steps such as scrape summaries, gap-analysis notes, source inventories, contradiction findings, and section briefs optimize for consistency, provenance, and parseability. Their formatting matters far less than whether they are complete and structured enough to feed later stages reliably.

Final reports and strategy documents are different. Those artifacts must ship cleanly as Markdown, TXT, DOCX, and eventually PDF, so Primr treats them as a stricter output contract with deterministic cleanup, citation normalization, validation gates, and renderer hardening.

What is already in place:
- Final-document canonicalization before shipping so report/strategy artifacts are normalized into a stable shape before MD/TXT/DOCX rendering
- Typed generated-section normalization at the section-writing seam, including validation-line cleanup, embedded reference stripping, and citation extraction
- Mixed-format parsing resilience so section batches can recover cleanly even if the model blends XML-style section envelopes with legacy `##` headings
- Cleaner artifact validation for rendered DOCX outputs, including reduced false positives from literal `#` content inside tables
- Configurable ship-time gates that withhold the polished DOCX (Markdown/TXT plus a sidecar diagnostic still ship) when a deliverable carries leaked internal scaffolding (`PRIMR_MAX_SCAFFOLDING_LEAKS`), dangling citations (inline `[cite: N]` with no matching Sources entry, `PRIMR_MAX_DANGLING_CITATIONS`), or structural defects (duplicate `##` headings and empty sections, `PRIMR_MAX_STRUCTURE_DEFECTS`). All default to zero tolerance and act as regression backstops behind the upstream cleanup/repair steps
- An artifact regression corpus (`tests/fixtures/artifacts/`) of long-form report/strategy fixtures that exercises the gates and renders the clean ones end-to-end to DOCX, so validator/renderer changes are tested against real-shaped output

The writing and regeneration prompts now carry an explicit prohibition against the internal-scaffolding markers the ship-time gate strips, sourced from a single shared constant co-located with the scanner so the upstream instruction and the downstream gate stay in lockstep. The deterministic cleanup is meant to be a safety net, not load-bearing, and the `writer_output_clean` signal tracks whether it stays that way. Near-term work remaining focuses on continuing to move final rendering toward structured document data rather than free-form markdown recovery.

## Modes

> **Cost note (May 2026 / v1.24.0):** Default is now ~$0.79/run when both `GEMINI_API_KEY` and `XAI_API_KEY` are set (Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing). XAI-only setups stay on the legacy ~$4.27/run Grok-NR path. The cross-provider default was picked via a real eval on a mid-market public-signal company: 4.4x cheaper than the legacy default with trust gate PASS and faster runtime. See [docs/EVAL_V1_24_0.md](docs/EVAL_V1_24_0.md) for the decision audit.

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| `primr skills` | QA-refined skill pack (Claude tree + Cowork .zip) from existing research | 30-90s | ~$0.20 |
| Default (Gemini + XAI) | Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing + AI Strategy | ~23-35 min | **~$0.79** |
| Default (XAI only) | Grok 4.3 hybrid + Grok 4.20-NR writing (legacy fallback) | ~35-50 min | ~$4.27 |
| `--platform ms` | Microsoft Azure + NVIDIA private cloud strategy | ~30-50 min | ~$0.85 |
| Default + multi-platform | Add `--platform aws azure` | ~30-50 min | ~$0.85 |
| Default + strategy type | Add `--strategy-type customer_experience` | ~23-35 min | ~$0.79 |
| `--grok-tier max` | Grok 4.3 everywhere (deeper reasoning across writing too) | ~35-50 min | ~$3.75 |
| `--premium` | Gemini + Deep Research + AI Strategy | 50-75 min | ~$5 |
| `--premium --platform ms` | Premium + Microsoft/NVIDIA | 75-120 min | $6-9 |
| `--premium --lite` | Pro model instead of DR for AI Strategy | 50-80 min | ~$4 |
| `--mode scrape` | Crawl site + extract insights only | 5-10 min | $0.10 |
| `--mode deep` | Gemini Deep Research on external sources only | 10-15 min | $2.50 |
| `primr recon` | DNS intelligence only (no API keys needed) | 2-3 sec | $0.00 |

The default `primr` command auto-detects: when `XAI_API_KEY` is set, it uses the Grok 4.3 hybrid pipeline (4.3 for reasoning-heavy stages, 4.20-non-reasoning for bulk writing) at ~$4.27/run. The standard pipeline includes research deepening, cross-validation, trust-polish, citation normalization, and constrained-evidence reasoning. Strategy types (`ai`, `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`, `skills`) are YAML-defined and auto-discovered; run `primr --list-strategies` for details. DDG searches are free. Use `--dry-run` for accurate cost estimates.

For model evaluation and quality comparison, see [Evaluation Guide](docs/EVAL.md).

## Quick Start

**One-line install**

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.sh | bash
```

After the installer finishes, open a **new** terminal and run `primr init`.

The installers are idempotent: re-run the same one-liner any time to upgrade to the latest release.

**Updating:**
```bash
primr update            # self-update to the latest release (detects pipx vs pip)
primr update --check    # check for a newer version without installing
```

`primr` also shows a one-line notice when a newer version is available (checked at most once a day, cached locally). Opt out with `PRIMR_NO_UPDATE_CHECK=1`.

---

**primr works on Windows, macOS, and Linux.**

```bash
pip install primr
primr init                      # Guided keys + browser setup
primr doctor                    # Verify everything works
primr "ExampleCo" https://example.co
```

`pip install primr` also pulls in `recon-tool` (used for the built-in `primr recon` DNS intelligence step).

**Requirements:** Python 3.12 or newer. On Windows, prefer the `py` launcher (`py -3.13` or just `py`) if your default `python` is older.

`primr init` guides you through API keys and browser setup the first time. Local `.env` files and environment variables are also supported.

### Recommended way (virtual environment or pipx)

This is the cleanest approach on every platform and avoids PATH headaches.

```bash
# 1. Create a virtual environment
python -m venv .venv          # some systems: python3 -m venv .venv

# 2. Activate it
#   Windows (PowerShell):   .\.venv\Scripts\Activate.ps1
#   macOS / Linux:          source .venv/bin/activate

# 3. Install
pip install primr

# 4. First-time setup + verification
primr init
primr doctor
```

**Simpler alternative with pipx** (recommended for CLI tools):

```bash
pipx install primr
primr init
primr doctor
```

pipx handles isolation and PATH for you automatically.

### Fast one-liner

```bash
pip install primr
primr init
primr doctor
```

**If `primr` (or `recon`) is not found after a bare `pip install` on Windows:**
This usually means a system Python was used without admin rights. The commands are installed to `%APPDATA%\Python\Python312\Scripts` but that folder isn't on PATH. Use the venv/pipx method above instead, or run `primr`'s `setup_env.py` from a source checkout (it can fix the PATH for you).

### Working from a source checkout?

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). It covers:
- venv + uv setups
- The Windows-friendly `setup_env.py` (handles Python detection, editable install, Playwright browsers, and user Scripts PATH)
- Full development workflow

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

# Skill pack: QA-refined Agent Skills for Claude + Microsoft 365 Copilot Cowork
primr skills "ExampleCo" https://example.co                              # 5 roles x 3 skills, ~$0.30
primr skills "ExampleCo" https://example.co --roles 10 --skills-per-role 3   # holistic pack (1-15 roles)
primr skills "ExampleCo" https://example.co --formats cowork             # only the .zip
primr skills "ExampleCo" https://example.co --from-report working/<existing-run>
primr skills "ExampleCo" https://example.co --plan-only                  # inspect the role plan, no authoring
primr skills "ExampleCo" https://example.co --from-plan path/to/role_plan.json  # author from a saved plan
primr skills "ExampleCo" https://example.co --roles-add "Account Executive,Procurement Manager"   # augment the discovered plan
primr skills "ExampleCo" https://example.co --roles-skip "Marketing Manager"                       # prune from the discovered plan
primr skills "ExampleCo" https://example.co --from-plan path/role_plan.json --roles-add "Cybersecurity Lead"  # augment a saved plan
primr skills "ExampleCo" https://example.co --roles-override "Account Executive,Cloud Migration Consultant,Practice Lead"  # bypass planning entirely
primr skills "ExampleCo" https://example.co --allow-recon-only           # proceed when no postings + no research
primr skills "ExampleCo" https://example.co --dry-run                    # estimate first
```

The skill pack output contains both a `roles/<slug>/SKILL.md` tree (drop-in for Claude Code, Cursor, VS Code Copilot, Gemini CLI, Junie) and a `<Company>_Cowork_Pack.zip` (sideload via M365 Admin Center > Manage Apps > Upload custom app). Each pack also emits a markdown pack report with the validation scorecard, per-role refinement counts, observed/plausible split, and role-plan reference. The planning step writes `role_plan.md` and `role_plan.json` into the working directory before authoring so operators can audit which roles came from actual postings vs which were inferred from research and industry classification.

When `--platform` is omitted, Primr runs recon first and uses strong infrastructure signals (for example Azure DNS/App Service/CDN, AWS Route53/CloudFront, or GCP DNS) to choose the AI strategy platform. If multiple strong platforms are detected, it generates one strategy per platform. Productivity, certificate, and email-only signals do not count as primary-cloud proof. If recon is unclear or skipped, the default strategy posture is Microsoft Azure plus private cloud/NVIDIA (`azure private`).

Use `--output-dir` to send customer-facing deliverables to a specific client folder:

```bash
primr "Company" https://company.com --output-dir "C:\Clients\Company"
```

With a custom output directory, Primr keeps that folder clean: Markdown and DOCX deliverables are written there, while TXT mirrors and validation diagnostics stay in the run's `working/<company>/<timestamp>/_diagnostics/` folder. The default `output/` folder still includes TXT mirrors for backward compatibility.

For batch processing, see [Batch Guide](docs/BATCH.md). For crash recovery and resume, see [Recovery Guide](docs/RECOVERY.md). For post-generation quality improvement, see [Improve Guide](docs/IMPROVE.md).

### What a run looks like

```
Grok 4.3 hybrid · recon auto-detected Azure

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

PASS | 23 chapters | 48 citations | ~$0.79
```

### What the output looks like

From the executive summary of a sample report:

> Northwind Haulage Corp is a mid-market logistics optimization vendor ($180-220M ARR, estimated) that sells route planning and fleet analytics software to regional shipping companies. The company occupies a defensible but narrowing niche: optimizing last-mile delivery for carriers still running legacy dispatch systems.
>
> **Key insights:**
>
> - Northwind's customer concentration is high. Cross-referencing case studies, press releases, and conference presentations, roughly 40% of referenced deployments involve just 3 carrier networks. Loss of any one would be material. *(Estimated)*
> - The company has no disclosed AI strategy, but 4 of their last 7 engineering hires have ML/optimization backgrounds. Combined with a patent filing for "autonomous route replanning under disruption," this suggests an unannounced product line. *(Hypothesis)*
> - Pricing has shifted from perpetual licenses to consumption-based billing (per-shipment), visible in public procurement portal RFP responses. *(Reported)*

Reports include 23 structured sections, SWOT analysis, competitive landscape, discovery questions, and inline confidence labels on non-obvious claims. Depth tracks the available public signal: a company with filings, postings, and press coverage produces a sharper brief than one with a four-page website, and the report says so rather than padding.

## Under the Hood

Primr uses a 9-tier browser-first retrieval engine with sticky tier memory, circuit breakers, and cookie handoff. The v1.24.0 default recipe pairs Gemini 3.1 Flash-Lite ($0.25/$1.50 per 1M tokens) for bulk writing with Grok 4.3 ($1.25/$2.50, $0.20 cached input) for reasoning. Gemini Deep Research (~$2.50/task) handles premium-mode autonomous synthesis. The agentic architecture includes hypothesis tracking, subagents for each pipeline stage, governance hooks, and persistent research memory.

For full architecture details, model pricing, and the retrieval tier breakdown, see [System Design](docs/ARCHITECTURE.md).

## Configuration

```bash
# Recommended first-run setup
primr init

# Writes to the per-user Primr config file
primr keys set gemini           # https://aistudio.google.com/apikey
primr keys set xai              # https://console.x.ai/
primr keys list
primr keys path

# Diagnose, then launch guided fixes if needed
primr doctor --fix

# Local .env files and shell env vars are also supported:
XAI_API_KEY=          # Grok standard pipeline (analysis + writing + utility tier)
GEMINI_API_KEY=       # Required only for --premium mode (and for utility tier when no XAI_API_KEY)
```

Web search uses DuckDuckGo by default, no key needed.

[Full config reference](docs/CONFIG.md) | [API key setup](docs/API_KEYS.md)

## Use primr from your AI tool

primr ships with an `AGENTS.md` (auto-loaded by Kiro, Codex, Aider, Jules), a Claude Code plugin under [`claude-code/`](claude-code/), and per-host MCP snippets under [`clients/`](clients/) for Cursor, Windsurf, VS Code + Copilot, and Claude Desktop.

**Claude Code (one-command install):**

```
/plugin marketplace add blisspixel/primr
/plugin install primr@blisspixel-primr
```

That registers both the MCP server (`primr mcp`, exposed as `mcp__primr__*` tools) and the skill (cost gate, async lifecycle, mode selection; loaded on-demand based on its description).

**Skill-only install (no plugin):** paste this to Claude Code or any agent that can fetch and write files:

> Fetch `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/SKILL.md` and save it to `~/.claude/skills/primr/SKILL.md`. Fetch the four files under `https://raw.githubusercontent.com/blisspixel/primr/main/claude-code/skills/primr/references/` and save them under `~/.claude/skills/primr/references/`. Then run `pip install primr && primr init` (use a venv if the `primr` command isn't on PATH afterward).

**Other hosts (Cursor / Windsurf / Kiro / VS Code):** see [`clients/README.md`](clients/README.md) for copy-pasteable MCP config plus instructions for placing the skill or referencing `AGENTS.md` from the host's rules system.

## Agent Integration (advanced)

**MCP server**, for Claude Code, Cursor, Windsurf, Claude Desktop, and any MCP-compatible client:

```bash
primr mcp                      # stdio transport (default; what hosts launch)
primr mcp --http --port 8000   # HTTP with JWT auth
primr-mcp --stdio              # legacy entry point, still supported
```

**A2A Protocol**, for Agent-to-Agent communication with any A2A-compatible agent:

```bash
pip install primr[a2a]                     # install optional A2A support
primr-a2a                                  # standalone A2A on 127.0.0.1:9000 (auth required)
primr-a2a --host 127.0.0.1 --no-auth       # local dev only; refuses non-loopback hosts
primr-mcp --http --a2a                     # co-hosted with MCP server (shares MCP auth)
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

9,000+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, ~82% branch coverage (enforced as a CI ratchet), and OpenTelemetry tracing. CI runs lint, type check, security gates, and tests on every push.

## Learn More

| Topic | Guide |
|-------|-------|
| Skill pack subsystem | [Skill Pack Guide](docs/SKILL_PACK.md) |
| Batch processing | [Batch Guide](docs/BATCH.md) |
| Model evaluation | [Evaluation Guide](docs/EVAL.md) |
| Crash recovery | [Recovery Guide](docs/RECOVERY.md) |
| Output improvement | [Improve Guide](docs/IMPROVE.md) |
| Configuration | [Full Config Reference](docs/CONFIG.md) |
| Security & threat model | [Security Policy](docs/SECURITY.md) |
| Architecture | [System Design](docs/ARCHITECTURE.md) |
| Adding a new model | [Model Onboarding Playbook](docs/MODEL_ONBOARDING.md) |
| Cloud deployment | [Deployment Guide](docs/CLOUD_DEPLOYMENT.md) |
| Agent integration | [MCP & A2A API](docs/API.md) |
| API key setup | [API Keys](docs/API_KEYS.md) |
| Azure quickstart | [Azure Quickstart](docs/AZURE_QUICKSTART.md) |
| OpenClaw | [Setup & Troubleshooting](docs/OPENCLAW.md) |
| Security ops | [Security Operations](docs/SECURITY_OPS.md) |
| Contributing | [Contribution Guidelines](docs/CONTRIBUTING.md) |
| Vulnerability reporting | [Security](docs/SECURITY.md) |
| Roadmap | [What's Planned](ROADMAP.md) |
| Version plan design docs | [docs/design/](docs/design/README.md) |

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
