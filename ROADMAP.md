# Primr Roadmap

Current State: v1.21.2

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

**Standard Mode** (default when `XAI_API_KEY` set): Grok 4.20 hybrid pipeline — 4.20 for reasoning stages (gap analysis, workbook, cross-validation), 4.1 for bulk writing. Research deepening, parallel section writing, cross-validation, coherence pass, and strategy enrichment. ~35-50 min, ~$0.67. Use `--grok-tier fast` for 4.1 everywhere (~$0.47) or `--grok-tier max` for 4.20 everywhere (~$4.29).

**Premium Mode** (`--premium`): Gemini + Deep Research pipeline for maximum depth. ~50-75 min, ~$5.

### AI Strategy & Report Generation

- AI strategy and roadmap generation with multi-platform support (`--platform aws azure`)
- Platform options: Azure, AWS, GCP, agnostic, private (NVIDIA/on-prem)
- DNS intelligence pre-flight (recon): auto-detects AI strategy platform from strong infrastructure fingerprints, injects tech stack context into all strategy types, and falls back to Azure + private cloud/NVIDIA when no primary cloud is clear
- `primr recon` subcommand for standalone DNS intelligence lookups
- `--platform ms` shorthand for Microsoft Azure + NVIDIA private cloud
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric
- Strategy enrichment: cross-validation, evidence search, section regeneration, polish pass, and pre-ship repair for citation/source/budget conflicts
- TXT, DOCX, and PDF outputs with citation styles
- Custom `--output-dir` support for clean client folders: Markdown and DOCX deliverables are written to the requested directory, while TXT mirrors and validation diagnostics stay with the run diagnostics
- 23-section reports with adaptive section selection, constrained-evidence reasoning, deduplication, and cross-validation

### Agent Integration

- MCP server (stdio + HTTP with JWT auth)
- A2A protocol (standalone or co-hosted with MCP)
- OpenClaw integration with packaged skills plus governed research/strategy workflows
- Claude Skills directory with MCP-first skill packages
- Agent governance surfaces for generic MCP clients: estimate-first prompts/resources, next-action hints, and optional server-enforced cost caps (`max_estimated_cost_usd`, `PRIMR_ENFORCE_MCP_COST_CAPS`)
- Long-running job guidance for agent clients: monitor/resume flows for 35-50 minute standard runs and 75-120 minute premium multi-vendor runs

### Quality & Trust

- Deterministic QA checks: hypothesis coverage, confidence labels, section length, citation density, report-type-aware structure, and appendix/source integrity
- `QAGateHook` with `ReportAnalyzer`-backed scoring (6 checks, penalty system)
- Claim verification via `--verify` flag (~$0.01, 3-5 min) — extracts claims, challenges them with DDG searches, produces trust score
- Versioned model evaluation harness: `primr eval` with scorecard generation (Markdown + CSV), versioned eval IDs, acceptance gates, and optional LLM-judge overlays
- Local eval judge capability for staged reports: Grok or local OpenAI-compatible backends (for example Ollama), including named local model lists, per-model JSON artifacts, and local multi-model sweep summaries across every staged non-baseline profile
- Output improvement: `primr improve` for deterministic cleanup + optional agentic review pass

### Pipeline Resilience

- Cost-ordered recovery hierarchies for all six pipeline stages (scraping, external search, analysis, section writing, cross-validation, strategy generation)
- Foreground/background stage classification — foreground stages retry aggressively, background stages bail on API overload or budget stress
- Model-level circuit breaker with provider-aware fallback chains (e.g., Grok 4.20 → Grok 4.1 → Gemini Flash)
- Recovery executor that orchestrates retry/fallback/skip logic and logs events to `_run_state.json`
- `--dry-run` shows the full recovery table (stage classifications + recovery hierarchies)

### Operational Maturity

- Cost estimation, usage tracking, job recovery, crash/reboot recovery
- System diagnostics (`primr doctor`)
- 5,700+ tests, full ruff and mypy compliance
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
- Product over middleware — integrations should act as a disciplined control plane for Primr's long-running research jobs, not turn Primr into a generic orchestration framework.
- Artifact-first delivery — the main unit of value is a report, strategy, or evaluation artifact, not a stream of chat-sized tool responses.
- The pipeline is the product — Primr's value is the 8-tier scraping engine, the org-aware link selection, the research deepening, the cross-validation, the deterministic QA gate, the eval harness, the crash recovery, and the cost estimation. None of these are model calls. They're all harness. The model is a commodity (Grok today, something else tomorrow); the orchestration pipeline is the moat. Research into production agentic systems consistently shows that 90%+ of a mature agent's codebase is harness engineering, not model interaction. Primr's architecture reflects this from the start.

Primr is intentionally not designed as a generic web scraper, a SaaS collaboration platform, a presentation builder, or a generic agent middleware layer.

---

## Planned Work

A single ordered list, top to bottom. The order reflects priority — items higher up either improve the core deliverable directly, address known regressions, or unlock items below them. No time estimates: this is the queue, not a schedule. Items may ship in different order if dependencies, capacity, or feedback change the picture, but the default is to work it top-down.

#### Continuous Reasoning Session

Primr's reasoning chain — gap analysis → workbook generation → cross-validation — used to run as independent Grok 4.20 calls that re-read `insights.txt` and `analysis_workbook.md` from disk at each handoff. The fresh-call-per-stage pattern is lossy on factual long-horizon chains: the validator sees only the polished workbook output and a list of source URLs, not the corpus or the reasoning that produced the workbook. The failure mode worth naming is Semantic Intent Divergence — the final stage drifting into reasoning *about* its own pipeline instead of the requested deliverable.

The continuous-session topology is now the **default for the standard pipeline**. Workbook generation (Phase 3) and cross-validation (Phase 5) share a single Grok 4.20 session so the validator inherits the corpus + workbook reasoning instead of re-reading the report cold. Section writing (Phase 4) is intentionally unchanged and remains parallel + fresh-call per section — the benchmark explicitly did not test parallel sub-agent topologies.

What shipped (full feature):
- `ContinuousReasoningSession` class in `src/primr/ai/grok_client.py` — multi-turn Grok session with shared message history, same retry/error/token-tracking semantics as the existing `grok_llm` helper
- Workbook + cross-validation wired through the shared session in `src/primr/core/research_agent.py`; the session is constructed lazily at the workbook stage so the workbook's system prompt becomes a real `role:system` message at session init (folding it into the first user turn measurably degraded workbook quality during the pilot)
- `--continuous-reasoning` is on by default; `--no-continuous-reasoning` reverts to the fresh-call topology for one run; `PRIMR_CONTINUOUS_REASONING=0` (or `false`/`no`/`off`) disables across all runs on the machine
- A deterministic artifact-type check in `ReportAnalyzer` that hard-blocks shipping if the final document drifts into a meta-pipeline shape regardless of reasoning topology (zero LLM cost; complements the topology change)

