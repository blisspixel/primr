# Primr Roadmap

Current State: v1.16.0 (March 2026)

Primr is a CLI-first, local research tool for company intelligence and strategic analysis. It aims to accelerate research workflows while being transparent about uncertainty.

The design is intentionally opinionated and local-first. This roadmap reflects planned improvements ordered to build toward Primr's role as research infrastructure — the foundation that tools like [Deepr](https://github.com/blisspixel/deepr) route through for company intelligence.

For completed work, see the [Changelog](#changelog) at the bottom of this file, or check [GitHub releases](https://github.com/blisspixel/primr/releases) for the latest.

## What's Working Today

### Research Engines

**Scrape Mode**: 8-tier web scraping with intelligent escalation (browser-first):
- Browser tiers: Playwright, Playwright aggressive
- TLS impersonation: curl_cffi (tier 3 — tried before stealth browsers)
- Stealth browser tiers: DrissionPage stealth, DrissionPage (driverless CDP)
- Vision tier: Screenshot + LLM extraction for image-heavy pages (enabled by default, can be disabled)
- HTTP tiers: httpx, requests
- Content-type routing: automatic PDF detection and LLM-powered extraction with PyMuPDF fallback
- Reader-mode content extraction (BeautifulSoup-based, removes boilerplate)
- Content quality validation (catches garbage pages, triggers escalation)
- Homepage-first link discovery (fresher than sitemaps)
- Sticky tier optimization (reuses working tier for same host)
- Circuit breaker pattern (skips failing tiers after 3 failures)
- Soft block detection (catches "200 OK" traps, browser blocks)

**Deep Mode**: Gemini Deep Research Agent with autonomous multi-step search and synthesis

**Standard Mode** (default when `XAI_API_KEY` set): Grok 4.1 pipeline with research deepening, parallel section writing, cross-validation, coherence pass, and strategy enrichment. ~30 min, ~$0.55.

**Premium Mode** (`--premium`): Gemini + Deep Research pipeline for maximum depth. ~50-75 min, ~$5.

### AI Strategy & Report Generation

- AI strategy and roadmap generation with multi-vendor support (`--cloud-vendor aws azure`)
- Cloud vendor options: Azure, AWS, GCP, agnostic, private (NVIDIA/on-prem)
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric
- Strategy enrichment: cross-validation, evidence search, section regeneration, and polish pass
- TXT, DOCX, and PDF outputs with citation styles
- 23-section reports with adaptive section selection, deduplication, and cross-validation

### Agent Integration

- MCP server (stdio + HTTP with JWT auth)
- A2A protocol (standalone or co-hosted with MCP)
- OpenClaw integration with skills and workflows
- Claude Skills directory

### Operational Maturity

- Cost estimation, usage tracking, job recovery, crash/reboot recovery
- System diagnostics (`primr doctor`)
- 4,500+ tests, full ruff and mypy compliance
- Serverless cloud deployment (AWS, Azure, GCP)
- Agentic architecture: hypothesis tracking, subagents, hooks, orchestrator
- Content sanitization for prompt injection protection

## Design Philosophy

- Structured output over raw data — briefs you can act on, not link dumps
- Hypothesis generation over premature conclusions — confidence levels on every claim
- Transparency about uncertainty — what's confirmed, what's inferred, what's speculation
- Deterministic verification before AI judgment — check structure, citations, and epistemic labels with code before asking a model to score prose quality
- Local-first, CLI-first — your data stays on your machine

Primr is intentionally not designed as a generic web scraper, a SaaS collaboration platform, or a presentation builder.

---

## Planned Work

Ordered to build toward Primr as research infrastructure: first make output better and cheaper, then add trust and speed, then enable compounding knowledge and expert-level intelligence. Each layer feeds the next — and feeds Deepr's routing, expert learning, and batch orchestration.

### Phase 1: Quality Foundation

Make individual reports better and prove it with data.

#### v1.13.0 — QA-Driven Report Iteration

Goal: Use QA feedback to iteratively improve weak sections until reports hit 90+.

**Deterministic Verification (Complete):**

Added code-level quality checks that run before (or instead of) AI-based scoring, validated by SkillsBench research (arXiv:2602.12670) showing deterministic checks outperform model-only evaluation for structural quality:

- **Hypothesis coverage**: Counts `(Hypothesis)` labels and validation phrases (`we hypothesize`, `to validate`, `worth validating`) with report-type thresholds
- **Confidence labels**: Counts all four epistemic labels `(Confirmed)`, `(Reported)`, `(Estimated)`, `(Hypothesis)` plus hedging phrases from `epistemic_rules.yaml`
- **Section length analysis**: Flags truncated sections (< 50 words) that indicate incomplete generation
- **Citation density**: Citations per 1000 words with type-specific thresholds (3.0 strategic, 2.0 AI strategy)
- **Report-type-aware structure**: Different required-section checklists for strategic_overview vs ai_strategy
- `QAGateHook` upgraded from 3 inline checks to `ReportAnalyzer`-backed scoring (6 checks, penalty system)
- `QASubagent` expanded from 5 to 7 quality dimensions with new `hypothesis_framing` and `confidence_labels` scores

**Iteration Workflow (Planned):**
1. Generate report
2. Run QA, get feedback on specific weak sections
3. Re-run just those sections with targeted improvements
4. Repeat until grade >= 90

Learny validated this pattern: their quality loop (grade -> specific feedback -> regenerate) across 286 documents achieved 98.6% A-grade. The key insight: feedback must be *specific* ("section X lacks quantified metrics") not generic ("improve quality").

Implementation:
- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work
- Section-level regeneration without full pipeline re-run

#### v1.13.1 — Versioned Model Evaluation Harness

Goal: Make model/profile upgrades measurable and repeatable before changing defaults.

Problem this solves:
- New model releases (for example Pro/Flash/Grok variants) are hard to compare consistently
- Teams need a defensible quality/cost decision, not anecdotal "looks better"

Planned capabilities:
- `primr eval` workflow to run a fixed company corpus across profiles (for example `full`, `full --lite`, `--fast`)
- Versioned evaluation IDs (for example `eval-2026-02-r1`) with immutable run manifests
- Aggregated scorecard per profile: cost, runtime, document length, citation density, required-section completeness, confidence-label coverage
- Side-by-side comparison output (Markdown + CSV) for baseline vs candidate profiles
- Configurable acceptance gates (example: quality >= 80% baseline and cost <= 20% baseline)
- CI guard for regression detection on a lightweight fixture corpus

Success criteria:
- Model default changes are backed by saved scorecards, not one-off manual judgment
- Users can answer "is this new model worth it?" in one command with reproducible evidence

#### v1.13.1b — True Quick Mode

Goal: Add a real quick profile that finishes in under 5 minutes for most companies. This becomes the cheap routing tier that Deepr auto-routes to for simple lookups.

Scope:
- New CLI profile (`--quick`) with explicit runtime budget and reduced token/search footprint
- Tight phase budget: fewer sections, capped external queries, and smaller synthesis context
- Quality floor + graceful fallback when evidence is thin
- Eval-harness benchmark vs standard mode for utility-per-minute and utility-per-dollar

Success criteria:
- Median runtime < 5 minutes on eval corpus
- Produces a usable briefing artifact with citations and explicit confidence labels
- Users can choose between `quick` (speed), `standard` (balanced), and `premium` (depth) tiers

### Phase 2: Multi-Provider & Speed

More provider options and faster execution. These directly feed Deepr's auto-routing — more providers means smarter routing decisions.

#### v1.13.2 — OpenAI Deep Research Integration

Goal: Add OpenAI's Deep Research API as an alternative research backend, giving users a third provider option alongside Grok and Gemini.

**Motivation:** OpenAI's Deep Research API offers a different cost/depth/speed tradeoff. Adding it unlocks better defaults — the eval harness (v1.13.1) can determine which provider wins at each tier (quick, standard, premium) based on real data instead of assumptions.

**Research Tiers:**
- **Quick**: Lightweight OpenAI Deep Research call for fast external research (potential replacement for DDG search + scrape in standard mode)
- **Full**: Full-depth OpenAI Deep Research for comprehensive analysis (potential `--premium` alternative to Gemini DR)

**Implementation:**
- `OPENAI_API_KEY` env var support
- OpenAI Deep Research client in `src/primr/ai/`
- `--provider openai` flag (or auto-detect from available keys)
- Cost estimator updated with OpenAI DR pricing
- Shared deep research parsing/polling modules extended for OpenAI response format

**Decision:** Which tier(s) OpenAI DR best serves (quick, standard, premium) will be determined by eval results from v1.13.1, not by assumption.

#### v1.13.3 — Cross-Provider Eval and Tier Optimization

Goal: Extend the eval harness to compare all available providers and determine the best default for each research tier.

**Motivation:** With three providers (Grok, Gemini, OpenAI), the eval system should answer: what's the best option for quick runs, standard runs, and premium runs? These answers should be data-driven, not hardcoded.

**Planned capabilities:**
- Eval profiles expanded: `grok-standard`, `gemini-premium`, `openai-quick`, `openai-full`, etc.
- Cross-provider scorecard: quality, cost, runtime, citation density compared side-by-side
- Tier recommendation output: "For quick: use X, for standard: use Y, for premium: use Z"
- Auto-detect available API keys and only eval providers the user has access to
- Historical eval tracking: compare across eval IDs to see if a provider improved over time

**Success criteria:**
- `primr eval` can answer "which provider should be my default?" with evidence
- Tier defaults (quick/standard/premium) are backed by saved scorecards across providers

#### v1.17.0 — Pipeline Overlap and Scraper Observability

Goal: Reduce end-to-end runtime by overlapping independent pipeline phases, and add per-tier metrics for data-driven scraper tuning.

**What's already parallel (no changes needed):**
- Section writing: `ThreadPoolExecutor(max_workers=4)` — up to 4 Grok sections concurrently
- External search queries: `ThreadPoolExecutor(max_workers=3)` — 3 concurrent DDG/Google queries
- Per-host rate limiting: 2 concurrent/host, 20 req/min/host, with 0-1.5s random jitter

**Why same-host scraping stays sequential:**
All 50 pages in a run come from one company website. Blasting concurrent requests to the same host is a bot detection signal. The current approach — sequential with per-host jitter (0-1.5s random delays), sticky tier optimization, and circuit breakers — mimics human browsing. The rate limiter already caps at 2 concurrent per host, but in practice sequential-with-jitter is what avoids WAF blocks, Cloudflare challenges, and fingerprint-based bot detection. This is an intentional design choice, not a limitation.

**Phase Overlap (the real runtime win):**
- Current: scrape all 50 pages -> THEN start external search -> THEN summarize
- Upgrade: start external search after homepage content is available (don't wait for all 50 pages)
- External searches hit different hosts (DDG, news sites, press releases) — safe to run alongside primary site scraping
- Insight extraction can begin on early pages while later pages are still scraping
- Simple scheduling with `asyncio.gather()` — no orchestration framework needed
- Pattern from [Anthropic's multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system): parallelism at the execution level, not the architecture level
- Expected gain: 5-10 min overlap between scraping and external research phases

**Completion Guarantees:**
- All overlapped phases must complete before downstream stages start (no partial results)
- `asyncio.gather(return_exceptions=True)` with explicit error handling
- Run state tracks per-phase completion status for crash recovery
- Progress display updated to show concurrent phases (e.g., "Scraping 23/50 | Searching 4/10")

**Scraper Tier Metrics:**
- Per-tier success rate, latency p95, and content quality score
- Stored in run state JSON for post-hoc analysis
- `primr doctor --scraper-stats` to show tier performance across recent runs
- Informs sticky tier policy and circuit breaker thresholds

**OpenTelemetry Spans:**
- Add spans per scrape tier attempt and per search query
- Trace scraping -> extraction -> summarization flow end-to-end
- Compatible with existing OTel setup

### Phase 3: Trust & Richer Data

Verify claims independently and extract more from visual content. Trust scoring feeds Deepr's source trust decisions and expert confidence tracking.

#### v1.18.0 — Verification Agent and Trust Scoring

Goal: Add a post-QA "skeptic" pass that actively disputes claims using fresh web searches, producing auditable trust scores.

**Skeptic Agent (orchestrator-worker pattern):**
- After QA pass, a lead verifier extracts all claims with confidence > 0.6
- Spawns parallel worker searches (DDG) to challenge each claim — different hosts, safe to parallelize
- Workers return evidence; lead verifier compares against report claims
- Produces a delta report: confirmed, disputed, unverifiable
- Pattern matches [Anthropic's production research system](https://www.anthropic.com/engineering/multi-agent-research-system): lead agent + parallel subagents, synchronous gather
- Opt-in via `--verify` flag (adds 5-10 min, negligible cost since DDG is free)
- Trust score: percentage of claims independently verified

**Trust Score in Output:**
- Report header includes verification summary (e.g., "Trust: 94% verified, 3% disputed, 3% unverifiable")
- Disputed claims get inline annotations with counter-evidence
- QA score incorporates verification results

**Implementation:**
- New `VerifierSubagent` in agentic/subagents.py
- Orchestrator stage: `IDLE -> SCRAPING -> ANALYZING -> WRITING -> QA -> VERIFYING -> COMPLETED`
- Hooks: `VerificationGateHook` can block output if trust < configurable threshold

#### v1.19.0 — First-Class VLM Extraction

Goal: Promote vision extraction from fallback tier to first-class path for data-dense pages (charts, tables, IR decks, org charts).

**Motivation:** Corporate sites in 2026 are increasingly visual — investor relations decks, product comparison matrices, org charts, and pricing tables are often images or rendered graphics that pure-text extraction misses entirely. The vision tier (tier 6) already works but only triggers after 5 other tiers fail.

**Smart VLM Routing:**
- Content-type detection identifies pages likely to be data-dense (PDF, pages with high image-to-text ratio)
- Route those pages directly to VLM extraction alongside (not instead of) text extraction
- LLM reconciliation merges text + VLM outputs, preferring structured data from VLM
- No change to existing tier fallback for text-heavy pages

**Structured Extraction:**
- VLM prompt optimized for tables, org charts, and financial data
- Output as structured JSON (not just prose description)
- Table data extracted to markdown tables in report sections

**Cost Control:**
- VLM extraction is more expensive per page — only trigger on high-value pages
- `--vlm-budget N` flag to cap VLM calls per run (default: 10 pages)
- Cost estimator updated with VLM pricing

### Phase 4: Compounding Knowledge

Make research compound across runs. This is where Learny's patterns pay off most — and where Primr becomes the knowledge layer that Deepr experts build on.

#### v1.20.0 — Cross-Run Research Memory

Goal: Make research compound across runs by persisting extracted claims, citations, and hypotheses in a searchable store.

**Motivation:** Currently each run starts fresh. If you research 50 companies in the same industry, each run rediscovers the same industry context. Cross-run memory enables meta-research ("show AI strategy evolution across all fintech targets") and few-shot learning for new verticals.

Learny proved this pattern at scale: their Stage 3 builds a corpus-wide knowledge base from ALL documents, then every subsequent analysis has full context. The same principle applies across Primr runs — industry context discovered in run 1 should inform run 50.

**Implementation:**
- SQLite-backed claim store (no external dependencies like Neo4j/Redis)
- Each claim stored with: company, section, text, confidence, citations, timestamp, embedding
- Embedding via local model (sentence-transformers) or API (Gemini embedding)
- `primr memory search "AI strategy fintech"` to query across all past runs
- `primr memory timeline "Company"` to show how understanding evolved across runs

**Research Priming:**
- When starting a new run, query memory for related companies/industries
- Inject relevant prior findings as context for the analysis stage
- Reduces redundant research and improves hypothesis quality for repeat verticals

**Privacy:**
- All data stays local (SQLite file in working directory)
- `primr memory clear` to reset
- No data leaves the machine unless user explicitly exports

#### v1.20.1 — Industry Knowledge Base for Batch Runs

Goal: When researching multiple companies in the same industry, build shared industry context first, then analyze each company with that context.

**Motivation:** Direct port of Learny's most powerful pattern. Learny's Stage 3 (Synthesis) builds a knowledge base from ALL extracted facts before any individual analysis runs. For Primr batch runs, this means: scrape all companies first, build an industry synthesis (themes, trends, common tech stacks, competitive dynamics), then inject that context into each company's analysis.

A company's positioning makes more sense when you know what the industry looks like. "Company X uses Kubernetes" is unremarkable if every company in the batch does. "Company X still runs bare-metal" is remarkable if nobody else does.

**Implementation:**
- `--batch companies.csv --industry-context` flag
- Phase 0: scrape all companies (existing batch behavior)
- Phase 0.5 (new): synthesize industry-wide patterns from all scrape results
  - Themes, trends, common tech stacks, competitive dynamics
  - Cost: one extra synthesis call (~$0.05), reused across all company analyses
- Phase 1+: each company analysis receives industry context as additional input
- Industry synthesis saved as a reusable artifact

**Stage Invariants (from Learny):**
- Industry synthesis may identify patterns and contradictions but may NOT introduce claims not present in scraped data
- Individual company analysis may interpret with industry context but must cite specific scraped content
- These invariants prevent hallucination propagation across the batch

#### v1.20.2 — Refinement and Learning Loop

Goal: Support post-discovery learning without re-running everything from scratch. This is the primitive that enables Deepr experts to learn over time.

- `primr refine` command accepting new information, notes, and follow-up findings
- Re-synthesize insights with updated confidence and revised hypotheses
- Outputs evolve as understanding deepens
- Cross-run memory (v1.20.0) stores the evolution

### Phase 5: Expert-Level Intelligence

Add perspective and narrative depth. These features directly feed Deepr's expert system — expert personas become Deepr domain experts, and narrative evolution becomes expert knowledge tracking.

#### v1.21.0 — Expert Perspective Passes

Goal: After standard pipeline, run parallel "expert review" passes that scrutinize findings from specific domain perspectives.

**Motivation:** Learny generates multi-perspective insights (business leaders, architects, developers, product teams) for every document. Primr can do the same: the report is the shared artifact, and each expert persona is a prompt that reviews it from a specific angle.

**Expert Personas:**
- **CFO perspective**: scrutinize financial claims, flag unsupported revenue estimates, assess unit economics
- **CTO perspective**: evaluate technology stack claims, assess technical moat, identify build-vs-buy signals
- **Competitive analyst**: compare findings against known competitors (from memory if available), identify positioning gaps
- **Risk analyst**: identify regulatory, market, and execution risks

**Implementation:**
- Each expert is a prompt persona + the same report, producing a short addendum
- Spawn 3-4 parallel expert reviews (different prompts, same input) via existing ThreadPoolExecutor
- Output: "Expert Perspectives" section appended to report, or separate sidecar document
- `--with-experts` flag (opt-in, adds ~$0.10-0.20 for 3-4 Grok passes)
- Expert findings feed back into cross-run memory as tagged claims

**Connection to Deepr:** Expert perspectives are the read-only version of what Deepr experts do. A Primr expert pass produces a one-shot assessment; a Deepr expert accumulates those assessments across sessions and fills its own gaps. Primr expert passes can seed Deepr experts with initial domain knowledge.

#### v1.22.0 — POV and Narrative Evolution

Goal: Make Primr the system of record for how thinking evolves about a company.

- Versioned research artifacts
- Explicit "what changed and why" sections
- Optional narrative framing outputs
- Diff-style comparison between runs: what shifted in confidence, what new evidence appeared
- Timeline view: how understanding of a company evolved across runs

This feeds Deepr's expert knowledge tracking — experts don't just know facts, they know how understanding has changed over time.

### Phase 6: Release

#### v2.0.0 — Public Release

Goal: Make Primr available to the broader community via PyPI.

**Prerequisites:**
- v1.8.1 Content Sanitization Layer (complete - security requirement satisfied)

**Scope:**
- PyPI publication (`pip install primr`)
- Public GitHub repository
- ~~GitHub Actions CI/CD for automated testing~~ (done - lint, type check, tests run on every push)
- Contribution workflow for external contributors
- Documentation site

---

## Why Not a Research DAG / LangGraph-Style Orchestration?

The QA feedback suggested replacing the linear pipeline with a DAG orchestration layer (LangGraph-style). After researching production experiences, we decided against this:

**What the research shows:**
- [Anthropic's own multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) does NOT use a DAG — it's a simple orchestrator-worker pattern (lead agent spawns 3-5 subagents in parallel, waits, synthesizes). They got 90% speed improvement purely from parallelism, not graph orchestration.
- Multi-agent systems use ~15x more tokens than single-agent ([LangChain State of Agents](https://www.langchain.com/state-of-agent-engineering)), which directly conflicts with Primr's $0.55 value proposition.
- [Production teams report](https://dev.to/isaachagoel/read-this-before-building-ai-agents-lessons-from-the-trenches-333i) the golden rule: "Can I code this without losing functionality?" Mechanical tasks (scraping, search) should be code, not agent orchestration.
- [Community consensus](https://community.latenode.com/t/coordinating-multiple-ai-agents-for-scraping-validation-and-reporting-does-the-complexity-actually-pay-off/60040): keep simple pipelines simple; multi-agent DAGs only justified for horizontal scaling or dynamic replanning.

**What Primr actually needs:**
The real bottlenecks are sequential page scraping and sequential search queries — both fixed with `asyncio.gather()` in v1.17.0, no framework required. The verification agent (v1.18.0) is a single new pipeline stage, not a graph node. Phase overlap (external search starting after homepage instead of after all pages) is a scheduling optimization, not an architectural change.

**The decision:** Invest in targeted parallelism (v1.17.0) and a verification stage (v1.18.0) rather than a DAG framework. This matches how the best production research systems actually work — simple orchestration with parallel execution where it matters — while keeping Primr maintainable as a solo project.

## Scale Readiness (Implemented in v1.6.0)

Primr now supports serverless cloud deployment for organizational adoption:

- **Execution model**: Job-based ephemeral containers (Fargate/Container Apps/Cloud Run Jobs)
- **Interface model**: REST API control plane + CLI preserved for local use
- **Reliability**: Event-driven queues, dead-letter handling, state reconciliation
- **Cost control**: Scale-to-zero, per-API-key quotas, cost estimation on submit
- **Governance**: Centralized secrets management, audit logging, manifest trail

See [docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) for deployment guide.

## Explicitly Deferred (By Design)

These are conscious non-goals for now:

**Web Interface**
- Browser-based submission
- Job dashboards

**Collaboration and Sharing**
- Accounts, permissions, comments
- Sharing reports externally

## TODO: README Assets

These require running the tool and capturing output manually:

- [ ] Record a terminal GIF of a real research run (asciinema or vhs) for the top of the README
- [ ] Screenshot a DOCX report to show the formatted output
- [ ] Update `docs/images/primr-demo.png` with a current screenshot (existing one is from an older version)

## Usage Reference

```bash
# Basic usage (auto-uses Grok 4.1 when XAI_API_KEY set)
primr "ExampleCo" https://example.co

# Research modes
primr "ExampleCo" https://example.co --mode scrape
primr "ExampleCo" https://example.co --mode deep
primr "ExampleCo" https://example.co --premium  # Gemini + Deep Research

# AI Strategy
primr "ExampleCo" https://example.co --cloud-vendor azure
primr "ExampleCo" https://example.co --cloud-vendor aws azure  # Multi-vendor
primr "ExampleCo" https://example.co --cloud-vendor azure private  # Azure + private cloud
primr "ExampleCo" https://example.co --no-ai-strategy

# Retry AI Strategy
primr --ai-strategy-only "output/ExampleCo_Strategic_Overview.md"

# Job management
primr --check-jobs
primr --clear-jobs

# Operations
primr doctor
primr "ExampleCo" https://example.co --dry-run

# MCP Server
primr-mcp --stdio
primr-mcp --http --port 8000

# A2A Server
primr-a2a --no-auth                        # Standalone A2A on port 9000
primr-mcp --http --a2a                     # Co-hosted MCP + A2A

# Cloud Deployment
cd deploy/aws && ./deploy.sh -d prod deploy
cd deploy/aws && ./deploy.sh -d prod destroy
```

---

## Changelog

For the latest changes, check [GitHub releases](https://github.com/blisspixel/primr/releases).

| Version | Date | Highlights |
|---------|------|------------|
| unreleased | Mar 2026 | Private cloud vendor (NVIDIA-first, on-prem AI strategy) |
| unreleased | Mar 2026 | A2A protocol integration (client, server, executor, hooks, 165 tests) |
| unreleased | Mar 2026 | Fast mode as default, `--premium` flag, quality improvements, strategy enrichment, startup banner, all strategy types in fast mode, output improve mode |
| unreleased | Mar 2026 | Agentic pipeline, report quality fixes (duplicate elimination, coherence rewrite, contradiction resolution), adaptive search depth, source quality filtering, dynamic section selection, 2 new report sections (23 total), stronger QA gate |
| unreleased | Feb 2026 | Deep-research refactor, scrape reliability hardening, shared error policy, warning reduction, eval workflow, Gemini 3.1 Pro, tiered pricing |
| 1.12.1 | Feb 2026 | Scraping robustness, PDF routing, bug fixes |
| 1.12.0 | Feb 2026 | Multi-cloud-vendor AI strategy |
| 1.11.2 | Feb 2026 | SharedBrowser, ETA progress, UI polish |
| 1.11.1 | Feb 2026 | Deep Research progress visibility and failure recovery |
| 1.11.0 | Feb 2026 | Interactive research mode, expanded external search, MCP progress subscriptions |
| 1.8.1 | Feb 2026 | Content sanitization for prompt injection protection |
| 1.7.0 | Feb 2026 | Agentic architecture (memory, hooks, orchestrator, subagents, skills, property tests) |
| 1.6.0 | Feb 2026 | Serverless cloud deployment (AWS/Azure/GCP) |
| 1.5.1 | Feb 2026 | Code quality fixes, full ruff compliance |
| 1.5.0 | Feb 2026 | Typed error hierarchy, circuit breaker, OpenTelemetry, property tests |
| 1.4.1 | Feb 2026 | Open Claw integration |
| 1.4.0 | Feb 2026 | MCP Server for AI agent integration |
| 1.3.1 | Jan 2026 | Resource cleanup, File Search Store billing fix |
| 1.3.0 | Jan 2026 | Python 3.11+ requirement |
| 1.2.0 | Jan 2026 | Test coverage, security review |
| 1.1.1 | Jan 2026 | Reader-mode extraction, vision tier |
| 1.1.0 | Jan 2026 | Browser-first discovery, LLM link selection |
| 1.0.0 | Dec 2025 | Rebrand to Primr, pip installable |
| 0.5.0 | Dec 2025 | Cost tracking, job recovery |
| 0.4.0 | Dec 2025 | AI Strategy generation |
| 0.3.0 | Dec 2025 | Full mode (two-step) |
| 0.2.0 | Nov 2025 | Deep Research integration |
| 0.1.0 | Nov 2025 | Core research pipeline |

<details>
<summary><strong>Detailed changelog for unreleased work</strong></summary>

### Post-v1.12.1 — Reliability, Maintainability, and Model Updates

**Deep Research Refactor:**
- Extracted shared deep research parsing helpers to `src/primr/ai/deep_research_parsing.py`
- Extracted adaptive polling policy helpers to `src/primr/ai/deep_research_polling.py`
- Extracted shared polling execution engine to `src/primr/ai/deep_research_execution.py`
- Refactored polling loops in deep research clients/orchestrators to use shared execution logic
- Enforced `store=True` for background Deep Research interactions to support durable async recovery
- Improved `primr --check-jobs` diagnostics to separate provider terminal failures from local status-check connectivity errors
- Added `primr --resume-latest` / `--resume-jobs` one-shot recovery flow
- Added `--resume-local` to reuse latest incomplete local working folders
- Added richer pending-job metadata capture (company/vendor/report kind)
- Added per-run `_run_state.json` phase/status timeline

**AI Error Policy Refactor:**
- Extracted shared error classification policy to `src/primr/ai/error_policy.py`
- Unified sync/async AI client retry classification through the shared policy module

**Flaky/Integration Warning Reduction:**
- Hardened handling around Playwright subprocess permission constraints in tests
- Hardened handling around network-restricted AI integration tests

**Scraping Reliability Hardening:**
- Adaptive lazy-load scrolling for Playwright tiers (up to 20 steps, early stop when page height stabilizes)
- Strict scrape-quality validation gate with `--skip-scrape-validation` override
- `_raw_scrapes/_scrape_trace.log` with per-page `OK/FAIL/DUP` outcomes
- External search caps: `MAX_EXTERNAL_SEARCH_QUERIES`, `MAX_EXTERNAL_SOURCES`

**Gemini 3.1 Pro Preview:**
- Registered `gemini-3.1-pro-preview` and `gemini-3.1-pro-preview-customtools` in ModelRegistry
- Tiered pricing support in `ModelConfig`

**Versioned Eval Workflow (Initial):**
- `primr --eval` command for offline, versioned profile comparison
- Scorecards at `output/evals/<eval-id>/scorecard.md` and `scorecard.csv`
- Auto-stages existing local reports (no API spend)
- Optional `--eval-run-missing` with explicit spend caps

### Fast Mode Default + Quality Improvements

**Mode Renaming:**
- Default `primr` command auto-detects: Grok 4.1 when `XAI_API_KEY` set, Gemini fallback
- `--premium` flag for Gemini + Deep Research
- MCP server accepts `"premium"` mode

**Quality Improvements:**
- Coherence pass rewritten to be surgical (cross-references only, not content deletion)
- Executive summary written last (after all other sections, with full report context)
- Parallel external source search (`ThreadPoolExecutor(max_workers=3)`)
- Robust cross-validation JSON parsing with retry and regex fallback
- Framework section word targets raised from 600 to 800

**Strategy Enrichment Pass:**
- Cross-validation, targeted DDG search, section regeneration, polish pass
- Strategy `max_tokens` raised from 16K to 32K
- Strategy context enriched with insights, gap analysis, and analysis workbook

**Output Improve Mode:**
- Deterministic output cleanup in default pipeline
- `primr improve <path>` standalone command
- `--improve-agentic` for agentic review + deterministic cleanup
- `--in-place` for safe overwrite

**Startup Banner:**
- Default-on for interactive terminals
- CLI: `--banner [auto|off|static|animated]`, `--no-banner`
- Env: `PRIMR_BANNER`, `PRIMR_NO_BANNER`, `PRIMR_BANNER_DURATION_MS`

**All Strategy Types in Fast Mode:**
- `--strategy-type` works during research runs
- YAML-based strategy configs auto-discovered at runtime

### Agentic Pipeline + Report Quality + New Sections

**Bug Fixes:**
- Duplicate section elimination
- Coherence pass rewrite (guard threshold 0.92 -> 0.96, eliminates catastrophic word-loss)
- Contradiction resolution during cross-validation

**UX Improvements:**
- Domain shown in progress
- Cleaner mode message
- Search sub-progress (live queries/results/validated counts)

**Agentic Behavior:**
- Adaptive search depth based on data richness
- Source quality filtering (LLM reviews, drops low-relevance)
- Dynamic section selection (skips sections with zero evidence signals)

**New Report Sections (23 total):**
- Industry Outlook (near/medium/long-term trends)
- Strategic Leadership Perspective (simulated board meeting)

**Stronger QA Gate:**
- Checks for duplicate headings and thin sections
- `dupes=` and `thin=` counts in display

### A2A Protocol Integration (v1.16.0)

**A2A Server:**
- AgentCard at `/.well-known/agent.json` with 5 skills
- `PrimrAgentExecutor` bridges A2A to pipeline runner
- Standalone `primr-a2a` or co-hosted `primr-mcp --http --a2a`

**A2A Client:**
- `delegate_to_agent` MCP tool
- `A2AClient` with httpx: discover, send, stream, get, cancel
- Governance hooks: SSRF, cost budget, content sanitization

**Testing:** 165 tests, 76% coverage across 9 modules

</details>

## Final Note

Primr is a tool for understanding companies. The focus is on useful output, not user growth.

## Disclaimer

**Legal Compliance**: Users are responsible for ensuring their use of Primr complies with applicable laws, website terms of service, and robots.txt directives. Web scraping may be restricted or prohibited by certain websites. The authors do not endorse or encourage scraping sites that prohibit it.

**Accuracy**: Primr uses AI models that may produce inaccurate, incomplete, or hallucinated information. All outputs should be treated as hypotheses requiring human verification, not facts. Do not make business decisions based solely on Primr outputs without independent validation.

**Costs**: Primr makes API calls to third-party AI services (Gemini, Grok) that incur real monetary charges. Web search uses DuckDuckGo by default (free). Cost estimates are approximate. Users are responsible for monitoring their own API usage and costs.

**No Warranty**: This software is provided "as is" without warranty of any kind. The authors are not liable for any damages, costs, or legal issues arising from use of this software.

**Intended Use**: Primr is designed for legitimate research purposes — understanding companies, evaluating opportunities, and making informed decisions. It is not intended for competitive intelligence gathering that violates laws or ethical standards, mass surveillance, or any malicious purpose.
