# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/blisspixel/primr/badge)](https://securityscorecards.dev/viewer/?uri=github.com/blisspixel/primr)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

**Point it at a company's website. It reads their DNS records, their job postings, and fifty pages of their site, then drafts a strategic brief: what they appear to be building, where they look constrained, and which questions are worth asking.**

Summaries of published articles are a commodity; any chat assistant's deep-research mode produces one. Primr is built for the layer underneath: primary-source signals that aren't in the articles. DNS records reveal the real tech stack. Job postings reveal what a company is actually building right now. The site corpus, external research, and that signal layer get triangulated into a long-form strategic analysis covering competitive positioning, likely economics, operating constraints, and working hypotheses, with confidence labels distinguishing what's confirmed, what's reported, and what's inference. The labels are model-applied and spot-audited for traceability (`primr calibrate`); treat them as editorial discipline, not ground truth.

```
primr "ExampleCo" https://example.co
```

About 31-47 minutes later for the base report, or 37-59 minutes with the default AI strategy add-on: a 23-section strategic analysis as Markdown, TXT, DOCX, and best-effort PDF when a local converter is available, with dense references consolidated at the end. **~$0.76-$0.79 in API costs before AI strategy** when both `GEMINI_API_KEY` and `XAI_API_KEY` are set (Grok 4.3 for reasoning with cached input, Gemini 3.1 Flash-Lite for bulk writing; the v1.24.0 default after a cross-provider eval). The default command includes AI strategy, so dry-run usually reports about **~$0.89-$1.01** with Gemini+XAI depending on platform count. XAI-only setups stay on the legacy Grok-NR writing/utility path at ~$4.36/run before AI strategy, or about ~$5.76 with the default two-platform strategy estimate.