How the default-change decision was made (n=3 paired-comparison pilot, blind LLM judge):
- Workbook quality: continuous won 3/3
- Cross-validation quality: continuous won 2/3 (one close call)
- Final report quality: continuous won 2/3, with the third call complicated by a separate baseline-pipeline drift issue (see "Artifact Drift in the Standard Pipeline")
- Quantified drift reduction: bare leaked-instruction lines drop from average 5.3 per baseline report to 1.0 per continuous report (−81%) — a hard count, not a judge opinion
- Cost delta: highly variable (−3.7% to +32%, average ~+12%) — never catastrophic, well under the original 40% gate

Planned next steps (now that the default is shipped):
- Wire `--continuous-reasoning` and `--no-continuous-reasoning` into the `primr eval` harness so future model upgrades or topology tweaks are scored against the same baseline systematically
- Track real-usage cost variability across more companies and surface in `primr show-usage` so any regression vs the pre-flip baseline is visible
- Revisit the "narrow topology" idea (fresh workbook + continuous cross-val seeded with corpus + workbook output) only if a future regression in workbook quality shows up — current data says the lazy-init `role:system` placement holds up

Decision principle:
- The reasoning chain is the most concentrated quality lever in the standard pipeline. Spend tokens there before spending them anywhere else, but only after the data confirms the topology is actually the bottleneck. The pilot confirmed it; the default flipped on the strength of n=3 directional evidence plus a hard quantitative drift-reduction signal, with `--no-continuous-reasoning` as the escape hatch for any user who hits a bad-cost case.

#### Artifact Drift in the Standard Pipeline

Surfaced during the continuous-reasoning pilot: the standard pipeline leaks internal scaffolding into final reports more often than expected. Across three baseline runs (one rich-signal, one mid-signal, one sparse-signal), reports averaged 5.3 bare `**What to validate:` instruction-style lines per report — text that looks like internal section-template guidance escaping into prose. One baseline run also leaked literal `[cross-ref Financial Profile][workbook]` markers. This is independent of which reasoning topology produced the workbook; it lives in the section-writing step or the typed `GeneratedSection` normalization at the writer boundary.

Planned next steps:
- Audit the section-writing prompts to see why the section template's `What to validate:` guidance sometimes survives into final prose as a bare instruction line rather than a discovery-question paragraph
- Strengthen `GeneratedSection` normalization to strip leaked instruction-style fragments at the writer boundary (the canonicalization layer already enforces a single trailing `What to validate:` block — extend it to recognize and remove instruction-style leftovers)
- Add a deterministic check to `ReportAnalyzer` that flags bare instruction-style lines and `[cross-ref ...]` / `[workbook]` markers in the shipping-artifact validation pass
- Quantify with an offline scan over recent runs to confirm the drift is widespread, not specific to a few unlucky cells

Decision principle:
- Final shipping artifacts must read as deliverables, not as internal scaffolding. Drift markers are a signal the section-writing seam needs more discipline regardless of whether continuous reasoning becomes default.

#### Artifact Pipeline Hardening

Primr needs a sharper separation between **intermediate research artifacts** and **final shipping artifacts**. This is now a near-term priority because the product is increasingly used for long-form outputs that need to survive batch runs and deterministic rendering, not just one-off interactive use.

Why this work matters:
- Research-stage artifacts such as scrape summaries, source inventories, contradiction notes, and section briefs are primarily machine-facing inputs to later stages. Their job is to be consistent, parseable, and provenance-preserving, not beautifully formatted.
- Final reports and strategy documents are different. Their job is to ship as polished Markdown, TXT, DOCX, and PDF artifacts with stable section structure, auditable citations, clean tables/lists/headings, and predictable validation behavior.
- Treating both classes of output as "just markdown" creates avoidable failure modes: placeholder leakage, brittle regex repair, false-positive validator blocks, and renderer edge cases that only show up at batch scale.

What has already shipped:
- A normalized final-document model for shipping artifacts so report/strategy markdown is canonicalized before rendering and validation
- Typed `GeneratedSection` normalization at the writer boundary, including embedded-reference stripping, single trailing `What to validate:` enforcement, and citation extraction
- Support for mixed section output formats during parsing, so the pipeline can recover if the model mixes XML-style section envelopes with legacy `##` headings
- Cleaner DOCX artifact validation with fewer false positives from literal markdown-like content inside rendered tables
- Regression coverage for recent artifact-parser and shipping-path edge cases

Planned next steps:
- Keep intermediate research outputs flexible, but make them more explicitly structured for downstream consumption (evidence packets, source inventories, contradiction records, section briefs)
- Push more consistency upstream into the long-form writing and regeneration prompts so final-stage cleanup has less arbitrary prose repair to do
- Strengthen artifact shipping gates to validate section structure and citation integrity, not just scan for forbidden markdown leftovers
- Build a regression corpus from real shipped and failed artifacts so renderer/validator changes are tested against actual long-form outputs
- Continue moving final rendering toward structured document data rather than free-form markdown recovery wherever practical

Decision principle:
- Be permissive about formatting in the research pipeline, but strict about formatting and structure in the final document pipeline.

#### Verified Page Access & Challenge Recovery

Primr's scraping pipeline needs to treat **real page access** as a stricter condition than "HTTP 200 + some DOM." The Canada Goose / Kasada case made this concrete: a browser tier can receive a challenge shell, script bootstrap, or interstitial and still look superficially successful unless the pipeline explicitly verifies that the destination content actually appeared.

What this work is for:
- Promote scrape success from transport success to **verified real-content success**
- Detect challenge/interstitial states consistently across homepage fast paths and orchestrated deep-page scraping
- Recover through **allowed first-party paths** such as sitemap, investor relations, newsroom, PDFs, and static metadata instead of pretending success or looping indefinitely

What has already shipped:
- A shared page-access classifier that assigns explicit states: `success`, `soft_block`, `thin_content`, `unknown`
- Evidence-backed classification fields on scrape results and trace artifacts so runs now preserve why a page was accepted or rejected
- Homepage fast-path validation wired into the same classifier used by the orchestrator, closing the previous gap where a browser-fetched challenge shell could be accepted as a "homepage success"
- Additional Kasada/KPSDK challenge-shell coverage in soft-block detection
- First-party recovery mode when the homepage is blocked: Primr now probes sitemap/guessed deep paths directly and only declares failure after those recoverable first-party paths are exhausted
- Regression tests for challenge shells, thin-but-real history/about pages, homepage fallback behavior, and trace serialization
- **Public-data fallback fan-out** (`src/primr/data/fallback_sources.py`): when the origin is fully blocked, Primr automatically routes around the block by fetching content in parallel from (1) the Wayback Machine via the CDX API, (2) live sister subdomains (investor / IR / newsroom / corporate / press), (3) SEC EDGAR 10-K filings when the company has a US public filer match, and (4) the Wikipedia REST API. All four sources fail open — any one of them returning content is enough for the run to produce a report instead of bailing.
- Wayback tier filters out captures that are themselves challenge shells (preserves only real archived content)
- New unit tests for fallback fan-out: per-source failure isolation, merge behavior, empty-result contract
- **Hiring-signal gathering** (`src/primr/data/hiring_signals.py`): after the main-site scrape, Primr discovers a company's open postings (Greenhouse, Lever, Ashby, SmartRecruiters board APIs tried first, HTML careers-page fallback if every ATS misses), triages up to 15 via an LLM call biased toward senior / engineering / product / data / security / platform roles, and extracts structured signals: tech-stack frequency, strategic initiatives, culture cues, notable absences, and a one-paragraph synthesis. Output lands in `<working>/_hiring/` and is threaded into `insights.txt` plus the raw external-sources bundle so every downstream phase — gap analysis, workbook, section writing, cross-validation, and Phase 6 strategy — sees the signals. Fail-open at every step. Skip with `PRIMR_SKIP_HIRING_SIGNALS=1`.

