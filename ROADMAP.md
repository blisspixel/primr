# Primr Roadmap

Current State: v1.27.1

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
- **Skill pack subsystem** (`primr skills`, MCP `generate_skill_pack`): a first-class workflow that takes recon + hiring + research evidence and produces a QA-refined Agent Skills pack. Up to 15 roles × M skills, two-call planning step (observed roles from postings + plausible roles inferred from research and industry classification, with provenance preserved end-to-end), archetype-grounded provenance-aware authoring, deterministic ASKILL-* validation, capped per-skill refinement loop, pack-level coherence pass. Inspectable `role_plan.md` / `role_plan.json` artifacts; `--plan-only` writes the plan and exits, `--from-plan` authors against a saved plan, `--roles-override` bypasses discovery entirely. Emits both an unpacked Claude/Cursor/VS Code tree AND a Microsoft 365 Copilot Cowork sideload `.zip` from one byte-identical set of SKILL.md files. Multi-provider image generation for the Cowork icon (Grok Imagine → Gemini Imagen → OpenAI image → programmatic Pillow gradient+shape → solid PNG).
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
- Public-data fallback fan-out (`src/primr/data/fallback_sources.py`): when origin is blocked, fetches in parallel from Wayback CDX, sister subdomains, RSS/Atom feeds, SEC EDGAR 10-Ks, Wikipedia REST, and Grok web_search synthesis
- Hiring-signal gathering (`src/primr/data/hiring_signals.py`): eight ATS providers (Greenhouse / Lever / Ashby / SmartRecruiters / Workday / Workable / Recruitee / Jobvite), corpus-driven Workday URL discovery for known boards, HTML careers-page fallback, DuckDuckGo web-search fallback across major job-board hosts when every other path comes up empty, LLM-triaged extraction threaded into all downstream phases. Skill packs are job-posting-first — when both posting and research evidence are empty the pipeline fails closed unless `--allow-recon-only` is passed.

### Operational Maturity

