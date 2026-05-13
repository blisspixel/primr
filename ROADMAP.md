# Primr Roadmap

Current State: v1.24.1

Primr is a CLI-first, local research tool for company intelligence and deep strategic analysis. It aims to accelerate research workflows while producing consultant-grade outputs that stay explicit about uncertainty.

The design is intentionally opinionated and local-first. This roadmap is a single ordered queue of work, top to bottom. The order reflects priority — items higher up either improve the core deliverable directly, address known regressions, or unlock items below them. No time estimates: this is the queue, not a schedule. Items may ship in a different order if dependencies, capacity, or feedback change the picture, but the default is to work it top-down.

For completed work, see the [Changelog](#changelog) at the bottom of this file, or check [GitHub releases](https://github.com/blisspixel/primr/releases) for the latest.

---

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

**Standard Mode** (default when both `XAI_API_KEY` and `GEMINI_API_KEY` are set): Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing — ~$0.79/run, ~23-35 min, trust gate PASS. XAI-only setups fall back to the legacy Grok 4.20-NR writing path (~$4.27/run). Research deepening, parallel section writing, cross-validation, coherence pass, and strategy enrichment.

**Premium Mode** (`--premium`): Gemini + Deep Research pipeline for maximum depth. ~50-75 min, ~$5.

### AI Strategy & Report Generation

- AI strategy and roadmap generation with multi-platform support (`--platform aws azure`)
- Platform options: Azure, AWS, GCP, agnostic, private (NVIDIA/on-prem)
- DNS intelligence pre-flight (recon): auto-detects AI strategy platform from strong infrastructure fingerprints, injects tech stack context into all strategy types, and falls back to Azure + private cloud/NVIDIA when no primary cloud is clear
- `primr recon` subcommand for standalone DNS intelligence lookups
- `--platform ms` shorthand for Microsoft Azure + NVIDIA private cloud
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric, Skills Ideation
- Skills Ideation strategy emits per-role `SKILL.md` files deterministically alongside the strategy doc
- Strategy enrichment: cross-validation, evidence search, section regeneration, polish pass, and pre-ship repair for citation/source/budget conflicts
- TXT, DOCX, and PDF outputs with citation styles
- Custom `--output-dir` support for clean client folders: Markdown and DOCX deliverables are written to the requested directory, while TXT mirrors and validation diagnostics stay with the run diagnostics
- 23-section reports with adaptive section selection, constrained-evidence reasoning, deduplication, and cross-validation

### Providers & Routing

- Five providers wired: xAI (Grok), Google (Gemini), OpenAI, Anthropic, Ollama (local)
- Provider abstraction at `src/primr/ai/providers/` — `Provider` ABC, `OpenAICompatibleProvider` (xAI/OpenAI/Ollama/vLLM), `GeminiProvider`, `AnthropicProvider`
- `pick_model_for_role` chooses the best model from configured providers; `primr doctor` shows what each key unlocks
- Provider-aware fallback chain: WRITING/UTILITY prefer GEMINI > OPENAI > ANTHROPIC > XAI; REASONING prefers XAI (cached) > GEMINI > OPENAI > ANTHROPIC
- Cross-provider dispatch in `grok_llm` and `llm()` so writing-tier calls reach the right provider when the resolved model is non-Grok
- Quota-aware `ModelCircuitBreaker.execute_with_fallback()` with midnight-UTC reset (callable; production call-site integration still pending — see queue below)
- Continuous reasoning session is the default: workbook generation and cross-validation share a single Grok 4.3 session so the validator inherits corpus + workbook reasoning. ~81% reduction in leaked-instruction lines, average ~+12% cost. Escape hatch: `--no-continuous-reasoning` or `PRIMR_CONTINUOUS_REASONING=0`.

### Agent Integration

- MCP server (stdio + HTTP with JWT auth)
- A2A protocol (standalone or co-hosted with MCP)
- OpenClaw integration with packaged skills plus governed research/strategy workflows
- Claude Skills directory with MCP-first skill packages
- Agent governance surfaces for generic MCP clients: estimate-first prompts/resources, next-action hints, and optional server-enforced cost caps (`max_estimated_cost_usd`, `PRIMR_ENFORCE_MCP_COST_CAPS`)
- Long-running job guidance for agent clients: monitor/resume flows for standard runs and premium multi-vendor runs

### Quality & Trust

- Deterministic QA checks: hypothesis coverage, confidence labels, section length, citation density, report-type-aware structure, and appendix/source integrity
- `QAGateHook` with `ReportAnalyzer`-backed scoring (6 checks, penalty system)
- Claim verification via `--verify` flag (~$0.01, 3-5 min) — extracts claims, challenges them with DDG searches, produces trust score
- Versioned model evaluation harness: `primr eval` with scorecard generation (Markdown + CSV), versioned eval IDs, acceptance gates, and optional LLM-judge overlays
- Eval profile slot registry — one slot per (provider × model × role-recipe), so new models register a slot, run the corpus once, and score against existing baselines without re-doing prior work
- Local eval judge capability: Ollama-backed LLM judging against staged reports, named local model lists, per-model JSON artifacts, and local multi-model sweep summaries
- Output improvement: `primr improve` for deterministic cleanup + optional agentic review pass

### Pipeline Resilience

- Cost-ordered recovery hierarchies for all six pipeline stages (scraping, external search, analysis, section writing, cross-validation, strategy generation)
- Foreground/background stage classification — foreground stages retry aggressively, background stages bail on API overload or budget stress
- Recovery executor that orchestrates retry/fallback/skip logic and logs events to `_run_state.json`
- `--dry-run` shows the full recovery table (stage classifications + recovery hierarchies)
- Public-data fallback fan-out (`src/primr/data/fallback_sources.py`): when origin is blocked, fetches in parallel from Wayback CDX, sister subdomains, SEC EDGAR 10-Ks, Wikipedia REST, and Grok web_search synthesis
- Hiring-signal gathering (`src/primr/data/hiring_signals.py`): Greenhouse / Lever / Ashby / SmartRecruiters board APIs first, HTML careers-page fallback, LLM-triaged extraction threaded into all downstream phases

### Operational Maturity

- Cost estimation, usage tracking, job recovery, crash/reboot recovery
- System diagnostics (`primr doctor`)
- 5,700+ tests, full ruff and mypy compliance
- Serverless cloud deployment templates (AWS, Azure, GCP); Azure validated end-to-end (remaining hardening below)
- Agentic architecture: hypothesis tracking, subagents, hooks, orchestrator
- Content sanitization for prompt injection protection

---

## Design Philosophy

- Strategic analysis over raw data — deep outputs you can act on, not link dumps
- Hypothesis generation over premature conclusions — confidence levels on every claim
- Transparency about uncertainty — what's confirmed, what's inferred, what's speculation
- Deterministic verification before AI judgment — check structure, citations, and epistemic labels with code before asking a model to score prose quality
- Local-first, CLI-first — your data stays on your machine
- Role over tool — Primr is an account strategist, not a "research command." Its outputs should be consumable by both humans and downstream agents.
- Product over middleware — integrations should act as a disciplined control plane for Primr's long-running research jobs, not turn Primr into a generic orchestration framework.
- Artifact-first delivery — the main unit of value is a report, strategy, or evaluation artifact, not a stream of chat-sized tool responses.
- The pipeline is the product — Primr's value is the 8-tier scraping engine, the org-aware link selection, the research deepening, the cross-validation, the deterministic QA gate, the eval harness, the crash recovery, and the cost estimation. None of these are model calls. The model is a commodity; the orchestration pipeline is the moat.

Primr is intentionally not designed as a generic web scraper, a SaaS collaboration platform, a presentation builder, or a generic agent middleware layer.

---

## Active Queue

The next ~15 items, ordered top-down by priority. Each is concrete enough to start without further design work.

### 1. Artifact Drift in the Standard Pipeline

Surfaced during the continuous-reasoning pilot: the standard pipeline leaks internal scaffolding into final reports more often than expected. Across three baseline runs, reports averaged 5.3 bare `**What to validate:` instruction-style lines per report — text that looks like internal section-template guidance escaping into prose. One baseline run also leaked literal `[cross-ref Financial Profile][workbook]` markers. This is independent of which reasoning topology produced the workbook; it lives in the section-writing step or the typed `GeneratedSection` normalization at the writer boundary.

Planned:
- Audit the section-writing prompts to see why the section template's `What to validate:` guidance sometimes survives into final prose as a bare instruction line rather than a discovery-question paragraph
- Strengthen `GeneratedSection` normalization to strip leaked instruction-style fragments at the writer boundary (canonicalization already enforces a single trailing `What to validate:` block — extend it to recognize and remove instruction-style leftovers)
- Add a deterministic check to `ReportAnalyzer` that flags bare instruction-style lines and `[cross-ref ...]` / `[workbook]` markers in the shipping-artifact validation pass
- Quantify with an offline scan over recent runs to confirm the drift is widespread, not specific to a few unlucky cells

Decision principle: final shipping artifacts must read as deliverables, not as internal scaffolding.

### 2. Artifact Pipeline Hardening

Primr needs a sharper separation between **intermediate research artifacts** and **final shipping artifacts**. Research-stage artifacts (scrape summaries, source inventories, contradiction notes, section briefs) are machine-facing inputs to later stages — they need to be consistent, parseable, and provenance-preserving. Final reports and strategy documents need to ship as polished Markdown / TXT / DOCX / PDF with stable section structure, auditable citations, and predictable validation behavior. Treating both classes as "just markdown" creates placeholder leakage, brittle regex repair, false-positive validator blocks, and renderer edge cases that only show up at batch scale.

Planned:
- Keep intermediate research outputs flexible, but make them more explicitly structured for downstream consumption (evidence packets, source inventories, contradiction records, section briefs)
- Push more consistency upstream into the long-form writing and regeneration prompts so final-stage cleanup has less arbitrary prose repair to do
- Strengthen artifact shipping gates to validate section structure and citation integrity, not just scan for forbidden markdown leftovers
- Build a regression corpus from real shipped and failed artifacts so renderer/validator changes are tested against actual long-form outputs
- Continue moving final rendering toward structured document data rather than free-form markdown recovery wherever practical

Decision principle: permissive about formatting in the research pipeline, strict about formatting and structure in the final document pipeline.

### 3. Verified Page Access — First-Party Recovery Expansion

The shared page-access classifier, evidence-backed classification, Kasada/KPSDK challenge-shell coverage, homepage fast-path validation, first-party sitemap/guessed-path recovery, Wayback challenge-shell filtering, and public-data fallback fan-out have all shipped. What remains:

- Expand first-party fallback probing beyond current sitemap/guessed-path recovery: investor/news/about/help PDFs, feeds, and structured data endpoints with better prioritization
- Add host-level learning so once Primr sees a confirmed real page for a host it can persist useful positive markers for later pages
- Add optional screenshot/text-snapshot comparison for browser tiers to distinguish stable real homepages from interstitial templates
- Surface a clearer user-facing blocked-site summary in the CLI with evidence snippets and recommended next actions
- Extend trace analytics and eval suites to score false-positive and false-negative rates for access classification on protected sites
- Hiring-signal extensions: add Workday / BambooHR / iCIMS ATS providers, wire hiring signals into `--premium` (fast-mode only today), and consider host-level memory so subsequent runs of the same company skip re-probing providers that already missed

Decision principle: a page counts as scraped only when Primr has evidence that the real page content appeared, not merely that a request returned HTML.

### 4. Consultant-Grade Strategic Writing

Push the standard output from a strong research artifact to a genuinely strategist-grade analysis for pre-discovery preparation.

- Section prompts tuned around management choices, operating constraints, likely economics, scenario paths, and validation questions
- Fewer brittle section suppressions, more constrained-evidence reasoning when direct company data is thin
- Dense references concentrated in final appendices so the body reads like analysis, not a source dump
- Better trust summaries so users can see what is confirmed, inferred, hypothesized, and still weak
- Target: sparse-company runs still feel substantive; rich-company runs become sharper and more differentiated

### 5. Cache-Hit Visibility & Operational Observability

Cache hit rate is load-bearing on the sub-$1 default — Grok 4.3 cached input at $0.20/M is what makes 4.3-for-reasoning viable on the budget. Without visibility, regressions in the recipe go unnoticed. Cache-token plumbing already exists at the provider level; the missing piece is threading it through to historical records and the usage UI.

- Bridge cached-token counts from providers into `tracker.record_usage()` and `UsageRecord` so `primr show-usage` displays cache hit rate per run
- Track real-usage cost variability across more companies and surface a continuous-reasoning regression signal in `primr show-usage`
- `primr doctor --scraper-stats` to show per-tier success rate, latency p95, and content quality score across recent runs
- `--budget $N` flag to enforce per-run cost ceiling (activates existing `CostGuardHook`)
- `primr show-usage` enhancements: total lifetime spend, per-company history, cost-by-mode breakdown
- Stored in run state JSON for post-hoc analysis; informs sticky tier policy and circuit breaker thresholds

### 6. Diminishing Returns Detection for Cross-Validation

Detect when cross-validation or section regeneration is making diminishing progress and stop early, rather than consuming the full token budget.

- After each section regeneration, measure improvement: word count delta, new citation count, QA score change
- If 3+ consecutive regenerations each produce <5% improvement in QA score, stop the loop early
- Log the early stop in the QA summary: `cross-validation: stopped early (diminishing returns after N iterations)`
- Applies to both the existing cross-validation pass and the planned QA iteration loop
- Start conservative and tune thresholds based on eval results

### 7. Wire Circuit Breaker Into Production LLM Call Sites

The `ModelCircuitBreaker.execute_with_fallback()` mechanism is callable and tested but not yet invoked from `research_agent.py` LLM call sites. Today a provider quota blip during a run can fail the run instead of advancing to the next model in the cross-provider chain. Wire it into the production pipeline so quota events trigger automatic provider failover.

### 8. Prompt Cache Preparation

Split section-writing prompts into cached (stable across sections) and volatile (per-section) components as a clean architectural separation.

- Cached prefix (identical across all parallel section writes): company context, analysis workbook, scrape summary, external research summary, general writing instructions, citation style guide
- Volatile suffix (per-section): section name, section-specific prompt, section-specific evidence excerpts, word target
- Ensure the cached prefix is byte-identical across all parallel section writes — no timestamps, no randomized evidence ordering, no section-specific context in the prefix
- Zero-cost prep step: doesn't add caching API calls, just structures the prompts so caching works when providers support it
- Applies the same principle to strategy generation prompts and cross-validation prompts where a shared context prefix is reused across multiple calls

### 9. Batch API for Section Writing (xAI + Anthropic Recipes)

Section writing is the most token-intensive stage (~40-50% of LLM spend) and the only one where all calls are independent. Route section writing through provider batch APIs for ~50% discount and zero rate-limit risk.

- New `--batch-api` flag to opt in for section writing
- After analysis/workbook completes, submit all section prompts as a single batch (xAI Batch API initially; Anthropic batch as a parallel recipe — the `grok43-haiku-batch` eval cell hung in pre-validation and needs root-cause investigation before that recipe can be promoted)
- Poll batch status until complete; retrieve results and feed into cross-validation as normal
- Graceful fallback: if batch API is unavailable or times out, fall back to existing `ThreadPoolExecutor` path
- Progress display updated: "Section writing (batch API, polling...)" with ETA based on batch state counters
- Strategy generation could also be batched when running multi-platform strategies
- Add batch-mode pricing fields to `ModelConfig` so cost estimates reflect the discount when `--batch-api` is used

### 10. QA Iteration Loop

Use QA feedback to iteratively improve weak sections until reports hit 90+.

- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work
- Section-level regeneration without full pipeline re-run
- Repeat until grade >= 90
- Integrates with the diminishing-returns detection above: stop the loop when regeneration produces <5% QA improvement per iteration

Structure the refinement loop around a four-phase consolidation protocol (Orient → Gather → Consolidate → Prune) to ensure the LLM surveys existing state before making changes:

1. Orient: Read full report + QA summary + source appendix. Identify which sections scored lowest, which citations are weak, which confidence labels are missing.
2. Gather: For weak sections, search for additional evidence. DDG queries targeted at specific gaps. Cross-reference existing scrape data for unused signal.
3. Consolidate: Regenerate weak sections with enriched context. Merge new evidence into existing narrative rather than rewriting from scratch. Preserve existing citations and confidence labels that are still valid.
4. Prune: Re-run deterministic QA. Normalize citations. Ensure Sources appendix is consistent with body citations. Validate budget/timeline figures in strategy sections.

Principle: separate reading (Orient/Gather) from writing (Consolidate/Prune). The LLM has full context before it starts editing, which prevents hallucinated improvements that contradict existing content.

### 11. Constrained Agent Permissions for Agentic Improve

When `primr improve --improve-agentic` runs an agentic review pass, constrain the agent's write permissions to the output file only. This transforms agentic improve from a trust-based policy ("the LLM should only edit the report") into an enforced architectural constraint.

- Allow: read any file in the working directory and output directory
- Allow: write only to the target output file (or `*_improved` variant)
- Allow: DDG search for additional evidence (read-only external)
- Deny: write to `_run_state.json`, `_raw_scrapes/`, working directory state files
- Deny: any shell commands that modify files outside the output target
- Implement as a wrapper around file I/O that checks the target path against an allowlist before writing

This pattern applies to any future agentic pipeline stage that modifies artifacts: expert perspective passes, strategy enrichment, cross-validation regeneration.

### 12. Expert Perspective Passes

After the standard pipeline, add domain-specific scrutiny of findings.

- Default: single "multi-perspective" prompt that evaluates from CFO, CTO, competitive, and risk viewpoints in one pass (~$0.03)
- `--with-experts full`: parallel expert reviews (4 separate passes, ~$0.15) for deeper analysis
- Output: "Expert Perspectives" section appended to report, or separate sidecar document

Perspectives:
- **CFO**: scrutinize financial claims, flag unsupported revenue estimates, assess unit economics
- **CTO**: evaluate technology stack claims, assess technical moat, identify build-vs-buy signals
- **Competitive analyst**: compare findings against known competitors, identify positioning gaps
- **Risk analyst**: identify regulatory, market, and execution risks

### 13. Auto-Eval on Model Releases

Reduce manual work when new model variants drop by automating the eval-and-compare cycle.

- Trigger eval sweep when a new model is registered in `ModelRegistry` (manual trigger initially, automated detection later)
- Run the standard 3-5 company corpus against the new model and current default, generate comparative scorecard
- LLM judge overlay (cloud or local Ollama) for subjective metrics: utility, strategic sharpness, hallucination rate
- Wire `--continuous-reasoning` / `--no-continuous-reasoning` into the eval harness so topology choice is scored against the same baseline systematically
- Decision output: "new variant is better/worse/equivalent for [stage]" with evidence
- Keeps defaults current without gut calls on each release

### 14. Capability-Requirement Routing Layer

Provider abstraction and role-based routing shipped in v1.22.0/v1.23.0. The still-planned half: each pipeline stage declares capability requirements and the router solves for the cheapest match.

- Each stage declares: minimum reasoning depth, required capabilities (web search, structured output, long context), acceptable providers
- Router selects the cheapest model that meets requirements from available providers
- Integrates with the circuit breaker — unhealthy models are skipped automatically
- Integrates with effort-level routing for hybrid inference
- Long-context surcharge modeling: populate `ModelConfig.tier_threshold_tokens` for OpenAI gpt-5.x family (>272K input: 2× input, 1.5× output) so cost estimates aren't silently wrong on long-input runs
- Move `grok_browse_and_summarize` and Gemini quota UI into providers (two pieces of provider-specific behavior still living outside the abstraction)

The requirements themselves come from observed eval cost/quality data per role, not a priori guessing.

### 15. Pipeline Overlap

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

### 16. Snapshot Subcommand

A new top-level subcommand for the case where you want a fast look at a company before deciding whether to spend on a real run. Explicitly framed as screening, not analysis. Not a quality dial on `primr` — a separate, narrower product.

Why this exists at all: degrading the standard pipeline to chase sub-5-minute runtime is a bad trade. If you want fast-and-shallow, you can already get that for free from a search engine. The interesting cheap-and-fast tier is one that does specifically what's free or near-free in well under a minute: DNS recon, homepage render, and a single LLM synthesis pass. Anything beyond that costs real time and money and should go through the real pipeline.

What the subcommand does:
- `primr recon` (DNS intelligence, ~3s, free, already exists)
- Homepage + 2-3 highest-signal pages (about, leadership, products) via Playwright tier 1 only — no escalation, no fallback fan-out
- One DDG search for recent news (free)
- One synthesis call (cheap utility-tier model — Gemini 3.1 Flash-Lite or equivalent) producing a one-page Markdown brief

Budget: ~30-45s wall-clock, ~$0.03, no DOCX, no QA gate, no cross-validation, no strategy.

Output shape: a single Markdown one-pager with sections for who they are, tech stack signals from DNS, what's on their homepage right now, one recent news item if DDG returned anything, and an explicit footer pointing to the full `primr` command. Header banner: "Snapshot — screening only, not strategic analysis."

What it explicitly is not:
- No tier escalation: if Playwright tier 1 doesn't render the homepage, the snapshot fails fast and tells the user to run the full pipeline
- No public-data fallback fan-out — that's a strategic recovery path, not a screening tool
- No hiring signals, no cross-validation, no strategy, no DOCX
- No cost-vs-depth dial on the standard pipeline — `primr` always means "excellent report"

Decision principle: the standard pipeline is the product. Snapshot is the cheap pre-flight that helps you decide whether to invoke it. Speed is only worth paying for when the alternative is free.

### 17. Agent Control Plane Hardening

The MCP/OpenClaw/skill integrations are treated as a disciplined Primr control plane rather than thin shell wrappers. Next work is narrower and more intentional than the initial integration push.

This work is for: making long-running, paid Primr runs safer and easier to route, approve, monitor, resume, and consume from agent clients. Keeping the user experience aligned to Primr's actual product shape: URL in, serious artifact out.

This work is not for: turning Primr into a generic orchestration platform, replacing the CLI, duplicating core business logic in skills, or exposing a shell-shaped `run_primr(command_string)` surface.

Planned:
- Add server-issued approval tokens for cost-incurring operations so approval is harder to bypass than cost-cap propagation alone
- Expand job-scoped resources for artifact consumption (`qa_summary`, source appendix, trace summary) so clients do not need large report bodies in context by default
- Add integration eval suites for routing, approval, recovery, and recomputation avoidance
- Keep skills thin and MCP-first; intentionally avoid turning SKILL files into duplicated application specs
- Preserve typed lifecycle/control-plane primitives instead of free-form execution wrappers

### 18. Windows Working-Directory Hardening

Reduce false negatives and transient failures on Windows machines where the repo lives inside OneDrive or similar synced folders.

- Make checkpoint/state writes tolerant of transient `PermissionError` during atomic rename
- Update `primr doctor` to probe the same atomic write path used during real runs
- Add explicit docs for keeping high-churn `working/` paths outside synced folders when possible
- Longer term: support a configurable working directory separate from the repo root

### 19. Azure Deployment Finalization

The Azure tiered deployment (team and organization) has its Bicep IaC, deploy script, OpenAPI spec, budget tracker, environment auto-detection, JWT validation, and cloud diagnostics in place. The deployment provisions in ~3.5 min, /healthz passes, and 162 tests across budget/auth/environment are green. The remaining items are concrete:

- **Container App entrypoint**: The MCP server (`primr-mcp --http`) needs to run correctly inside the Docker container. The Bicep command override is in place but the container crashes on startup — likely a dependency or import path issue that needs local debugging. The Dockerfile currently builds for the job runner; the API server entrypoint needs the same image to also serve HTTP.
- **Container App Job triggering**: The MCP server's `research_company` tool needs to trigger Container App Jobs in cloud mode instead of running the pipeline in-process. This is the queue integration that enables 20+ concurrent users.
- **ACR build log streaming on Windows**: Azure CLI's `az acr build` crashes on Windows due to a Unicode encoding bug in colorama/cp1252. Workaround in place: poll `az acr task list-runs` for completion instead of streaming logs. Needs to be finalized in `deploy.ps1`.
- **Structured logging for Application Insights**: Log fields (request_id, job_id, tool_name, duration_ms) are designed but not yet wired into the container runtime.
- **VNet integration**: Documented as a production TODO. Private endpoints for Cosmos DB, Storage, Key Vault, and Service Bus are not yet configured.

---

## Considered for Later

Concepts where the design is sketched but the work isn't queued for the next active cycle — either because they depend on an upstream item, the scope is large, or the value is real but not yet pressing.

### Gemini 3.1 Pro Enhancements for Premium Mode

Adopt Gemini 3.1 Pro improvements to strengthen premium mode, especially for sparse-company runs and strategy sections.

- Add `thinking_level` control per pipeline stage: "high" for strategy sections and cross-validation, "low" for extraction and summarization
- Enable built-in tools + function calling combinations (Grounding with Google Search + URL context) for external validation during premium analysis stages
- Test Interactions API / Deep Research Agent polling with durability features (`store=True`, improved resume)
- Aligns with deterministic QA + constrained-evidence reasoning: stronger model reasoning reduces "thin" sections without huge cost jumps

### First-Class VLM Extraction

Promote vision extraction from fallback tier to first-class path for data-dense pages (charts, tables, IR decks, org charts).

Smart VLM Routing:
- Content-type detection identifies pages likely to be data-dense (PDF, pages with high image-to-text ratio)
- Route those pages directly to VLM extraction alongside (not instead of) text extraction
- LLM reconciliation merges text + VLM outputs, preferring structured data from VLM
- No change to existing tier fallback for text-heavy pages

Structured Extraction:
- VLM prompt optimized for tables, org charts, and financial data
- Output as structured JSON (not just prose description)
- Table data extracted to markdown tables in report sections

Cost Control:
- VLM extraction is more expensive per page — only trigger on high-value pages
- `--vlm-budget N` flag to cap VLM calls per run (default: 10 pages)
- Cost estimator updated with VLM pricing

Scrape Tier Evolution:
- Managed Playwright service fallback (Scrapfly / Firecrawl / similar) when local browser tiers fail — handles infra/scaling edge cases without maintaining headless browser farms
- `MANAGED_SCRAPE_API_KEY` env var, used only after local tiers exhaust retries
- Network interception during Playwright runs: capture underlying JSON APIs (XHR/fetch) during page loads — often yields cleaner structured data than HTML parsing for financials, careers, and dynamically loaded content
- Intercepted API responses stored alongside HTML scrapes in `_raw_scrapes/` for downstream extraction

### Local Inference Mode (Full Pipeline)

Run the full Primr pipeline on local hardware with zero API costs. Primary target: RTX 4090 (24GB VRAM) with Ollama. Goal: a working `--inference local` mode that produces useful research output — not cloud-quality, but good enough for batch screening, internal research, and cost-sensitive workloads.

What's already built (v1.23.0+):
- Ollama provider via `OpenAICompatibleProvider`, with registered models at zero marginal cost
- Local eval judge capability and named local model lists (`4090-top10`, `installed-starter`) for eval sweeps
- Multi-model judge sweeps comparing every staged non-baseline profile
- Eval artifacts with backend metadata, coverage, and consensus tracking

Three execution profiles:
- `--inference cloud`: current behavior, all AI stages use cloud providers (default)
- `--inference hybrid`: local for high-volume/low-complexity stages, cloud for deep research and trust-critical synthesis — the sweet spot for most users with a GPU
- `--inference local`: all compatible stages on local inference, $0 API cost, longer runtime

Stage routing hypothesis (validated by eval, not assumed):

| Stage | Local (RTX 4090) | Hybrid | Cloud |
|---|---|---|---|
| Link selection | Local 7B | Local 7B | Gemini Flash |
| Content quality assessment | Local 7B | Local 7B | Gemini Flash |
| Scrape summarization | Local 14B | Local 14B | Gemini Flash |
| External search query generation | Local 14B | Cloud | Gemini 3.1 Flash-Lite |
| Analysis workbook | Local 32B-Q4 | Cloud | Grok 4.3 |
| Section writing | Local 14B-32B | Cloud | Gemini 3.1 Flash-Lite |
| Cross-validation | Local 14B | Cloud | Grok 4.3 |
| Strategy generation | Local 32B-Q4 | Cloud | Grok 4.3 |
| Deep Research | Skip (no local equivalent) | Cloud | Gemini DR |

What gets built:
- Production-safe local/cloud/hybrid stage routing (extends the capability-requirement routing layer above)
- Per-stage model selection based on capability requirements + available backends
- Cost estimator reflects local inference as $0.00 API cost while tracking runtime
- `primr doctor --local` validates Ollama is running, models are pulled, VRAM is sufficient
- Graceful degradation: if a local model can't handle a stage, fall back to cloud (hybrid) or skip (local) with clear logging
- Progress display shows which backend each stage is using: `Analysis (local: qwen3:30b)` vs `Analysis (cloud: grok-4.3)`

Validation approach:
- Run the eval harness on the standard company corpus: cloud baseline vs hybrid vs local
- Compare quality, runtime, and trust gate pass rates
- Start with hybrid (local for cheap stages, cloud for hard stages) before attempting full local
- Publish the eval results so the tradeoffs are explicit and data-driven
- If local quality is unacceptable for certain stages, that's a valid outcome — hybrid mode still saves significant cost

Promotion criteria:
- Trust gate passes: citation coverage, section completeness, confidence-label quality
- Decision-utility within acceptable band of cloud baseline for replaced stages
- No silent fallback: if local can't meet requirements, fail clearly or require explicit hybrid
- Runtime documented: local runs will be slower — the tradeoff is cost, not speed

### Cross-Run Research Memory

Make research compound across runs by persisting extracted claims, citations, and hypotheses in a searchable store. Currently each run starts fresh. If you research 50 companies in the same industry, each run rediscovers the same industry context. Cross-run memory enables meta-research ("show AI strategy evolution across all fintech targets") and better hypothesis quality for repeat verticals. Three staged layers, build top-down:

**Layer 1 — Persistent company tracking (entry point):**
- `primr company track <name> <url>` — creates persistent profile folder with versioned reports, hypothesis deltas, and freshness score
- `primr company list` — shows tracked companies with last-run date and staleness indicator
- `primr improve --track` — auto-runs improvement pass on stale profiles (configurable staleness threshold)
- Profile folder stores run history, confidence evolution, and gaps flagged across runs
- `primr company export <name>` — structured MD/JSON bundle with confidence tags and flagged gaps

**Layer 2 — Claim store + priming:**
- SQLite-backed claim store (no external dependencies); each claim stored with company, section, text, confidence, citations, timestamp, embedding
- Embedding via local model (sentence-transformers) or API (Gemini embedding)
- `primr memory search "AI strategy fintech"` to query across all past runs
- `primr memory timeline "Company"` to show how understanding evolved across runs
- When starting a new run, query memory for related companies/industries and inject relevant prior findings as context for the analysis stage

**Layer 3 — Knowledge compounding + narrative evolution:**
- `--batch companies.csv --industry-context`: synthesize industry-wide patterns from all scrape results in Phase 0.5, then each company analysis receives industry context as additional input. One extra synthesis call (~$0.05) reused across all company analyses. Invariant: industry synthesis may identify patterns but may NOT introduce claims not present in scraped data; individual company analysis may interpret with industry context but must cite specific scraped content.
- `primr refine` accepts new information, notes, and follow-up findings; re-synthesizes insights with updated confidence and revised hypotheses; cross-run memory stores the evolution
- Versioned research artifacts with explicit "what changed and why" sections; diff-style comparison between runs (confidence shifts, new evidence); timeline view of a company over time

Privacy: all data stays local (SQLite in working directory). `primr memory clear` to reset. No data leaves the machine unless explicitly exported.

### Multi-Cloud Deployment Validation (GCP + AWS)

Azure is the validated cloud (see active queue above for remaining hardening). GCP and AWS templates exist as reference implementations but are not validated end-to-end.

**GCP:**
- Validate `deploy/gcp/` templates: Cloud Run Jobs → Pub/Sub → Cloud Storage
- Workload Identity Federation for keyless auth
- Cloud Trace + Cloud Monitoring integration
- `deploy/gcp/deploy.sh validate` smoke test
- Cost profile documented

**AWS:**
- Validate `deploy/aws/` templates: Fargate → SQS → S3
- IAM roles for task execution (no long-lived credentials)
- X-Ray tracing + CloudWatch integration
- Step Functions for job orchestration (already templated in `step-function.json`)
- `deploy/aws/deploy.sh validate` smoke test
- Cost profile documented

**Cross-cloud consistency:**
- Unified CLI: `primr deploy <cloud> <env>` wraps the per-cloud deploy scripts
- Shared control plane API contract across all three clouds (same endpoints, same auth, same job lifecycle)
- Integration test suite that runs against any deployed environment: submit → poll → retrieve → validate artifact quality
- Terraform or Pulumi option alongside the existing shell scripts for teams that prefer declarative IaC
- Documentation: deployment guide per cloud, cost comparison table, architecture diagrams

What stays local-first:
- CLI is always the primary interface — cloud deployment is for organizational scale, not a replacement
- All research logic runs in the container, unchanged — the cloud layer is queue + storage + auth, not a rewrite
- `primr doctor` works in both local and deployed contexts
- Artifacts are downloadable as the same MD/DOCX/TXT files you get locally

### Post-Research Skill Processing (Anthropic Skills API)

Primr produces a strategic overview, an AI strategy document, and supporting artifacts. What happens next — turning those into a client-ready deliverable, an internal brief, a CRM enrichment payload — is different for every user. Today that workflow is manual: copy the `.md` output, paste it into Claude, run your own skill or prompt, iterate. This feature makes the handoff automatic and generic. Primr ships the plumbing to pipe its artifacts through any user-provided skill via the Anthropic Skills API. The skill itself is entirely the user's business.

> The Skills Ideation strategy (`--strategy-type skills`, shipped v1.23.0) is the narrower, in-pipeline version of the same idea: Primr generates per-role `SKILL.md` files directly from its own research, no Anthropic Skills API call required. The entry below remains the broader vision: arbitrary user-supplied downstream skills running against any Primr output.

CLI shape:

```bash
# One-off: run a skill against the outputs of this research run
primr "Company" https://company.com --post-skill skill_01AbCd...

# Reprocess existing artifacts through a skill without re-running research
primr skill-run "output/Company_Strategic_Overview_03-06-2026.md" --skill skill_01AbCd...

# Upload a local skill folder to the Anthropic Skills API (helper, not required)
primr skill-upload ./my-skill-folder
```

Configuration (`.env`):

```bash
# ANTHROPIC_API_KEY=sk-ant-...
# PRIMR_POST_SKILL_ID=skill_01AbCd...
# PRIMR_POST_SKILL_VERSION=latest
```

When `PRIMR_POST_SKILL_ID` is set, every research run automatically pipes artifacts through the skill after the standard pipeline completes. `--post-skill` overrides or supplements the env config. `--no-post-skill` skips it.

Implementation shape:
- New module: `src/primr/ai/skills_api.py` — thin Anthropic Skills API client (upload, invoke, download results)
- New pipeline phase: `post_skill` — runs after report generation and QA, before final output summary
- Skill invocation uses the Messages API with `container.skills` and `code_execution` tool enabled so skills can run bundled scripts
- Multi-turn handling: skills that need multiple turns (pause_turn) are handled automatically
- File download via the Anthropic Files API for any artifacts the skill produces
- Output files land in the same output directory as the research artifacts, with a `_skill/` subfolder
- Cost tracking: skill API calls are tracked in the same usage/cost system as research calls
- `--dry-run` includes estimated skill processing cost (based on input token count of artifacts)

Security considerations:
- Skills run in Anthropic's cloud containers, not on the user's machine — the skill cannot access local files beyond what Primr explicitly sends
- Primr sends only the research artifacts (report, strategy, QA summary) — no API keys, no working directory contents, no scrape traces
- Users are responsible for the security of their own skills
- `primr doctor` warns if a configured skill ID is invalid or inaccessible

### Agentic Interoperability

The framing shift: from tool to role. Primr already does deep company research. The next evolution is positioning it as a composable role in multi-agent workflows — not just something a human runs, but a specialist that other agents can assign work to and build on. Today: "run primr on this company." Next: "assign the account strategist to this deal and let downstream roles build on its findings." The infrastructure (A2A protocol, MCP tools, subagent architecture) is already in place. What changes is the framing and how Primr presents itself to the broader agentic ecosystem.

- Role-aware output shaping: when called via A2A, adapt output to the requesting workflow's needs — a downstream agent building a proposal gets tighter focus on opportunities; one doing risk assessment gets constraints and gaps emphasized
- Extend AgentCard skills with output-format negotiation so callers can request the emphasis they need
- Expert perspective passes become named analyst roles that shape output tone, not just appended report sections
- Workflow composability: Primr as one role in a team, receives a company assignment, produces intelligence, and the next role picks it up — no orchestrator built into Primr; Primr is a specialist, not the coordinator

### Public Release Polish

PyPI publication has shipped (`pip install primr` works). Remaining items for a broader public release push:

- Contribution workflow for external contributors
- Documentation site
- Reduce `setup_env.py` to a thin wrapper around `primr init` once the PyPI install path is the default documented path
- README screen capture / GIF assets (asciinema or vhs recording of a real research run; refreshed DOCX screenshot; updated `docs/images/primr-demo.png`)

---

## Model Adaptability

AI models are released frequently. Primr's strategy for staying current without chasing hype:

1. **Eval harness** — `primr eval` runs a fixed company corpus across profile slots (one slot per provider × model × role-recipe) and generates a scorecard (cost, runtime, citation density, section completeness, confidence-label coverage)
2. **Data-driven adoption** — A candidate recipe is adopted only when it clears all of: total run cost <$1.00 (the budget gate), trust gate passes at or above current baseline, mean decision-utility score ≥ baseline. Soft signals (utility-per-dollar, hallucination rate, drift markers) are tiebreakers among recipes that clear the hard gates.
3. **Model registry** — New models are registered in `src/primr/config/models.py` with pricing, context limits, capability flags, cached-input rates where applicable, and backend/runtime metadata for local inference. Audit the registry before each major eval — registry drift produces wrong scorecards.
4. **No lock-in** — The pipeline stays backend-agnostic by design. Each model is swappable via the eval process rather than hard-coded ideology. The only hard constraint is the budget gate.

Workflow when a new model drops: audit registry → register new entry → run eval slot → compare scorecard against budget + quality gates → adopt or skip. No gut decisions.

**Local inference eval policy:**
- Start with staged-report judge sweeps and same-company/profile comparisons before replacing production pipeline stages
- Use judge sweeps to compare one model, a named shortlist, or the current top-N candidate set across every staged non-baseline profile
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
- Multi-agent systems use ~15x more tokens than single-agent ([LangChain State of Agents](https://www.langchain.com/state-of-agent-engineering)), which directly conflicts with Primr's sub-$1-per-run target.
- [Production teams report](https://dev.to/isaachagoel/read-this-before-building-ai-agents-lessons-from-the-trenches-333i) the golden rule: "Can I code this without losing functionality?" Mechanical tasks (scraping, search) should be code, not agent orchestration.
- [Community consensus](https://community.latenode.com/t/coordinating-multiple-ai-agents-for-scraping-validation-and-reporting-does-the-complexity-actually-pay-off/60040): keep simple pipelines simple; multi-agent DAGs only justified for horizontal scaling or dynamic replanning.

**What Primr actually needs:**
The real bottlenecks are sequential page scraping and sequential search queries — both fixable with `asyncio.gather()`, no framework required. The verification agent is a single pipeline stage (now implemented via `--verify`), not a graph node. Phase overlap (external search starting after homepage instead of after all pages) is a scheduling optimization, not an architectural change.

**The decision:** Invest in targeted parallelism and a verification stage rather than a DAG framework. This matches how the best production research systems actually work — simple orchestration with parallel execution where it matters — while keeping Primr maintainable as a solo project.

---

## Explicitly Deferred (By Design)

These are conscious non-goals:

**Web Interface**
- Browser-based submission, job dashboards

**Collaboration and Sharing**
- Accounts, permissions, comments, sharing reports externally

**Real-Time Monitoring**
- Always-on company watching, webhooks, alerting
- Primr is a job-based tool: you run it, get a brief, done

**Quantum / Blockchain / Web3**
- Quantum computing hooks for financial modeling
- Blockchain-based citation verification
- These add complexity with zero practical benefit for company research

**Voice / Conversational Modes**
- Interactive voice querying of reports, chatbot interfaces

**Generic Scraping Framework**
- Primr's scraper exists to serve the research pipeline, not as a standalone tool
- Not competing with Scrapy, Crawl4AI, or similar

**Plugin / Extension Marketplace**
- Community-contributed strategy types can be added via YAML PRs
- No plugin architecture or marketplace planned

---

## Usage Reference

```bash
# Basic usage (auto-selects best recipe from configured provider keys)
primr "ExampleCo" https://example.co

# Research modes
primr "ExampleCo" https://example.co --mode scrape
primr "ExampleCo" https://example.co --mode deep
primr "ExampleCo" https://example.co --premium  # Gemini + Deep Research

# AI Strategy (most common: Microsoft + NVIDIA)
primr "ExampleCo" https://example.co --platform ms              # Microsoft + NVIDIA shorthand
primr "ExampleCo" https://example.co --platform azure
primr "ExampleCo" https://example.co --platform aws azure       # Multi-platform
primr "ExampleCo" https://example.co --platform microsoft nvidia  # Same as --platform ms
primr "ExampleCo" https://example.co --no-ai-strategy

# DNS Intelligence (standalone, no API keys)
primr recon example.co                                          # Quick domain intel
primr recon example.co --json                                   # Structured output
primr recon example.co --full                                   # Everything

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
| 1.24.1 | May 2026 | Re-release of v1.24.0 with sanitized docs (generic placeholder for eval-target company). |
| 1.24.0 | May 2026 | **Sub-$1 default.** Cross-provider eval picked Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing as the new default — verified at $0.79/run (vs $3.49 on the previous Grok-only hybrid, 4.4x cheaper with trust gate PASS and faster runtime). `pick_model_for_role` uses a provider-aware fallback chain: WRITING/UTILITY prefer GEMINI > OPENAI > ANTHROPIC > XAI; REASONING prefers XAI (Grok 4.3 cached) > GEMINI > OPENAI > ANTHROPIC. OpenAI-only users get gpt-5.4-nano writing + o4-mini reasoning; Anthropic-only users get Haiku + Sonnet. XAI-only stays on legacy ~$4.27/run. Phase 5 enrichment loop got a 5-min per-section deadline (had been unbounded). `grok_llm` extended with cross-provider dispatch. OpenAI provider uses `max_completion_tokens` for gpt-5.x family. Eval profile slot registry in `model_eval.py` + `src/primr/config/eval_profiles.py` with 11 candidate slots. Roles split: PRO -> REASONING + WRITING + UTILITY in `routing.py`; `EvalRecipeOverride` contextvar for per-run recipe forcing. Decision audit in `docs/EVAL_V1_24_0.md`. |
| 1.23.0 | May 2026 | Multi-provider foundation. OpenAI / Anthropic / Ollama providers wired in (gpt-5.5 / 5.4 / 5.4-mini / 5.4-nano via `OpenAICompatibleProvider`; Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 via dedicated `AnthropicProvider`; Ollama via `OpenAICompatibleProvider`). Quota-aware `ModelCircuitBreaker.execute_with_fallback` with cross-provider chains and midnight-UTC reset. Prompt-cache token plumbing across xAI / OpenAI / Anthropic responses. Skills Ideation strategy (`--strategy-type skills`) with per-role `SKILL.md` emission. Anthropic correctness fixes: Opus 4.7 context 1M / output 128K, Sonnet 4.6 context 1M, Haiku 4.5 output 64K with `supports_thinking=True`; `cache_control_blocks` provider-kwarg removed (Anthropic caching is content-level). |
| 1.22.0 | May 2026 | Grok 4.3 onboarded as the new flagship reasoning model ($1.25/$2.50 per 1M with $0.20 cached input, 1M context, always-on reasoning). HYBRID/MAX tiers route reasoning to 4.3; FAST stays on 4.1; 4.20 IDs remain for resume of in-flight runs. Utility-tier dispatch rewired: `llm()` routes scraping summaries / link selection to Grok 4.1-NR when `XAI_API_KEY` set. Standard pipeline no longer requires a Gemini key. Provider abstraction landed: `src/primr/ai/providers/` package with `Provider` ABC, `OpenAICompatibleProvider`, `GeminiProvider`, `ProviderRegistry`. `src/primr/ai/routing.py` centralizes role-to-model routing. `primr doctor` gains a "Providers" section. 60+ new tests. `docs/MODEL_ONBOARDING.md` codifies the verify → register → wire → test → eval-gate process. |
| 1.21.2 | Apr 2026 | Release fix for client-folder output and recon platform defaults: `--output-dir` reaches the research pipeline; custom output directories keep only Markdown/DOCX deliverables while TXT mirrors and validation diagnostics stay in run diagnostics; recon platform selection uses strong infrastructure signals only; unclear/skipped recon falls back to Azure + private cloud/NVIDIA. |
| 1.20.1 | Apr 2026 | PyPI release infrastructure: `.github/workflows/release.yml` triggers on `v*` tag push or manual dispatch, builds sdist + wheel, runs `twine check`, publishes via PyPI trusted-publisher OIDC. Repo cleanup: root `.md` reduced to `README.md` and `ROADMAP.md`. |
| 1.20.0 | Apr 2026 | Continuous reasoning session is now the default for the standard pipeline: workbook generation and cross-validation share a single Grok session so the validator inherits corpus + workbook reasoning. ~81% reduction in leaked-instruction lines, avg ~+12% cost. New `ContinuousReasoningSession` class, `--no-continuous-reasoning` opt-out, `PRIMR_CONTINUOUS_REASONING` env var. |
| 1.19.0 | Apr 2026 | Hiring-signal gathering (Greenhouse / Lever / Ashby / SmartRecruiters + careers-page fallback, LLM triage and structured extraction). Public-data fallback fan-out (Wayback / EDGAR / Wikipedia / sister subdomains) when origin is fully blocked. Patchright stealth tier with global headed-popup budget. Verified page-access classifier promoted to first-class. |
| 1.18.1 | Apr 2026 | Observability and reliability hardening: thread-safe `LogContext` via contextvars, structured logging added to 15+ silent `except` paths, cross-validation and gap-analysis failures now surface to user instead of looking like clean passes. |
| 1.18.0 | Apr 2026 | Recon integration (DNS intelligence pre-flight, auto-platform detection, `primr recon` subcommand, 156 fingerprints, 20 signals, crt.sh cert transparency). `--cloud-vendor` renamed to `--platform` with backward compat. `--platform ms` shorthand. |
| 1.17.0 | Apr 2026 | Pipeline resilience (cost-ordered recovery, foreground/background stages, model circuit breaker), MCP estimate_run fix, corrected duration estimates. |
| 1.16.0 | Mar 2026 | A2A protocol, Grok 4.20 hybrid default, private cloud vendor, output shipping gate, fast mode default, agentic pipeline, deep-research refactor, eval workflow. |
| 1.12.1 | Feb 2026 | Scraping robustness, PDF routing, bug fixes. |
| 1.12.0 | Feb 2026 | Multi-cloud-vendor AI strategy. |
| 1.11.x | Feb 2026 | SharedBrowser, ETA progress, deep research progress visibility, interactive research mode, MCP progress subscriptions. |
| 1.8.1 | Feb 2026 | Content sanitization for prompt injection protection. |
| 1.7.0 | Feb 2026 | Agentic architecture (memory, hooks, orchestrator, subagents, skills, property tests). |
| 1.6.0 | Feb 2026 | Serverless cloud deployment (AWS / Azure / GCP). |
| 1.5.x | Feb 2026 | Typed error hierarchy, circuit breaker, OpenTelemetry, property tests, full ruff compliance. |
| 1.4.x | Feb 2026 | MCP Server for AI agent integration; OpenClaw integration. |
| 1.3.x | Jan 2026 | Python 3.11+ requirement; resource cleanup, File Search Store billing fix. |
| 1.2.0 | Jan 2026 | Test coverage, security review. |
| 1.1.x | Jan 2026 | Reader-mode extraction, vision tier, browser-first discovery, LLM link selection. |
| 1.0.0 | Dec 2025 | Rebrand to Primr, pip installable. |
| 0.5.0 | Dec 2025 | Cost tracking, job recovery. |
| 0.4.0 | Dec 2025 | AI Strategy generation. |
| 0.3.0 | Dec 2025 | Full mode (two-step). |
| 0.2.0 | Nov 2025 | Deep Research integration. |
| 0.1.0 | Nov 2025 | Core research pipeline. |

---

## Final Note

Primr is a tool for understanding companies. The focus is on useful output, not user growth.

---

## Disclaimer

**Legal Compliance**: Users are responsible for ensuring their use of Primr complies with applicable laws, website terms of service, and robots.txt directives. Web scraping may be restricted or prohibited by certain websites. The authors do not endorse or encourage scraping sites that prohibit it.

**Accuracy**: Primr uses AI models that may produce inaccurate, incomplete, or hallucinated information. All outputs should be treated as hypotheses requiring human verification, not facts. Do not make business decisions based solely on Primr outputs without independent validation.

**Costs**: Primr makes API calls to third-party AI services that incur real monetary charges. Web search uses DuckDuckGo by default (free). Cost estimates are approximate. Users are responsible for monitoring their own API usage and costs.

**No Warranty**: This software is provided "as is" without warranty of any kind. The authors are not liable for any damages, costs, or legal issues arising from use of this software.

**Intended Use**: Primr is designed for legitimate research purposes — understanding companies, evaluating opportunities, and making informed decisions. It is not intended for competitive intelligence gathering that violates laws or ethical standards, mass surveillance, or any malicious purpose.