Planned next steps:
- Expand first-party fallback probing beyond current sitemap/guessed-path recovery: investor/news/about/help PDFs, feeds, and structured data endpoints with better prioritization
- Add host-level learning so once Primr sees a confirmed real page for a host it can persist useful positive markers for later pages
- Add optional screenshot/text-snapshot comparison for browser tiers to distinguish stable real homepages from interstitial templates
- Surface a clearer user-facing blocked-site summary in the CLI with evidence snippets and recommended next actions (`--mode deep`, site-wide block vs partial access, first-party fallback coverage)
- Extend trace analytics and eval suites to score false-positive and false-negative rates for access classification on protected sites
- **Hiring-signal extensions**: extend the ATS provider list (Workday, BambooHR, iCIMS) and wire hiring signals into `--premium` mode (currently fast-mode only). Consider host-level memory so subsequent runs of the same company skip re-probing providers that already missed.

Decision principle:
- A page counts as scraped only when Primr has evidence that the **real page content** appeared, not merely that a request returned HTML.

#### Grok Tier Evaluation — 4-Way Comparison

Run the eval harness on 3-5 companies across all Grok tiers (fast/hybrid/max/multi-agent) plus premium to produce a proper scorecard. Hybrid is now the default based on a single-company spot comparison that showed meaningfully better analytical depth for ~$0.20 more. Need systematic data to confirm hybrid remains the right default, whether max tier ever justifies 6x the cost, and where multi-agent fits in the lineup.

- Same companies across all tiers for apples-to-apples comparison
- Eval scorecard with quality, trust, utility, hallucination rate, and utility-per-dollar metrics
- LLM judge overlay for subjective quality assessment
- Include multi-agent tier: compare hypothesis depth, source cross-checking quality, and contradiction detection against single-agent tiers
- Decision: validate hybrid default, identify if multi-agent justifies higher cost for reasoning-heavy stages, identify if any company profile benefits from max

#### Consultant-Grade Strategic Writing

Push the standard output from a strong research artifact to a genuinely strategist-grade analysis for pre-discovery preparation.

- Section prompts tuned around management choices, operating constraints, likely economics, scenario paths, and validation questions
- Fewer brittle section suppressions, more constrained-evidence reasoning when direct company data is thin
- Dense references concentrated in final appendices so the body reads like analysis, not a source dump
- Better trust summaries so users can see what is confirmed, inferred, hypothesized, and still weak
- Target: sparse-company runs still feel substantive; rich-company runs become sharper and more differentiated

#### Expert Perspective Passes

After the standard pipeline, add domain-specific scrutiny of findings.

- Default: single "multi-perspective" prompt that evaluates from CFO, CTO, competitive, and risk viewpoints in one pass (~$0.03)
- `--with-experts full`: parallel expert reviews (4 separate Grok passes, ~$0.15) for deeper analysis
- Output: "Expert Perspectives" section appended to report, or separate sidecar document

**Perspectives:**
- **CFO**: scrutinize financial claims, flag unsupported revenue estimates, assess unit economics
- **CTO**: evaluate technology stack claims, assess technical moat, identify build-vs-buy signals
- **Competitive analyst**: compare findings against known competitors, identify positioning gaps
- **Risk analyst**: identify regulatory, market, and execution risks

#### QA Iteration Loop

Use QA feedback to iteratively improve weak sections until reports hit 90+.

- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work
- Section-level regeneration without full pipeline re-run
- Repeat until grade >= 90
- Integrates with diminishing returns detection : stop the loop when regeneration produces <5% QA improvement per iteration

Structure the refinement loop around a four-phase consolidation protocol (Orient → Gather → Consolidate → Prune) to ensure the LLM surveys existing state before making changes:

1. Orient: Read full report + QA summary + source appendix. Identify which sections scored lowest, which citations are weak, which confidence labels are missing.
2. Gather: For weak sections, search for additional evidence. DDG queries targeted at specific gaps. Cross-reference existing scrape data for unused signal.
3. Consolidate: Regenerate weak sections with enriched context. Merge new evidence into existing narrative rather than rewriting from scratch. Preserve existing citations and confidence labels that are still valid.
4. Prune: Re-run deterministic QA. Normalize citations. Ensure Sources appendix is consistent with body citations. Validate budget/timeline figures in strategy sections.

The critical principle: separate reading (Orient/Gather) from writing (Consolidate/Prune). The LLM has full context before it starts editing, which prevents hallucinated improvements that contradict existing content.

#### Constrained Agent Permissions for Agentic Improve

When `primr improve --improve-agentic` runs an agentic review pass, constrain the agent's write permissions to the output file only. This transforms the agentic improve from a trust-based policy ("the LLM should only edit the report") into an enforced architectural constraint.

- Allow: read any file in the working directory and output directory
- Allow: write only to the target output file (or `*_improved` variant)
- Allow: DDG search for additional evidence (read-only external)
- Deny: write to `_run_state.json`, `_raw_scrapes/`, working directory state files
- Deny: any shell commands that modify files outside the output target
- Implement as a wrapper around file I/O that checks the target path against an allowlist before writing

This pattern applies to any future agentic pipeline stage that modifies artifacts: expert perspective passes, strategy enrichment, cross-validation regeneration. The principle is the same — declare what the agent can touch, enforce it in code, not in prompts.

#### Diminishing Returns Detection for Cross-Validation

Detect when cross-validation or section regeneration is making diminishing progress and stop early, rather than consuming the full token budget.

- After each section regeneration, measure improvement: word count delta, new citation count, QA score change
- If 3+ consecutive regenerations each produce <5% improvement in QA score, stop the loop early
- Log the early stop in the QA summary: `cross-validation: stopped early (diminishing returns after N iterations)`
- Applies to both the existing cross-validation pass and the planned QA iteration loop 
- Start conservative and tune thresholds based on eval results

#### Auto-Eval on Model Releases

Reduce manual work when new Grok/Gemini variants drop by automating the eval-and-compare cycle.

