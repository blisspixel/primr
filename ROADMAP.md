# Primr Roadmap

Current State: v1.16.0 (released 2026-03-23)

Primr is a CLI-first, local research tool for company intelligence and deep strategic analysis. It aims to accelerate research workflows while producing consultant-grade outputs that stay explicit about uncertainty.

The design is intentionally opinionated and local-first. This roadmap reflects planned improvements ordered by practical impact: first make the core output more strategically valuable, then make runs faster and cheaper, then expand extraction and provider choices, then enable compounding knowledge across runs.

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

**Standard Mode** (default when `XAI_API_KEY` set): Grok 4.20 hybrid pipeline — 4.20 for reasoning stages (gap analysis, workbook, cross-validation), 4.1 for bulk writing. Research deepening, parallel section writing, cross-validation, coherence pass, and strategy enrichment. ~35-45 min, ~$0.67. Use `--grok-tier fast` for 4.1 everywhere (~$0.47) or `--grok-tier max` for 4.20 everywhere (~$4.29).

**Premium Mode** (`--premium`): Gemini + Deep Research pipeline for maximum depth. ~50-75 min, ~$5.

### AI Strategy & Report Generation

- AI strategy and roadmap generation with multi-vendor support (`--cloud-vendor aws azure`)
- Cloud vendor options: Azure, AWS, GCP, agnostic, private (NVIDIA/on-prem)
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric
- Strategy enrichment: cross-validation, evidence search, section regeneration, polish pass, and pre-ship repair for citation/source/budget conflicts
- TXT, DOCX, and PDF outputs with citation styles
- 23-section reports with adaptive section selection, constrained-evidence reasoning, deduplication, and cross-validation

### Agent Integration

- MCP server (stdio + HTTP with JWT auth)
- A2A protocol (standalone or co-hosted with MCP)
- OpenClaw integration with skills and workflows
- Claude Skills directory

### Quality & Trust

- Deterministic QA checks: hypothesis coverage, confidence labels, section length, citation density, report-type-aware structure, and appendix/source integrity
- `QAGateHook` with `ReportAnalyzer`-backed scoring (6 checks, penalty system)
- Claim verification via `--verify` flag (~$0.01, 3-5 min) — extracts claims, challenges them with DDG searches, produces trust score
- Versioned model evaluation harness: `primr eval` with scorecard generation (Markdown + CSV), versioned eval IDs, acceptance gates, and optional LLM-judge overlays
- Local eval judge capability for staged reports: Grok or local OpenAI-compatible backends (for example Ollama), including named local model lists, per-model JSON artifacts, and local multi-model sweep summaries across every staged non-baseline profile
- Output improvement: `primr improve` for deterministic cleanup + optional agentic review pass

### Operational Maturity

- Cost estimation, usage tracking, job recovery, crash/reboot recovery
- System diagnostics (`primr doctor`)
- 4,500+ tests, full ruff and mypy compliance
- Serverless cloud deployment (AWS, Azure, GCP)
- Agentic architecture: hypothesis tracking, subagents, hooks, orchestrator
- Content sanitization for prompt injection protection

## Design Philosophy

- Strategic analysis over raw data — deep outputs you can act on, not link dumps
- Hypothesis generation over premature conclusions — confidence levels on every claim
- Transparency about uncertainty — what's confirmed, what's inferred, what's speculation
- Deterministic verification before AI judgment — check structure, citations, and epistemic labels with code before asking a model to score prose quality
- Local-first, CLI-first — your data stays on your machine
- Role over tool — Primr is an account strategist, not a "research command." Its outputs should be consumable by both humans and downstream agents.

Primr is intentionally not designed as a generic web scraper, a SaaS collaboration platform, or a presentation builder.

---

## Planned Work

Ordered by practical impact: first make the standard output more strategically useful, then make runs faster and cheaper, then expand extraction and provider choices, then enable compounding knowledge across runs.

### Near-Term

Scoped, practical improvements. Some are partially built.

#### Grok Tier Evaluation — 4-Way Comparison