Primr is local-first and CLI-first; it also runs as an MCP server and as agent-host skill guidance so agents can drive it ([details below](#use-primr-from-your-ai-tool)). The long-term backend story is intentionally plural: official account-capacity runners for users who already have sanctioned host allocation; direct provider API keys for reproducible sub-dollar runs; local/gateway models for teams that control their own inference; and premium API paths only when the extra spend buys measured quality.

> **Not a developer?** For today's full local pipeline you need three things: Python, `pip install primr`, and API keys from one or two AI providers. `primr init` walks through all of it. If you already live in an MCP-compatible agent host, Primr can also be operated from that tool. Roadmap work tracks account-capacity stage runners so paid agent subscriptions or workplace-agent allocations can cover compatible LLM work instead of separate API credits where the host officially supports it.

## Why This Exists

Company research is tedious. You visit the website, click around, search the company, read articles, synthesize it all, write it up. That process easily takes 1-2 hours per company and the output is usually unstructured notes. Primr compresses most of that into a single command: you get a structured, sourced draft instead of a blank page. You should still read it critically; it's a head start, not a finished judgment.

## What Makes It Different

- **DNS intelligence pre-flight**: Automatic domain reconnaissance detects cloud platforms, SaaS services, email security, and identity providers from DNS records. Zero API keys, 2-3 seconds. Strategies are grounded in real tech stack data.
- **Hiring-signal gathering**: After the main scrape, Primr discovers open job postings across eight ATS providers (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Workable, Recruitee, Jobvite) plus explicit career / ATS URL inputs for segmented boards, a corpus-driven Workday URL discovery path, an HTML careers-page fallback, and a DuckDuckGo web-search fallback that sweeps LinkedIn / Indeed / Glassdoor / job-board hosts when every other path comes up empty. The pipeline LLM-triages the most signal-rich postings and extracts tech-stack frequency, strategic initiatives, culture cues, and notable absences. Job posts are the most honest statement of what a company is actually building right now; they feed every downstream phase from gap analysis to final strategy and are the primary input to the skill pack subsystem. Skip with `PRIMR_SKIP_HIRING_SIGNALS=1`.
- **Adaptive scraping**: 9 retrieval methods from browser rendering to TLS fingerprinting to screenshot+vision extraction, with per-host optimization. Starts with full browser rendering and falls back through increasingly specialized methods. Some heavily protected sites still win; access is evidence-validated, so a blocked site is reported as blocked rather than silently summarized from nothing.
- **Org-aware site selection**: Link discovery and prioritization now adapt for commercial companies, government sites, nonprofits, education, and healthcare organizations instead of assuming every site looks like a SaaS company.
- **Fail-fast scrape quality gate**: Full/scrape modes now abort when site extraction is too thin, while still preserving short structured pages like contact, leadership, and org-chart references when they carry useful signal (override with `--skip-scrape-validation`).
- **Autonomous external research**: Gemini Deep Research for comprehensive analysis, Grok 4.3 for fast turnaround. Both plan queries, follow leads, cross-validate sources, and synthesize findings.
- **Cost controls built in**: `--dry-run` estimates (including recovery table and stage classifications), `--budget $N` per-run cost ceiling (refuses to start over budget, skips optional stages once actual spend reaches it), usage tracking with per-run cache hit rates in `primr show-usage`, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills, all first-class.
- **Credential optionality by design**: API-keyed cloud runs are the supported direct path today; local OpenAI-compatible endpoints already power $0 eval/utility slices; the roadmap extends the same pipeline to account-capacity runners and full local profiles so users can spend capacity they already have, whether that is sanctioned host allocation or desk-side AI hardware, without pretending either is an ordinary API key.
- **Skill pack generation**: `primr skills "<Company>" <url>` produces a QA-refined Agent Skills pack of up to 15 roles × M skills, grounded in DNS recon + actual job postings + strategic research. Internal pipeline: a two-call role planning step that emits an inspectable `role_plan.md` / `role_plan.json` (observed roles backed by posting citations + plausible roles inferred from research and industry classification, with provenance preserved end-to-end), archetype-grounded authoring with provenance-aware prompts, deterministic ASKILL-* validation, capped refinement loop, and pack-level coherence pass. The bundled archetype catalog covers technical roles plus common business functions such as sales, marketing, people operations, finance, legal/compliance, and operations; weak fuzzy matches stay ungrounded instead of steering authoring into the wrong template family. Emits both an unpacked Claude/Cursor/VS Code tree AND a Microsoft 365 Copilot Cowork sideload `.zip` from the same byte-identical SKILL.md files. Full **operator roster curation**: `--plan-only` to inspect, `--from-plan` to author from a saved plan, `--from-jd` to add a local role brief / job description as hiring evidence, repeatable `--career-url` to point at exact segmented career or ATS boards, `--roles-add` to augment the discovered roster, `--roles-skip` to prune from it (composes with `--from-plan`), `--roles-override` for full control.

## Artifact Model

Primr treats **research artifacts** and **shipping artifacts** as different classes of output. Intermediate research steps such as scrape summaries, gap-analysis notes, source inventories, contradiction findings, and section briefs optimize for consistency, provenance, and parseability. Their formatting matters far less than whether they are complete and structured enough to feed later stages reliably.

Final reports and strategy documents are different. Those artifacts must ship cleanly as Markdown, TXT, DOCX, and best-effort PDF when a local converter is available, so Primr treats them as a stricter output contract with deterministic cleanup, citation normalization, validation gates, and renderer hardening.

In practice that means final-document canonicalization, typed section normalization, ship-time structural gates for dangling citations and section defects, non-blocking scaffolding-leak visibility, and a regression corpus of real-shaped artifacts. The full breakdown is in [Artifact Pipeline](docs/ARTIFACTS.md).

## Modes

> **Cost note (current dry-run):** The base Strategic Overview is now ~$0.76-$0.79/run when both `GEMINI_API_KEY` and `XAI_API_KEY` are set (Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing). The default command also includes AI strategy, which current dry-runs estimate at about ~$0.89 with one strategy platform or ~$1.01 with the two-platform Azure+private fallback. XAI-only setups stay on the legacy ~$4.36/run Grok-NR writing/utility path before strategy, or about ~$5.76 with the default two-platform strategy estimate. The cross-provider default was picked via a real eval on a mid-market public-signal company: 4.4x cheaper than the legacy default with trust gate PASS and faster runtime. See [docs/EVAL_V1_24_0.md](docs/EVAL_V1_24_0.md) for the decision audit. Use `--dry-run` for the current estimate before any billable run.

> **Backend target:** Once backend-freedom wiring is validated, unflagged runs should choose the lowest incremental spend that still clears the measured quality bar: already-paid official host runners or local/gateway capacity when configured and approved, otherwise the best validated sub-dollar API recipe. Premium modes stay explicit and should explain what extra quality or coverage the higher spend is expected to buy.
>
> **4090-class local path:** A single RTX 4090 is good enough to deserve an eval-backed `$0 API vs sub-dollar API` comparison before spending on repeated reports. Primr now names a focused `4090-report-race` local model shortlist for that first pass; the bar is not "local sounds cool," it is whether the local outputs clear the same trust, utility, runtime, and provenance checks as the ~$1 cloud default.

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| `primr skills` | QA-refined skill pack (Claude tree + Cowork .zip) from existing research | ~3 min | ~$0.30 |
| Default command (Gemini + XAI) | Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing + auto AI Strategy | ~34-59 min | **~$0.89-$1.01** |
| Base report only (`--no-ai-strategy`) | Strategic Overview without AI Strategy | ~31-47 min | ~$0.76-$0.79 |
| Default command (XAI only) | Grok 4.3 hybrid + Grok 4.20-NR writing/utility (legacy fallback) + auto AI Strategy | ~37-59 min | ~$5.76 |
| XAI-only base report (`--no-ai-strategy`) | Legacy Grok-NR writing/utility path without AI Strategy | ~31-47 min | ~$4.36 |
| `--platform ms` | Microsoft Azure + NVIDIA private cloud strategy | ~37-59 min | ~$1.01 |
| Default + multi-platform | Add `--platform aws azure` | ~37-59 min | ~$1.01 |
| Default + strategy type | Add `--strategy-type customer_experience` | varies | run `--dry-run` |
| `--grok-tier max` | Grok 4.3 everywhere (deeper reasoning across writing too) | ~35-50 min | ~$3.75 |
| `--premium` | Gemini + Deep Research + AI Strategy | 50-75 min | ~$5 |
| `--premium --platform ms` | Premium + Microsoft/NVIDIA | 75-120 min | $6-9 |
| `--premium --lite` | Pro model instead of DR for AI Strategy | 50-80 min | ~$4 |
| `--mode scrape` | Crawl site + extract insights only | 5-10 min | $0.10 |
| `--mode deep` | Gemini Deep Research on external sources only | 10-15 min | $2.50 |
| `primr recon` | DNS intelligence only (no API keys needed) | 2-3 sec | $0.00 |

The default `primr` command auto-detects: when `XAI_API_KEY` is set, it uses Grok 4.3 for reasoning-heavy stages; when `GEMINI_API_KEY` is also set, bulk writing routes to Gemini 3.1 Flash-Lite for the sub-dollar base report. With XAI only, writing falls back to Grok 4.20-NR. The standard pipeline includes research deepening, cross-validation, trust-polish, citation normalization, constrained-evidence reasoning, and AI strategy unless disabled with `--no-ai-strategy`. Strategy types (`ai`, `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`, `skills`) are YAML-defined and auto-discovered; run `primr --list-strategies` for details. DDG searches are free. Use `--dry-run` for accurate cost estimates.

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
primr skills "ExampleCo" --from-jd path/to/job-description.md --roles-override "Licensing Operations Analyst"  # JD-only single-role draft
primr skills "ExampleCo" --career-url https://jobs.example.co/corporate --career-url https://boards.greenhouse.io/exampleco  # segmented hiring evidence
primr skills "ExampleCo" https://example.co --allow-recon-only           # proceed when no postings + no research
primr skills "ExampleCo" https://example.co --dry-run                    # estimate first
```

The skill pack output contains both a `roles/<slug>/SKILL.md` tree (drop-in for Claude Code, Cursor, VS Code Copilot, Gemini CLI, Junie) and a `<Company>_Cowork_Pack.zip` (sideload via M365 Admin Center > Manage Apps > Upload custom app). Generated `SKILL.md` files use clean `name` + `description` frontmatter by default, with optional metadata available through `--emit-agent-metadata`. Each authored skill also receives a deterministic `references/role-family.md` file shared across the role family, so role evidence, archetype capabilities, and cross-skill terminology stay consistent instead of being re-authored per skill. `--from-jd` materializes a sanitized local JD / role brief into `_hiring/operator_role_brief.md`; it is evidence for role planning and authoring, not an instruction payload or a report section. `--career-url` values are exact hiring-source hints; Primr fetches each through the existing SSRF guard, parses direct ATS boards when possible, merges multiple valid board slices, and uses the resulting postings as hiring evidence. Each pack also emits a markdown pack report with the validation scorecard, per-role refinement counts, observed/plausible split, posting-coverage warning when the observed postings look like a partial enterprise career-site slice, Cowork packaging cap visibility, and role-plan reference. The planning step writes `role_plan.md` and `role_plan.json` into the working directory before authoring so operators can audit which roles came from actual postings or role briefs vs which were inferred from research and industry classification. Cowork plugin zips cap `agentSkills` at 20, so larger packs keep the full Claude/Cursor tree and include the first valid 20 skills in the Cowork sideload.

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

PASS | 23 chapters | 48 citations | ~$0.89
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
primr keys set openai           # optional GPT/o-series provider
primr keys set anthropic        # optional Claude provider
primr keys list
primr keys path

# Diagnose, then launch guided fixes if needed
primr doctor --fix

# Local .env files and shell env vars are also supported:
XAI_API_KEY=          # Grok standard reasoning + strategy
GEMINI_API_KEY=       # Gemini writing/utility, premium mode, cheapest default writer with XAI
OPENAI_API_KEY=       # Optional OpenAI fallback for utility, writing, reasoning
ANTHROPIC_API_KEY=    # Optional Anthropic fallback for writing/reasoning
OLLAMA_BASE_URL=      # Optional local OpenAI-compatible endpoint for local eval/utility paths
```

Web search uses DuckDuckGo by default, no key needed.
Provider-aware routing is opt-in by configured key today: the measured default is Grok + Gemini, while OpenAI and Anthropic are wired in the provider layer and dry-run estimator for users who already have those accounts. A pure capability router now exists for stage-level cloud, gateway, host-agent, and local candidate planning, and `primr doctor` shows sanitized provider availability from the same generic snapshots. Full-report execution still uses the role router until the backend-freedom wiring is validated. Full no-xAI report execution still has runtime preflight and continuous-reasoning work tracked in the roadmap. Ollama and other OpenAI-compatible local endpoints are wired for local utility and eval paths while the full $0 API local report profile remains tracked there too.

Credential modes are deliberately separate:

- **Direct API mode**: Primr owns the LLM calls and bills through configured provider keys. This is the supported full-report path today; the target default is the best validated sub-dollar recipe when no zero-incremental runner is configured.
- **Agent-hosted mode**: MCP-compatible agent hosts can operate Primr through its tools and skill guidance. The host account pays for the surrounding agent work, but the current full internal report pipeline still uses Primr provider keys.
- **Account-capacity runner mode**: planned under backend freedom. Primr will hand bounded stage packets to official account-capacity runners where supported, such as authenticated CLI agents or sanctioned host connectors. This is not API-key reuse, browser scraping, or an unofficial proxy. Because plan usage and API-credit handoff are account policy, enabling this as part of default routing requires explicit operator opt-in.
- **Local/gateway mode**: planned for full runs, already partly used for eval/utility paths. Primr talks to OpenAI-compatible local servers or enterprise gateways and validates quality before advertising a recipe. Local mode is the true $0 API path. It may start as slower or stage-limited on today's hardware, but the routing/eval design treats local capacity as a first-class path that can improve into the default as desktop AI hardware improves.

[Full config reference](docs/CONFIG.md) | [API key setup](docs/API_KEYS.md)

## Use primr from your AI tool

primr ships with an `AGENTS.md` (auto-loaded by Kiro, Codex, Aider, Jules), a Claude Code plugin under [`claude-code/`](claude-code/), and per-host MCP snippets under [`clients/`](clients/) for Cursor, Windsurf, VS Code + Copilot, and Claude Desktop. These integrations let your agent host run Primr with the same cost gate and async lifecycle rules. Direct model execution inside Primr still follows the credential mode above.

Account-capacity hosts are tracked only where they provide official automation, local CLI, hooks, or connector interfaces. Primr's roadmap treats these as bounded host-agent runners, not provider API keys and not repo-owned credentials.

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

These skills are thin intent routers over Primr MCP rather than separate product definitions. Generic MCP clients can also use `primr://agent/governance`, `primr://research/next-actions`, `primr://agent/audit/recent`, and the `governed_execution` prompt to follow the same estimate/approval/monitor/audit pattern.
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

9,000+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, 80%+ branch coverage enforced as a CI ratchet, and OpenTelemetry tracing. CI runs lint, type check, security gates, and tests on every push.

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

Apache 2.0 (see [LICENSE](LICENSE)). Free to use, build on, fork, and share.