- Trigger eval sweep when a new model variant is registered in ModelRegistry (manual trigger initially, automated detection later)
- Run the standard 3-5 company corpus against the new variant and current default, generate comparative scorecard
- LLM judge overlay (cloud or local Ollama) for subjective metrics: utility, strategic sharpness, hallucination rate
- Decision output: "new variant is better/worse/equivalent for [stage]" with evidence
- Keeps defaults current (hybrid vs multi-agent vs premium) without gut calls on each release

#### Grok 4.20 Multi-Agent Integration

Leverage xAI's Grok 4.20 Multi-Agent Beta (parallel agents with built-in web_search/x_search tools, verbose streaming, reasoning effort control) for reasoning-heavy pipeline stages.

- Register `grok-4.20-multi-agent-beta` (or latest variant) in ModelRegistry with pricing and capability flags
- Add `--grok-multi-agent` flag and `--grok-agent-count` (dynamic range 4-16 based on complexity + budget)
- Route to multi-agent for reasoning-heavy stages only: gap analysis, workbook generation, cross-validation, strategy enrichment — keep 4.1 for bulk writing where single-agent is sufficient
- Multi-agent reasoning enables parallel hypothesis debate, real-time source cross-checking, and contradiction synthesis — directly improves analytical depth for sparse-company runs
- Cost: ~$2-6/M input/output (higher than single-agent 4.1, but lower hallucination rate and deeper analysis)
- Eval sweep required before promotion: compare hybrid vs multi-agent on 5 companies (quality, hallucination rate, depth, cost, utility-per-dollar)
- Decision gated by eval harness, not assumption — multi-agent may not justify cost for all company profiles

#### Gemini 3.1 Pro Enhancements for Premium Mode

Adopt Gemini 3.1 Pro improvements to strengthen premium mode, especially for sparse-company runs and strategy sections.

- Register `gemini-3.1-pro-preview` and custom-tools variants in ModelRegistry (partially done)
- Add `thinking_level` control per pipeline stage: "high" for strategy sections and cross-validation, "low" for extraction and summarization — reduces cost without sacrificing depth where it matters
- Enable built-in tools + function calling combinations (Grounding with Google Search + URL context) for external validation during premium analysis stages
- Test Interactions API / Deep Research Agent polling with durability features (`store=True`, improved resume) — builds on existing shared polling modules
- Aligns with deterministic QA + constrained-evidence reasoning: stronger model reasoning reduces "thin" sections without huge cost jumps

#### Provider Expansion

**OpenAI Integration**

Add OpenAI as a third provider option alongside Grok and Gemini.

- `OPENAI_API_KEY` env var support
- OpenAI client in `src/primr/ai/` using the existing thin-client pattern
- OpenAI Deep Research API for autonomous research (comparable to Gemini DR)
- OpenAI reasoning models (o3, o4-mini) as candidates for analysis/writing stages
- `--provider openai` flag (or auto-detect from available keys)
- Cost estimator updated with OpenAI pricing
- Shared deep research parsing/polling modules extended for OpenAI response format
- Which tier(s) OpenAI best serves (quick, standard, premium) determined by eval results, not assumption

**Anthropic Claude Integration**

Add Anthropic Claude as a fourth provider option.

- `ANTHROPIC_API_KEY` env var support (shared with the Post-Research Skill Processing entry above)
- Claude client in `src/primr/ai/` — Claude Opus for analysis/writing, Claude Sonnet for scraping/QA
- Extended thinking support for reasoning-heavy stages (gap analysis, cross-validation)
- Natural fit for the post-skill processing pipeline — same API key, same provider
- Eval-gated adoption: Claude may excel at strategic writing and hypothesis generation but cost more than Grok for bulk section writing

**Provider-Agnostic Routing Layer**

Formalize the model selection into a proper routing layer so each pipeline stage declares capability requirements and the router selects the best available model.

- Each pipeline stage declares: minimum reasoning depth, required capabilities (web search, structured output, long context), acceptable providers
- Router selects the cheapest model that meets requirements from available providers
- Integrates with the model circuit breaker — unhealthy models are skipped automatically
- Integrates with effort-level routing for hybrid inference 
- `primr doctor` shows available providers and which stages each can serve

**Cross-Provider Eval**

Extend the eval harness to compare all available providers and determine the best default for each research tier.

- Eval profiles expanded: `grok-standard`, `gemini-premium`, `openai-quick`, `claude-standard`, etc.
- Cross-provider scorecard: quality, cost, runtime, citation density compared side-by-side
- Tier recommendation output: "For quick: use X, for standard: use Y, for premium: use Z"
- Auto-detect available API keys and only eval providers the user has access to
- Historical eval tracking: compare across eval IDs to see if a provider improved over time

#### First-Class VLM Extraction

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

#### Local Inference Mode

Run the full Primr pipeline on local hardware with zero API costs. Primary target: RTX 4090 (24GB VRAM) with Ollama, which is available for testing and validation. The goal is a working `--inference local` mode that produces useful research output — not cloud-quality, but good enough for batch screening, internal research, and cost-sensitive workloads.

At scale, API costs compound: 100 companies × $0.75 = $75 per batch. Local inference eliminates that entirely for workloads where 80% quality at $0 cost is the right tradeoff. Primr is already local-first in execution — scraping, orchestration, and outputs all run locally. This version makes the AI stages local too.

**Three Execution Profiles:**

- `--inference cloud`: current behavior, all AI stages use cloud providers (default)
- `--inference hybrid`: local for high-volume/low-complexity stages, cloud for deep research and trust-critical synthesis — the sweet spot for most users with a GPU
- `--inference local`: all compatible stages on local inference, $0 API cost, longer runtime

**RTX 4090 Target (24GB VRAM):**

The RTX 4090 is the validation target. Models that fit in 24GB VRAM and run at acceptable speed:

- 7B-14B models for high-volume stages: link selection, content quality assessment, scrape summarization, extraction cleanup, QA checks
- 14B-32B quantized models (Q4/Q5) for medium-complexity stages: section writing, insight extraction, report improvement
- The eval harness determines which specific models work — not assumptions

Larger GPUs (48GB+, multi-GPU, DGX-class) can run bigger models for better quality, but the 4090 is the baseline that must work.

**Stage Routing:**

Each pipeline stage declares a minimum capability tier. The router selects the best available model:

| Stage | Local (RTX 4090) | Hybrid | Cloud |
|---|---|---|---|
| Link selection | Local 7B | Local 7B | Gemini Flash |
| Content quality assessment | Local 7B | Local 7B | Gemini Flash |
| Scrape summarization | Local 14B | Local 14B | Gemini Flash |
| External search query generation | Local 14B | Cloud | Grok 4.1 |
| Analysis workbook | Local 32B-Q4 | Cloud | Grok 4.20 |
| Section writing | Local 14B-32B | Cloud | Grok 4.1 |
| Cross-validation | Local 14B | Cloud | Grok 4.20 |
| Strategy generation | Local 32B-Q4 | Cloud | Grok 4.1 |
| Deep Research | Skip (no local equivalent) | Cloud | Gemini DR |