Run the eval harness on 3-5 companies across all Grok tiers (fast/hybrid/max/multi-agent) plus premium to produce a proper scorecard. Hybrid is now the default based on initial Litehouse Foods comparison (meaningfully better analytical depth for ~$0.20 more). Need systematic data to confirm hybrid remains the right default, whether max tier ever justifies 6x the cost, and where multi-agent fits in the lineup.

- Same companies across all tiers for apples-to-apples comparison
- Eval scorecard with quality, trust, utility, hallucination rate, and utility-per-dollar metrics
- LLM judge overlay for subjective quality assessment
- Include multi-agent tier: compare hypothesis depth, source cross-checking quality, and contradiction detection against single-agent tiers
- Decision: validate hybrid default, identify if multi-agent justifies higher cost for reasoning-heavy stages, identify if any company profile benefits from max

#### v1.17.0 — Deeper Strategic Analysis

**Consultant-Grade Strategic Writing**

Push the standard output from a strong research artifact to a genuinely strategist-grade analysis for pre-discovery preparation.

- Section prompts tuned around management choices, operating constraints, likely economics, scenario paths, and validation questions
- Fewer brittle section suppressions, more constrained-evidence reasoning when direct company data is thin
- Dense references concentrated in final appendices so the body reads like analysis, not a source dump
- Better trust summaries so users can see what is confirmed, inferred, hypothesized, and still weak
- Target: sparse-company runs still feel substantive; rich-company runs become sharper and more differentiated

**Grok 4.20 Multi-Agent Integration**

Leverage xAI's Grok 4.20 Multi-Agent Beta (parallel agents with built-in web_search/x_search tools, verbose streaming, reasoning effort control) for reasoning-heavy pipeline stages.

- Register `grok-4.20-multi-agent-beta` (or latest variant) in ModelRegistry with pricing and capability flags
- Add `--grok-multi-agent` flag and `--grok-agent-count` (dynamic range 4-16 based on complexity + budget)
- Route to multi-agent for reasoning-heavy stages only: gap analysis, workbook generation, cross-validation, strategy enrichment — keep 4.1 for bulk writing where single-agent is sufficient
- Multi-agent reasoning enables parallel hypothesis debate, real-time source cross-checking, and contradiction synthesis — directly improves analytical depth for sparse-company runs
- Cost: ~$2-6/M input/output (higher than single-agent 4.1, but lower hallucination rate and deeper analysis)
- Eval sweep required before promotion: compare hybrid vs multi-agent on 5 companies (quality, hallucination rate, depth, cost, utility-per-dollar)
- Decision gated by eval harness, not assumption — multi-agent may not justify cost for all company profiles

**Gemini 3.1 Pro Enhancements for Premium Mode**

Adopt Gemini 3.1 Pro improvements to strengthen premium mode, especially for sparse-company runs and strategy sections.

- Register `gemini-3.1-pro-preview` and custom-tools variants in ModelRegistry (partially done)
- Add `thinking_level` control per pipeline stage: "high" for strategy sections and cross-validation, "low" for extraction and summarization — reduces cost without sacrificing depth where it matters
- Enable built-in tools + function calling combinations (Grounding with Google Search + URL context) for external validation during premium analysis stages
- Test Interactions API / Deep Research Agent polling with durability features (`store=True`, improved resume) — builds on existing shared polling modules
- Aligns with deterministic QA + constrained-evidence reasoning: stronger model reasoning reduces "thin" sections without huge cost jumps

#### v1.18.0 — Faster Runs

**Quick Mode (`--quick`)**

A real quick profile that finishes in under 5 minutes for most companies. Ideal for batch screening or fast lookups.

- New CLI profile with explicit runtime budget and reduced token/search footprint
- Tight phase budget: fewer sections, capped external queries (5 max), smaller synthesis context
- Scraping capped at tiers 1-3 (Playwright → Playwright Aggressive → curl_cffi) — skip slow stealth/vision tiers
- Fewer pages scraped (10-15 instead of 50)
- Grok 4.1 everywhere (skip cross-validation and coherence passes to stay under budget)
- `--quick --lite-strategy` for minimal strategy sections only (skip full AI strategy generation)
- Quality floor + graceful fallback when evidence is thin
- Target: median runtime < 5 min, cost < $0.40, with citations and confidence labels
- Users choose between `quick` (speed), `standard` (balanced), and `premium` (depth)
- Cost-vs-depth profiles reflected in eval harness for systematic comparison across tiers