- Cost estimation, usage tracking, job recovery, crash/reboot recovery
- System diagnostics (`primr doctor`)
- 6,500+ tests, full ruff compliance, mypy clean on an incremental strict ratchet (see [Engineering Standards & Toolchain](#engineering-standards--toolchain))
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

The active queue is ordered top-down by priority. Each item is concrete enough to start without further design work.

> Cross-cutting engineering-standards and toolchain work is tracked separately in [Engineering Standards & Toolchain](#engineering-standards--toolchain) rather than as a numbered queue item, since it spans the whole repo and runs in parallel with feature work. Phase 1 (uv lockfile, CI Python matrix, security gates, coverage ratchet, pre-commit) is the current active engineering initiative.

### 1. Artifact Drift — Remaining Work

The cleanup cuts shipped in v1.24.2 fixed the dominant leak vectors at the canonicalization seam: bold-wrapped `**What to validate:**` lines now dedup into the single canonical trailing line via `_normalize_generated_section_payload`, and `[cross-ref ...]` plus bare/space-separated `[workbook]` markers are stripped in `_clean_fast_report_output`. An offline scan over 16 recent reports confirmed the leak was widespread (240 workbook + 87 cross-ref + 65 bold-validate instances), and the `ReportAnalyzer.analyze_scaffolding_leakage()` check makes regressions visible. **The three remaining items are now SHIPPED:**

- **Upstream-cause audit + hardening — DONE.** The model bolds the label (`**What to validate:**`) because the section prompts present `"What to validate:"` as a quoted label and never told the writer to emit it as plain prose; the canonicalization seam (`section_parsing.py` `_normalize_generated_section_payload`) then normalizes the line-leading bold form, but residue survives when a section bypasses that seam (mixed-format/regenerated paths). Symptom-fix at the seam stays; added a minimal upstream instruction in both `section_prompts.py` OUTPUT CONTRACT blocks and the `research_agent.py` regeneration prompt to write the line as plain text (no bold/italics/bullet), reducing the rate the bold form is produced at all.
- **Configurable shipping gate — DONE.** The leak scan is now factored into the pure `qa.report_analyzer.scan_scaffolding_leakage()` (single source of truth) and wired into the ship-time gate `output.artifact_validation._validate_output_markdown`. Leaks above a configurable threshold (`PRIMR_MAX_SCAFFOLDING_LEAKS`, default 0 = zero tolerance, malformed/negative falls back to 0) fail the markdown gate, which withholds the polished DOCX (MD/TXT + sidecar validation report still written) — no longer just a warning. Because canonicalization runs upstream, a healthy run sits at 0 leaks and never trips; the gate only fires on a regression.
- **Eval-harness wiring — DONE.** `model_eval` computes a `scaffolding_leaks` per-report metric and a `total_scaffolding_leaks` per-profile aggregate, surfaced in a new scorecard `## Artifact Drift` section (clean/DRIFT status per profile) and a `scaffolding_leaks` CSV column — so the regression is tracked every eval run instead of via ad-hoc offline scans.

Decision principle: final shipping artifacts must read as deliverables, not as internal scaffolding.

### 2. Artifact Pipeline Hardening

Primr needs a sharper separation between **intermediate research artifacts** and **final shipping artifacts**. Research-stage artifacts (scrape summaries, source inventories, contradiction notes, section briefs) are machine-facing inputs to later stages — they need to be consistent, parseable, and provenance-preserving. Final reports and strategy documents need to ship as polished Markdown / TXT / DOCX / PDF with stable section structure, auditable citations, and predictable validation behavior. Treating both classes as "just markdown" creates placeholder leakage, brittle regex repair, false-positive validator blocks, and renderer edge cases that only show up at batch scale.

Planned:
- Keep intermediate research outputs flexible, but make them more explicitly structured for downstream consumption (evidence packets, source inventories, contradiction records, section briefs)
- Push more consistency upstream into the long-form writing and regeneration prompts so final-stage cleanup has less arbitrary prose repair to do. **Foundation shipped:** the final-stage cleanup is now *measured* — `report_cleanup.compute_repair_report(before, after)` (reusing the ship-time scaffolding scanner) quantifies how many markers the deterministic cleanup had to strip per run and whether the raw writer output was already clean; wired at the report cleanup seam to log a summary + persist `_shipping_repair.json`. The headline `writer_output_clean` signal turns "is the cleanup load-bearing or a safety net?" from invisible into tracked, so the prompt-hardening can target the repairs that actually fire (and be validated against the metric) rather than guessing. One upstream fix already landed (the plain-text `What to validate:` instruction). **Prompt hardening — DONE:** the writer/regeneration prompts now carry an explicit prohibition against the markers the cleanup strips, sourced from a single shared constant `qa.report_analyzer.SCAFFOLDING_PROHIBITION_GUIDANCE` co-located with `scan_scaffolding_leakage` so the upstream instruction and the downstream ship-time gate cannot drift. It names every category the scanner flags (`[workbook]`/`[Analysis Workbook]`, `[cross-ref ...]`/`[see ## ...]`, informal `[cite: label]`, bold `**What to validate:**`) and gives the writer the substitute behavior (prose references, numeric-only `[cite: N]`). Spliced into both `section_prompts.py` writer prompts (`_build_fast_batch_prompt`, `_build_fast_section_prompt`) and both regeneration prompts (`_fast_regenerate_section`, `_strategy_regenerate_section` — the latter also gained the previously-missing plain-text validate instruction). Parity is locked by a deterministic test (`TestScaffoldingProhibitionParity`: every scanned category must be named in the guidance) plus presence tests on all four prompts; runtime effect is tracked by the `writer_output_clean` signal in `_shipping_repair.json` and the eval `## Artifact Drift` metric. With both the foundation and this hardening shipped, this bullet is complete.
- Strengthen artifact shipping gates to validate section structure and citation integrity, not just scan for forbidden markdown leftovers. **Citation integrity — DONE:** `_validate_output_markdown` now runs a configurable citation-integrity gate (dangling inline `[cite: N]` with no matching `## Sources` entry) backed by the pure `qa.report_analyzer.scan_citation_integrity()`; default zero-tolerance (`PRIMR_MAX_DANGLING_CITATIONS`), fail-closed, withholds the DOCX (MD/TXT + sidecar still written). This is the deterministic backstop behind the upstream LLM citation repair, which keeps the original (possibly still-dangling) report when it cannot reach zero. Covers both report and strategy docs (both ship through that validator). **Section structure — DONE (safe subset):** a configurable section-structure gate (`scan_section_structure()`, `PRIMR_MAX_STRUCTURE_DEFECTS`, default 0) now blocks the DOCX on the *unambiguous* defects — duplicate top-level `##` headings and empty sections — validated against the regression corpus so it does not false-block clean long-form reports. **Deliberately not gated:** required-section *presence*, which is report-type-dependent and too false-positive-prone to block shipping on; it stays a QA-scoring signal in `analyze_structure`.
- Build a regression corpus from real shipped and failed artifacts so renderer/validator changes are tested against actual long-form outputs. **DONE (seed + harness):** `tests/fixtures/artifacts/` holds long-form report/strategy fixtures (placeholder companies) with a `manifest.json` of expected gate outcomes; the data-driven harness `tests/test_output/test_artifact_corpus.py` runs each through `_validate_output_markdown` (asserting pass/fail + issue categories) and renders the clean ones end-to-end through `markdown_to_docx` + `_validate_output_docx`. A completeness test fails if a fixture is dropped in without a manifest entry. Sanitized real shipped/failed artifacts can be added later by dropping a file + a manifest row — no test code changes. This unblocks the section-structure gate above.
- Continue moving final rendering toward structured document data rather than free-form markdown recovery wherever practical

Decision principle: permissive about formatting in the research pipeline, strict about formatting and structure in the final document pipeline.

### 3. Verified Page Access — First-Party Recovery Expansion

The shared page-access classifier, evidence-backed classification, Kasada/KPSDK challenge-shell coverage, homepage fast-path validation, first-party sitemap/guessed-path recovery, Wayback challenge-shell filtering, and public-data fallback fan-out have all shipped. What remains:

- Expand first-party fallback probing beyond current sitemap/guessed-path recovery: investor/news/about/help PDFs, feeds, and structured data endpoints with better prioritization. **RSS/Atom feeds — DONE:** `fallback_sources.fetch_feed_content` recovers recent press/news/blog content from the host's own feeds — clean XML that is frequently served uncached/unprotected even when the marketing origin sits behind a WAF. Discovers feeds via HTML `<link rel="alternate">` autodiscovery plus a common-path sweep, same-site-filtered (defense-in-depth on top of the SSRF guard in `_http_get`), parses RSS 2.0 + Atom namespace-agnostically with stdlib (no new dependency), dedupes items across feeds, and joins the parallel fan-out as a first-class `source="feed"` alongside subdomain/EDGAR/Wikipedia/Wayback. Remaining: investor/news PDFs and structured-data endpoints with better prioritization
- Add host-level learning so once Primr sees a confirmed real page for a host it can persist useful positive markers for later pages
- Add optional screenshot/text-snapshot comparison for browser tiers to distinguish stable real homepages from interstitial templates
- Surface a clearer user-facing blocked-site summary in the CLI with evidence snippets and recommended next actions
- Extend trace analytics and eval suites to score false-positive and false-negative rates for access classification on protected sites
- Hiring-signal extensions: Workday + Workable + Recruitee + Jobvite providers landed with a corpus-driven Workday URL discovery path and a DuckDuckGo web-search fallback when every ATS plus the careers crawl misses. Remaining: BambooHR and iCIMS providers (both lack clean public JSON APIs — handled by HTML fallback for now), wire hiring signals into `--premium` (fast-mode only today), and consider host-level memory so subsequent runs of the same company skip re-probing providers that already missed

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

### 6. Wire Circuit Breaker Into Production LLM Call Sites

The `ModelCircuitBreaker.execute_with_fallback()` mechanism is callable and tested but not yet invoked from `research_agent.py` LLM call sites. Today a provider quota blip during a run can fail the run instead of advancing to the next model in the cross-provider chain. Wire it into the production pipeline so quota events trigger automatic provider failover.

### 7. Diminishing Returns Detection for Cross-Validation

Detect when cross-validation or section regeneration is making diminishing progress and stop early, rather than consuming the full token budget.

- After each section regeneration, measure improvement: word count delta, new citation count, QA score change
- If 3+ consecutive regenerations each produce <5% improvement in QA score, stop the loop early
- Log the early stop in the QA summary: `cross-validation: stopped early (diminishing returns after N iterations)`
- Applies to both the existing cross-validation pass and the planned QA iteration loop
- Start conservative and tune thresholds based on eval results

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

### 12. Working-Directory Tidiness for CLI Users

When primr is installed via `pip install primr` and run from an arbitrary
folder (e.g. `docs/<company>/`), the working files (`working/`,
`output/`, `_diagnostics/`) end up scattered into wherever the user
invoked the command. Running back-to-back in `companyname/`, then
`company2name/`, then `company3name/` leaves a messy filesystem with
duplicated state. Tighten the story:

- Default `output/` and `working/` paths should resolve relative to the
  invocation directory consistently, and the on-disk shape should
  document itself with a top-level README per output folder so the user
  knows what's safe to delete vs preserve.
- Add a per-user cache directory (e.g. `~/.cache/primr/` or
  `%LOCALAPPDATA%\primr\`) for shared state that has no business
  per-company duplication — vendor research, recon caches, eval
  baselines, prompt cache hints.
- Vendor news (`vendor-research/`) is the prime example of shared
  state that primr currently writes into the invocation directory; it
  belongs in the per-user cache. Move it and add migration logic.
- `primr doctor` should surface where each category of file lives so
  users have a single page that documents the on-disk story.

### 13. Vendor News Caching Across Runs + Weekly Freshness

The `is_vendor_research_current` default was 14 days; v1.26 tightened it
to 7 days (weekly). The remaining gaps:

- Vendor news is currently regenerated per invocation directory because
  the cache lives under the CWD. Multiple back-to-back runs in
  different company folders each regenerate the same vendor research,
  wasting Deep Research budget and time. Once item #12 lands the
  per-user cache, this collapses to a single shared file per vendor.
- Make the weekly freshness gate configurable via `PRIMR_VENDOR_NEWS_TTL_DAYS`
  env var so power users can dial it for high-velocity vendors (Azure
  during Ignite week) vs slow ones.
- Expose a `--refresh-vendor-news` flag and a `primr show-usage` line
  that says when each vendor research file was last refreshed.

### 14. Windows Working-Directory Hardening

Reduce false negatives and transient failures on Windows machines where the repo lives inside OneDrive or similar synced folders. Bumped up from the bottom of the queue because it actively bites this very dev environment (transient `PermissionError` on atomic renames, CRLF warnings on every git operation, OneDrive-driven race conditions on `_run_state.json`).

- Make checkpoint/state writes tolerant of transient `PermissionError` during atomic rename
- Update `primr doctor` to probe the same atomic write path used during real runs
- Add explicit docs for keeping high-churn `working/` paths outside synced folders when possible
- Longer term: support a configurable working directory separate from the repo root

### 15. Skill Pack: Deeper Anthropic Best-Practices

The v1.26 skill pack ships Anthropic's published authoring conventions
already (third-person descriptions, gerund-form names, checklist
workflows, template-pattern output formats, explain-WHY style, concision
over padding — all enforced via prompt + validator SOFT checks). The
remaining items from Anthropic's [skill-creator workflow](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
and [best-practices guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
are structural and worth their own milestone:

- **Agent-handoff declarations in SKILL.md frontmatter** (near-term — being
  implemented now): today the generated frontmatter is just `name` +
  `description`. Add an explicit capability/budget contract so a primr-authored
  skill is immediately usable by an agent without inferring what it implies —
  declared tool surface (`allowed-tools`), an MCP/A2A capability hint, and an
  estimated per-invocation budget. This makes the pack self-describing to a
  consuming agent (e.g. Deepr) and folds into the agent control-plane work (#21).
- **Per-skill trigger eval generation**: after authoring, generate 8-10
  should-trigger queries + 8-10 should-not-trigger near-misses, run the
  description through a discovery simulator, and iterate the description
  until trigger accuracy clears a threshold. This is Anthropic's published
  description-optimization loop applied per-skill.
- **Multi-model testing**: Anthropic recommends testing skills against
  Haiku, Sonnet, and Opus before shipping — "what works perfectly for
  Opus might need more detail for Haiku." Wire the skill pack pipeline
  to run a quick comprehension probe against multiple model tiers.
- **Progressive disclosure with `references/` and `scripts/` subfolders**:
  v1 emits single-file SKILL.md only. For richer skills, move deep
  reference material to `references/<topic>.md` (loaded on-demand,
  one level deep per Anthropic guidance) and deterministic helpers to
  `scripts/<name>.py` (executed via bash, output-only context cost).
- **Verifiable intermediate outputs (plan-validate-execute pattern)**:
  for skills that perform batch or high-stakes operations, emit a
  separate plan-file step the agent can validate before applying.
- **"Solve, don't punt" hardening**: when a skill references a script
  it would author later, generate the actual `.py` file alongside —
  per Anthropic's "bundled helper scripts make skills more reliable
  than letting Claude write them per-run."
- **Skill-level evals with grader**: produce `evals/evals.json` per
  skill (Anthropic's published structure) so users can re-grade the
  pack against their own assertions later.

After the standard pipeline, add domain-specific scrutiny of findings.

- Default: single "multi-perspective" prompt that evaluates from CFO, CTO, competitive, and risk viewpoints in one pass (~$0.03)
- `--with-experts full`: parallel expert reviews (4 separate passes, ~$0.15) for deeper analysis
- Output: "Expert Perspectives" section appended to report, or separate sidecar document

Perspectives:
- **CFO**: scrutinize financial claims, flag unsupported revenue estimates, assess unit economics
- **CTO**: evaluate technology stack claims, assess technical moat, identify build-vs-buy signals
- **Competitive analyst**: compare findings against known competitors, identify positioning gaps
- **Risk analyst**: identify regulatory, market, and execution risks

### 16. Strategic Inconsistency Refinement Pass

When the pack-level coherence pass flags a HARD `PACK-STRAT` finding
(roles assume contradicting stacks — e.g. one says Java/Spring, others
say Python/AWS, because both stacks exist in the company's hiring
postings), the v1.26 pipeline surfaces it in the report but doesn't
auto-fix. Add an explicit reconciliation round: when PACK-STRAT fires,
re-author the conflicting skills with cross-role context so they
acknowledge the multi-stack reality rather than contradict each other.

### 17. Auto-Eval on Model Releases

Reduce manual work when new model variants drop by automating the eval-and-compare cycle.

- Trigger eval sweep when a new model is registered in `ModelRegistry` (manual trigger initially, automated detection later)
- Run the standard 3-5 company corpus against the new model and current default, generate comparative scorecard
- LLM judge overlay (cloud or local Ollama) for subjective metrics: utility, strategic sharpness, hallucination rate
- Wire `--continuous-reasoning` / `--no-continuous-reasoning` into the eval harness so topology choice is scored against the same baseline systematically
- Decision output: "new variant is better/worse/equivalent for [stage]" with evidence
- Keeps defaults current without gut calls on each release

### 18. Capability-Requirement Routing Layer

Provider abstraction and role-based routing shipped in v1.22.0/v1.23.0. The still-planned half: each pipeline stage declares capability requirements and the router solves for the cheapest match.

- Each stage declares: minimum reasoning depth, required capabilities (web search, structured output, long context), acceptable providers
- Router selects the cheapest model that meets requirements from available providers
- Integrates with the circuit breaker — unhealthy models are skipped automatically
- Integrates with effort-level routing for hybrid inference
- Long-context surcharge modeling: populate `ModelConfig.tier_threshold_tokens` for OpenAI gpt-5.x family (>272K input: 2× input, 1.5× output) so cost estimates aren't silently wrong on long-input runs
- Move `grok_browse_and_summarize` and Gemini quota UI into providers (two pieces of provider-specific behavior still living outside the abstraction)

The requirements themselves come from observed eval cost/quality data per role, not a priori guessing.

### 19. Pipeline Overlap

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

### 20. Snapshot Subcommand

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

### 21. Agent Control Plane Hardening

The MCP/OpenClaw/skill integrations are treated as a disciplined Primr control plane rather than thin shell wrappers. Next work is narrower and more intentional than the initial integration push.

This work is for: making long-running, paid Primr runs safer and easier to route, approve, monitor, resume, and consume from agent clients. Keeping the user experience aligned to Primr's actual product shape: URL in, serious artifact out.

This work is not for: turning Primr into a generic orchestration platform, replacing the CLI, duplicating core business logic in skills, or exposing a shell-shaped `run_primr(command_string)` surface.

Planned:
- Add server-issued approval tokens for cost-incurring operations so approval is harder to bypass than cost-cap propagation alone
- Expand job-scoped resources for artifact consumption (`qa_summary`, source appendix, trace summary) so clients do not need large report bodies in context by default
- Add integration eval suites for routing, approval, recovery, and recomputation avoidance
- Keep skills thin and MCP-first; intentionally avoid turning SKILL files into duplicated application specs
- Preserve typed lifecycle/control-plane primitives instead of free-form execution wrappers

### 22. Azure Deployment Finalization

The Azure tiered deployment (team and organization) has its Bicep IaC, deploy script, OpenAPI spec, budget tracker, environment auto-detection, JWT validation, and cloud diagnostics in place. The deployment provisions in ~3.5 min, /healthz passes, and 162 tests across budget/auth/environment are green. The remaining items are concrete:

- **Container App entrypoint**: The MCP server (`primr-mcp --http`) needs to run correctly inside the Docker container. The Bicep command override is in place but the container crashes on startup — likely a dependency or import path issue that needs local debugging. The Dockerfile currently builds for the job runner; the API server entrypoint needs the same image to also serve HTTP.
- **Container App Job triggering**: The MCP server's `research_company` tool needs to trigger Container App Jobs in cloud mode instead of running the pipeline in-process. This is the queue integration that enables 20+ concurrent users.
- **ACR build log streaming on Windows**: Azure CLI's `az acr build` crashes on Windows due to a Unicode encoding bug in colorama/cp1252. Workaround in place: poll `az acr task list-runs` for completion instead of streaming logs. Needs to be finalized in `deploy.ps1`.
- **Structured logging for Application Insights**: Log fields (request_id, job_id, tool_name, duration_ms) are designed but not yet wired into the container runtime.
- **VNet integration**: Documented as a production TODO. Private endpoints for Cosmos DB, Storage, Key Vault, and Service Bus are not yet configured.

### 23. Refactor Orchestrators for Unit-Test Coverage

After the v1.25.x refactor extracted `cli_batch.py`, `cli_doctor.py`, `cli_parser.py`, `section_planning.py`, `strategy_artifacts.py`, and similar helper modules out of the three monsters, line coverage now sits at: `cli.py` 82%, `deep_research.py` 72%, `research_agent.py` 30%. The remaining gap is concentrated in two functions that resist unit-mock testing because they interleave I/O, LLM calls, and state-machine transitions in a single body:

- `research_agent.perform_fast_research` (~1900 lines) — extract pure helpers for the per-section orchestration loop, the strategy-artifact pipeline, and the cross-validation/repair cycle so each stage is callable in isolation with a mocked LLM and scrape boundary
- `deep_research.DeepResearchOrchestrator._execute_consulting_research` (~270 lines) — split Phase 1 (dossier) and Phase 2 (section-by-section writing) into discrete async helpers that take pre-built prompts and return structured results, so failure modes (consecutive-failure stop, fallback to Stage 1 context) can be tested without standing up the full pipeline

Target: all three monster files at 80%+ line coverage. This is a refactor for testability, not a new feature — the rule should be no behavior change, only seam introduction, and existing eval scores should remain identical.

---

## Engineering Standards & Toolchain

primr is a mature, shipping PyPI application (`py.typed`, ~6,500 tests, heavy native deps: playwright / patchright / curl_cffi / DrissionPage / pymupdf / pandas), not a greenfield internal service. The standards below are calibrated for that reality: adopt the high-leverage, low-risk discipline; defer code-reshaping behind non-regression ratchets; and decline the maximalist conventions that would churn a stable codebase or hurt downstream consumers. The buckets are explicit so the decisions are durable and don't get re-litigated.

**Decision principle:** modern where it pays, conservative where users feel it. Track the Python floor to the EOL line (not the bleeding edge) and the ceiling to current stable; gate on reproducibility and supply-chain integrity; ratchet type-strictness, complexity, and verification (contracts, mutation, fault-injection) rather than flipping them globally; and stay deliberately native-dep-first where the scraping/document engine demands it, pure-Python-preferred everywhere else.

### Adopted (load-bearing today)

- Ruff as the single linter (`E/F/W/I/N/UP/B/C4/SIM/RUF/PIE/PT/TCH`), line-length 100. CI hard-fails on any violation. `target-version` intentionally trails the 3.12 floor at `py311` so pyupgrade doesn't push PEP 695 / typing rewrites until the one-time Phase-2 reflow.
- mypy (authoritative config in `mypy.ini`, `python_version = 3.12`) on an incremental strict ratchet: a relaxed global with complex SDK-bound modules `ignore_errors`'d, plus a growing **strict allowlist** of fully-verified modules that require `disallow_untyped_defs` + `disallow_incomplete_defs` (currently `skill_pack.{schema,config,planner,industry}`, `utils.content_sanitizer`, `utils.logging_config`, `data.hiring_signals`). The allowlist only grows. (The former `[tool.mypy]` block in `pyproject.toml` was dead config and has been removed.)
- Ships `py.typed` — primr is a good typing citizen for downstream importers.
- Property-based tests (Hypothesis) for core invariants; a hard-gated hardcoded-secret scanner in CI.
- No silent `xfail` rot: `xfail_strict = true` (an unexpectedly-passing xfail fails the run); the suite currently uses zero xfail markers.
- SSRF protection on every outbound URL (`primr.utils.security`); content sanitization for prompt-injection defense.
- Single source of version truth enforced by `tests/test_release_integrity.py` (pyproject ↔ `__version__` ↔ ROADMAP "Current State").
- No-real-company-data rule across the repo (see `docs/CONTRIBUTING.md`).

### In progress — Phase 1: infrastructure & cheap gates

The current active engineering initiative. Each item is verified locally, then landed; findings are triaged (targeted ignore or downgraded to a Phase-2 ratchet) rather than force-passed.

- **Supported-Python window**: `requires-python = ">=3.12"`, EOL-driven — 3.10 reaches EOL Oct 2026 and 3.11 Oct 2027, while 3.12 carries security support to Oct 2028. CI runs a `3.12 / 3.13 / 3.14` **hard** matrix — all three fully supported (the full suite passes on each; validated locally on 3.12 and 3.14 at 8,391 passed, and the native-dep stack installs cleanly on 3.14). 3.14 classifier shipped; `.python-version` pins the dev default. Free-threading (PEP 703 / 3.14t) remains a non-goal — primr is I/O-bound and its native deps aren't `cp314t`-ABI-ready (this is about the GIL build, separate from standard 3.14 which is fully supported).
- **uv toolchain + reproducibility**: commit a `uv.lock`; CI installs via `uv sync --frozen`; keep the proven setuptools build backend. Reconcile the divergence where `requirements.txt` carries lower bounds but `pyproject.toml` deps are unpinned — lift sensible lower bounds into `[project.dependencies]` (no hard upper caps except the existing intentional `ruff<0.16` / `a2a-sdk<0.4`).
- **Security gates in CI**: wire the already-configured `bandit` (`.bandit`) and a dependency-vulnerability audit (`pip-audit`) as gates; add `.github/dependabot.yml` (weekly `pip` + `github-actions`, grouped patch/minor, majors flagged for manual review); attach a dependency manifest (`uv export`) to each GitHub release.
- **Coverage baseline + non-regression ratchet**: measured global branch coverage is **78%** (8,471 tests, branch mode); CI gates at `--cov-branch --cov-fail-under=77` (1-point margin for platform variance). A ratchet that only ever rises — not the brief's blanket 95%, which is the wrong target for heavy I/O / LLM glue.
- **pre-commit**: `.pre-commit-config.yaml` running `ruff check` + `ruff format --check` + a fast mypy hook + hygiene hooks; opt-in for contributors, CI stays the hard gate.
- **SLSA build provenance**: `release.yml` generates a signed SLSA provenance attestation (`actions/attest-build-provenance`) for the published wheel + sdist; publishing already uses OIDC trusted publishing (no static credentials). First exercised on the next `v*` tag.

### Phased ratchets (tracked, not yet started — Phase 2/3)

- **mypy strict expansion**: SHIPPED a first real strict allowlist in `mypy.ini` (7 modules: `skill_pack.{schema,config,planner,industry}`, `utils.content_sanitizer`, `utils.logging_config`, `data.hiring_signals`) and consolidated the duplicate config (removed the dead `pyproject` `[tool.mypy]` block; bumped `python_version` to 3.12). Remaining: keep growing the allowlist module-by-module toward eventual `--strict`, and burn down the ~45 `ignore_errors` modules. Evaluate Astral `ty` as a fast local supplement (not the CI gate while it is preview).
- **One-time `ruff format` reflow** — SHIPPED. Formatted 173 files in a single behavior-preserving commit; `ruff format --check` is now enforced in pre-commit and CI. `E501` stays ignored deliberately: `ruff format` already wraps code lines, so the remaining >100-char lines are strings / URLs / comments where wrapping hurts readability — enforcing E501 there would be churn without value. Remaining: bump `target-version` to `py312` and apply the pyupgrade (UP) rewrites it surfaces.
- **Complexity budget**: add `C901` + `max-complexity` once the documented monsters are refactored (`perform_fast_research` ~1900 lines, `_execute_consulting_research` ~270 lines — Active Queue #23).
- **Parse-don't-validate boundaries**: parse external data once at the system boundary into rich domain types — `NewType` / frozen dataclasses / Pydantic `strict=True, extra='forbid'` — so core logic never receives raw, possibly-invalid primitives. Targets the MCP / API input boundary first (most MCP inputs are JSON-schema-validated today); audit and fill gaps, not a blanket conversion.
- **Explicit invariant hardening + property tests** (chosen over the `deal` library — no new dep, fits primr's exception-based style): the load-bearing invariants are pinned with Hypothesis property tests. SHIPPED: skill-pack roster-cap merge (`_merge_and_cap` / `_drop_excess_to_cap` — partition, cap, observed-first, archetype-dedup, trim-priority), the SSRF guard result-shape (`is_safe_url` always `(True,None)` or `(False,msg)`), and `CostGuardHook` budget rule (`remaining ≥ 0`; BLOCK iff `spent + est > max`). Remaining: the scraping tier-escalation state machine (covered by the stateful-Hypothesis item below).
- **OpenSSF Secure Coding Guide audit**: a one-time pass against the OpenSSF Secure Coding Guide for Python (input neutralization, exception safety, logging hygiene, crypto via `cryptography` only, concurrency), recording conformance + any deliberate deviations. Complements the bandit/pip-audit gates already in CI.
- **Stateful + fault-injection testing**: SHIPPED — a Hypothesis `RuleBasedStateMachine` for the per-host tier circuit breaker (`tests/test_data/test_scraping/test_circuit_breaker_stateful.py`: failures ≤ attempts; any success ⇒ never skipped; skip ⇒ all-failures past threshold), and a fault-injection test that surfaced + closed a real redaction gap — `SecretMaskingFilter` now also masks secrets in **exception tracebacks** (`exc_text`), not just `getMessage()`. Remaining: a `RuleBasedStateMachine` for the job lifecycle, and broader malformed-payload / mid-stream-failure injection at the LLM seam (network/HTTP faults already covered by the recovery-regression suite).
- **Mutation testing on a core slice (`mutmut`)**: TRACKED — run `mutmut` against the highest-stakes modules (`utils/security`, `utils/cost_estimator`, `skill_pack/planner`, `utils/circuit_breaker`) to prove test efficacy beyond line coverage, triage surviving mutants, and harden weak tests. Deferred to a focused session (the value is in running + triaging, not just configuring); never a CI gate (prohibitively slow on the full suite).
- **Per-module coverage targets**: raise the 80% line-coverage target on core modules (`deep_research.py` 72%, `research_agent.py` 30%) as their refactors land.
- **Supply-chain hardening (Sigstore + Trivy + SBOM)** — SHIPPED. On top of the SLSA build-provenance attestation + OIDC trusted publishing: PEP 740 Sigstore attestations made explicit on the publish step; a CycloneDX JSON SBOM (`cyclonedx-py`) + pinned uv manifest attached to each release via a dedicated `sbom/` artifact (kept out of `dist/` so PyPI upload stays clean — also fixed a latent bug where the manifest in `dist/` would have failed the next publish); and a Trivy filesystem scan (vuln + misconfig; secret scanning omitted — it flags the deliberate fake fixtures, and real leaks are hard-gated by the hardcoded-secret property test) in CI, now a **HARD GATE**. Trivy's first real run found + fixed a CRITICAL (secret API keys declared via `ENV` in `openclaw/Dockerfile.primr`) and surfaced KSV-0118 ("default security context allows root") on the Cloud Run manifests. **Resolution (corrected from the original plan):** the runner image is *already* non-root — both `deploy/Dockerfile` and `openclaw/Dockerfile.primr` run `USER primr` (uid 1000), which Cloud Run honors at runtime. The original plan ("add a non-root `securityContext` to the manifest, then drop the ignore") is **infeasible**: Cloud Run *fully managed* does not expose `securityContext` in its v1 YAML schema (the RunV1 SecurityContext type carries only `runAsUser`, documented "Not supported by Cloud Run"), so adding `runAsNonRoot` is rejected by `gcloud run ... replace`. KSV-0118 is therefore a **permanent, platform-dictated false-positive**, justified-ignored in `.trivyignore` with the doc reference, pinned by a regression test (`tests/test_deploy/test_gcp_deployment.py::TestGCPSecurityContext`) that forbids adding a deploy-breaking `securityContext`, and documented inline in both manifests. With the baseline clean (the Trivy step exits 0 after the ignore), the scan was **promoted from signal-only to a hard gate**. Remaining: container image scan if/when images become a shipped artifact; formal SLSA L3 attestation review.
- **Model landscape refresh (May 30, 2026 audit)**: `claude-opus-4-8` and `gemini-3.5-flash` registered in `config/models.py`. The PRO-tier repoint decision is now **wired for eval**: `config/eval_profiles.py` registers a head-to-head pair — `protier-gemini31pro` (reference, $2/$12) vs `protier-gemini35flash` (candidate, $1.50/$9) — same reasoning+utility, only the quality writer differs. **Eval-gated, billed, user-triggered**: run `primr eval <corpus> --profiles protier-gemini31pro protier-gemini35flash` against the standing corpus; repoint the default PRO/quality tier to `gemini-3.5-flash` only if its scorecard matches-or-beats 3.1 Pro at lower cost. It is **not** a writing-tier swap (dearer than `gemini-3.1-flash-lite`). Register `gemini-3.5-pro` (June) and `gemini-omni` once their API slugs go GA. Re-audit before each major eval per "Model Adaptability".

### AI / agent security posture

primr is an **LLM API client + adaptive scraper + MCP/A2A agent** — it does not train, fine-tune, or serve models. So the bulk of adversarial-ML security (training-time poisoning/backdoors, model extraction/stealing, membership/attribute inference, model inversion, watermarking, weight exfiltration, DP-SGD, confidential-compute/enclave serving, certified ℓp-robustness) is **structurally out of scope** — those are "you host the model" concerns, and for primr the model is a commodity API (the pipeline is the asset, not the weights). The real surface is four things: untrusted scraped content flowing into the LLM, LLM output driving downstream actions, the agentic tool surfaces (MCP/A2A), and API-key secrets.

Already shipped: SSRF guard on every outbound URL (`primr.utils.security`), content sanitization for prompt-injection defense, a hard-gated hardcoded-secret scanner, MCP JWT auth, A2A loopback/auth, `CostGuardHook` budget caps, and the supply-chain gates above. The threat model and per-threat control status live in [docs/SECURITY.md](docs/SECURITY.md). Status of the posture work:

- **Indirect prompt-injection hardening** — SHIPPED. `fence_untrusted` (`utils/content_sanitizer.py`) sanitizes + wraps untrusted retrieved content in an explicit "data, never instructions" fence; applied at the previously-unfenced boundaries (insights extraction, the Deep Research dossier + stage-1 website context, discovery notes). Backed by an injection red-team corpus (`tests/security/test_prompt_injection_corpus.py`). Remaining: an LLM-judged injection/jailbreak *eval* scorecard slice to measure evasion over time (deterministic corpus ships now).
- **Output / egress guardrails** — SHIPPED. `is_safe_url` + post-redirect validation enforced on every egress helper (`HTTPClient.get`, `fallback_sources._http_get`, `hiring_signals._http_get`); the "no fetch bypasses the SSRF guard" invariant is locked by `tests/security/test_egress_guardrails.py`.
- **Secret / log redaction** — SHIPPED. `SecretMaskingFilter` on all log handlers (sink-level, not opt-in) + `mask_sensitive_data` (incl. xAI) applied in `chat_logger` before persist, with atomic writes. Provider patterns: xAI/Google/OpenAI/Anthropic/GitHub/AWS/Slack/JWT. Note: `usage_history.json` and `_run_state.json` are metadata-only (no secrets) — verified, no change needed.
- **Scoped threat model** — SHIPPED. `docs/SECURITY.md` documents the client/scraper/agent threat model (ATLAS-style table T1-T8), shipped controls, residual-risk acceptance, and coordinated disclosure.
- **Agentic trust boundaries (MCP/A2A)** — PLANNED (T8). Capability-scoped tokens + per-tool authorization so every tool invocation is authenticated, capability-bounded, and cost-bounded (the JWT `role` claim is extracted today but not enforced per-tool). Folds into Active Queue #11 (constrained agent permissions) and #21 (agent control-plane hardening).

Decision principle: secure the surface primr actually has — untrusted input, agent tool use, secrets, supply chain — and explicitly decline model-training/serving security primr will never own.

### Out of scope (rejected, with rationale)

So future contributors don't re-open these:

- **`requires-python >= 3.14` floor** — 3.14 is fully supported and a hard CI gate, but it is not the *floor*: the floor tracks the EOL line (3.12) so users on 3.12/3.13 aren't cut off. Raising the floor to 3.14 would strand them for no benefit.
- **Model-training / model-serving security** (poisoning, extraction, inference attacks, enclaves, certified robustness, weight protection) — primr trains and serves no models; see "AI / agent security posture" above for what *is* in scope.
- **Free-threaded build adoption (3.14t)** — primr is I/O-bound (scrape + LLM); removing the GIL buys ~nothing and the native deps (playwright/pymupdf/curl_cffi/DrissionPage) aren't `cp314t`-ABI-ready. The free-threading concurrency discipline (no shared mutable state, message-passing) is therefore moot here.
- **Pure-Python-first as a hard rule / "C-extensions disallowed by default"** — primr's moat *is* its native stack: playwright, patchright, pymupdf, pandas, curl_cffi, pytesseract are load-bearing and have no pure-Python equivalent of comparable quality. Adopted instead as a *new-dependency policy*: prefer pure-Python for additions, and treat a new C-extension dependency as a reviewed exception (justify, and check `cp314t` ABI impact if free-threading is ever revisited). Existing native deps stay.
- **structlog everywhere / Pydantic-everywhere / dataclass → Pydantic conversion** — high churn, low payoff on a stable codebase that already has a `get_logger` abstraction and uses dataclasses deliberately. Structured output, if wanted, goes behind `get_logger`.
- **NASA Power-of-10 literalism** (forbid recursion, mandate "two asserts per public API", forbid post-`__init__` attributes) — dogmatic for an AI/scraping pipeline. Keep the spirit (complexity budget, boundary validation), not the letter.
- **>95% global branch coverage** — wrong target for I/O/LLM-heavy code; replaced by a measured ratchet + per-module targets.
- **Copier / multi-repo template** — a portfolio-level concern, not primr's. primr can instead serve as the *reference implementation* a template is later extracted from.

---

## Considered for Later

Concepts where the design is sketched but the work isn't queued for the next active cycle — either because they depend on an upstream item, the scope is large, or the value is real but not yet pressing.

### Strategy Delta Mode (incremental re-analysis)

Ongoing monitoring of a company should produce an incremental update against a
prior run rather than a full re-run. Given a previous report + its run state,
diff the freshly gathered signals (recon, hiring, external sources) against the
last snapshot and regenerate only the sections whose evidence materially
changed, emitting a "what changed since <date>" delta artifact alongside the
refreshed report.

- Depends on durable per-company run state and a changed-signal layer; connects
  to vendor-news caching (#13) and the per-user cache (#12).
- Must respect the single-job model — delta mode is still one job, not a daemon.
- Value is real (cheap refreshes, change tracking) but scope is a meaningful
  build; sketch first, queue once #12/#13 land.

### Watch / Delta as a Consumed Primitive (not a push daemon)

A "detect strategic change" primitive is legitimate primr surface: expose the
delta (above) and the skill-pack capability declarations as **artifacts and
job-scoped resources** that a downstream orchestrator can poll/consume. The
boundary is deliberate and load-bearing: **downstream experts (e.g. Deepr)
integrate *into* primr by consuming its outputs; primr stands on its own and
never runs an always-on watcher that pushes into, or depends on, a downstream
system.** That keeps primr "URL in, serious artifact out" rather than becoming
generic orchestration middleware (see Design Philosophy: "product over
middleware"). The auto-feed/scheduling half lives on the consumer side.

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
primr-a2a                                  # Standalone A2A on 127.0.0.1:9000 (auth required)
primr-a2a --host 127.0.0.1 --no-auth       # Local dev only — refuses non-loopback hosts
primr-mcp --http --a2a                     # Co-hosted MCP + A2A (shares MCP auth)

# Cloud Deployment
cd deploy/aws && ./deploy.sh -d prod deploy
cd deploy/aws && ./deploy.sh -d prod destroy
```

---

## Changelog

For the latest changes, check [GitHub releases](https://github.com/blisspixel/primr/releases).

| Version | Date | Highlights |
|---------|------|------------|
| 1.27.1 | May 2026 | **Skill pack: operator roster curation.** Four-flag curation surface — `--plan-only` to inspect, `--from-plan` to author from a saved plan, `--roles-add "A, B"` to augment the discovered plan with operator-supplied labels (materialized as `provenance: override`), `--roles-skip "X, Y"` to drop named roles (matches display name or kebab-case slug, exact, case-insensitive). The four compose: `--from-plan PATH --roles-add ...` augments a saved plan; `--roles-skip ...` + `--roles-add ...` swaps roles in a single command. `--roles-override` (existing) bypasses planning entirely; with curation flags it warns and ignores them. Cap-aware merge with operator-priority — plausible roles trim first, then observed, then never operator-added; trimmed entries flow to `gap_flagged`. Name + archetype dedupe between add and discovered (existing role wins to preserve citations; operator can force with skip + add). Empty roster after curation is a hard error. Plan artifact gains "## Operator-Added Roles" and "## Operator-Skipped Roles" sections; pack report shows the operator-added count; CLI completion message reports the full breakdown (observed / plausible / added / skipped). `RolePlan` schema gains `operator_added: list[Role]` and `operator_skipped: list[str]` fields; `RoleEvidence` provenance vocabulary unchanged. MCP `generate_skill_pack` tool gains `roles_add` and `roles_skip` array params. 21 new curation tests covering the full composition matrix and edge cases (cap overflow, dedup, skip-removes-everything hard error, unmatched-skip warning, override+curation mutex). |
| 1.27.0 | May 2026 | **Skill pack: holistic input layer + planning architecture rebuild.** Hiring-signal gathering expanded from 4 ATS providers to 8 (added Workday with corpus-driven URL discovery + bounded blind probing, Workable widget API, Recruitee offers API, Jobvite RSS) plus a new DuckDuckGo web-search fallback that fires when every other path comes up empty. New two-call planning step (`src/primr/skill_pack/planner.py`) replaces the single `discover_roles` call: Call A extracts observed roles backed by posting citations, Call B infers plausible roles backed by research citations + industry classification, archetype-based merge with observed-wins dedupe. `IndustryClassification` (LLM-resolved, no heuristics) drives plausible-role gating — common org-shape roles (Marketing, Sales, Customer Success, Finance, HR) become plausible only when company stage is Mid-market or larger. Inspectable `role_plan.md` + `role_plan.json` artifacts persisted to the working dir; `--plan-only` writes the plan and exits, `--from-plan` authors against a saved plan. `RoleProvenance` enum (posting/research/industry/override) preserved end-to-end; authoring prompt branches grounding emphasis per provenance. `MAX_ROLES` raised 8 → 15 for holistic packs. New CLI flags: `--plan-only`, `--from-plan`, `--roles-override`, `--allow-recon-only`. Hard-failure mode when both posting and research evidence are empty (skill packs are job-posting-first). Pack report now shows observed/plausible split, industry classification, per-role provenance, and citation excerpts. 30+ new tests; ruff clean. |
| 1.26.0 | May 2026 | **Skill pack subsystem (`primr skills`).** A first-class workflow for producing QA-refined Agent Skills artifacts grounded in primr's recon + hiring evidence. Top N roles × M skills (configurable, defaults 5 × 3), archetype-grounded authoring with deep per-company customization, deterministic ASKILL-* validation, capped per-skill refinement loop (default 2 iterations with diminishing-returns stop), and pack-level coherence pass. Emits both an unpacked Claude/Cursor/VS Code `roles/<slug>/SKILL.md` tree and a Microsoft 365 Copilot Cowork sideload `.zip` (manifest v1.28, deterministic UUID v5, programmatic icon generation) from one byte-identical set of SKILL.md files. Multi-provider image generation for the Cowork icon (Grok Imagine → Gemini Imagen → OpenAI image → programmatic Pillow gradient+shape → solid PNG). Authoring prompt + validator encode Anthropic's published authoring discipline: third-person descriptions (DESC-VOICE), "pushy" multi-trigger guidance (DESC-PUSHY), gerund-form names (NAME-GERUND), workflow checklist pattern, Template-pattern Output Format, explain-WHY style, concision-over-padding default. New CLI subcommand `primr skills "<Company>" <url>` and MCP tool `generate_skill_pack`. Legacy `--strategy-type skills` still works and logs a pointer at the new command. Also: vendor-news freshness gate tightened from 14d to 7d (`is_vendor_research_current`). 53 new tests; ruff and mypy clean. |
| 1.25.2 | May 2026 | **Refactor for testability + 50+ new test files.** Extracted helper modules from the three monsters so each pipeline stage is callable in isolation: `core/` got `cli_batch`, `cli_doctor`, `cli_init`, `cli_parser`, `cli_recovery`, `fast_mode_helpers`, `report_cleanup`, `resilience_listeners`, `run_state_io`, `section_parsing`, `section_planning`, `section_prompts`, `strategy_artifacts`; `ai/` got `citation_resolution`, `file_search_resources`, `job_persistence`; plus `output/artifact_validation` and `pipeline/llm_failover`. Coverage on the three monsters: cli.py 78%→82% (passed 80% target); deep_research.py 64%→72%; research_agent.py 27%→30%. Remaining 80% gap on deep_research/research_agent now tracked as roadmap item #20 — needs further orchestrator-level refactors (perform_fast_research ~1900 lines, _execute_consulting_research ~270 lines). CI: re-enabled tests/test_qa and tests/test_output (previously excluded for unknown historical reasons, pass cleanly today). Dead-code removal: utils/defensive.py, utils/memory_profiler.py; utils/retrieve_research.py moved to scripts/. No behavior change. |
| 1.24.4 | May 2026 | **Cost estimator now reflects cross-provider routing.** `_estimate_fast_mode_cost` hardcoded the Grok 4.20-nr writing model and always reported the legacy ~$5.67 number, even when GEMINI_API_KEY was set and the live pipeline correctly routed bulk writing to gemini-3.1-flash-lite. Now defers to `pick_model_for_role(Role.WRITING)` for FAST / HYBRID tiers (still respects `--grok-tier max` as the explicit Grok-everywhere opt-in). Dry-run for the v1.24.x sub-$1 default now correctly reports ~$0.76 baseline / ~$1.01 with 2-vendor AI strategy. Updated stale `routing.py:pick_model_for_role` docstring that still described v1.23.0 behavior. Tests deterministic via env monkeypatch; +3 cross-provider tests. |
| 1.24.3 | May 2026 | Re-release of v1.24.2 — prior release had a `primr.__version__` mismatch with pyproject.toml that broke the integrity check; v1.24.2 was yanked. Same content as v1.24.2. |
| 1.24.2 | May 2026 | (Yanked.) **Artifact drift cleanup (roadmap #1).** Offline scan of 16 recent reports surfaced 240 leaked `[workbook]` markers, 87 `[cross-ref ...]` markers, and 65 bold-wrapped `**What to validate:**` lines. Three root causes fixed at the canonicalization seam: cross-ref strip was colon-only (missed space-separated form, the dominant variant); workbook strip missed bare `[workbook]` and space-separated `[workbook ARDA/prior]`; section normalizer didn't match bold-wrapped validate lines. Verified on five historical reports: 28+51 leaked markers stripped to 0; bold-validate now dedups at the per-section writer boundary. Added `ReportAnalyzer.analyze_scaffolding_leakage()` covering all four categories plus informal `[cite: label]` markers. Bonus: removed a hardcoded vendor-domain URL categorizer (leftover from an early test report); fixed `lstrip("www.")` → `removeprefix("www.")` typo introduced in the same patch. +11 tests. |
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