This table is a starting hypothesis. The eval harness validates it — if a local 14B model can't write sections that pass the trust gate, it gets bumped to cloud in hybrid mode.

**Backend Support:**

- `--local-backend ollama` (primary): Ollama with OpenAI-compatible API at `localhost:11434`
- `--local-backend openai-compatible`: any OpenAI-compatible endpoint (LAN-hosted servers, vLLM, etc.)
- `OLLAMA_BASE_URL`, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_API_KEY` env vars
- Model registry extended with local model entries: VRAM requirements, context limits, quantization level, capability flags

**What's Already Built:**

- Local eval judge capability: Ollama-backed LLM judging against staged reports
- Named local model lists (`4090-top10`, `installed-starter`) for eval sweeps
- Multi-model judge sweeps comparing every staged non-baseline profile
- Eval artifacts with backend metadata, coverage, and consensus tracking

**What Gets Built:**

- Production-safe local/cloud/hybrid stage routing (extends the provider-agnostic routing layer described in the Provider Expansion entry above)
- Per-stage model selection based on capability requirements + available backends
- Cost estimator reflects local inference as $0.00 API cost while tracking runtime
- `primr doctor --local` validates Ollama is running, models are pulled, VRAM is sufficient
- Graceful degradation: if a local model can't handle a stage, fall back to cloud (hybrid) or skip (local) with clear logging
- Progress display shows which backend each stage is using: `Analysis (local: qwen3:30b)` vs `Analysis (cloud: grok-4.1)`

**Validation Approach:**

- Run the eval harness on the standard company corpus: cloud baseline vs hybrid vs local
- Compare quality, runtime, and trust gate pass rates
- Start with hybrid (local for cheap stages, cloud for hard stages) before attempting full local
- Publish the eval results so the tradeoffs are explicit and data-driven
- If local quality is unacceptable for certain stages, that's a valid outcome — hybrid mode still saves significant cost

**Promotion Criteria:**

- Trust gate passes: citation coverage, section completeness, confidence-label quality
- Decision-utility within acceptable band of cloud baseline for replaced stages
- No silent fallback: if local can't meet requirements, fail clearly or require explicit hybrid
- Runtime documented: local runs will be slower (minutes, not seconds per stage) — the tradeoff is cost, not speed

#### Pipeline Overlap

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

#### Operational Observability

Surface the cost, performance, and scraping data that Primr already tracks internally.

- Per-tier success rate, latency p95, and content quality score
- `primr doctor --scraper-stats` to show tier performance across recent runs
- `--budget $N` flag to enforce per-run cost ceiling (activates existing `CostGuardHook`)
- `primr show-usage` enhancements: total lifetime spend, per-company history, cost-by-mode breakdown
- Stored in run state JSON for post-hoc analysis
- Informs sticky tier policy and circuit breaker thresholds

#### Prompt Cache Preparation

Split section-writing prompts into cached (stable across sections) and volatile (per-section) components as a clean architectural separation, even before model providers fully support prompt caching for Primr's use case.

- Cached prefix (identical across all 23 parallel section writes): company context, analysis workbook, scrape summary, external research summary, general writing instructions, citation style guide
- Volatile suffix (per-section): section name, section-specific prompt, section-specific evidence excerpts, word target
- Ensure the cached prefix is byte-identical across all parallel section writes — no timestamps, no randomized evidence ordering, no section-specific context in the prefix
- This is a zero-cost architectural prep step: it doesn't add caching API calls, it just structures the prompts so caching works when providers support it
- When prompt caching becomes available (Anthropic supports it now; xAI and Google may follow), the payoff is significant: a cache miss on the shared prefix means paying full input token cost 23 times instead of once
- Applies the same principle to strategy generation prompts and cross-validation prompts where a shared context prefix is reused across multiple calls

#### xAI Batch API for Section Writing

Use xAI's Batch API for the most token-intensive pipeline stage (section writing) to reduce cost and eliminate rate-limit risk during large batch runs.

Why section writing: each company generates 23 independent section-writing calls — the single most expensive stage (~40-50% of Grok spend) and the only one where all calls are independent of each other. The other stages (gap analysis, workbook, cross-validation) are sequential and depend on prior outputs, making them poor candidates for async batch processing.

- New `--batch-api` flag on `primr --batch` to opt in to Batch API for section writing
- After the analysis/workbook stage completes for a company, submit all 23 section prompts as a single xAI batch instead of running them through `ThreadPoolExecutor(max_workers=4)`
- Poll batch status until complete (typically minutes, SLA up to 24 hours)
- Retrieve results and feed into cross-validation as normal
- xAI Batch API benefits: reduced pricing (typically ~50% discount), no per-minute rate limits, requests processed in background queue
- For a 100-company batch at ~$0.65 Grok spend each: saves ~$16-32 on section writing alone, plus zero risk of 429 errors during the most API-intensive phase
- Scraping and sequential LLM stages (gap analysis, workbook, cross-validation, strategy) remain synchronous — they're either I/O-bound (scraping) or sequentially dependent
- Graceful fallback: if Batch API is unavailable or times out, fall back to existing `ThreadPoolExecutor` path
- Progress display updated: "Section writing (batch API, polling...)" with ETA based on batch state counters
- Strategy generation could also be batched when running multi-platform strategies (multiple independent strategy calls)
- Requires `xai-sdk` or raw HTTP — evaluate SDK maturity vs direct `httpx` calls to `/v1/batches`
- Decision gated by xAI Batch API pricing confirmation and SDK stability

Larger batch pipeline restructuring (scrape-all-first, then batch all LLM work across companies) is a bigger architectural change. Evaluate after single-company batch API proves out. The wall-clock tradeoff (async queue vs immediate) may not justify the complexity for batches under ~20 companies.

#### Snapshot Subcommand

A new top-level subcommand for the case where you want a fast look at a company before deciding whether to spend $0.60 on a real run. Explicitly framed as screening, not analysis. Not a quality dial on `primr` — a separate, narrower product.

Why this exists at all (and why the older "Quick Mode" framing was dropped): degrading the standard pipeline to chase sub-5-minute runtime is a bad trade. If you want fast-and-shallow, you can already get that for free from a search engine. The interesting cheap-and-fast tier is one that does specifically what's actually free or near-free in well under a minute: DNS recon, homepage render, and a single LLM synthesis pass. Anything beyond that costs real time and real money and should go through the real pipeline.

What the subcommand does:
- `primr recon` (DNS intelligence, ~3s, free, already exists)
- Homepage + 2-3 highest-signal pages (about, leadership, products) via Playwright tier 1 only — no escalation, no fallback fan-out
- One DDG search for recent news (free)
- One Grok 4.1 synthesis call producing a one-page Markdown brief

Budget: ~30-45s wall-clock, ~$0.03, no DOCX, no QA gate, no cross-validation, no strategy.

Output shape: a single Markdown one-pager with sections for who they are, tech stack signals from DNS, what's on their homepage right now, one recent news item if DDG returned anything, and an explicit footer pointing to the full `primr` command. The artifact has a header banner that says "Snapshot — screening only, not strategic analysis" so it's never confused with a real report.

What it explicitly is not:
- No tier escalation: if Playwright tier 1 doesn't render the homepage, the snapshot fails fast and tells the user to run the full pipeline
- No public-data fallback fan-out (Wayback / EDGAR / Wikipedia) — that's a strategic recovery path, not a screening tool
- No hiring signals, no cross-validation, no strategy, no DOCX
- No cost-vs-depth dial on the standard pipeline — `primr` always means "excellent report"

Decision principle:
- The standard pipeline is the product. Snapshot is the cheap pre-flight that helps you decide whether to invoke it. Speed is only worth paying for when the alternative is free.

#### Post-Research Skill Processing (Anthropic Skills API)

**The problem Primr solves today ends at the artifact.** Primr produces a strategic overview, an AI strategy document, and supporting artifacts. What happens next — turning those into a client-ready deliverable, an internal brief, a CRM enrichment payload, an ideas page — is different for every user and every organization. Today that workflow is manual: copy the `.md` output, paste it into Claude, run your own skill or prompt, iterate.

This feature makes that handoff automatic and generic. Primr ships the plumbing to pipe its artifacts through any user-provided skill via the [Anthropic Skills API](https://docs.anthropic.com/en/docs/build-with-claude/skills). The skill itself is entirely the user's business — Primr doesn't know or care what it does. A consulting firm might run a "client brief generator" skill. A sales team might run a "deal qualification" skill. An investor might run a "due diligence memo" skill. Primr just feeds the artifacts in and collects whatever comes out.

**What this is:**
- A generic, optional post-processing phase in the Primr pipeline
- Infrastructure that belongs in the public repo because it's skill-agnostic
- A clean boundary: Primr's job ends at research artifacts, the skill's job starts there

**What this is not:**
- Primr shipping specific downstream skills (those are user/org-specific, outside the repo)
- A replacement for the existing MCP skills (those are for controlling Primr, not consuming its outputs)
- A requirement — if you don't configure a skill, nothing changes

**How it works:**

1. User creates their own skill (a folder with `SKILL.md` + scripts + resources) for whatever downstream workflow they need
2. User uploads it to the Anthropic Skills API (once) and gets back a `skill_id`
3. User configures Primr with the skill ID and an Anthropic API key
4. After research completes, Primr calls the Messages API with the skill loaded and the research artifacts as input
5. Primr downloads any files the skill produces and drops them alongside the other outputs

**CLI interface:**

```bash
# One-off: run a skill against the outputs of this research run
primr "Company" https://company.com --post-skill skill_01AbCd...