**Pipeline Overlap**

Reduce end-to-end runtime by overlapping independent pipeline phases.

- Current: scrape all 50 pages → THEN start external search → THEN summarize
- Upgrade: start external search after homepage content is available (don't wait for all pages)
- External searches hit different hosts (DDG, news sites) — safe to run alongside primary site scraping
- Insight extraction can begin on early pages while later pages are still scraping
- Simple scheduling with `asyncio.gather()` — no orchestration framework needed
- Expected gain: 5-10 min overlap between scraping and external research phases

What's already parallel (no changes needed):
- Section writing: `ThreadPoolExecutor(max_workers=4)` — up to 4 sections concurrently
- External search queries: `ThreadPoolExecutor(max_workers=3)` — 3 concurrent DDG/Google queries
- Per-host rate limiting: 2 concurrent/host, 20 req/min/host, with 0-1.5s random jitter

Why same-host scraping stays sequential: all 50 pages come from one company website. Concurrent requests to the same host is a bot detection signal. Sequential with per-host jitter, sticky tier optimization, and circuit breakers mimics human browsing. This is an intentional design choice, not a limitation.

Completion guarantees:
- All overlapped phases must complete before downstream stages start (no partial results)
- `asyncio.gather(return_exceptions=True)` with explicit error handling
- Run state tracks per-phase completion status for crash recovery
- Progress display updated to show concurrent phases (e.g., "Scraping 23/50 | Searching 4/10")

**Operational Observability**

Surface the cost, performance, and scraping data that Primr already tracks internally.

- Per-tier success rate, latency p95, and content quality score
- `primr doctor --scraper-stats` to show tier performance across recent runs
- `--budget $N` flag to enforce per-run cost ceiling (activates existing `CostGuardHook`)
- `primr show-usage` enhancements: total lifetime spend, per-company history, cost-by-mode breakdown
- Stored in run state JSON for post-hoc analysis
- Informs sticky tier policy and circuit breaker thresholds

#### v1.19.0 — Better Reports

**Expert Perspective Passes (`--with-experts`)**

After the standard pipeline, add domain-specific scrutiny of findings.

- Default: single "multi-perspective" prompt that evaluates from CFO, CTO, competitive, and risk viewpoints in one pass (~$0.03)
- `--with-experts full`: parallel expert reviews (4 separate Grok passes, ~$0.15) for deeper analysis
- Output: "Expert Perspectives" section appended to report, or separate sidecar document

**Perspectives:**
- **CFO**: scrutinize financial claims, flag unsupported revenue estimates, assess unit economics
- **CTO**: evaluate technology stack claims, assess technical moat, identify build-vs-buy signals
- **Competitive analyst**: compare findings against known competitors, identify positioning gaps
- **Risk analyst**: identify regulatory, market, and execution risks

**QA Iteration Loop**

Use QA feedback to iteratively improve weak sections until reports hit 90+.

- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work
- Section-level regeneration without full pipeline re-run
- Repeat until grade >= 90

**Auto-Eval on Model Releases**

Reduce manual work when new Grok/Gemini variants drop by automating the eval-and-compare cycle.

- Trigger eval sweep when a new model variant is registered in ModelRegistry (manual trigger initially, automated detection later)
- Run the standard 3-5 company corpus against the new variant and current default, generate comparative scorecard
- LLM judge overlay (cloud or local Ollama) for subjective metrics: utility, strategic sharpness, hallucination rate
- Decision output: "new variant is better/worse/equivalent for [stage]" with evidence
- Keeps defaults current (hybrid vs multi-agent vs premium) without gut calls on each release

### Medium-Term

Larger investments that expand Primr's capabilities.

#### v1.20.0 — First-Class VLM Extraction

Promote vision extraction from fallback tier to first-class path for data-dense pages (charts, tables, IR decks, org charts).

Corporate sites are increasingly visual — investor relations decks, product comparison matrices, org charts, and pricing tables are often images or rendered graphics that pure-text extraction misses. The vision tier already works but only triggers after 5 other tiers fail.

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

**Scrape Tier Evolution**

Expand the scraping engine with managed fallbacks and deeper data extraction.

- Managed Playwright service fallback (e.g., Scrapfly or Firecrawl API key) when local browser tiers fail — handles infra/scaling edge cases without maintaining headless browser farms
- `MANAGED_SCRAPE_API_KEY` env var, used only after local tiers 1-5 exhaust retries
- Network interception during Playwright runs: capture underlying JSON APIs (XHR/fetch) during page loads — often yields cleaner structured data than HTML parsing, especially for company financials, careers pages, and dynamically loaded content
- Intercepted API responses stored alongside HTML scrapes in `_raw_scrapes/` for downstream extraction
- No change to existing tier priority or sequential same-host behavior

#### v1.21.0 — Provider Expansion

**OpenAI Deep Research Integration**

Add OpenAI's Deep Research API as a third provider option alongside Grok and Gemini.

- `OPENAI_API_KEY` env var support
- OpenAI Deep Research client in `src/primr/ai/`
- `--provider openai` flag (or auto-detect from available keys)
- Cost estimator updated with OpenAI DR pricing
- Shared deep research parsing/polling modules extended for OpenAI response format
- Which tier(s) OpenAI DR best serves (quick, standard, premium) determined by eval results, not assumption

**Cross-Provider Eval**

Extend the eval harness to compare all available providers and determine the best default for each research tier.

- Eval profiles expanded: `grok-standard`, `gemini-premium`, `openai-quick`, `openai-full`, etc.
- Cross-provider scorecard: quality, cost, runtime, citation density compared side-by-side
- Tier recommendation output: "For quick: use X, for standard: use Y, for premium: use Z"
- Auto-detect available API keys and only eval providers the user has access to
- Historical eval tracking: compare across eval IDs to see if a provider improved over time

#### v1.22.0 — Local Inference Exploration

Explore running parts of the pipeline on local NVIDIA hardware via Ollama or another OpenAI-compatible local endpoint, cutting API costs toward zero for batch workloads without pretending local models are automatically good enough for the full pipeline.

At scale, API costs compound: 100 companies × $0.55 = $55 per batch. Local inference is worth evaluating because Primr is already local-first in execution. The question is not "can Primr run locally?" — it already does for scraping, orchestration, and outputs. The real question is which AI stages can move to local inference without unacceptable quality loss.

**Positioning:**
- Treat this as an eval-driven exploration first, not a default product promise
- Optimize for `--hybrid` before `--local`: use local models where they are cheap and good enough, keep frontier/cloud models where they still materially outperform
- Support both single-machine setups (desktop with GPU) and LAN-hosted model servers

**Hardware Targets:**
- **RTX 4090 (24GB VRAM)**: 7B-14B models — scraping helpers, link selection, content quality assessment, QA checks, insight extraction, deterministic improvement assists
- **Larger workstation / server GPUs**: 32B+ models — selective section drafting, structured synthesis, heavier review passes
- **High-memory systems (for example DGX-class boxes)**: 70B+ models — candidates for broader synthesis experiments, still subject to eval gates before promotion

**Execution Profiles:**
- `--inference cloud`: current behavior; all AI stages use cloud providers
- `--inference hybrid`: local for high-volume/low-complexity stages, cloud for deep research and trust-critical synthesis
- `--inference local`: route all compatible stages to local inference, explicitly experimental
- `--local-backend ollama|openai-compatible`: local backend selector; Ollama first, but avoid hard-coding the architecture to one vendor/runtime

**Routing Hypothesis (initial):**
- Local-first candidates: scrape summarization, link selection, extraction cleanup, content quality assessment, section QA helpers, report-improve assistance
- Hybrid/default-cloud candidates: analysis workbook generation, long-form section writing, cross-validation, expert-perspective passes
- API-only initially: Gemini Deep Research, web search grounding, any vision/VLM path until separately evaluated

**Initial Capability (implemented):**
- Primr can now run optional eval-time LLM judging against Grok or local OpenAI-compatible backends such as Ollama
- Local eval runs can target one model, an explicit model set, or a maintained named shortlist such as `4090-top10` or `installed-starter`
- Local judge sweeps now compare the baseline against every staged non-baseline profile by default, not just one convenient profile pair
- Eval artifacts now capture backend metadata per run plus candidate-profile coverage, consensus rate, and per-profile breakdowns so local judge results are reproducible and inspectable
- This is intentionally narrower than full local inference: it evaluates local models against existing artifacts before routing production pipeline stages to them
- It should remain easy to conclude "local is not good enough" with evidence and stop there if needed

**Integration:**
- Build on the existing local/OpenAI-compatible eval client in `src/primr/ai/` rather than creating a second backend path
- `OLLAMA_BASE_URL` env var (default: `http://localhost:11434`)
- Generalize toward `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, and `LOCAL_LLM_API_KEY` so LAN-hosted inference works the same as localhost
- Extend the model registry with local model entries, VRAM requirements, context limits, and capability flags
- Add a routing layer so each pipeline stage declares a minimum capability tier and acceptable backends
- Expand the current eval-plumbing into production-safe local/cloud/hybrid stage routing
- Cost estimator reflects local inference as $0.00 API cost while still tracking runtime and hardware assumptions

**Immediate Eval Track (this machine):**
- Use the existing eval harness as the acceptance gate rather than shipping on intuition
- Baseline against current cloud profiles on staged cloud-generated reports for the same company/profile pairs
- Run first-pass local tests on this machine's RTX 4090 + Ollama setup using single-model and multi-model judge sweeps
- Use the judge sweep to narrow candidate local models before attempting any stage-level production routing
- Compare `cloud` vs `hybrid` first; only try `local` end-to-end after stage-level results look credible

**Promotion Criteria:**
- Trust gate still passes: citation coverage, section completeness, confidence-label quality
- Mean decision-utility remains within an acceptable band of cloud baseline for the stages being replaced
- Runtime is not materially worse for the target workload, or the cost savings justify the slowdown
- No silent fallback: if a requested local profile cannot meet capability or quality requirements, fail clearly or require explicit hybrid fallback

**What stays API-only (initially):**
- Gemini Deep Research (autonomous multi-step search — no local equivalent today)
- Web search grounding (DDG/Google — already cheap/free)
- Vision extraction (local VLMs exist but quality varies too much to assume parity)

### Stretch Goals

Ambitious ideas that would meaningfully expand what Primr can do. These depend on the earlier work and may or may not happen.

#### v1.23.0 — Cross-Run Research Memory

Make research compound across runs by persisting extracted claims, citations, and hypotheses in a searchable store.

Currently each run starts fresh. If you research 50 companies in the same industry, each run rediscovers the same industry context. Cross-run memory enables meta-research ("show AI strategy evolution across all fintech targets") and better hypothesis quality for repeat verticals.

**Persistent Company Tracking (entry point)**

Lightweight precursor to the full claim store — turns one-off runs into living company profiles.

- `primr company track <name> <url>` — creates persistent profile folder with versioned reports, hypothesis deltas, and freshness score
- `primr company list` — shows tracked companies with last-run date and staleness indicator
- `primr improve --track` — auto-runs improvement pass on stale profiles (configurable staleness threshold, e.g., >90 days or after model upgrade)
- Profile folder stores run history, confidence evolution, and gaps flagged across runs
- `primr company export <name>` — structured MD/JSON bundle with confidence tags and flagged gaps for external consumption
- This is the foundation layer — the full claim store and embedding search build on top of tracked profiles

**Full Claim Store:**
- SQLite-backed claim store (no external dependencies)
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

#### v1.23.0 — Knowledge Compounding

Build on cross-run memory (v1.22.0) to make research compound across batch runs and evolving investigations.

**Industry Knowledge Base for Batch Runs**

When researching multiple companies in the same industry, build shared industry context first, then analyze each company with that context.

A company's positioning makes more sense when you know what the industry looks like. "Company X uses Kubernetes" is unremarkable if every company in the batch does. "Company X still runs bare-metal" is remarkable if nobody else does.

- `--batch companies.csv --industry-context` flag
- Phase 0: scrape all companies (existing batch behavior)
- Phase 0.5 (new): synthesize industry-wide patterns from all scrape results
- Phase 1+: each company analysis receives industry context as additional input
- Industry synthesis saved as a reusable artifact
- Cost: one extra synthesis call (~$0.05), reused across all company analyses

**Invariants:**
- Industry synthesis may identify patterns but may NOT introduce claims not present in scraped data
- Individual company analysis may interpret with industry context but must cite specific scraped content

**Refinement Loop**

Support post-discovery learning without re-running everything from scratch.

- `primr refine` command accepting new information, notes, and follow-up findings
- Re-synthesize insights with updated confidence and revised hypotheses
- Outputs evolve as understanding deepens
- Cross-run memory (v1.22.0) stores the evolution

#### v1.24.0 — Narrative Evolution

Make Primr the system of record for how thinking evolves about a company. Requires cross-run memory (v1.22.0).

- Versioned research artifacts
- Explicit "what changed and why" sections
- Diff-style comparison between runs: what shifted in confidence, what new evidence appeared
- Timeline view: how understanding of a company evolved across runs

#### v1.25.0 — Agentic Interoperability

**The shift: from tool to role.**

Primr already does deep company research. The next evolution is positioning it as a composable role in multi-agent workflows — not just something a human runs, but a specialist that other agents can assign work to and build on.

Today: "run primr on this company." Next: "assign the account strategist to this deal and let downstream roles build on its findings."

The infrastructure is already in place (A2A protocol, MCP tools, subagent architecture). What changes is the framing and how Primr presents itself to the broader agentic ecosystem.

**Role-Aware Output Shaping:**
- When called via A2A, Primr adapts its output to the requesting workflow's needs — a downstream agent building a proposal gets tighter focus on opportunities and angles; one doing risk assessment gets constraints and gaps emphasized
- AgentCard skills already declare capabilities; extend with output-format negotiation so callers can request the emphasis they need
- Expert perspective passes (v1.19.0) become named analyst roles that shape output tone, not just appended report sections

**Workflow Composability:**
- Primr as one role in a team: receives a company assignment, produces intelligence (MD, DOCX), and the next role picks it up
- A2A protocol already supports assignment and handoff; the evolution is Primr understanding its place in a larger workflow rather than assuming it's the terminal step
- No orchestrator built into Primr — Primr is a specialist, not the coordinator

#### v2.0.0 — Public Release

Make Primr available to the broader community via PyPI.

**Prerequisites:**
- v1.8.1 Content Sanitization Layer (complete - security requirement satisfied)

**Scope:**
- PyPI publication (`pip install primr`)
- Public GitHub repository
- ~~GitHub Actions CI/CD for automated testing~~ (done - lint, type check, tests run on every push)
- Contribution workflow for external contributors
- Documentation site

---

## Model Adaptability

AI models are released frequently. Primr's strategy for staying current without chasing hype:

1. **Eval harness** — `primr eval` runs a fixed company corpus across profiles and generates a scorecard (cost, runtime, citation density, section completeness, confidence-label coverage)
2. **Data-driven adoption** — A candidate model is adopted when: trust gate passes, mean decision-utility score >= 80% of baseline, and cost meets budget targets
3. **Model registry** — New models are registered in `src/primr/config/models.py` with pricing, context limits, capability flags, and eventually backend/runtime metadata for local inference
4. **No lock-in** — The pipeline should stay backend-agnostic by design. Grok for analysis, Gemini Flash for scraping, Deep Research for autonomous search, Ollama for local helper tasks — each should be swappable via the eval process rather than hard-coded ideology

When a new model or local runtime drops, the workflow is: register it → run eval → compare scorecard → adopt or skip. No gut decisions.

**Local inference eval policy:**
- Start with staged-report judge sweeps and same-company/profile comparisons before replacing production pipeline stages
- Use judge sweeps to compare one model, a named shortlist, or the current top-10 candidate set across every staged non-baseline profile
- Treat judge sweeps as evidence about comparative preference and consistency, not as sufficient proof for production stage routing on their own
- Evaluate local models at the stage level before trying to replace full runs
- Prefer `hybrid` promotion before `local` promotion
- Keep a fixed reference corpus and compare local, hybrid, and cloud on the same inputs
- Record hardware context for every eval run (GPU, VRAM, runtime, model quantization) so results are reproducible
- Treat local models as accepted only when the quality loss is explicit and operationally worth the savings

---

## Why Not a Research DAG / LangGraph-Style Orchestration?

The QA feedback suggested replacing the linear pipeline with a DAG orchestration layer (LangGraph-style). After researching production experiences, we decided against this:

**What the research shows:**
- [Anthropic's own multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) does NOT use a DAG — it's a simple orchestrator-worker pattern (lead agent spawns 3-5 subagents in parallel, waits, synthesizes). They got 90% speed improvement purely from parallelism, not graph orchestration.
- Multi-agent systems use ~15x more tokens than single-agent ([LangChain State of Agents](https://www.langchain.com/state-of-agent-engineering)), which directly conflicts with Primr's $0.55 value proposition.
- [Production teams report](https://dev.to/isaachagoel/read-this-before-building-ai-agents-lessons-from-the-trenches-333i) the golden rule: "Can I code this without losing functionality?" Mechanical tasks (scraping, search) should be code, not agent orchestration.
- [Community consensus](https://community.latenode.com/t/coordinating-multiple-ai-agents-for-scraping-validation-and-reporting-does-the-complexity-actually-pay-off/60040): keep simple pipelines simple; multi-agent DAGs only justified for horizontal scaling or dynamic replanning.

**What Primr actually needs:**
The real bottlenecks are sequential page scraping and sequential search queries — both fixable with `asyncio.gather()`, no framework required. The verification agent is a single pipeline stage (now implemented via `--verify`), not a graph node. Phase overlap (external search starting after homepage instead of after all pages) is a scheduling optimization, not an architectural change.

**The decision:** Invest in targeted parallelism and a verification stage rather than a DAG framework. This matches how the best production research systems actually work — simple orchestration with parallel execution where it matters — while keeping Primr maintainable as a solo project.

## Scale Readiness (Implemented in v1.6.0)

Primr now supports serverless cloud deployment for organizational adoption:

- **Execution model**: Job-based ephemeral containers (Fargate/Container Apps/Cloud Run Jobs)
- **Interface model**: REST API control plane + CLI preserved for local use
- **Reliability**: Event-driven queues, dead-letter handling, state reconciliation
- **Cost control**: Scale-to-zero, per-API-key quotas, cost estimation on submit
- **Governance**: Centralized secrets management, audit logging, manifest trail

See [docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) for deployment guide.

## Explicitly Deferred (By Design)

These are conscious non-goals:

**Web Interface**
- Browser-based submission
- Job dashboards

**Collaboration and Sharing**
- Accounts, permissions, comments
- Sharing reports externally

**Real-Time Monitoring**
- Always-on company watching, webhooks, alerting
- Primr is a job-based tool: you run it, get a brief, done

**Quantum / Blockchain / Web3**
- Quantum computing hooks for financial modeling
- Blockchain-based citation verification
- These add complexity with zero practical benefit for company research

**Voice / Conversational Modes**
- Interactive voice querying of reports
- Chatbot interfaces

**Generic Scraping Framework**
- Primr's scraper exists to serve the research pipeline, not as a standalone tool
- Not competing with Scrapy, Crawl4AI, or similar

**Plugin / Extension Marketplace**
- Community-contributed strategy types can be added via YAML PRs
- No plugin architecture or marketplace planned

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
| 1.16.0 | Mar 2026 | A2A protocol, Grok 4.20 hybrid default, private cloud vendor, output shipping gate, fast mode default, agentic pipeline, deep-research refactor, eval workflow |
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
<summary><strong>Detailed changelog for v1.16.0</strong></summary>

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