# Reprocess existing artifacts through a skill without re-running research
primr skill-run "output/Company_Strategic_Overview_03-06-2026.md" --skill skill_01AbCd...

# Upload a local skill folder to the Anthropic Skills API (helper, not required)
primr skill-upload ./my-skill-folder
# → prints skill_id to configure in .env or pass via --post-skill
```

**Configuration (`.env`):**

```bash
# Optional — post-research skill processing via Anthropic Skills API
# ANTHROPIC_API_KEY=sk-ant-...
# PRIMR_POST_SKILL_ID=skill_01AbCd...
# PRIMR_POST_SKILL_VERSION=latest
```

When `PRIMR_POST_SKILL_ID` is set, every research run automatically pipes artifacts through the skill after the standard pipeline completes. `--post-skill` on the CLI overrides or supplements the env config. `--no-post-skill` skips it for a single run.

**Implementation shape:**

- New module: `src/primr/ai/skills_api.py` — thin Anthropic Skills API client (upload, invoke, download results)
- New pipeline phase: `post_skill` — runs after report generation and QA, before final output summary
- Skill invocation uses the Messages API with `container.skills` and `code_execution` tool enabled so skills can run bundled scripts
- Multi-turn handling: skills that need multiple turns (pause_turn) are handled automatically
- File download via the Anthropic Files API for any artifacts the skill produces
- Output files land in the same output directory as the research artifacts, with a `_skill/` subfolder to keep them separate
- Cost tracking: skill API calls are tracked in the same usage/cost system as research calls
- `--dry-run` includes estimated skill processing cost (based on input token count of artifacts)

**What the user's skill folder looks like (their repo, not Primr's):**

```
my-downstream-skill/
├── SKILL.md # Instructions for Claude on what to produce
├── scripts/
│ ├── generate_html.py # Custom output generation
│ └── brand_assets.py # Org-specific styling/templates
└── templates/
 └── brief_template.html
```

Primr never sees or ships this. The user uploads it once, gets a skill ID, and configures Primr to use it.

**Batch support:**

When running `primr --batch companies.csv`, the post-skill phase runs per-company after each company's research completes. This means a batch of 20 companies produces 20 research artifacts AND 20 downstream deliverables in one pipeline run.

**Relationship to existing skills:**

The four skills in `skills/` (company-research, hypothesis-tracking, qa-iteration, scrape-strategy) are MCP-first control-plane skills — they tell Claude how to drive Primr. Post-skill processing is the inverse: Primr drives Claude with the user's skill to transform its own outputs. These are complementary, not competing.

**Relationship to Agentic Interoperability (Agentic Interoperability):**

This is a concrete, near-term version of the "Primr produces intelligence, the next role picks it up" vision. The difference is that Agentic Interoperability envisions this happening via A2A protocol between agents, while post-skill processing does it via the Anthropic Skills API within a single pipeline. Post-skill processing is the simpler, more immediate path that works today without requiring a multi-agent orchestrator.

**Setup flow integration:**

`setup_env.py` adds the optional Anthropic Skills API section to `.env` with comments explaining the flow. `primr doctor` checks for valid `ANTHROPIC_API_KEY` and `PRIMR_POST_SKILL_ID` when configured, and verifies the skill exists and is accessible. Documentation covers the full lifecycle: create a skill folder → upload it → configure Primr → run research → get downstream deliverables automatically.

**Security considerations:**

- Skills run in Anthropic's cloud containers, not on the user's machine — the skill cannot access local files beyond what Primr explicitly sends
- Primr sends only the research artifacts (report, strategy, QA summary) — no API keys, no working directory contents, no scrape traces
- Users are responsible for the security of their own skills (same as any code they upload to a cloud API)
- `primr doctor` warns if a configured skill ID is invalid or inaccessible

#### Agent Control Plane Hardening

The MCP/OpenClaw/skill integrations are now treated as a disciplined Primr control plane rather than thin shell wrappers. The next work here is narrower and more intentional than the initial integration push.

What this work is for:
- Make long-running, paid Primr runs safer and easier to route, approve, monitor, resume, and consume from agent clients.
- Keep the user experience aligned to Primr's actual product shape: URL in, serious artifact out.

What this work is not for:
- Turning Primr into a generic orchestration platform.
- Replacing the CLI or duplicating core business logic in skills.
- Exposing a shell-shaped `run_primr(command_string)` surface.

Planned next steps:
- Add server-issued approval tokens for cost-incurring operations so approval is harder to bypass than cost-cap propagation alone
- Expand job-scoped resources for artifact consumption (`qa_summary`, source appendix, trace summary) so clients do not need large report bodies in context by default
- Add integration eval suites for routing, approval, recovery, and recomputation avoidance
- Keep skills thin and MCP-first; intentionally avoid turning SKILL files into duplicated application specs
- Preserve typed lifecycle/control-plane primitives instead of free-form execution wrappers

#### Windows Working-Directory Hardening

Reduce false negatives and transient failures on Windows machines where the repo lives inside OneDrive or similar synced folders.

- Make checkpoint/state writes tolerant of transient `PermissionError` during atomic rename
- Update `primr doctor` to probe the same atomic write path used during real runs
- Add explicit docs for keeping high-churn `working/` paths outside synced folders when possible
- Longer term: support a configurable working directory separate from the repo root

#### Cross-Run Research Memory

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

#### Knowledge Compounding

Build on cross-run memory to make research compound across batch runs and evolving investigations.

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
- Cross-run memory stores the evolution

#### Narrative Evolution

Make Primr the system of record for how thinking evolves about a company. Requires cross-run memory .

- Versioned research artifacts
- Explicit "what changed and why" sections
- Diff-style comparison between runs: what shifted in confidence, what new evidence appeared
- Timeline view: how understanding of a company evolved across runs

#### Agentic Interoperability

**The shift: from tool to role.**

Primr already does deep company research. The next evolution is positioning it as a composable role in multi-agent workflows — not just something a human runs, but a specialist that other agents can assign work to and build on.

Today: "run primr on this company." Next: "assign the account strategist to this deal and let downstream roles build on its findings."

The infrastructure is already in place (A2A protocol, MCP tools, subagent architecture). What changes is the framing and how Primr presents itself to the broader agentic ecosystem.

**Role-Aware Output Shaping:**
- When called via A2A, Primr adapts its output to the requesting workflow's needs — a downstream agent building a proposal gets tighter focus on opportunities and angles; one doing risk assessment gets constraints and gaps emphasized
- AgentCard skills already declare capabilities; extend with output-format negotiation so callers can request the emphasis they need
- Expert perspective passes become named analyst roles that shape output tone, not just appended report sections

**Workflow Composability:**
- Primr as one role in a team: receives a company assignment, produces intelligence (MD, DOCX), and the next role picks it up
- A2A protocol already supports assignment and handoff; the evolution is Primr understanding its place in a larger workflow rather than assuming it's the terminal step
- No orchestrator built into Primr — Primr is a specialist, not the coordinator

#### Cloud Deployment Hardening

Take the existing IaC templates (`deploy/`) from reference implementations to validated, production-ready deployments. The infrastructure code exists (the cloud deployment work) but hasn't been battle-tested end-to-end. This version makes it real.

**Approach:** Azure first (most immediate need), then GCP, then AWS. Each cloud gets the same treatment: deploy, run real research jobs, validate artifacts, tear down, document.

**Azure Tiered Deployment (In Progress)**

Primr's Azure deployment now follows a tiered model — team and organization — with declarative Bicep IaC, a hardened deploy script, and integration surfaces for Microsoft agent platforms.

*What's implemented:*

- Bicep templates (`deploy/azure/bicep/`) for all Azure resources with tier-conditional provisioning (team vs organization)
- Deploy script (`deploy/azure/deploy.sh`) with `--tier`, `--bicep`, `--budget`, `--min-replicas`/`--max-replicas` support
- OpenAPI spec (`deploy/azure/openapi.yaml`) with `x-ms-agentic-protocol: mcp-streamable-1.0` for Power Platform connector creation
- Budget tracker module with per-API-key spending limits (per-job, daily, monthly)
- Environment auto-detection (local vs Azure) based on Azure-specific env vars
- Entra ID JWT audience claim validation for organization tier
- `show_usage` MCP tool for agent clients to check remaining budget
- Enhanced `doctor` tool with cloud diagnostics (Cosmos DB, Blob Storage, Service Bus, App Insights)
- `/healthz` endpoint for Container App health checks
- Azure Budget resources with alerts at 50%, 80%, 100% of configurable monthly spend

*Agent platform integration surfaces:*

- **Foundry Agent Service**: MCP tool connection via project connection (key-based, Entra agent identity, Entra managed identity). Guide: `docs/FOUNDRY_AGENT_GUIDE.md`
- **Copilot Studio**: Power Platform custom connector from OpenAPI spec with MCP tool discovery. Guide: `docs/COPILOT_STUDIO_GUIDE.md`
- **Copilot Cowork**: Copilot Studio agent published to M365 Agent Store for organization-wide discovery. Guide: `docs/COPILOT_COWORK_GUIDE.md`
- **Any MCP client**: Claude Desktop, Cursor, VS Code, Microsoft Agent Framework — point at `https://{fqdn}/mcp`

*Deployment tier comparison:*

| Resource | Team (< $5/mo idle) | Organization (< $15/mo idle) |
|---|---|---|
| Container App (MCP + API) | Scale-to-zero | Min 1 replica |
| Cosmos DB | Serverless | Autoscale (400-4000 RU/s) |
| Service Bus | — | Standard (dead-letter) |
| Application Insights | — | With daily cap |
| Entra ID Auth | — | ✅ |
| Budget Tracker | — | ✅ (Cosmos container) |
| Azure Budget Alerts | $50 default | $200 default |

*What's remaining (known issues):*

- **Container App entrypoint**: The MCP server (`primr-mcp --http`) needs to run correctly inside the Docker container. The Bicep command override is in place but the container crashes on startup — likely a dependency or import path issue that needs local debugging. The Dockerfile currently builds for the job runner; the API server entrypoint needs the same image to also serve HTTP.
- **Container App Job triggering**: The MCP server's `research_company` tool needs to trigger Container App Jobs in cloud mode instead of running the pipeline in-process. This is the queue integration that enables 20+ concurrent users.
- **ACR build log streaming on Windows**: Azure CLI's `az acr build` crashes on Windows due to a Unicode encoding bug in colorama/cp1252. Workaround: poll `az acr task list-runs` for completion instead of streaming logs. The deploy.ps1 script needs this fix finalized.
- **Structured logging for Application Insights**: Log fields (request_id, job_id, tool_name, duration_ms) are designed but not yet wired into the container runtime.
- **VNet integration**: Documented as a production TODO. Private endpoints for Cosmos DB, Storage, Key Vault, and Service Bus are not yet configured.
- **GCP and AWS validation**: Azure is the first cloud target. AWS and GCP templates exist as reference implementations but are not validated.

*What's validated and working:*

- Bicep IaC deploys all resources in one command (~3.5 minutes)
- Container App scales to zero, cold starts in ~30 seconds
- Cosmos DB (serverless) connected via managed identity
- Blob Storage connected via managed identity
- Key Vault with RBAC, deployer access, and placeholder secrets
- ACR with managed identity pull
- /healthz endpoint passes (Cosmos DB + Blob Storage connectivity verified)
- Budget tracker with per-user spending limits (55 tests)
- Auth with Entra ID JWT audience validation (66 tests)
- Environment auto-detection, cloud diagnostics (41 tests)
- Full security review: 28 findings identified and fixed
- OpenAPI spec with x-ms-agentic-protocol for Copilot Studio
- Documentation: Azure Quickstart, Foundry Agent Guide, Copilot Studio Guide, Copilot Cowork Guide
- Cost profile documented: idle cost ($0), per-run overhead, storage costs

**GCP**

- Validate `deploy/gcp/` templates: Cloud Run Jobs → Pub/Sub → Cloud Storage
- Workload Identity Federation for keyless auth
- Cloud Trace + Cloud Monitoring integration
- `deploy/gcp/deploy.sh validate` smoke test
- Cost profile documented

**AWS**

- Validate `deploy/aws/` templates: Fargate → SQS → S3
- IAM roles for task execution (no long-lived credentials)
- X-Ray tracing + CloudWatch integration
- Step Functions for job orchestration (already templated in `step-function.json`)
- `deploy/aws/deploy.sh validate` smoke test
- Cost profile documented

**Cross-Cloud Consistency**

- Unified CLI: `primr deploy <cloud> <env>` wraps the per-cloud deploy scripts
- Shared control plane API contract across all three clouds (same endpoints, same auth, same job lifecycle)
- Integration test suite that runs against any deployed environment: submit → poll → retrieve → validate artifact quality
- Terraform or Pulumi option alongside the existing shell scripts for teams that prefer declarative IaC
- Documentation: deployment guide per cloud, cost comparison table, architecture diagrams

**What stays local-first:**

- CLI is always the primary interface — cloud deployment is for organizational scale, not a replacement
- All research logic runs in the container, unchanged — the cloud layer is queue + storage + auth, not a rewrite
- `primr doctor` works in both local and deployed contexts
- Artifacts are downloadable as the same MD/DOCX/TXT files you get locally

#### Public Release

Make Primr available to the broader community via PyPI.

**Prerequisites:**
- Content Sanitization Layer (complete — security requirement satisfied)
- Cloud Deployment Hardening (at least one cloud validated end-to-end — see entry above)

**Scope:**
- PyPI publication (`pip install primr`)
- Public GitHub repository
- ~~GitHub Actions CI/CD for automated testing~~ (done - lint, type check, tests run on every push)
- Contribution workflow for external contributors
- Documentation site
- Guided first-run setup is now covered by `primr init`, with `primr doctor --fix` as the explicit interactive recovery path and `primr keys set/list/path` for direct key management. PyPI users no longer need to discover a repo-local `.env` before running diagnostics.
- Remaining packaging cleanup: keep `setup_env.py` as a source-checkout helper for now, then reduce it to a thin wrapper around `primr init` once the PyPI install path is the default documented path.


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
- Multi-agent systems use ~15x more tokens than single-agent ([LangChain State of Agents](https://www.langchain.com/state-of-agent-engineering)), which directly conflicts with Primr's ~$0.75 value proposition.
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

# AI Strategy (most common: Microsoft + NVIDIA)
primr "ExampleCo" https://example.co --platform ms              # Microsoft + NVIDIA shorthand
primr "ExampleCo" https://example.co --platform azure
primr "ExampleCo" https://example.co --platform aws azure  # Multi-platform
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
| 1.21.2 | Apr 2026 | Release fix for client-folder output and recon platform defaults: `--output-dir` now reaches the research pipeline, custom output directories keep only Markdown/DOCX deliverables while TXT mirrors and validation diagnostics stay in run diagnostics, recon platform selection now uses strong infrastructure signals only, and unclear/skipped recon falls back to Azure + private cloud/NVIDIA. |
| 1.20.1 | Apr 2026 | PyPI release infrastructure: `.github/workflows/release.yml` triggers on `v*` tag push or manual dispatch, builds sdist + wheel, runs `twine check`, publishes via PyPI trusted-publisher OIDC (no API token in repo secrets). Repo cleanup: root `.md` reduced to `README.md` and `ROADMAP.md` — `CHANGELOG`, `CONCURRENCY`, `CONTRIBUTING`, `SECURITY` moved to `docs/`. `CLAUDE.md` removed from version control (gitignored, kept on disk for local workflow). ROADMAP entry queued to fold `setup_env.py` into a `primr init` subcommand once PyPI ships. |
| 1.20.0 | Apr 2026 | Continuous reasoning session is now the default for the standard pipeline: workbook generation and cross-validation share a single Grok 4.20 session so the validator inherits corpus + workbook reasoning instead of re-reading the report cold. Decision driven by an n=3 paired-comparison pilot — 3/3 workbook wins, 2/3 cross-val wins, 2/3 final-report wins, ~81% reduction in leaked-instruction lines, avg ~+12% cost. New `ContinuousReasoningSession` class, `--no-continuous-reasoning` opt-out, `PRIMR_CONTINUOUS_REASONING` env var. Roadmap restructured into a single ordered priority list (no version-numbered milestones). Separate ROADMAP entry added for artifact drift in the standard pipeline (independent of topology). |
| 1.19.0 | Apr 2026 | Hiring-signal gathering (Greenhouse / Lever / Ashby / SmartRecruiters board APIs + careers-page fallback, LLM triage and structured extraction, threaded into all downstream phases). Public-data fallback fan-out (Wayback / EDGAR / Wikipedia / sister subdomains) when the origin is fully blocked. Patchright stealth tier with global headed-popup budget. Verified page-access classifier promoted to first-class. |
| 1.18.1 | Apr 2026 | Observability and reliability hardening: thread-safe `LogContext` via contextvars, `ContextFilter` wired into file logging, structured logging added to 15+ silent `except` paths (run state, source relevance, trust polish, gap analysis, cross-validation, search queries, section writing, scrape cache, domain profiles, usage tracker), cross-validation and gap analysis failures now surface to user instead of looking like clean passes, Gemini client errors logged to file (not just stdout), failed search query aggregate tracking, `__init__.py` version synced with pyproject.toml |
| 1.18.0 | Apr 2026 | Recon integration (DNS intelligence pre-flight, auto-platform detection, `primr recon` subcommand, 156 fingerprints, 20 signals, crt.sh cert transparency, SRV detection, custom signals), `--cloud-vendor` renamed to `--platform` with backward compat, `--platform ms` shorthand, recon context injection into all strategy types |
| 1.17.0 | Apr 2026 | Pipeline resilience (cost-ordered recovery, foreground/background stages, model circuit breaker), MCP estimate_run fix (cloud vendors, strategy type, historical data, time ranges), corrected duration estimates |
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
