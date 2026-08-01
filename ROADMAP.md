# Primr Roadmap

Current State: v1.39.0

Primr is a CLI-first, local research tool for company intelligence and deep strategic analysis. It aims to accelerate research workflows while producing consultant-grade outputs that stay explicit about uncertainty.

The design is intentionally opinionated and local-first. This roadmap is a single ordered queue of work, top to bottom. The order reflects priority - items higher up either improve the core deliverable directly, address known regressions, or unlock items below them. No time estimates: this is the queue, not a schedule. Items may ship in a different order if dependencies, capacity, or feedback change the picture, but the default is to work it top-down.

For completed work, see the [Changelog](#changelog) at the bottom of this file, or check [GitHub releases](https://github.com/blisspixel/primr/releases) for the latest.

> **Before you add a rule or make something agentic, read
> [`docs/design/agentic-balance.md`](docs/design/agentic-balance.md) - and keep it
> current.** That doc is the standing decision aid for the choice that recurs all
> over this queue: hardcode the path (a *rule*) or let the model decide
> (*judgment*). Getting it wrong is our repeated own-goal. Brittle rules that try
> to gate *content* are a documented failure driver - they false-block good
> output and rot as prompts evolve - and over-agentifying the plumbing makes runs
> unpredictable and unbounded. Rule of thumb: **determinism on structure and
> irreversible acts (spend, egress, disk); judgment on content; measured eval
> (never a regex, and never a lone judge) for quality.** The failure is
> symmetric: a brittle hand-rule that gates content rots as prompts evolve, but a
> single LLM-judge is just as brittle (verdicts swing on seed, option order, and
> paraphrase), so swapping a regex for one judge only moves the problem. Quality
> eval must therefore be layered and agreement-validated (a multi-judge panel, or
> cloud-vs-local concordance), and no hard ship or eval gate is ever armed from a
> noisy single-judge or small-sample measurement. When a change teaches you
> something new about where that line sits, update the doc in the same PR so the
> next change inherits the lesson.

---

## What's Next And Why

The short execution brief lives in
[`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md). It is the current answer to "what
next and why"; this roadmap remains the full ordered backlog.

Current priority order:

1. **Evidence-grounded validation and label honesty.** This is the measured
   quality gap: report claims, conclusions, caveats, and confidence labels must
   survive evidence, contradiction, source-quality, and reasoning review before
   Primr can trust eval gates, routing comparisons, or future memory. Label
   traceability is the first measurable slice, not the whole validation story.
   The standard `--verify` path now surfaces contradicted claims in the final
   Report Trust summary; calibration scorecards now include evidence-review,
   inference source-copy, and judge-agreement signals;
   `primr calibrate --pack-manifest` freezes baseline
   candidates locally; `--pack-selection-template` writes a zero-spend starter
   selection for manual representative tagging; curated `--pack-selection`
   inputs make representative coverage explicit; `--inspect-selection` shows
   missing representative tags before manifest generation; and
   `primr calibrate --baseline-from` writes a zero-spend readiness artifact
   that refuses to mark small, unvalidated, or
   under-representative packs as ready while naming the exact next actions
   needed to make the pack baseline-ready. Readiness now requires an explicit
   curated pack-selection manifest with non-empty representative tag
   requirements, and it reports `missing_representative_selection` for
   aggregate latest-N packs that have not been curated. It also requires every
   selected report to carry evidence-review dimensions and cloud-vs-local
   judge-agreement metadata, so partial sidecar coverage cannot make a pack
   look ready by aggregate counts alone. Calibration pack manifests now carry
   report and sidecar byte sizes plus SHA-256 content hashes so a baseline
   candidate names the exact artifacts it measured. Calibration sidecars also
   bind themselves to the exact report bytes they evaluated; pack aggregation
   and compact MCP/A2A readback reject missing or stale bindings. `primr
   calibrate
   --inspect-baseline` prints the same blocker set as machine-readable JSON for
   operators and agent control planes, including current-file fingerprint
   missing/mismatch checks that do not return report bodies, and MCP exposes the
   same inspection through
   `primr://calibration/baseline/inspection?path=<baseline.json>` under the
   existing path-allowlist boundary. Ready baseline artifacts now publish a
   report-only gate recommendation from the per-report Confirmed traceability
   floor, including an environment-variable assignment only when every selected
   report contributes a decidable Confirmed floor; otherwise they remain
   report-only and name the missing floor evidence. Ready curated
   multi-report baselines now carry
   `measurement.status=measured_operator_curated_multi_report_baseline` when
   representative coverage, evidence review, and judge agreement are complete.
   Calibration
   baseline artifacts and inspections now also include a body-free
   operator-review block that keeps automatic gate arming disabled, names the
   exact review items for representative coverage, evidence dimensions,
   judge disagreement, false-positive and false-negative risk, and the
   threshold decision, and distinguishes gate candidates from report-only
   recommendations without returning report bodies or raw claims. Baseline
   `next_actions` now carries the body-free hard-gate action state and
   selected-report counts for absent, incomplete, or zero Confirmed floors, so
   ready-but-report-only baselines explain why the environment variable remains
   unset. A body-free `operator_decision_template` now lists the allowed
   decisions, required review items, selected-report counts, and
   operator-supplied fields needed to document a later report-only or manual
   gate decision without recording one automatically. The calibration CLI now
   writes an explicit body-free decision record only when the inspected template
   allows the requested decision; it never sets the environment variable itself.
   Decision records can now be re-inspected with a body-free readback that
   verifies the baseline fingerprint still matches and the current template
   still allows the recorded decision before agents trust the record.
   **Current measured-baseline milestone COMPLETE (2026-07-13):** five distinct
   reports cover every required representative tag, 50 evidence reviews are
   present, cloud and local judges agree on 33 of 37 comparable claims, and all
   ten report or sidecar fingerprints pass inspection. The measured Confirmed
   floor is 30 percent across three contributing reports. Operator review
   deliberately records `keep_report_only` because two reports lack a
   decidable Confirmed floor. Raw report-bound sidecars preserve each
   disagreement as a body-free claim-index and verdict pointer while compact
   MCP and A2A summaries remain body-free. Recalibration on a fully decidable
   production corpus is follow-up work, not a blocker to priority 2.
2. **Backend freedom production wiring.** Provider abstractions and pure routing
   foundations exist, and `core/stage_inventory.py` now records router-ready
   capability requirements and promotion gates for fast-mode and premium
   deep-research stages. Full-report execution still carries xAI/Gemini-era
   assumptions. The xAI browse surrogate and Gemini quota guidance now live in
   provider-owned seams, estimates now expose live input, cached input,
   cached-input cost, and long-context surcharge fields, and
   `fast.scrape_summary`, `fast.source_relevance`, and
   `fast.hiring_signals` now consume the capability router behind the
   `--inference cloud|hybrid` flag while executing through existing provider
   seams. The remaining fast-pipeline stages
   (`research_deepening`, `analysis_workbook`, `cross_validation` for
   reasoning; `report_sections`, `trust_polish`, `strategy_generation` for
   writing) also resolve through the capability router with body-free route
   records and fail-closed agent/local behavior when no adapter qualifies.
   `fast.source_relevance`
   also has a bounded Codex CLI adapter. The first promotion-safety slice now
   exposes it only as an unpromoted, single-company experimental route when the
   operator supplies `--inference hybrid --acknowledge-host-agent-may-bill`.
   Codex authentication does not prove whether execution uses plan allowance or
   metered API-key billing, so route and estimate metadata says
   `potentially_metered`, excludes unknown host charges from the Primr estimate
   and budget, and rejects batch fan-out. Runtime route resolution
   consumes sanitized env-only cloud provider availability snapshots by
   default, can accept injected quota snapshots, and records body-free
   availability metadata without collecting live quota data or probing local
   services during normal runs. All ten fast-pipeline routes (including optional
   label honesty when enabled) record body-free usage metadata in
   `_run_state.json`, including measured token/cache/cost deltas when provider
   counters expose them. Routed stages fail closed when the internal agent
   profile is exercised by tests or evals and no host adapter qualifies: scrape
   summary writes deterministic source excerpts, hiring signals use
   deterministic triage plus posting metadata, research deepening skips gap
   analysis, the workbook falls back to collected insights, report writing
   returns no content, cross-validation leaves the report unchanged, trust
   polish keeps deterministic cleanup only, strategy generation is skipped, and
   label honesty leaves labels unchanged. The next architecture unlock is the
   representative source-relevance
   host-vs-cloud comparison. The explicit host gate is not promotion and cloud
   remains the validated baseline. Broader host/local candidates still require
   stage-specific adapters and stage-scoped eval data. Stage scorecard artifacts are now available through
   the eval CLI and compact MCP readback at
   `primr://eval/stage_scorecard/{eval_id}` without exposing prompt, report,
   quality-source, or raw run-state content. Website-summary local-stage evals
   now write scorecard-ready structured quality evidence as report-only input,
   and source-relevance labeled fixtures now write body-free precision, recall,
   F1, and exact-match evidence for review-only host/cloud scorecards. The
   packaged standing corpus `source_relevance_standing_v1` covers required
   representative tags with dual cloud/host candidates and is scored offline
   via `--eval-source-relevance-standing-corpus`; it remains report-only
   (`promotion_status=not_promoted`). Live host-vs-cloud comparison and
   human-reviewed promotion are still required before any host route clears
   the gate.
3. **Agent control-plane consumption resources and A2A parity.** MCP already has
   scopes, approval tokens, tool/resource-read audit events, and budget
   propagation. A2A now shares the HTTP bearer-token auth context and enforces
   the same `read`/`research` split for equivalent skills. A2A skill invocation
   audit parity is shipped. A2A `estimate_research` now issues the same
   server-bound approval tokens as MCP `estimate_run`, and A2A
   `research_company` enforces `max_estimated_cost_usd` plus a matching
   approval token when cost-cap enforcement is active before creating a job,
   then propagates the approved cap into `PipelineRunner` as the runtime
   budget. MCP report-read scope separation is now shipped, A2A now has
   matching report-read parity behind the explicit `report` scope, and compact
   status output negotiation now points authenticated agents to explicit
   resource URIs instead of inline bodies or raw output paths. The seven MCP
   job-scoped resource slices shipped:
   `primr://output/artifacts/by_job/{job_id}` returns owned-job artifact
   metadata, and `primr://output/qa_summary/by_job/{job_id}` returns compact QA
   score/status/count metadata, and
   `primr://output/usage_summary/by_job/{job_id}` returns compact cost, timing,
   approval, execution, and artifact-count metadata, and
   `primr://output/source_summary/by_job/{job_id}` returns compact citation and
   source appendix metadata, and
   `primr://output/trace_summary/by_job/{job_id}` returns compact scrape trace
   metadata, and `primr://output/verification_summary/by_job/{job_id}` returns
   compact claim verification metadata, and
   `primr://output/calibration_summary/by_job/{job_id}` returns compact
   label-calibration metadata, including inference source-copy counts. None
   returns report body content; trace
   summaries omit raw trace entries, verification summaries omit raw claims,
   source URLs, search queries, and explanations, and calibration summaries
   omit raw claims, source URLs, evidence reviews, and rationales. MCP also
   exposes compact eval-id readback for stage scorecards at
   `primr://eval/stage_scorecard/{eval_id}`, without arbitrary file paths,
   prompt bodies, report bodies, quality-source bodies, or raw run-state
   content. A2A now advertises the read-scoped `read_stage_scorecard` skill
   backed by the same compact eval-id summary contract. MCP resource
   report-body reads now use `primr://output/report/by_job/{job_id}` with
   ownership checks, explicit `report` scope for authenticated HTTP callers,
   and `content_mode` / `artifact_type` / `max_chars` output negotiation.
   `check_jobs`, `primr://output/latest`, and `primr://output/by_job/{job_id}`
   omit report bodies or previews for authenticated HTTP callers even when
   they hold `report`, while local stdio retains backwards-compatible inline
   artifact behavior. MCP resource
   reads now append privacy-preserving audit events with hashed URI/result
   values, normalized resource kind, job id when present, caller scope, and
   outcome without storing raw URI query values or resource bodies. A2A skill
   calls and task cancellations now append matching privacy-preserving audit
   events with hashed message/result payloads and job id when present. A2A
   also exposes all seven job-scoped compact resource parity slices:
   `read_artifacts_by_job` returns ownership-gated artifact metadata through
   the same compact summary helper as MCP, and `read_qa_summary_by_job`
   returns ownership-gated compact QA score, status, count, parse-state, and
   artifact metadata without report or detailed QA bodies, and
   `read_usage_summary_by_job` returns compact cost, timing, approval,
   execution, artifact-count, and manifest metadata without approval tokens,
   caller ids, manifest artifact paths, source URLs, or report bodies, and
   `read_source_summary_by_job` returns compact source appendix and citation
   metadata without report bodies while preserving the MCP source-row
   contract, and `read_trace_summary_by_job` returns compact scrape telemetry
   without raw trace entries, URLs, final URLs, page content, or report
   bodies, and `read_verification_summary_by_job` returns compact claim
   verification metadata without raw claims, source URLs, search queries,
   explanations, or report bodies, and `read_calibration_summary_by_job`
   returns compact label-calibration metadata without raw claims, source URLs,
   evidence reviews, rationales, or report bodies. A2A `read_report_by_job`
   now requires `report` scope for authenticated callers and reuses the
   ownership-gated `primr://output/report/by_job/{job_id}` reader with
   `content_mode`, `artifact_type`, and `max_chars` negotiation.
   A2A research execution also reuses MCP's estimate-first approval-token
   contract and runtime budget propagation for cost-governed research jobs.
   A transport-neutral `primr.job-status` v1.0 projection now normalizes
   lifecycle, progress, timestamps, artifact availability, and observation
   errors across CLI, MCP, A2A, hosted, and application API status surfaces
   without removing legacy fields. Completed-job artifact inventory now uses a
   bounded shared seam that preserves explicit missing paths and expands only
   exact adjacent deliverables and manifests, while MCP fast and standard runs
   attach their generated run manifest to the owned job.
4. **Research memory layer 1.** Memory comes after calibrated claims and safer
   artifact consumption so prior-run material can compound value without
   laundering weak claims into fresh findings.
5. **Coverage and maintenance ratchet.** Every feature slice continues to carry
   focused tests, static checks, strict docs, and a bug-hunt/security-review
   lane.

Not next: expanding the README with roadmap detail, adding regex-like prose
quality gates, treating phrase overlap as validation, promoting a backend from a
one-off success, building memory before data-governance rules, or turning Primr
into generic agent middleware.

---

## What's Working Today

### Research Engines

**Scrape Mode**: 9-tier web scraping with intelligent escalation (browser-first):
- Browser tiers: Playwright, Playwright aggressive
- Patchright stealth browser (tier 3 - real Chrome + persistent profile for Kasada/Akamai challenge shells)
- TLS impersonation: curl_cffi (tier 4)
- Stealth browser tiers: DrissionPage stealth, DrissionPage (driverless CDP)
- Vision tier: Screenshot + LLM extraction for image-heavy pages (enabled by default, can be disabled)
- HTTP tiers: httpx, requests
- Content-type routing: automatic PDF detection with local PyMuPDF extraction by default; Gemini PDF extraction is opt-in via `PRIMR_PDF_LLM_MAX_CALLS`
- Reader-mode content extraction (BeautifulSoup-based, removes boilerplate)
- Content quality validation (catches garbage pages, triggers escalation)
- Homepage-first link discovery (fresher than sitemaps)
- Sticky tier optimization (reuses working tier for same host)
- Circuit breaker pattern (skips failing tiers after 3 failures)
- Soft block detection (catches "200 OK" traps, browser blocks)

**Deep Mode**: Gemini Deep Research Agent with autonomous multi-step search and synthesis

**Standard Mode** (default when `XAI_API_KEY` is set): Grok 4.3 reasoning, with Gemini 3.1 Flash-Lite writing when `GEMINI_API_KEY` is also configured. Base Strategic Overview: ~$0.76-$0.79, ~31-47 min. The default command produces one integrated AI strategy for about ~$0.89 and ~34-53 min. Explicit two-platform fan-out is about ~$1.01 and ~37-59 min. XAI-only setups use the legacy Grok 4.20-NR writing/utility path (~$4.36 base, ~$5.06 with one AI strategy, or ~$5.76 with explicit two-platform fan-out). Research deepening, parallel section writing, cross-validation, coherence pass, and strategy enrichment.

**Premium Mode** (`--premium`): Gemini + Deep Research pipeline for maximum depth. ~50-75 min, ~$5.

### AI Strategy & Report Generation

- AI strategy and roadmap generation with multi-platform support (`--platform aws azure`)
- Platform options: Azure, AWS, GCP, agnostic, private (NVIDIA/on-prem)
- DNS intelligence pre-flight (recon): uses one strong infrastructure fingerprint as an ecosystem emphasis, combines multiple strong ecosystems into one integrated vendor-neutral strategy, defaults to one agnostic strategy when evidence is unclear, and injects bounded recon context into all strategy types
- `primr recon` subcommand for standalone DNS intelligence lookups
- `--platform ms` shorthand for Microsoft Azure + NVIDIA private cloud
- Canonical business-first AI Strategy contract: begins with company economics, an enterprise performance agenda, strategic tensions, value pools, industry direction, and art of the possible before technology; tests defend, improve, extend, and create choices against measurable revenue, efficiency, product, service, and risk outcomes; bundles the Strategic Overview with available insights, gap analysis, workbook, bounded recon, hiring, discovery, and operator-supplied context on paths where those artifacts exist; then evaluates a ranked initiative portfolio, non-AI alternatives, opportunity cost, fully loaded unit economics, operating ownership, governance, a disposition for every material observed ecosystem, and public, multicloud, private, edge, or hybrid workload placement
- Platform selection is an evaluation emphasis rather than an exclusive architecture. Current product details must be supported by current official evidence or left unasserted with an explicit evidence gap and validation action. Credible alternatives remain visible, and no dated vendor catalog is authoritative in the shipped YAML
- Standalone strategy recovery is estimate-first: `--ai-strategy-only --dry-run` is zero-call, execution repeats the estimate and requires approval, report input is contained to fixed roots, and a stable-descriptor content digest binds validation to the private snapshot consumed by generation. Standard strategy context retains a normal full Strategic Overview up to a 200,000-character deterministic bound
- Governed batch research quotes and budgets the whole pending batch, requires websites before paid research, runs local-only preflight after approval, disables automatic paid retries, and emits one-object JSON dry-runs. Separate governed enrichment quotes only missing-site lookups, pins the quoted utility model, disables retry and provider failover, and preserves website-only legacy rows through validated hostname derivation
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric, Skills Ideation
- Skills Ideation strategy emits per-role `SKILL.md` files deterministically alongside the strategy doc
- **Skill pack subsystem** (`primr skills`, MCP `generate_skill_pack`): a first-class workflow that takes recon + hiring + research evidence and produces a QA-refined Agent Skills pack. Up to 15 roles × M skills, two-call planning step (observed roles from postings or operator role briefs + plausible roles inferred from research and industry classification, with provenance preserved end-to-end), archetype-grounded provenance-aware authoring, deterministic ASKILL-* validation, capped per-skill refinement loop, pack-level coherence pass. Inspectable `role_plan.md` / `role_plan.json` artifacts; `--plan-only` writes the plan and exits, `--from-plan` authors against a saved plan, `--from-jd` adds a local JD / role brief as sanitized hiring evidence, repeatable `--career-url` points discovery at exact segmented career / ATS boards, and `--roles-override` bypasses discovery entirely while still grounding authoring in supplied evidence. Emits both an unpacked Claude/Cursor/VS Code tree AND a Microsoft 365 Copilot Cowork sideload `.zip` from one byte-identical set of SKILL.md files. Cowork icons are generated locally by default; remote image APIs are explicit opt-in via `--remote-icons` or MCP `remote_icons`.
- Strategy enrichment: cross-validation, evidence search, section regeneration, polish pass, and pre-ship repair for citation/source/budget conflicts
- TXT and DOCX outputs with citation styles, plus best-effort PDF conversion when `docx2pdf` or LibreOffice is available
- Custom `--output-dir` support for clean client folders: Markdown and DOCX deliverables are written to the requested directory, while TXT mirrors and validation diagnostics stay with the run diagnostics
- 23-section reports with adaptive section selection, constrained-evidence reasoning, deduplication, and cross-validation

### Providers & Routing

- Seven providers wired: xAI (Grok), Google (Gemini), OpenAI, Anthropic, Ollama (local), Microsoft Foundry (Azure OpenAI-compatible `/openai/v1/`), Amazon Bedrock (boto3 `converse`)
- Provider abstraction at `src/primr/ai/providers/` - `Provider` ABC, `OpenAICompatibleProvider` (xAI/OpenAI/Ollama/vLLM), `GeminiProvider`, `AnthropicProvider`, `AzureFoundryProvider`, `BedrockProvider`
- `pick_model_for_role` chooses the best model from configured providers; `primr doctor` shows what each key unlocks; `primr keys test` does live auth-only validation (free `models.list`, no model spend) via `Provider.validate_credentials()`
- Pure capability router foundation shipped in `src/primr/ai/capability_routing.py`: `StageRequirements`, backend capability rows, cloud/agent/hybrid/local profiles, billing-mode guards, ordered route plans, explicit rejection reasons, and pure availability-to-backend annotation. Runtime consumption is now wired for `fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals` behind `--inference cloud|hybrid`, with an explicitly acknowledged, single-company Codex experiment for `fast.source_relevance` and capped body-free route usage records persisted to `_run_state.json`. Codex route metadata reports potentially metered billing and pending-eval status; it does not prove whether authentication is plan-backed or API-key billed.
- Provider availability foundation shipped across `src/primr/ai/provider_availability.py` and `src/primr/ai/provider_availability_collectors.py`: normalized quota windows, binding headroom, elapsed-reset handling, stale last-known-good snapshots, deterministic provider ranking, non-secret cloud provider configuration snapshots, generic local OpenAI-compatible availability probes, sanitized routing metadata, and `primr doctor` visibility. Official live cloud quota/status collectors and production execution wiring remain planned.
- Provider-aware fallback chain: WRITING/UTILITY prefer GEMINI > OPENAI > ANTHROPIC > XAI; REASONING prefers XAI (cached) > GEMINI > OPENAI > ANTHROPIC
- Cross-provider dispatch in `grok_llm` and `llm()` so writing-tier calls reach the right provider when the resolved model is non-Grok
- Quota-aware `ModelCircuitBreaker.execute_with_fallback()` with midnight-UTC reset (callable; production call-site integration still pending - see queue below)
- Continuous reasoning session is the default: workbook generation and cross-validation share a single Grok 4.3 session so the validator inherits corpus + workbook reasoning. ~81% reduction in leaked-instruction lines, average ~+12% cost. Escape hatch: `--no-continuous-reasoning` or `PRIMR_CONTINUOUS_REASONING=0`.
- Known runtime gap: provider/routing and dry-run estimates cover OpenAI-only and Anthropic-only configurations, but the main full-report preflight and continuous-reasoning session still assume the xAI/Gemini-era execution path. Full no-xAI report execution remains in Active Queue #26 / Backend Freedom rather than being claimed as shipped.
- **Planned, not urgent — broad model coverage + estimate-vs-actual evals.** The
  seven-provider transport can *reach* any of these services; filling in the model
  catalog and validating each is deliberately deferred. Future work: (1) register
  the current-generation models across all providers, including deployment-surface
  models (Foundry Phi-4; Bedrock Nova 2, Gemma 4, DeepSeek R1/V3, Llama 4) and the
  latest flagships (grok-4.5, gpt-5.6, claude-fable-5) as *available-but-never-default*
  entries — verify each id/price against official docs before it enters the
  registry; (2) do **not** eval every model now; when models are evaluated, extend
  the eval-slot registry so each run records the pre-run **cost estimate and the
  actual metered cost and compares them**, per provider × model × role, so routing
  picks are backed by measured quality *and* estimate accuracy. Defaults stay chosen
  on output $/1M near the ~$1 target; premium models remain explicit opt-in.

### Agent Integration

- MCP server (stdio + HTTP with JWT auth)
- A2A protocol (standalone or co-hosted with MCP)
- OpenClaw integration with packaged skills plus governed research/strategy workflows
- Claude Skills directory with MCP-first skill packages
- Agent-host routing keeps `primr "Company" https://company.example` as the
  public request and defaults it to Primr Zero when no explicit paid intent is
  present. The host handles `primr prep` internally, configured keys never
  imply spend consent, and explicit provider-backed requests retain the fresh
  estimate and approval gate. Checked `.claude/skills/primr` and
  `.claude/skills/primr-zero` project mirrors make the behavior discoverable in
  a fresh Claude Code checkout. When Primr cannot be launched and installation
  is unavailable or declined, the Zero skill uses host-native research and
  reports the missing collectors instead of stalling. Direct terminal CLI
  behavior is unchanged. The emitted workflow fences target metadata as data,
  uses the canonical four-label confidence vocabulary, checkpoints the report
  inside the prep bundle, and confirms its body-free `primary_report` inventory
  role before a requested downstream handoff when local execution is available.
- Agent governance surfaces for generic MCP clients: estimate-first prompts/resources, next-action hints, and server-enforced cost caps (`max_estimated_cost_usd`) - enforcement defaults ON for the HTTP transport (the networked, agent-facing surface), off for host-mediated stdio; `PRIMR_ENFORCE_MCP_COST_CAPS` overrides either way (`mcp_server/cost_caps.py`)
- Long-running job guidance for agent clients: monitor/resume flows for standard runs and premium multi-vendor runs

### Quality & Trust

- Deterministic QA checks: hypothesis coverage, confidence labels, section length, citation density, report-type-aware structure, and appendix/source integrity. **These are soft *signals*, not quality truth** - most are regex/count proxies for editorial discipline, not measures of whether the analysis is good (per [`agentic-balance.md`](docs/design/agentic-balance.md), a regex can't judge quality). Only appendix/source integrity (does `[cite: N]` resolve) is a legitimate structural gate; the rest must never block shipping.
- `QAGateHook` with `ReportAnalyzer`-backed scoring (6 checks, penalty system) - an *artifact-discipline* proxy, not a factual-quality score (a self-report dressed as a metric; agentic-balance Principle 4). Use it as a dashboard signal; real quality is the job of the eval/calibration instruments below, not this score.
- Claim verification via `--verify` flag (~$0.01, 3-5 min) - extracts claims, challenges them with DDG searches, produces trust score
- Versioned model evaluation harness: `primr eval` with scorecard generation (Markdown + CSV), versioned eval IDs, acceptance gates, and optional LLM-judge overlays
- Eval profile slot registry - one slot per (provider × model × role-recipe), so new models register a slot, run the corpus once, and score against existing baselines without re-doing prior work
- Local eval judge capability: Ollama-backed LLM judging against staged reports, named local model lists, per-model JSON artifacts, and local multi-model sweep summaries
- Output improvement: `primr improve` for deterministic cleanup + optional agentic review pass
- Resource-lifecycle maintenance now covers SQLite-backed globals and the
  sync/async bridge with warning-escalated focused tests; the full non-manual
  coverage gate passes with `ResourceWarning`, unknown pytest markers, and
  unraisable warnings promoted to errors.

### Pipeline Resilience

- Cost-ordered recovery hierarchies for all six pipeline stages (scraping, external search, analysis, section writing, cross-validation, strategy generation)
- Foreground/background stage classification - foreground stages retry aggressively, background stages bail on API overload or budget stress
- Recovery executor that orchestrates retry/fallback/skip logic and logs events to `_run_state.json`
- `--dry-run` shows concise stage classifications and recovery hierarchies, followed by launch, monitoring, interruption-recovery, and artifact-retrieval steps. `--verbose` includes the serialized recovery policy; `--json` remains a single machine-readable estimate object.
- Primr Zero prep bundles now assemble in private same-root staging directories
  and become discoverable only after a complete manifest is ready. Collection
  failures and interrupts remove unpublished work, artifact scans ignore active
  staging directories, and skill-install dry runs report their requested
  destination without network access or file writes.
- Public prep commands now dispatch through the lightweight console/module
  composition boundary instead of loading the provider-backed CLI graph.
  Collection and skill-install interruption return conventional exit code 130
  with operation-specific recovery guidance, and command help exposes both
  zero-activity dry-run modes.
- Public-data fallback fan-out (`src/primr/data/fallback_sources.py`): when origin is blocked, fetches in parallel from Wayback CDX, sister subdomains, RSS/Atom feeds, SEC EDGAR 10-Ks, Wikipedia REST, and Grok web_search synthesis
- Hiring-signal gathering (`src/primr/data/hiring_signals.py`): ten ATS/provider adapters (Greenhouse / Lever / Ashby / SmartRecruiters / Workday / Workable / Recruitee / Jobvite / iCIMS / BambooHR), repeatable explicit career / ATS URL inputs for segmented boards, corpus-driven Workday URL discovery for known boards, HTML careers-page fallback, DuckDuckGo web-search fallback across major job-board hosts when every other path comes up empty, LLM-triaged extraction threaded into all downstream phases. Skill packs are job-posting-first: when both posting and research evidence are empty the pipeline fails closed unless `--allow-recon-only` is passed.

### Operational Maturity

- Cost estimation, usage tracking, job recovery, crash/reboot recovery
- System diagnostics (`primr doctor`)
- Lightweight one-screen `primr --help`, `primr init --help`, and
  `primr doctor --help` surfaces for onboarding and diagnostics, with
  `primr --help-all` retaining the complete command reference. Console and
  `python -m primr` execution share one dispatcher; version and focused help
  avoid operational CLI imports and workspace initialization.
- One-command install/update: idempotent `scripts/install.{ps1,sh}` one-liners (pipx-based, upgrade on re-run), a `primr update` self-upgrade command (detects pipx vs pip), and a passive once-a-day "update available" notice (cached in the per-user dir, opt-out via `PRIMR_NO_UPDATE_CHECK`)
- 10,000+ tests, full ruff compliance, mypy clean on an incremental strict ratchet (see [Engineering Standards & Toolchain](#engineering-standards--toolchain))
- Serverless cloud deployment templates (AWS, Azure, GCP); Azure validated end-to-end (remaining hardening below)
- Agentic architecture: hypothesis tracking, subagents, hooks, orchestrator
- Content sanitization for prompt injection protection

---

## Design Philosophy

- Strategic analysis over raw data - deep outputs you can act on, not link dumps
- Hypothesis generation over premature conclusions - confidence levels on every claim
- Transparency about uncertainty - what's confirmed, what's inferred, what's speculation
- Deterministic verification before AI judgment - check structure, citations, and epistemic labels with code before asking a model to score prose quality
- Local-first, CLI-first - your data stays on your machine
- Role over tool - Primr is an account strategist, not a "research command." Its outputs should be consumable by both humans and downstream agents.
- Product over middleware - integrations should act as a disciplined control plane for Primr's long-running research jobs, not turn Primr into a generic orchestration framework.
- Artifact-first delivery - the main unit of value is a report, strategy, or evaluation artifact, not a stream of chat-sized tool responses.
- The pipeline is the product - Primr's value is the 9-tier scraping engine, the org-aware link selection, the research deepening, the cross-validation, the deterministic QA gate, the eval harness, the crash recovery, and the cost estimation. None of these are model calls. The model is a commodity; the orchestration pipeline is the moat.
- Credentials are transport, not product identity. API keys, official agent-account auth, enterprise gateways, and local models are all ways to run the same pipeline. Do not bake a provider, billing model, or subscription workaround into the core loop. The default routing goal is the lowest incremental spend that clears the measured quality bar: local or gateway capacity when configured and explicitly approved, then any official host runner whose billing basis is proven or explicitly acknowledged, then the best validated sub-dollar direct API recipe, with premium paths opt-in and justified by measured lift. Direct APIs remain the reproducible baseline and fallback. An official automation seam alone does not prove plan-backed billing, so the Codex in-pipeline adapter is an explicitly gated experiment with its quality eval still pending. `primr-zero` is the supported plan-native path, with host OAuth and session state kept inside the host. Local and gateway profiles are validated recipes, not second-class forks. As local AI hardware improves, the same eval gate should let $0 API local stages graduate from utility support to hybrid default, and eventually to full-run default where they honestly match the quality bar.
- Evidence before language - Primr is Python-first because its product layer is
  I/O-heavy and benefits from Python's research, data, document, and AI
  ecosystems, not because the project imposes language purity. Improve the
  pipeline topology and Python implementation first. Admit a native extension,
  service, or accelerator runtime only behind a narrow, versioned boundary when
  production-shaped measurements show a material product, tail-latency,
  memory, reliability, deployment, or safety gain that repays the permanent
  toolchain cost. Polyglot is an available technique, not a goal. See
  [`docs/design/runtime-language-boundaries.md`](docs/design/runtime-language-boundaries.md).

Primr is intentionally not designed as a generic web scraper, a SaaS collaboration platform, a presentation builder, or a generic agent middleware layer.

---

## Release Cadence

The queue is worked top-down, but a release is never *only* features. Every
release cycle folds in a standing **bug-hunt + harden** lane, independent of
whatever feature lands:

1. **Adversarial review.** A focused sweep for correctness and security bugs
   across the modules touched since the last release, plus a rotating "cold"
   module that hasn't been reviewed in a while. Findings are fixed *with
   regression tests* in the same release - the test pins the bug so it can't
   silently return.
2. **Supply-chain + dependency hygiene.** The `bandit` / `pip-audit` / Trivy
   gates are re-checked; flagged action/dependency bumps are applied by hand
   (no bot PRs - see Engineering Standards).
3. **Coverage ratchet.** The branch-coverage gate only ever rises. New code
   ships with tests, and the ratchet is bumped when a focused push clears
   headroom.
4. **Release pre-flight.** Version integrity (`pyproject` ↔ `__version__` ↔
   ROADMAP "Current State"), `ruff` check + format, `mypy`, and a dry-run cost
   estimate all run locally before any `v*` tag is pushed.

This is why the changelog shows hardening-only points (e.g. 1.29.2, 1.29.3)
interleaved with feature points: hardening is a recurring lane, not a one-time
milestone. A release is "done" when the feature works **and** the harden pass
is clean - not before.

---

## Version Plan: 1.x → 2.0 → 3.0

The version line is deliberately incremental - primr ships small, verifiable
releases, not big-bang rewrites. The major-version arc is about *what primr
is*, not a feature count. No dates anywhere in this plan: each band is gated
on exit criteria, and the build sequence below is a **dependency order**, not
a schedule. Detailed breakdowns live in [`docs/design/`](docs/design/README.md)
- one design doc per workstream, kept in lockstep with this section.

### 1.x - the excellent single-shot brief (current line)

The job is "URL in, consultant-grade artifact out," done well.

**Status (as of v1.37.0):** most of the 1.x engineering backlog is closed -
artifact pipeline contract (#1-2), cost/observability surface (#5, #7, #8,
#12, #13), production failover (#6), QA iteration loop (#10), agentic write
constraints (#11), runtime robustness (#24), and the `perform_fast_research`
orchestrator extraction (#23) are DONE. What remains is the quality half, which
by design needs paid evals and live sites to validate, plus the follow-on
per-module coverage ratchet unlocked by the refactor:

- **#4 consultant-grade strategic writing** - reframed by a June-2026 eval pass
  ([`docs/design/eval-plan.md`](docs/design/eval-plan.md)): a direct read of a
  brief shows the **prose is already consultant-grade**, and two evidence-plumbing
  levers (hypothesis-steered collection #4-tradecraft-Step-4, context curation)
  both **evaluated as washes**. The one *measured* quality gap is **epistemic
  grounding** - the artifact needs stronger evidence support, contradiction
  handling, source-quality judgment, reasoning review, and uncertainty honesty.
  `(Confirmed)/(Reported)` labels tracing to sources only ~0-8% is the first
  measured symptom, not the whole disease. So the validated next quality work is
  an **evidence-grounded validation slice**: calibrate labels as a cheap first
  measure, but evaluate sampled report units against source support,
  contradiction, independence, authority, reasoning strength, and uncertainty.
  Do not reduce this to phrase matching or a deterministic content gate.
- **#3 remainder** - page-access recovery extensions (host-level learning,
  blocked-site UX); CLI premium/deep hiring signals shipped in 1.34.43, only
  the MCP/A2A orchestrator-direct path remains
- **#23 orchestrator refactor**: `perform_fast_research` extraction is complete:
  all ten stages are out (Batches A-G), each as a module with a hermetic test
  suite; the orchestrator is now a ~295-line coordinator, and the C901
  complexity budget is enforced. Remaining follow-on work: raise
  `research_agent` per-module coverage toward 80% as the split exposes more
  testable seams, per
  [`docs/design/23-orchestrator-refactor-map.md`](docs/design/23-orchestrator-refactor-map.md)
- **#9 batch API** - the governed CLI execution core is shipped with
  deterministic column classification, whole-batch cost gating, separate
  enrichment, exact flag forwarding, and zero-call dry-run JSON. A public API
  surface and one explicitly approved cheap live batch validation remain.
- Label-calibration measurement + evidence-fetching `--verify` (from the
  v1.30 panel review) - converts the epistemic apparatus from style guide to
  measured quantity. Tooling COMPLETE: `primr calibrate` audits shipped
  reports (sidecar JSON, `--dry-run` cost preview), the eval scorecard reads
  sidecars into a `## Label Calibration` section plus CSV columns, and the
  `FAIL_CALIBRATION` decision gate arms via
  `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY`. The judge also runs on any local
  OpenAI-compatible server (Ollama/LM Studio/vLLM) for $0 - `--judge
  auto|local`, auto-detected, cloud default, provenance stamped in sidecars,
  `--judge-compare` measures cloud-vs-local agreement (the first production
  slice of the 2.0 backend-freedom pattern: detect, opt in, validate by
  agreement, fail open). Evidence-review tooling is now also present: sidecars
  record support, contradiction, source independence, source authority,
  reasoning strength, uncertainty honesty, and business relevance dimensions,
  and the eval scorecard surfaces pooled `## Evidence Review` report-only
  metrics plus CSV columns. `--judge-compare` also stamps per-report
  cloud-vs-local agreement into calibration sidecars, including body-free
  claim-index and verdict pointers for disagreements, and offline eval surfaces
  pooled `## Judge Agreement` report-only metrics plus CSV columns. Compact MCP
  and A2A summaries omit those pointers and all raw claim or source content.
  `--pack-manifest` writes a local JSON manifest of the selected reports,
  sidecar state, estimates, per-label totals, inference source-copy counts,
  and judge-agreement metadata so a representative pack can be frozen before
  any paid baseline. Curated
  `--pack-selection` inputs now record exact report paths and explicit
  representative coverage tags in the manifest, and the readiness artifact
  now computes missing report, sidecar, evidence-review, judge-agreement,
  representative-selection, and coverage-tag gaps plus reason-specific
  remediation, suggested commands, and the policy to keep the hard gate unset
  for any not-ready pack. It refuses to treat a latest-N aggregate manifest as
  ready until a curated selection with required representative tags is present.
  Calibration
  sidecars and eval/baseline summaries now also flag source-copied
  `(Estimated)`/`(Hypothesis)` claims as a report-only signal. Baseline
  artifacts now include a body-free operator-review block that keeps
  automatic gate arming disabled and names the exact review items for
  representative coverage, evidence dimensions, judge disagreement,
  false-positive and false-negative risk, and threshold selection. Gate
  recommendations now also distinguish a zero Confirmed floor from an
  incomplete per-report Confirmed floor; a ready pack with reports lacking
  decidable `(Confirmed)` claims stays report-only with
  `incomplete_confirmed_traceability_floor` until an operator reviews that
  coverage gap, and `next_actions` carries the same hard-gate action state and
  selected-report counts for agent control planes. Baseline artifacts now also
  include a body-free decision template for operator-supplied gate evidence, and
  the calibration CLI can now write a body-free operator decision record bound
  to the inspected baseline fingerprint. Remaining:
  gather a multi-report, agreement-validated baseline (cloud-vs-local
  concordance), then set the threshold from those numbers; a single small run is too
  judge-noisy to arm a hard gate on (judge variance is itself a documented
  failure mode, see
  [`docs/design/agentic-balance.md`](docs/design/agentic-balance.md)). See
  `docs/design/1x-completion.md` workstream 1

**Exit criteria:** a sparse-company run still feels substantive; a
rich-company run is sharp and differentiated; the deliverable ships clean
every time; confidence labels have *measured* calibration; and the three
monster functions are refactored so the test suite exercises the heart of the
pipeline, not just its perimeter. Design doc:
[`docs/design/1x-completion.md`](docs/design/1x-completion.md).

### 2.0 - primr as a composable, cost-tunable research *role*

The step-change that earns the major bump is three pillars landing together:

- **Backend freedom** - the capability-requirement routing layer (#18) plus
  validated API-keyed cloud, billing-verifiable host runner, gateway, and
  local/hybrid inference profiles, so a run is cost-tunable from proven or
  explicitly acknowledged host billing, or $0 API local, through sub-$1 cloud
  and up to premium only when measured lift justifies it, *without changing the
  pipeline*. `primr-zero` remains the supported plan-native path while embedded
  host runners are not billing-verifiable. Local is not a permanent low-quality tier; it is a measured path
  that should automatically move up the default order as desktop-class models
  and hardware pass stage-level evals. Design doc:
  [`docs/design/2.0-backend-freedom.md`](docs/design/2.0-backend-freedom.md).
- **Memory** - research that compounds across runs (cross-run claim store +
  persistent company tracking + Strategy Delta Mode) instead of starting cold
  every time, shipped *with* its data-governance story (retention, deletion,
  classification), not acquiring one later. Design doc:
  [`docs/design/2.0-research-memory.md`](docs/design/2.0-research-memory.md).
- **Interoperability** - primr presented as a *role* other agents assign work
  to: per-tool capability-scoped authorization (T8, Stage 1 shipped),
  server-issued approval tokens for MCP cost-cap-governed tools (Stage 2 slice
  shipped), a structured audit log for tool calls and resource reads,
  job-scoped artifact metadata and QA, usage/cost, source appendix, scrape
  trace, verification, and calibration summary resources,
  A2A output negotiation (#21). The MCP `2026-07-28` specification is final
  and **shipped in Primr**: the server runs on MCP Python SDK v2, speaks
  2026-07-28 natively (stateless core, `server/discover`, protocol-level
  `ttlMs`/`cacheScope` cache hints, resource templates, aligned error codes)
  while still answering the legacy `initialize` handshake for older clients
  on both stdio and streamable HTTP. Remaining watch items from that
  revision: the Tasks extension (`io.modelcontextprotocol/tasks`) as a
  spec-native surface for Primr's long-running jobs alongside the existing
  job tools, OpenTelemetry `_meta` trace propagation, and Client ID Metadata
  Documents on the auth side. Design doc:
  [`docs/design/2.0-agent-control-plane.md`](docs/design/2.0-agent-control-plane.md).

**Exit criteria:** a downstream agent can delegate to primr unattended - on a
backend the operator chose, under enforced per-tool authorization and budget,
with an auditable invocation trail - and primr remembers what it already
learned, while still being the same "serious artifact out" tool when run
locally by a human.

### 3.0 - the research frontier, same guardrails

Extends *reach* without changing what primr is:

- **First-class VLM extraction** for data-dense pages (IR decks, org charts,
  financial tables) - promoted from fallback tier to routed-by-content-type,
  with structured JSON output and a per-run VLM budget
- **Knowledge compounding / meta-research** across whole verticals - industry
  context synthesized once and reused across a batch, claim-store queries
  across companies ("AI strategy evolution across all fintech targets")
- **Post-artifact skill-processing handoff** - a generic seam where consumers
  (downstream experts, orchestrators) take primr artifacts forward, with the
  skill pack as the first instance

Design doc: [`docs/design/3.0-research-frontier.md`](docs/design/3.0-research-frontier.md).

**Exit criteria:** primr reads what today it can only screenshot; the 50th
company in a vertical is meaningfully cheaper and sharper than the 1st; and
downstream systems consume primr artifacts through stable, versioned contracts.

### Intentionally never (any version)

The standing non-goals hold across every band - see
[Explicitly Deferred (By Design)](#explicitly-deferred-by-design) and
[Why Not a Research DAG](#why-not-a-research-dag--langgraph-style-orchestration):
no web app or SaaS hosting, no always-on watcher/daemon, no collaboration
platform, no generic agent middleware or DAG framework, no model
training/serving. Loops and scheduling live on the *consumer* side; primr
stays "URL in, serious artifact out." The engineering-standards rejections
(coverage maximalism, Pydantic-everywhere, free-threading, etc.) are recorded
in [Out of scope](#out-of-scope-rejected-with-rationale).

### Order of operations (dependency order, not a schedule)

Each step unblocks the ones after it; items within a step are independent.

1. **Measure the epistemics** (1.x): label-calibration audit as an eval hard
   gate + evidence-fetching `--verify`. Everything quality-shaped downstream
   (#4 prompt work, refine-loop acceptance, 3.0 compounding) needs a trusted
   measurement of claim quality first - otherwise improvements are vibes.
   **Done + measured (June 2026):** the calibration run found grounding
   systemically deficient (Confirmed ~8% / Reported ~0% traceability), which
   *redefines* #4 below - the lever is evidence-grounded validation, not prose
   ornamentation.
2. **Refactor the orchestrators** (#23) (1.x): splitting
   `perform_fast_research` unlocks unit coverage on the pipeline core, the
   complexity budget, and makes every later pipeline change (batch API,
   overlap, routing) reviewable. Do this *before* features that touch the
   monster, not after.
3. **Consultant-grade writing** (#4) (1.x): now scoped by step 1's measurement to
   **evidence-grounded validation**. The prose already grades well and the
   evidence-plumbing levers washed, so the next slice is not prettier writing or
   a new regex gate. It is a layered evaluation of support, contradiction, source
   independence, source authority, reasoning strength, and uncertainty honesty.
   **Shipped (opt-in, `PRIMR_LABEL_HONESTY=1`):** the runtime pass in
   `qa/label_honesty.py` downgrades a `(Confirmed)`/`(Reported)` claim to
   `(Estimated)` when its cited source is judged not to support it. Model
   judgment decides, the downgrade is a mechanical fail-safe rewrite, confidence
   only ever lowers, every other verdict fails open, an audit sidecar is written,
   and shipping is never blocked. Default-off until an agreement-validated
   calibration baseline and broader validation rubric justify promotion; arming
   a hard gate stays bound to step 1's instruments, never a lone judge.
   **Also shipped (always-on, judge-free):** the deterministic complement -
   `summarize_label_citation_coverage()` surfaces a "Label Citations" trust row
   (how many `(Confirmed)`/`(Reported)` claims carry a resolvable citation, the
   `no_source` slice) at zero cost, so a label-traceability signal is visible
   even when the paid pass is off. It renders on fast runs and - via the shared
   `label_citations_trust_row` formatter (single source of the row's wording) -
   on deep and `--premium` runs too, which previously shipped with no trust
   summary at all. Report-only, structural (a labeled claim citing nothing is a
   defect regardless of phrasing), never a gate.
4. **Cost levers** (#9 batch API, #19 pipeline overlap) (1.x): mechanical
   after step 2; each validated with one cheap live run.
5. **Control plane** (T8 + #21) (2.0): per-tool authz is now shipped for MCP
   dispatch (`read`, `research`, `delegate`, `admin`; OAuth `scope` / Entra
   `scp` honored; legacy `write` remains a compatibility alias). Approval
   tokens are now shipped for MCP cost-cap-governed execution tools and A2A
   `research_company` parity. Structured MCP invocation audit is now shipped
   for tool calls and resource reads, and the first seven job-scoped resource
   slices now cover artifact metadata, compact QA summaries, compact usage/cost
   summaries, compact source appendix
   summaries, compact scrape trace summaries, compact claim verification
   summaries, and compact label-calibration summaries. A2A skill-scope,
   skill-audit, artifact-metadata compact read, QA-summary compact read,
   usage-summary compact read, source-summary compact read, stage-scorecard
   compact eval-read parity, approval-token enforcement, runtime budget
   propagation, A2A report-read scope separation, and compact non-fast runtime
   budget visibility through run manifests and usage summaries are now shipped.
   Independent of steps 1-4; can proceed in parallel.
6. **Backend freedom** (#18 + provider expansion) (2.0):
   capability-requirement routing and provider-availability headroom first
   (pure refactors of existing routing), then first-class OpenAI/Anthropic API
   recipes, official host runners with proven billing provenance or explicit
   operator acknowledgment, gateway recipes, hybrid-mode eval, and full-local
   eval. Depends on step 1's instruments to judge each backend's quality
   honestly.
7. **Memory layer 1 → 2 → 3** (2.0): persistent company tracking (filesystem,
   no new deps) → claim store + priming (SQLite + embeddings) → Strategy
   Delta Mode. Layer 3 also depends on the per-user cache (#12, shipped) and
   benefits from step 1 (delta detection needs trustworthy claims). Layer 1
   foundation is now started: default research memory and company profiles live
   in the per-user data directory with `PRIMR_DATA_DIR` relocation, doctor
   readback for memory paths, no-secret write enforcement, and deterministic
   `primr company track/list/show/export` profile commands.
8. **2.0 release** when steps 5-7 all hold their exit criteria together.
9. **3.0 workstreams** (VLM, compounding, handoff): VLM depends on nothing
   above (can start anytime resources allow); compounding depends on the
   claim store (step 7); the handoff contract depends on the control plane
   (step 5).

---

## Active Queue

The active queue is ordered top-down by priority. Each item is concrete enough to start without further design work.

> Cross-cutting engineering-standards and toolchain work is tracked separately in [Engineering Standards & Toolchain](#engineering-standards--toolchain) rather than as a numbered queue item, since it spans the whole repo and runs in parallel with feature work. Phase 1 (uv lockfile, CI Python matrix, security gates, coverage ratchet, pre-commit) is the current active engineering initiative.

> **No brittle junk (applies to every item below).** primr's recurring self-inflicted wound is building a quality moat out of regex: deterministic gates that judge *content* (scaffolding-leak scanners, the QA penalty score, skill-pack heuristics) - they false-block good output, rot as prompts evolve, and become a maintenance treadmill. **The rule, per [`docs/design/agentic-balance.md`](docs/design/agentic-balance.md):** quality is enforced *upstream* (the writer/author prompt) and *measured* by eval/calibration - never by a new ship-time content gate. Deterministic checks are allowed ONLY for irreversible acts (spend, egress, disk) and prose-invariant structural validity (the DOCX renders, `[cite: N]` resolves, no duplicate `##`). Existing content scanners are shrinking backstops that trend toward signals, not blocks, and do not grow. If any item below tempts you to "add a check," that is the trap - fix the prompt and add the eval metric instead. Litmus: *would the check need a new case when the model rephrases?* If yes, don't build it. The same skepticism applies to the *fix*: do not replace a brittle rule with a single LLM-judge and call it measured. Judges are themselves brittle (sensitive to seed, option order, and paraphrase), so quality eval must be layered and agreement-validated, and a hard gate (including `FAIL_CALIBRATION`) is armed only from a robust, multi-judge or agreement-confirmed sample, never a single noisy run.

### Cross-Cutting Product Surface Debt

This ledger separates current product-surface debt from the numbered feature
queue. It does not reorder the feature priorities above.

- **Feature work:** unchanged. Evidence-grounded validation, backend freedom,
  control-plane parity, and memory remain the ordered product priorities.
- **UX flow debt:** the root help surface is now one-screen and workflow-first,
  with the exhaustive reference at `primr --help-all`. `primr prep` now labels
  partial collection, surfaces every handoff artifact, and gives the host a
  concrete next action. Agent-host Zero requests continue through native
  research when the Primr launcher is unavailable or installation is declined.
  Batch research and enrichment now expose separate reviewable plans, website
  recovery, whole-batch budget meaning, and visible unsupported-option errors.
- **Visual polish debt:** no separate graphical surface is in scope. Terminal,
  Markdown, DOCX, and PDF presentation remain governed by their existing
  renderer and artifact-regression workstreams.
- **Observability debt:** cloud doctor reserves `ok` for its live control-plane
  probe and labels unprobed dependencies `configured` without exposing endpoint
  or account values. MCP/A2A doctor and the admin audit resource now expose a
  body-free audit-sink snapshot, including not-observed/ok/degraded state,
  recent write/read outcomes, malformed-event count, and bounded-tail status.
  Cloud probe failures now affect overall health in both transports, and audit
  metadata is normalized, size-capped, and schema-checked before admin reads.
  The audit sink also rejects symbolic-link targets and reports external
  replacement or truncation after a successful write. Production-shaped
  service probes remain where credentials permit.
- **Reliability debt:** destructive pending-job cleanup now requires
  confirmation, holds an operating-system lock across each atomic
  read-modify-write transaction, fails visibly on malformed state, and
  preserves records added after preview even when another Primr process writes
  concurrently. Recovered MD/TXT/DOCX files now render and verify in a
  same-filesystem staging directory before promotion, with restoration of
  pre-existing outputs on an in-process failure or user interruption. Recovery
  registry read failures are visible and artifact paths reject traversal and
  symbolic links. Atomic run allocation, cross-process ownership leases,
  dead-owner recovery, company publication locks, and job-local MCP strategy
  output now prevent concurrent runs from sharing mutable workspace or artifact
  targets. Abrupt process termination during multi-file promotion and same-day
  name-collision policy remain explicit bounded follow-ups.
- **Security debt:** versioned package installation is the trusted default;
  convenience scripts are download-inspect-run only. Security operations now
  distinguish provider credentials, MCP/A2A JWTs, admin tokens, and the
  process-local REST scaffold; staging guidance targets the supported MCP/A2A
  protocol boundary and avoids billable research calls. Durable REST identity
  and pipeline wiring remain prerequisites before that scaffold can be
  presented as production-ready. Standalone strategy input is now fixed-root,
  link-rejecting, content-digest-bound, and copied to a private snapshot before
  model use, including fail-closed detection of metadata-preserving swaps.
- **Accessibility debt:** concise help is plain text, ordered by task, and does
  not require color to convey meaning. No high-severity accessibility gap is
  currently evidenced; future terminal presentation changes must preserve
  non-color semantics and focused help.
- **Documentation debt:** README, strategy portfolio, run modes, agent
  integration, zero-cost, API, security, client, and operator guidance now
  match these behaviors. The remaining documentation priority is keeping the
  short `docs/NEXT_STEPS.md` execution brief synchronized as the numbered
  feature queue advances.

### 1. Artifact Drift - Remaining Work

The cleanup cuts shipped in v1.24.2 fixed the dominant leak vectors at the canonicalization seam: bold-wrapped `**What to validate:**` lines now dedup into the single canonical trailing line via `_normalize_generated_section_payload`, and `[cross-ref ...]` plus bare/space-separated `[workbook]` markers are stripped in `_clean_fast_report_output`. An offline scan over 16 recent reports confirmed the leak was widespread (240 workbook + 87 cross-ref + 65 bold-validate instances), and the `ReportAnalyzer.analyze_scaffolding_leakage()` check makes regressions visible. **The three remaining items are now SHIPPED:**

- **Upstream-cause audit + hardening - DONE.** The model bolds the label (`**What to validate:**`) because the section prompts present `"What to validate:"` as a quoted label and never told the writer to emit it as plain prose; the canonicalization seam (`section_parsing.py` `_normalize_generated_section_payload`) then normalizes the line-leading bold form, but residue survives when a section bypasses that seam (mixed-format/regenerated paths). Symptom-fix at the seam stays; added a minimal upstream instruction in both `section_prompts.py` OUTPUT CONTRACT blocks and the `research_agent.py` regeneration prompt to write the line as plain text (no bold/italics/bullet), reducing the rate the bold form is produced at all.
- **Configurable visibility - DONE.** The leak scan is factored into the pure `qa.report_analyzer.scan_scaffolding_leakage()` (single source of truth) and wired into `output.artifact_validation._validate_output_markdown` as a non-blocking warning channel plus eval metric. Scaffolding leakage no longer withholds the polished DOCX; blocking remains reserved for structural/referential validity and unambiguous internal-token leaks.
- **Eval-harness wiring - DONE.** `model_eval` computes a `scaffolding_leaks` per-report metric and a `total_scaffolding_leaks` per-profile aggregate, surfaced in a new scorecard `## Artifact Drift` section (clean/DRIFT status per profile) and a `scaffolding_leaks` CSV column - so the regression is tracked every eval run instead of via ad-hoc offline scans.

Decision principle: final shipping artifacts must read as deliverables, not as internal scaffolding - but the mechanism is **upstream prompting + an eval metric (`writer_output_clean`), not a growing scanner.** The scaffolding-leak scan is a shrinking backstop: it must not gain new marker cases (that is the regex treadmill - see the standing rule above and [`agentic-balance.md`](docs/design/agentic-balance.md)). A healthy run is 0 leaks because the writer doesn't emit them, not because the scanner caught them. **DONE - the ship-time block is demoted:** the scaffolding-leak scan is now a non-blocking `warnings` channel in `_validate_output_markdown` - a leak is surfaced (logged) and eval-tracked (`## Artifact Drift`) but no longer withholds the DOCX. Blocking is reserved for structural/referential validity (citation resolution, duplicate/empty sections) and unambiguous internal-token leaks (raw `[Source:]`/`[Workbook:]`), which stay gated. Content quality is the prompt's job, measured by eval - not a gate.

### 2. Artifact Pipeline Hardening

Primr needs a sharper separation between **intermediate research artifacts** and **final shipping artifacts**. Research-stage artifacts (scrape summaries, source inventories, contradiction notes, section briefs) are machine-facing inputs to later stages - they need to be consistent, parseable, and provenance-preserving. Final reports and strategy documents need to ship as polished Markdown / TXT / DOCX / PDF with stable section structure, auditable citations, and predictable validation behavior. Treating both classes as "just markdown" creates placeholder leakage, brittle regex repair, false-positive validator blocks, and renderer edge cases that only show up at batch scale.

Planned:
- Keep intermediate research outputs flexible, but make them more explicitly structured for downstream consumption (evidence packets, source inventories, contradiction records, section briefs). When a consumer needs the *findings graph* (not the prose report), emit it as an OKF bundle (markdown + YAML frontmatter + linked tree), the single shape shared with 2.0 memory export and the 3.0 handoff manifest; see [`docs/design/open-knowledge-format.md`](docs/design/open-knowledge-format.md). The polished MD/DOCX report is unchanged by this.
- Push more consistency upstream into the long-form writing and regeneration prompts so final-stage cleanup has less arbitrary prose repair to do. **Foundation shipped:** the final-stage cleanup is now *measured* - `report_cleanup.compute_repair_report(before, after)` (reusing the ship-time scaffolding scanner) quantifies how many markers the deterministic cleanup had to strip per run and whether the raw writer output was already clean; wired at the report cleanup seam to log a summary + persist `_shipping_repair.json`. The headline `writer_output_clean` signal turns "is the cleanup load-bearing or a safety net?" from invisible into tracked, so the prompt-hardening can target the repairs that actually fire (and be validated against the metric) rather than guessing. One upstream fix already landed (the plain-text `What to validate:` instruction). **Prompt hardening - DONE:** the writer/regeneration prompts now carry an explicit prohibition against the markers the cleanup strips, sourced from a single shared constant `qa.report_analyzer.SCAFFOLDING_PROHIBITION_GUIDANCE` co-located with `scan_scaffolding_leakage` so the upstream instruction and the downstream ship-time gate cannot drift. It names every category the scanner flags (`[workbook]`/`[Analysis Workbook]`, `[cross-ref ...]`/`[see ## ...]`, informal `[cite: label]`, bold `**What to validate:**`) and gives the writer the substitute behavior (prose references, numeric-only `[cite: N]`). Spliced into both `section_prompts.py` writer prompts (`_build_fast_batch_prompt`, `_build_fast_section_prompt`) and both regeneration prompts (`_fast_regenerate_section`, `_strategy_regenerate_section` - the latter also gained the previously-missing plain-text validate instruction). Parity is locked by a deterministic test (`TestScaffoldingProhibitionParity`: every scanned category must be named in the guidance) plus presence tests on all four prompts; runtime effect is tracked by the `writer_output_clean` signal in `_shipping_repair.json` and the eval `## Artifact Drift` metric. With both the foundation and this hardening shipped, this bullet is complete.
- Strengthen artifact shipping gates to validate section structure and citation integrity, not just scan for forbidden markdown leftovers. **Citation integrity - DONE:** `_validate_output_markdown` now runs a configurable citation-integrity gate (dangling inline `[cite: N]` with no matching `## Sources` entry) backed by the pure `qa.report_analyzer.scan_citation_integrity()`; default zero-tolerance (`PRIMR_MAX_DANGLING_CITATIONS`), fail-closed, withholds the DOCX (MD/TXT + sidecar still written). This is the deterministic backstop behind the upstream LLM citation repair, which keeps the original (possibly still-dangling) report when it cannot reach zero. Covers both report and strategy docs (both ship through that validator). **Section structure - DONE (safe subset):** a configurable section-structure gate (`scan_section_structure()`, `PRIMR_MAX_STRUCTURE_DEFECTS`, default 0) now blocks the DOCX on the *unambiguous* defects - duplicate top-level `##` headings and empty sections - validated against the regression corpus so it does not false-block clean long-form reports. **Deliberately not gated:** required-section *presence*, which is report-type-dependent and too false-positive-prone to block shipping on; it stays a QA-scoring signal in `analyze_structure`.
- Build a regression corpus from real shipped and failed artifacts so renderer/validator changes are tested against actual long-form outputs. **DONE (seed + harness):** `tests/fixtures/artifacts/` holds long-form report/strategy fixtures (placeholder companies) with a `manifest.json` of expected gate outcomes; the data-driven harness `tests/test_output/test_artifact_corpus.py` runs each through `_validate_output_markdown` (asserting pass/fail + issue categories) and renders the clean ones end-to-end through `markdown_to_docx` + `_validate_output_docx`. A completeness test fails if a fixture is dropped in without a manifest entry. Sanitized real shipped/failed artifacts can be added later by dropping a file + a manifest row - no test code changes. This unblocks the section-structure gate above.
- Bug-hunt follow-up: informal citation cleanup now only rewrites brackets that begin with `cite:` or `cites:`, so bracketed prose containing the word `cite:` is preserved in report and strategy artifacts.
- Bug-hunt follow-up: final-report and strategy cleanup now preserves literal scaffolding examples inside Markdown fenced code blocks while still stripping the same markers from prose.
- Continue moving final rendering toward structured document data rather than free-form markdown recovery wherever practical

Decision principle: permissive about formatting in the research pipeline; in the final document pipeline, strict **only** on prose-invariant *structure* and *irreversible acts* (does the DOCX render, does `[cite: N]` resolve, no duplicate `##`) - never on content *quality*. Content quality is a prompt-and-eval problem, not a gate ([`agentic-balance.md`](docs/design/agentic-balance.md)). The shipped gates here are at their ceiling: citation-resolution and the duplicate-heading/empty-section checks are the *only* structural gates worth having; do not add a "required-section presence" gate or any quality gate (the roadmap already, correctly, left presence a signal). No new ship-time content gate without an eval metric that supersedes it.

### 3. Verified Page Access - First-Party Recovery Expansion

The shared page-access classifier, evidence-backed classification, Kasada/KPSDK challenge-shell coverage, homepage fast-path validation, first-party sitemap/guessed-path recovery, Wayback challenge-shell filtering, and public-data fallback fan-out have all shipped. What remains:

- Expand first-party fallback probing beyond current sitemap/guessed-path recovery: investor/news/about/help PDFs, feeds, and structured data endpoints with better prioritization. **DONE:** RSS/Atom feeds now join the fan-out as `source="feed"`; first-party JSON-LD now joins as `source="structured_data"`; first-party PDFs now join as `source="first_party_pdf"`, with bounded priority landing-page discovery plus direct investor/news/about/help PDF probes, same-site filtering, byte/entity/output caps, and local PyMuPDF extraction only through the SSRF-safe `_http_get` seam. No paid provider path is invoked by this fallback.
- Add host-level learning so once Primr sees a confirmed real page for a host it can persist useful positive markers for later pages. **DONE:** verified homepage classification now learns only explicit matched company/host markers from confirmed real pages, filters generic and secret-like values, persists a bounded host marker set under user data (`PRIMR_DATA_DIR`), and reuses those markers in orchestrator page-access classification for later pages without provider calls.
- Add optional screenshot/text-snapshot comparison for browser tiers to
  distinguish stable real homepages from interstitial templates. **DONE:**
  Playwright, aggressive Playwright, DrissionPage, DrissionPage stealth, and
  Patchright now record compact render-snapshot evidence from initial/final DOM
  text. The page-access classifier uses that body-free evidence to distinguish
  cleared challenges and stable real pages from persistent interstitials, and
  browser tiers can hand rendered text to the existing extraction path when the
  snapshot confirms the render.
- Surface a clearer user-facing blocked-site summary in the CLI with evidence snippets and recommended next actions. **DONE:** when homepage access and first-party recovery both fail, the CLI now prints sanitized evidence snippets, the same-site recovery candidate count, and the public-fallback / `--mode deep` next action before routing through Wayback, subdomains, EDGAR, and Wikipedia.
- Extend trace analytics and eval suites to score false-positive and false-negative rates for access classification on protected sites. **DONE:** `data.scraping.page_access_eval` scores labeled local fixtures or trace-derived access predictions into true/false-positive and false-negative metrics, tag-level breakdowns, and body-free JSON/Markdown review artifacts without copying raw HTML, URLs, or page bodies; `primr --eval --eval-page-access-fixture <fixture.json>` writes operator-facing page-access eval artifacts under `output/evals/<eval-id>/page_access_stage/`; and `tests/fixtures/page_access/protected_site_trace_corpus.json` seeds the representative protected-site corpus from sanitized trace `access_assessment` records with required challenge/recovery tags plus known false-positive and false-negative historical cases.
- Hiring-signal extensions: Workday + Workable + Recruitee + Jobvite providers landed with a corpus-driven Workday URL discovery path and a DuckDuckGo web-search fallback when every ATS plus the careers crawl misses. **DONE:** iCIMS and BambooHR now have bounded public-board adapters that parse hosted HTML career portals through the existing SSRF-safe HTTP seam because their official job APIs require authenticated customer or partner access. **CLI premium wiring - DONE:** the CLI Deep Research paths (`--premium`/complete and `--mode deep`) now gather the same hiring-signal stage and append the block - fenced, since it carries scraped posting titles into otherwise-trusted stage-1 context - via `ResearchConfig.supplemental_context` into the context the comprehensive report call consumes (when a run continues past a failed structured phase, the block still reaches the deep call). Strategy-only runs and the legacy parallel hybrid path skip the gather entirely (hybrid never consumes stage-1 context, so its estimate carries no hiring note either); deep/complete estimates carry the hiring note and duration bump. Remaining: the MCP/A2A premium and deep jobs run the orchestrator directly without the hiring stage (their estimates therefore overstate duration by 1-2 min at $0 cost until wired - a working-folder story is needed there first), and consider host-level memory so subsequent runs of the same company skip re-probing providers that already missed

Decision principle: a page counts as scraped only when Primr has evidence that the real page content appeared, not merely that a request returned HTML.

### 4. Consultant-Grade Strategic Writing

Push the standard output from a strong research artifact to a genuinely strategist-grade analysis for pre-discovery preparation.

> **Now pursued via the research-tradecraft workstream** ([`docs/design/research-tradecraft.md`](docs/design/research-tradecraft.md)). **Shipped:** framing as a first-class input (Step 1), the Day-1 hypothesis tree (Step 2), the `--plan` checkpoint (Step 3), and hypothesis-steered, budget-aware deepening (Step 4) - with the rule-vs-judgment guardrails in [`agentic-balance.md`](docs/design/agentic-balance.md). The shape of this work is **better content into a consistent structure**, not per-run structure. **Report section structure stays a curated rule** (the `company_overview.yaml` scaffold), iterated *offline* - consistency is a feature of a strategic deliverable, and the fixed scaffold does not demonstrably fall short (Principle 1). Step 5's original "argument-derived structure" is therefore **DESCOPED**: the agentic judgment lives in the *content within* each section (depth, insight, Pyramid-style "so what", constrained-evidence reasoning) - prompt work fed by Steps 1-4 - not in choosing sections. **Remaining (the heart of #4):** that content-depth prompt work (eval-gated), Step 6 adversarial ACH/pre-mortem refine, and Step 7 two-axis evidence grading. **Eval-measured (June 2026, [`eval-plan.md`](docs/design/eval-plan.md)):** the prose already grades consultant-grade and two evidence-plumbing levers (Step 4 collection-steering, context curation) washed, so the highest-value, evidence-backed remaining work is **epistemic grounding** (the label-honesty pass under Step 7) - labels trace to sources only ~0-8% today - not more prose-prompt tuning. **The label-honesty pass is now shipped opt-in (`PRIMR_LABEL_HONESTY=1`, `qa/label_honesty.py`):** it re-judges each `(Confirmed)`/`(Reported)` claim against its cited source and mechanically downgrades the ones that do not trace to `(Estimated)` (fail-safe: confidence only lowers, uncertain verdicts keep the label, an audit sidecar records every change). It stays default-off and never blocks shipping until an agreement-validated calibration baseline sets the bar; a hard gate is never armed from a lone judge.

- Section prompts tuned around management choices, operating constraints, likely economics, scenario paths, and validation questions
- Fewer brittle section suppressions, more constrained-evidence reasoning when direct company data is thin
- Dense references concentrated in final appendices so the body reads like analysis, not a source dump
- Better trust summaries so users can see what is confirmed, inferred, hypothesized, and still weak
- Target: sparse-company runs still feel substantive; rich-company runs become sharper and more differentiated

### 5. Cache-Hit Visibility & Operational Observability

Cache hit rate is load-bearing on the sub-$1 default - Grok 4.3 cached input at $0.20/M is what makes 4.3-for-reasoning viable on the budget. Without visibility, regressions in the recipe go unnoticed. Cache-token plumbing already exists at the provider level; the missing piece is threading it through to historical records and the usage UI.

- **Bridge cached-token counts - DONE.** `ChatResponse` now carries `cached_input_tokens` (xAI `cached_tokens`, OpenAI `prompt_tokens_details.cached_tokens`, Anthropic `cache_read_input_tokens`, Gemini `cached_content_token_count`); the grok session counters mirror it per model through a single `_mirror_session_usage` seam (all four call paths: grok_llm xAI, cross-provider dispatch, ContinuousReasoningSession, grok_browse_and_summarize); `UsageRecord`/`record_usage()` persist it and `primr show-usage` displays cache hit rate per run and lifetime. Actual-cost reporting (`_compute_session_llm_cost`) is now cache-aware - cached input is billed at the model's cached rate instead of overstating spend.
- **`--budget $N` flag - DONE for pre-flight, fast optional stages, and non-fast optional strategies.** Per-run cost ceiling for standard research, activating the existing `CostGuardHook` accounting via `primr.utils.run_budget`. Pre-flight: refuses to start when the dry-run estimate exceeds the ceiling. Mid-run fast-path checkpoints at the optional spend stages (Phase 2 research deepening, Phase 5 cross-validation enrichment and contradiction resolution, and Phase 6 strategy generation, including per-vendor AI-strategy dispatch in multi-platform runs) sync actual session spend and skip that stage (and, in a multi-strategy run, any remaining strategy documents) once the ceiling is reached. Premium, deep, complete, and hybrid Deep Research paths now checkpoint before and between optional strategy documents after the required Deep Research task completes; the required Deep Research task cannot be stopped mid-flight because the provider exposes only task-complete cost state. Scrape remains estimate-gated only. CLI dry-run JSON and MCP `estimate_run` payloads state the selected runtime behavior explicitly. CLI estimates also clamp enabled AI-strategy runs to at least one vendor, matching MCP estimate behavior for empty internal platform tuples, and price `--strategy-type` documents with the runtime's exact semantics (fast mode additive writing bundle; non-fast replace-AI-strategy plus one planned Deep Research task for Deep Research-backed types; placeholder types noted, not priced). Budget is cleared in a `finally` so it can't leak across runs. All three surfaces that quote a run - `--dry-run`, the `--budget` pre-flight gate, and the interactive confirm prompt (`display_cost_estimate`) - now price `--verify` (post-QA claim verification), which none of them did before; the two config-driven surfaces share one `build_run_estimate` shaping helper so they cannot drift apart again. The interactive prompt additionally now prices `--grok-tier` (it already priced `--fast`/`--strategy-type`), so a `--grok-tier max` or `--verify` run confirms against a number that matches actual spend (unblocked once the dead vendor-research code freed research_agent line-cap headroom).
- **`primr show-usage` enhancements - DONE.** Lifetime totals (already present) plus per-company history (top 10 by spend with run counts and last-run date), per-mode totals alongside averages, and the By Mode breakdown now lists *observed* modes (fast-mode runs previously never appeared in the fixed mode list).
- **`primr doctor --scraper-stats` - DONE.** `data/scraping/trace_stats.py` aggregates the per-run JSONL scrape traces (`logs/scrape_traces/`, already persisted by `TraceLogger`) across the most recent 20 runs into per-tier attempts / success rate / latency p95+avg, overall page success rate, and content-quality signals (avg chars/page, thin-page count, validation pass rate). Pure read-side analytics; unreadable trace files are skipped so analytics can never break doctor.
- **Cloud diagnostic truthfulness - DONE.** The MCP cloud doctor performs a
  live `/healthz` probe only for the control plane. Cosmos DB, Blob Storage,
  Service Bus, Application Insights, and cost-governor configuration now report
  `configured` with `probe_performed: false` instead of claiming healthy
  connectivity from environment-variable presence. Endpoint, account, and
  connection values are omitted from the diagnostic payload.
- **Cost variability + regression signal - DONE.** `UsageTracker.get_cost_variability()` compares the recent-5 runs of each observed mode against the PRIOR history (timestamp-sorted; a lifetime baseline would drag the mean toward the regression being measured), and `primr show-usage` renders a "Cost Variability" section with a report-only SIGNAL line when recent cost rises >25% over the prior average or the cache hit rate drops >10 points - the continuous-reasoning / prompt-cache regression surface. Fast runs also persist a clamped `cache_hit_rate` into `_run_state.json` alongside `actual_cost_usd` for post-hoc analysis. Signals only; nothing gates. Sticky tier policy and circuit-breaker threshold tuning from this data remain open.

### 6. Wire Circuit Breaker Into Production LLM Call Sites - DONE

All direct `grok_llm()` call sites in `research_agent.py` (coherence pass, citation repair, trust polish, strategy artifact repair, fast + strategy cross-validation and their JSON retry, section + strategy regeneration, strategy polish, analysis workbook, contradiction resolution, both strategy-generation closures) now route through `call_with_failover()` with the stage's model as `preferred_model`, and the `llm()` utility-tier xAI dispatch routes through the same seam - so a `QuotaExhaustedError` on the primary model advances to the next provider in the chain instead of failing or silently degrading the stage. Explicit model params are honored as the first-tried model when registered + keyed; unknown model strings fall through to the chain default by design. Wiring pinned by `tests/test_core/test_llm_failover_wiring.py`. Remaining (deliberate): `ContinuousReasoningSession.send()` stays direct - a multi-turn session's history is bound to its model, and mid-session failover needs a session-replay design first; the Gemini pro-tier path in `llm()` keeps its explicit quota UI (premium mode is single-provider by user choice).

### 7. Diminishing Returns Detection for Cross-Validation - DONE (initial)

Detect when cross-validation section regeneration is making diminishing progress and stop early, rather than consuming the full token budget.

- **Shipped:** `pipeline/diminishing_returns.py` - a pure `DiminishingReturnsDetector` + `assess_improvement()` (word-growth ratio and net-new `[cite: N]` markers, score = max of the two signals, never negative). Wired into the cross-validation regeneration loop in `perform_fast_research`: after each rewrite the detector records the measured improvement and the loop breaks after 3 consecutive regenerations below 5% improvement. The early stop is logged (`cross-validation: stopped early (diminishing returns after N iteration(s) ...)`) and a `diminishing_returns` summary (iterations, stopped_early, per-section scores) is persisted into `cross_validation.json`.
- Thresholds start conservative (3 consecutive, <5%) per this item's original spec - tune against eval results, not intuition.
- **Detector reuse - DONE:** the `primr refine` loop (#10) consumes the same `DiminishingReturnsDetector` for its grade-gain stop condition (two consecutive iterations under 5% relative gain). Remaining: consider a QA-score-based improvement signal once section-level QA scoring is cheap enough to run per regeneration.

### 8. Prompt Cache Preparation - DONE (section + strategy writing)

Split section-writing prompts into cached (stable across sections) and volatile (per-section) components as a clean architectural separation.

- **Shipped:** `build_fast_section_prompt_parts()` / `build_fast_batch_prompt_parts()` in `section_prompts.py` return `(cached_prefix, volatile_suffix)`; the existing builders concatenate them, so call sites are unchanged. The prefix carries only run-shared context (company header, analysis workbook, raw corpus, external research, citation key, general writing instructions, scaffolding prohibition, output contract) and is byte-identical across all parallel section writes - pinned by tests that build prompts for different sections/indexes/reasoning modes and assert prefix equality and no per-section leakage. Per-section material (TOC position, rolling context, reasoning mode, section spec, word target) moved to the suffix; instruction text is otherwise unchanged apart from direction words ("above" → named block references) since the volatile blocks now sit after the instructions.
- Zero-cost prep step: no caching API calls added - providers' implicit prefix caching (xAI cached input at $0.20/M is the load-bearing case) now gets a shared prefix to key on; the `cached_input_tokens` plumbing from item #5 makes the effect measurable in `primr show-usage`.
- **Strategy generation - DONE:** `core/strategy_prompt_parts.py` gives the strategy stage the same split - `build_strategy_context_prefix()` builds the run-shared cached prefix (company report + working-folder artifact blocks) once, and `build_strategy_prompt_parts()` returns `(cached_prefix, volatile_suffix)` with vendor research docs and the per-strategy prompt in the suffix. Both `fast_run_strategy` loops consume it: the AI-vendor closure no longer rebuilds (and re-reads) the shared context per vendor, and the YAML loop reads artifacts once instead of once per strategy type. Concatenation reproduces the legacy prompt byte-for-byte (pinned by tests, including live-stage prefix-equality wiring tests across vendors and across YAML strategy types). The module also absorbed the artifact-block read logic the two loops had duplicated.
- Remaining: apply the same principle to the cross-validation regeneration prompts in `research_agent` (`_fast_regenerate_section` / `_strategy_regenerate_section` embed shared workbook/source context per call); the lite/Pro strategy path in `ai_strategy_runtime` hand-assembles a structurally different context wrapper (whole-file reads, vendor docs interleaved) and is single-call, so it stays unmigrated by design; validate the measured cache-hit gain on a real run before tuning further.

### 9. Batch API for Section Writing (xAI + Anthropic Recipes)

Section writing is the most token-intensive stage (~40-50% of LLM spend) and the only one where all calls are independent. Route section writing through provider batch APIs for ~50% discount and zero rate-limit risk.

- New `--batch-api` flag to opt in for section writing
- After analysis/workbook completes, submit all section prompts as a single batch (xAI Batch API initially; Anthropic batch as a parallel recipe - the `grok43-haiku-batch` eval cell hung in pre-validation and needs root-cause investigation before that recipe can be promoted)
- Poll batch status until complete; retrieve results and feed into cross-validation as normal
- Graceful fallback: if batch API is unavailable or times out, fall back to existing `ThreadPoolExecutor` path
- Progress display updated: "Section writing (batch API, polling...)" with ETA based on batch state counters
- Strategy generation could also be batched when running multi-platform strategies
- Add batch-mode pricing fields to `ModelConfig` so cost estimates reflect the discount when `--batch-api` is used

### 10. QA Iteration Loop - DONE (initial)

Use QA feedback to iteratively improve weak sections.

> **Brittleness warning (see [`agentic-balance.md`](docs/design/agentic-balance.md)).** "Until reports hit 90+" optimizes prose to satisfy `compute_quality_score()` - a regex/count *discipline* proxy. Looping to maximize a proxy is Goodhart by construction: the loop learns to please the scanner, not the reader. The anti-Goodhart guard added in v1.31 (each iteration audited by the calibration harness - an instrument the objective can't see - and reverted when label traceability degrades) is the real gate; the discipline score is only a cheap pre-filter for *which* sections to look at. Do not harden this loop by adding more deterministic scoring; sharpen it by moving its acceptance test toward the eval/calibration ground truth. The "per-section grading" remaining item below must be a calibration/eval signal, not a richer regex score.

- **Shipped:** `primr refine "Company"` (`core/refine.py`) - locates the latest markdown Strategic Overview + run context (website, analysis workbook from `working/<Company>/<run>/`), then runs the Orient → Gather → Consolidate → Prune loop: deterministic weak-section identification (short / citation-free / unlabeled sections, ranked, max 3 per iteration, never the same section twice), targeted DDG evidence gathering with validated scraping, section regeneration via the failover-wrapped writer, deterministic cleanup, and re-scoring. Stop conditions in priority order: grade >= `--target-grade` (default 90), no weak sections left, diminishing returns (two consecutive iterations under 5% relative grade gain - reuses the #7 detector), max iterations (default 3). Output written through the #11 write guard (`*_improved` sibling, or `--in-place`).
- **Scoring API:** `ReportAnalyzer.compute_quality_score()` factored out as the single source of truth - the QA scorecard and the refine loop grade reports identically.
- All loop seams (score / gather / regenerate / prune) injectable; control flow pinned by deterministic tests with zero LLM/network calls.
- Remaining: per-section grading (today the loop scores the whole report; section-level QA scores would sharpen weak-section selection), and budget/timeline validation for strategy docs in the Prune phase (currently report-focused).

Principle: separate reading (Orient/Gather) from writing (Consolidate/Prune). The LLM has full context before it starts editing, which prevents hallucinated improvements that contradict existing content.

### 11. Constrained Agent Permissions for Agentic Improve - DONE

When `primr improve --improve-agentic` runs an agentic review pass, constrain the agent's write permissions to the output file only. This transforms agentic improve from a trust-based policy ("the LLM should only edit the report") into an enforced architectural constraint.

- **Shipped:** `primr.utils.write_guard.ArtifactWriteGuard` - an enforced write allowlist constructed with the stage's target artifact. Allowed: the target file and its `*_improved` sibling (plus explicit `extra_allowed` destinations such as a sidecar diagnostics report). Denied unconditionally - even if mistakenly allowlisted: `_run_state.json`, `usage_history.json`, and anything under `_raw_scrapes/` / `_hiring/` / `_diagnostics/`. Paths are resolved before checking, so `..` traversal is judged by where the write actually lands. `improve_output_file` now writes through the guard (`WriteGuardError` surfaces as a blocked improve, not a silent write).
- Reads remain unrestricted (the stage may read working/output files for context); DDG search is read-only external and unaffected.
- The guard is the seam any future agentic artifact-modifying stage must use: expert perspective passes, strategy enrichment, cross-validation regeneration. Folds into the per-tool authorization work in #21 for the MCP surface.

### 12. Working-Directory Tidiness for CLI Users

When primr is installed via `pip install primr` and run from an arbitrary
folder (e.g. `docs/<company>/`), the working files (`working/`,
`output/`, `_diagnostics/`) end up scattered into wherever the user
invoked the command. Running back-to-back in `companyname/`, then
`company2name/`, then `company3name/` leaves a messy filesystem with
duplicated state. Tighten the story:

- **Self-documenting folders - DONE.** `output/` and `working/` now receive a
  top-level `README.md` when primr creates them (written once, user edits
  preserved, read-only directories tolerated): what lives there, what is safe
  to delete vs preserve (`working/` = resumable intermediates including
  `_run_state.json`; `output/` = finished deliverables with no run state),
  and the synced-folder caution. Both paths already resolve from the same
  `PROJECT_ROOT` (pyproject/.env anchor, else the invocation directory), so
  a pip install run from an arbitrary folder gets both dirs side by side
  with their explanations.
- **Per-user cache directory - DONE.** `primr.utils.user_cache` resolves
  `PRIMR_CACHE_DIR` override → `%LOCALAPPDATA%\primr\` (Windows) →
  `$XDG_CACHE_HOME/primr` → `~/.cache/primr`, with a `migrate_legacy_file`
  helper for one-time moves. Recon caches / eval baselines / prompt cache
  hints can adopt the same seam as they come up.
- **Vendor news moved - DONE.** `get_vendor_research_path` now lives in the
  per-user cache (the legacy location was `PROJECT_ROOT/vendor-research/`,
  which lands inside site-packages for pip installs); a file at the legacy
  path is migrated on first access. Preflight write-checks validate the new
  directory.
- **`primr doctor` file locations - DONE.** A "File Locations" section shows
  where deliverables, working files, the user cache, vendor research, and
  usage history live, and which are per-run vs shared.

### 13. Vendor News Caching Across Runs + Weekly Freshness - DONE

The `is_vendor_research_current` default was 14 days; v1.26 tightened it
to 7 days (weekly). All three gaps closed:

- **Grounded-lite default (1.37.0) - DONE.** Vendor news now defaults to a
  grounded-lite engine - a single Gemini call with live Google Search grounding
  (~$0.30, current and cited) - instead of Deep Research. The heavyweight Deep
  Research engine (~$2.50/task) is opt-in via `--deep-research`.
- **Shared per-vendor cache - DONE** (via #12's per-user cache): back-to-back
  runs in different company folders now reuse one vendor research file per
  vendor. Missing cache files are now skipped unless refresh/generation is
  explicitly enabled, so cache misses do not add hidden Deep Research spend.
- **Configurable TTL - DONE.** `PRIMR_VENDOR_NEWS_TTL_DAYS` (default 7,
  invalid/negative values fall back) drives `is_vendor_research_current` AND
  the reuse/refresh gates in `get_or_generate_vendor_research[_sync]` - the
  previously hardcoded 14-day fresh-gate now follows the same TTL. Refresh
  still requires explicit opt-in (`--refresh-vendor-research`, direct-library
  `PRIMR_ALLOW_VENDOR_REFRESH=1`, or `force_refresh`), preserving the cost-cap
  behavior. Estimate-bound CLI and MCP paths ignore the ambient setting.
- **Freshness visibility - DONE.** `primr show-usage` ends with a "Vendor
  Research Freshness" section listing each cached file's age and
  fresh/stale status against the TTL. (`--refresh-vendor-research` already
  existed as the refresh flag.)
- **Estimate-bound refresh and context parity - DONE.** Integrated fast and
  standard strategy paths disable ambient cache refresh, carry the explicit
  `--refresh-vendor-research` intent into execution, and quote one
  grounded-lite refresh task per selected platform (or a Deep Research task
  under `--deep-research`). Fast AI Strategy now reads
  the same cached cross-industry research as standard and standalone paths
  through bounded, identity-stable, body-safe file handling; an optional cache
  failure cannot block strategy generation. Refresh publication is atomic,
  provider usage is recorded even when local publication fails, existing cache
  content remains the explicit fallback, and fast multi-platform refresh work
  is serialized before parallel strategy writing to protect shared client and
  usage state.
- **Direct generation cost governance - DONE.** The standalone
  `--generate-vendor-research` command aggregates every requested Deep Research
  task, including private accelerated-infrastructure research, into one
  estimate, supports zero-call `--dry-run` and `--budget`, and
  requires interactive confirmation unless `--skip-confirm` explicitly
  approves noninteractive execution. JSON returns one estimate or result
  object, and partial failures preserve successful paths while returning a
  nonzero status.
- **Standalone strategy machine contract - DONE.** Zero-call JSON dry-runs,
  approval-required refusals, and approved execution results are distinct
  versioned one-object contracts. Result objects name every expected target,
  preserve successful artifact paths on partial completion, contain provider
  exceptions without exposing response bodies, and return nonzero for any
  unfulfilled target.
- **Truthful integrated outcomes and task accounting - DONE.** Base-report
  completion is now independent from requested strategy and vendor-refresh
  fulfillment. Fast, standard, deep, complete, and hybrid runs persist expected,
  completed, failed, and budget-skipped targets; JSON preserves the report path
  while separating base status from aggregate `fulfillment_status`; and the CLI
  returns nonzero when an explicit target is missing or outcome state cannot be
  trusted. Human completion and local job-monitoring surfaces expose unresolved
  targets. Provider callbacks feed run-local refresh and AI Strategy task
  ledgers, so concurrent jobs cannot contaminate counts and preflight failures
  are not priced as submissions. Standard-mode summaries include AI Strategy
  and refresh Deep Research tasks, while refresh usage rows remain
  single-counted. Optional standard-strategy failures preserve the completed
  base report. Linked, hard-linked, oversized, or mutation-unstable vendor
  context is rejected through one shared private-snapshot seam before lite,
  standard, or asynchronous provider egress.
  Local job monitoring parses the same canonical outcome contracts and refuses
  to report completed fulfillment for missing, unknown, or inconsistent
  lifecycle state. Fast refresh budget gates include every earlier submitted
  task, and provider or polling exceptions after refresh submission create one
  conservative usage record without double-counting publication failures.

### 14. Windows Working-Directory Hardening

Reduce false negatives and transient failures on Windows machines where the repo lives inside OneDrive or similar synced folders. Bumped up from the bottom of the queue because it actively bites this very dev environment (transient `PermissionError` on atomic renames, CRLF warnings on every git operation, OneDrive-driven race conditions on `_run_state.json`).

- Make checkpoint/state writes tolerant of transient `PermissionError` during atomic rename. **DONE:** every temp-write + rename persistence path now goes through the single `utils.atomic_io.atomic_replace` seam (retry with backoff on `PermissionError`, then re-raise): `_run_state.json` saves (`run_state_io`, which additionally keeps its direct-overwrite last-resort fallback), pending Deep Research jobs (`ai/job_persistence`, whose redundant exists/rename branch also collapsed into the seam), the update-check cache (`utils/version_check`), host-marker state (`data/scraping/host_markers`), plus the already-wired chat logger, agentic memory, company profiles, MCP job store, and usage tracker. The former inline retry loop in `run_state_io` was a second copy of the seam's logic and is gone. Wiring pinned by transient-lock tests in `test_run_state_io.py` and `test_job_persistence.py`.
- Update `primr doctor` to probe the same atomic write path used during real runs. **DONE:** doctor's filesystem probe (`_atomic_write_probe`) now performs temp write + `atomic_replace` - the identical seam state saves use - against `output/` and `working/`, so sync-client lock contention surfaces in doctor before it bites a live run.
- Add explicit docs for keeping high-churn `working/` paths outside synced folders when possible. **DONE:** `docs/CONFIG.md` PathConfig section now has a "Synced folders" subsection explaining the lock-contention mechanism, the safe-by-design retry/fallback behavior, and the recommended layout (high-churn dirs local, only `output/` synced).
- Longer term: support a configurable working directory separate from the repo root

### 15. Skill Pack: Deeper Anthropic Best-Practices

The v1.26 skill pack ships Anthropic's published authoring conventions
already (third-person descriptions, gerund-form names, checklist
workflows, template-pattern output formats, explain-WHY style, concision
over padding - all enforced via prompt + validator SOFT checks). A four-tier
refinement pass then landed (see Changelog, Unreleased), closing most of the
gap against Anthropic's [skill-creator workflow](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
and [best-practices guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):

> **Watch the validators here - same trap.** The ASKILL-* heuristics
> (`DESC-PUSHY`, `NAME-PRODUCT`, `SEC-INJECT`, …) are regex policing
> LLM-generated skill markdown, and the changelog already records the treadmill
> (false-positives patched release after release). Per the standing rule
> ([`agentic-balance.md`](docs/design/agentic-balance.md)): the right tier-2/4
> work is the *eval* (trigger-discovery + behavioral with/without grading) -
> those measure quality. The content-shape validators stay structural and
> safety-focused: valid YAML, path traversal, injection, portability, minimum
> substance, and explicit authoring markers. Avoid subjective prose-grading
> regexes; prefer fixing the authoring prompt over policing style.

- **Quality baseline (Tier 1) - SHIPPED:** holistic rosters (plausible
  reserve + universal-function coverage so a posting-heavy company still gets
  sales/marketing/HR/finance/ops/IT alongside named practices); task-named
  skills enforced (`NAME-PRODUCT` - no bare product titles); `DESC-PUSHY`
  rewritten to count enumerated trigger intents (no more false positives on
  services descriptions); thin bodies auto-expanded; cross-role overlaps
  auto-resolved (`PACK-OVERLAP-LLM` / `PACK-TRIGGER`) instead of only flagged.
  Follow-up shipped: bodies under 300 words are hard failures, `BODY-QUALITY`
  requires intake, scope guardrail, human checkpoint, and worked input/output
  markers, and `author_skill.yaml` now asks for those hand-built-skill patterns
  directly.
- **Saved-plan admission and approval parity - SHIPPED (2026-07-14):** saved
  plans are byte-bounded, structurally validated, prompt-bounded, globally
  capped, and curated atomically before estimation. CLI and MCP estimates bind
  and price the same prepared in-memory plan snapshot that execution consumes,
  including full refinement and bounded pack-level reconciliation fan-out.
  Canonical plan content and all cost-relevant controls are covered by the
  approval token, and diagnostics do not reflect untrusted plan values.
- **Business-role archetype coverage - SHIPPED (2026-06-19):** the bundled
  archetype catalog now covers sales, marketing, people operations, finance,
  legal/compliance, and operations roles, matching the universal-function roster
  work above. `match_archetype` no longer returns weak display-name similarity
  as usable grounding, so unknown roles author from evidence only instead of
  inheriting a misleading technical template family.
- **Per-skill trigger eval generation - SHIPPED (Tier 2, `--optimize-triggers`):**
  generate should/should-not-trigger queries, score the description against a
  blind discovery simulator, and rewrite it when below threshold - kept only
  if it beats the original on a held-out split (`skill_pack/trigger_eval.py`).
- **Progressive disclosure with `references/` and `scripts/` subfolders -
  SHIPPED (Tier 3):** `BundledFile` on the schema; authoring may emit
  `references/*.md` for load-on-demand context, while reviewed first-party
  code supplies executable helpers. The packager writes accepted companions
  to both output formats; `BUNDLE-PATH` validates paths and drops unsafe ones.
- **"Solve, don't punt" hardening - SHIPPED (Tier 3):** the authoring prompt
  requires deterministic checks to be specified in the workflow. Executable
  companion output is discarded rather than treated as sandboxed Python. A
  structural `SEC-EXEC` boundary uses a CommonMark parser to reject every
  fenced or indented code block, including nested container forms, reject raw
  HTML except the verifier's literal artifact placeholder, plus
  explicit interpreter and command forms, machine-readable execution keys,
  non-empty argument vectors, correlated process file and argument specifications,
  helper-materialization directions, and unregistered executable references
  in agent-consumed authored fields. Link destinations, titles, and used or
  unused CommonMark reference definitions are decoded before inspection, and
  multiline code and embedded JSON reconstruction are explicitly bounded; it
  does not pretend to infer arbitrary prose semantics. The
  guaranteed `scripts/verify-artifact.py` is an exact registered first-party
  artifact with bounded regular-file scanning over portable, workspace-relative,
  link-free local paths; altered or additional scripts fail the `SEC-BUNDLE`
  gate and are dropped again by the packager. The final
  `ROLE-VERIFIER` invariant also survives refinement and overlap resolution.
  Every external authoring-evidence field is sanitized and nonce-fenced as data,
  and the final package boundary reuses its high-confidence authored-output
  prompt-injection policy without blocking legitimate examples and role prose.
  Generated instruction prose is explicitly treated as untrusted and requires
  review before installation or sideloading. `SEC-EXEC` remains a defense-in-depth
  structural and explicit-carrier backstop; host tool allowlists, approval gates,
  and sandboxing remain mandatory because arbitrary natural-language intent is
  not mechanically decidable.
  Same-day output is built in a fresh sibling and replaces only marker-owned or
  narrowly recognized legacy trees; links, mounts, and unrelated directories
  fail closed, and bounded Windows rename/cleanup behavior is explicit.
- **Skill-level evals with grader - SHIPPED (Tier 4, `--with-evals`):**
  per skill, generate task cases + assertions, run the task WITH vs WITHOUT
  the skill, grade both blind, report the pass-rate delta, and write
  `evals/evals.json` (`skill_pack/behavioral_eval.py`). Generated cases pass
  a field-specific control-plane boundary before model execution, grader inputs
  are nonce-fenced, and packaged eval JSON passes a bounded form of Anthropic's
  current `expectations` schema before either supported artifact format is
  written. The optional `files` key is accepted only when empty until Primr can
  package and integrity-check companion eval assets; nonempty references fail
  closed rather than shipping dangling paths. New bundles use the upstream
  field names while the earlier Primr `assertions` form remains readable. This
  closes direct-bundle instruction carriers without blocking realistic
  code-generation or strictly review-only fenced code tasks. The boundary
  canonicalizes CommonMark and links before validation, rechecks decoded
  Unicode, rejects execution intent around review blocks, rejects sensitive
  credential access and transfer, and rejects Markdown links because hidden
  destinations and definitions are not required by the eval schema. Review
  fences admit executable examples only under an inert frame and still scan
  all content for prompt control plus comment prose for unsafe operational and
  sensitive-data instructions. A shared,
  typed CommonMark security surface owns canonicalization and link policy;
  evaluation schema and control-plane policy live together in a focused
  validator. Task arms and their graders use fresh stateless calls that retain
  the configured model and reasoning tier without generation history. Cost
  approval reserves the exact one generation plus four calls per case,
  model-registry pricing, token ceilings, sequential runtime, and the same
  strict two-attempt cap enforced at execution. OpenAI-compatible SDK retries
  are disabled at construction so Primr's explicit loop is the sole retry
  owner and the approved attempt cap is also the physical HTTP-request cap.
  The admission grammar covers response-oriented secret disclosure, common
  credential artifacts, terminal entry, executable-result coreference, and
  artifact activation while preserving bounded business-task and
  credential-metadata reporting forms. It also binds adjacent-clause secret
  pronouns, recognizes structural terminal and interpreter sinks, scans inline
  comments by language, blocks lexically non-public raw HTTP targets without
  DNS, preserves pure non-Latin prose, and skips skills whose generated cases
  are all inadmissible rather than recording a zero-case benchmark.
- **Agent-handoff declarations in SKILL.md frontmatter** - PARTIAL: the
  primr-namespaced `metadata` block (role, provenance, confidence,
  context-token budget, MCP/A2A refresh hint) is available as an explicit
  opt-in (`--emit-agent-metadata` / MCP `emit_agent_metadata`) while clean
  `name` + `description` frontmatter remains the default. Remaining: an
  explicit declared tool surface (`allowed-tools`) so the pack is fully
  self-describing to a consuming agent. Folds into the control-plane work (#21).
- **Multi-model testing** - PLANNED: Anthropic recommends testing skills
  against Haiku, Sonnet, and Opus before shipping. The Tier-4 behavioral
  harness gives the natural seam - run the with/without grading across model
  tiers and flag skills that regress on the cheaper tier.
- **Verifiable intermediate outputs (plan-validate-execute pattern)** -
  PLANNED: for skills that perform batch or high-stakes operations, emit a
  separate plan-file step the agent can validate before applying.
- **Security/profile rules for generated skills and agent clients**:
  PLANNED: maintain a small Primr-owned policy profile with metadata tags for
  always-apply rules, context-selected rules, artifact type, and security
  domain. Use it to guide skill-pack authoring and structural validation around
  secrets, raw endpoint/account leakage, data retention, external egress,
  approval thresholds, and declared tool permissions. Keep this as versioned
  local data plus validators, not a prose mega-skill and not one tool per rule.
  Later, allow optional operator policy overlays so generated packs can reflect
  local org requirements without baking those requirements into Primr itself.

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
(roles assume contradicting stacks - e.g. one says Java/Spring, others
say Python/AWS, because both stacks exist in the company's hiring
postings), the pipeline surfaces it in the report but doesn't auto-fix.
Add an explicit reconciliation round: when PACK-STRAT fires, re-author the
conflicting skills with cross-role context so they acknowledge the
multi-stack reality rather than contradict each other. **Seam now exists:**
the Tier-1 `auto_resolve_overlaps` pass (which re-scopes one skill of an
overlapping/colliding pair and reverts on a new HARD finding) is the same
shape this needs - extend it to the PACK-STRAT case with a reconcile-both
prompt instead of the narrow-the-second-skill prompt.

### 17. Auto-Eval on Model Releases

Reduce manual work when new model variants drop by automating the eval-and-compare cycle.

- Trigger eval sweep when a new model is registered in `ModelRegistry` (manual trigger initially, automated detection later)
- Run the standard 3-5 company corpus against the new model and current default, generate comparative scorecard
- LLM judge overlay (cloud or local Ollama) for subjective metrics: utility, strategic sharpness, hallucination rate
- Wire `--continuous-reasoning` / `--no-continuous-reasoning` into the eval harness so topology choice is scored against the same baseline systematically
- Decision output: "new variant is better/worse/equivalent for [stage]" with evidence
- Keeps defaults current without gut calls on each release

### 18. Capability-Requirement Routing Layer

Provider abstraction and role-based routing shipped in v1.22.0/v1.23.0. The first stage-requirements slice is in place as a pure router, and `fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals` now consume it at runtime behind `--inference cloud|hybrid` with route usage metadata persisted in the run state. The Codex adapter is available only as an explicitly acknowledged, single-company experiment with potentially metered billing and pending-eval metadata; the remaining work is its representative host-vs-cloud comparison, broader production wiring, provider-health integration, billing-verifiable host/local adapters, and per-stage eval-backed tuning.

- **Shipped foundation:** `StageRequirements`, `BackendCapabilities`, `RoutingPolicy`, and `route_stage()` return ordered cloud/gateway/host-agent/local candidates with explicit rejection reasons and no live provider calls
- **Shipped availability foundation:** `ProviderQuotaSnapshot`, `QuotaWindow`, `availability_decision()`, and `provider_with_most_headroom()` normalize provider quota windows and stale last-known-good service availability without live provider calls
- **Shipped generic collectors:** `collect_provider_availability_snapshots()` reports non-secret provider configuration status and generic local OpenAI-compatible availability from the user's own runtime environment, without storing API key values, raw endpoint URLs, account ids, or installed model names
- **Shipped router bridge:** `backend_with_availability()` and `backends_with_availability()` apply provider snapshots to backend capability rows and attach sanitized availability metadata before `route_stage()`
- **Shipped doctor visibility:** `primr doctor` now shows sanitized provider availability from the same generic snapshots, without paid cloud probes or local endpoint leakage
- Production-stage requirements are declared in `core/stage_inventory.py`: minimum reasoning depth, trust sensitivity, required capabilities, token/context estimates, and acceptable backend families
- Runtime bridge shipped in `ai/stage_routing.py`: `fast.scrape_summary`, `fast.source_relevance`, and `fast.hiring_signals` resolve their legacy utility models through `route_stage()`, log safe route metadata, append capped body-free `stage_routes` records to `_run_state.json`, include measured token/cache/cost deltas when provider counters expose them, and execute through the existing utility provider seams with today's role defaults preserved as fallback. When tests or evals exercise the internal agent profile, stages without a host adapter record `agent_profile_unavailable` and use deterministic local output rather than silently falling back to cloud LLMs. The public CLI remains `cloud|hybrid`.
- Stage route comparison artifacts shipped in `core/stage_route_comparison.py`: run-state route records can be aggregated by stage/backend/profile into body-free JSON and Markdown summaries with attempts, selected/fallback/failure counts, latency, and measured token/cache/cost deltas
- Stage eval scorecards shipped in `core/stage_eval_scorecard.py` with CLI artifact flow behind `primr --eval --eval-stage-scorecard`: explicit quality evidence can now be joined with route comparison rows to classify candidates as human-review-ready, needing quality eval, below quality bar, or needing reliability review without auto-promotion
- Stage scorecard MCP readback shipped in `mcp_server/stage_scorecard_summary.py`: `primr://eval/stage_scorecard/{eval_id}` returns compact route, quality-score, status, and blocker fields from the eval artifact without arbitrary path reads, prompt bodies, report bodies, quality-source bodies, or raw run-state content
- Generated stage quality evidence shipped in `core/local_stage_eval.py` and `core/cli_local_stage_eval.py`: website-summary local-stage evals write `website_summary_stage_quality_evidence.json`, and same-command scorecard generation can consume that structured evidence when no manual quality file is supplied
- Semantic local stage evidence shipped in `core/local_stage_eval.py` and `core/cli_local_stage_eval.py`: `--eval-local-stage website-summary --eval-local-stage-semantic-judge` runs a local OpenAI-compatible semantic judge pass or comma-separated local judge panel, writes body-free semantic eval artifacts with score-spread agreement metadata, and can feed same-command scorecards as review-only evidence. This is not a promotion gate by itself; broader calibrated samples and human-reviewed acceptance criteria are still required.
- Source-relevance labeled fixture evidence shipped in `core/source_relevance_eval.py` and `core/cli_local_stage_eval.py`: `--eval-source-relevance-fixture` converts expected and candidate keep-list source numbers into body-free precision, recall, F1, exact-match, and scorecard quality evidence for `fast.source_relevance`
- Router selection must continue to be wired into execution and cost estimation stage by stage, keeping today's role defaults as fallback until eval data promotes a requirement profile
- Integrates with the circuit breaker - unhealthy models are skipped automatically
- Official cloud quota/status collectors must translate supported provider surfaces into the availability shape, then feed the existing availability-to-backend adapter before routing
- Integrates with effort-level routing for hybrid inference
- Provider prompt-caching research must cover Anthropic, OpenAI, Gemini, xAI,
  and gateway variants before new caching behavior is enabled. Caching is only
  allowed when the estimator models cache-write and cache-read prices, usage
  records expose hit/write tokens, and the route can prove expected savings. No
  default pre-warming, no background cache refresh jobs, no 1-hour TTL default,
  and no paid keepalive workaround. If the first write is not expected to be
  reused inside the provider's supported window, do not cache.
- Long-context and cache-token estimate modeling - DONE: `ModelConfig` now
  carries long-context tier metadata across the OpenAI GPT-5.x family
  (>270K input: 2x input, 1.5x output), `PrimrModels.calculate_cost_breakdown()`
  reports live input, cached input, cached-input cost, selected tier, and
  long-context surcharge, `CostEstimate` surfaces those fields, and historical
  cached-token averages feed estimates without assuming speculative cache hits.
- Move provider-specific behavior into providers. `XAIProvider` now owns the
  xAI Responses API browse/search surrogate behind the legacy
  `grok_browse_and_summarize` compatibility wrapper, and `GeminiProvider` now
  owns terminal quota guidance rendered by the legacy Gemini `llm()` path.

The requirements themselves come from observed eval cost/quality data per role, not a priori guessing.

### 19. Pipeline Overlap

Reduce end-to-end runtime by overlapping independent pipeline phases.

- Current standard path: homepage and default 10-page sequential pilot, then a
  bounded three-worker crawl; external search still waits for the full corpus
- Upgrade: start external search after homepage content is available (don't wait for all pages)
- External searches hit different hosts (DDG, news sites) - safe to run alongside primary site scraping
- Insight extraction can begin on early pages while later pages are still scraping
- Simple scheduling with `asyncio.gather()` - no orchestration framework needed
- Expected gain: 5-10 min overlap between scraping and external research phases

Current production concurrency:

- Homepage and pilot pages run sequentially so Primr can learn access quality,
  block behavior, and the effective tier before widening work
- Remaining site pages use a bounded three-worker pool; the per-host limiter
  remains authoritative for concurrency, request rate, and token-wait jitter;
  persistent host cooldown state owns live 429 recovery
- Section writing: `ThreadPoolExecutor(max_workers=4)` - up to 4 sections concurrently
- External search queries: `ThreadPoolExecutor(max_workers=3)` - 3 concurrent DDG/Google queries
- Link verification and the standalone parallel-scraper helper have separate
  concurrency budgets; their worker counts are not the live site-corpus policy

Same-host concurrency stays deliberately cautious rather than sequential.
Measure block rate, recovery rate, p95 page time, and total corpus time before
changing the three-worker or per-host limits. Sticky-tier optimization,
token-bucket admission, jitter, persistent cooldowns, and circuit breakers
remain the safety controls.

Completion guarantees:
- All overlapped phases must complete before downstream stages start (no partial results)
- `asyncio.gather(return_exceptions=True)` with explicit error handling
- Run state tracks per-phase completion status for crash recovery
- Progress display updated to show concurrent phases (e.g., "Scraping 23/50 | Searching 4/10")

### 20. Snapshot Subcommand

A new top-level subcommand for the case where you want a fast look at a company before deciding whether to spend on a real run. Explicitly framed as screening, not analysis. Not a quality dial on `primr` - a separate, narrower product.

Why this exists at all: degrading the standard pipeline to chase sub-5-minute runtime is a bad trade. If you want fast-and-shallow, you can already get that for free from a search engine. The interesting cheap-and-fast tier is one that does specifically what's free or near-free in well under a minute: DNS recon, homepage render, and a single LLM synthesis pass. Anything beyond that costs real time and money and should go through the real pipeline.

What the subcommand does:
- `primr recon` (DNS intelligence, ~3s, free, already exists)
- Homepage + 2-3 highest-signal pages (about, leadership, products) via Playwright tier 1 only - no escalation, no fallback fan-out
- One DDG search for recent news (free)
- One synthesis call (cheap utility-tier model - Gemini 3.1 Flash-Lite or equivalent) producing a one-page Markdown brief

Budget: ~30-45s wall-clock, ~$0.03, no DOCX, no QA gate, no cross-validation, no strategy.

Output shape: a single Markdown one-pager with sections for who they are, tech stack signals from DNS, what's on their homepage right now, one recent news item if DDG returned anything, and an explicit footer pointing to the full `primr` command. Header banner: "Snapshot - screening only, not strategic analysis."

What it explicitly is not:
- No tier escalation: if Playwright tier 1 doesn't render the homepage, the snapshot fails fast and tells the user to run the full pipeline
- No public-data fallback fan-out - that's a strategic recovery path, not a screening tool
- No hiring signals, no cross-validation, no strategy, no DOCX
- No cost-vs-depth dial on the standard pipeline - `primr` always means "excellent report"

Decision principle: the standard pipeline is the product. Snapshot is the cheap pre-flight that helps you decide whether to invoke it. Speed is only worth paying for when the alternative is free.

### 21. Agent Control Plane Hardening

The MCP/OpenClaw/skill integrations are treated as a disciplined Primr control plane rather than thin shell wrappers. Next work is narrower and more intentional than the initial integration push.

This work is for: making long-running, paid Primr runs safer and easier to route, approve, monitor, resume, and consume from agent clients. Keeping the user experience aligned to Primr's actual product shape: URL in, serious artifact out.

This work is not for: turning Primr into a generic orchestration platform, replacing the CLI, duplicating core business logic in skills, or exposing a shell-shaped `run_primr(command_string)` surface.

Shipped:
- Server-issued approval tokens for the MCP cost-cap-governed execution tools
  (`research_company`, `generate_strategy`, `generate_skill_pack`). Estimate
  tools return short-lived, HMAC-signed, single-use tokens bound to the target
  tool, approval-shape hash, approved max cost, and expiry. When server-side
  MCP cost enforcement is active, execution requires both the cap and a matching
  token.
- Privacy-preserving MCP invocation audit logging. Tool calls append JSONL
  events with timestamp, transport, tool name, hashed caller id, granted
  scopes, argument/result hashes, approval token id, cost metadata, job id,
  duration, and outcome. `primr://agent/audit/recent` exposes recent events to
  local stdio callers and admin-scoped HTTP callers without storing raw
  arguments, raw results, or approval tokens.
- Privacy-preserving MCP resource-read audit logging. Resource reads append
  JSONL events with timestamp, transport, hashed caller id, granted scopes,
  normalized resource kind, hashed resource URI, hashed result body, job id
  when present, duration, and outcome. Raw resource URIs, URI query values,
  resource bodies, and caller ids are not persisted.
- OpenTelemetry-compatible audit projection. Tool, resource, and A2A skill
  audit events now carry `request_id` plus a body-free `otel_span`
  name/attribute payload with job id when present, so structured logs can feed
  App Insights or OTLP exporters without persisting raw arguments, results,
  resource bodies, report bodies, URLs, or caller ids.
- MCP runtime budget propagation for `research_company` fast-path runs. The
  approved `max_estimated_cost_usd` now reaches `PipelineRunner` as an active
  `RunBudget`, so the same mid-run checkpoints used by CLI `--budget` apply to
  the MCP networked surface. The process-global budget is cleared in a
  `finally` after success, cancellation, or failure.
- Truthful local MCP/A2A execution ownership. Each long research job now runs
  in a packaged Python child behind a strict versioned JSONL protocol. The
  shared parent supervisor retains the process handle, waits for the worker's
  ownership-ready handshake, validates monotonic progress, and commits a
  terminal result only after observed exit. Cancellation is cooperative first,
  then bounded process-tree termination through POSIX process groups or a
  kill-on-close Windows Job Object. Repeated cancellation is idempotent,
  interrupted journals reconcile on restart, and supervised failed or
  cancelled worker exits receive manifests stating that remote provider work
  is `unknown` when it cannot be confirmed stopped. Spawn and restart failures
  remain journal-only.
- MCP execution now matches its estimate for the default AI Strategy artifact.
  Full and premium calls use agnostic strategy by default unless
  `no_ai_strategy=true`; the standard premium/orchestrator path now generates
  that promised strategy instead of pricing an artifact it did not deliver.

Planned:
- Converge hosted one-job containers and the older deployment runner on the
  packaged worker protocol, then add explicit provider-side cancellation state
  where provider APIs make confirmation possible.
- Add integration eval suites for routing, approval, recovery, and recomputation avoidance
- Expose a compact project security/profile resource for agent clients when
  useful, including always-on guardrails and context-selected guidance for
  security-sensitive edits, without duplicating the application spec or growing
  the MCP tool surface one rule at a time
- Keep skills thin and MCP-first; intentionally avoid turning SKILL files into duplicated application specs
- Preserve typed lifecycle/control-plane primitives instead of free-form execution wrappers

### 22. Azure Deployment Finalization

The Azure tiered deployment (team and organization) has its Bicep IaC, deploy script, OpenAPI spec, budget tracker, environment auto-detection, JWT validation, and cloud diagnostics in place. The deployment provisions in ~3.5 min, /healthz passes, and 162 tests across budget/auth/environment are green. The remaining items are concrete:

- **Container App entrypoint**: The MCP server (`primr-mcp --http`) needs to run correctly inside the Docker container. The Bicep command override is in place but the container crashes on startup - likely a dependency or import path issue that needs local debugging. The Dockerfile currently builds for the job runner; the API server entrypoint needs the same image to also serve HTTP.
- **Container App Job triggering**: The MCP server's `research_company` tool needs to trigger Container App Jobs in cloud mode instead of running the pipeline in-process. This is the queue integration that enables 20+ concurrent users.
- **ACR build log streaming on Windows**: Azure CLI's `az acr build` crashes on Windows due to a Unicode encoding bug in colorama/cp1252. Workaround in place: poll `az acr task list-runs` for completion instead of streaming logs. Needs to be finalized in `deploy.ps1`.
- **Structured logging for Application Insights**: Log fields (request_id, job_id, tool_name, duration_ms) are designed but not yet wired into the container runtime.
- **VNet integration**: Documented as planned production work. Private endpoints for Cosmos DB, Storage, Key Vault, and Service Bus are not yet configured.

### 23. Refactor Orchestrators for Unit-Test Coverage

After the v1.25.x refactor extracted `cli_batch.py`, `cli_doctor.py`, `cli_parser.py`, `section_planning.py`, `strategy_artifacts.py`, and similar helper modules out of the three monsters, the remaining coverage gap was concentrated in functions that resisted unit-mock testing because they interleaved I/O, LLM calls, and state-machine transitions in a single body. The `perform_fast_research` split has now closed the largest structural blocker; the remaining work is the per-module coverage ratchet on the exposed seams:

- `research_agent.perform_fast_research` (~1900 lines) - extract pure helpers for the per-section orchestration loop, the strategy-artifact pipeline, and the cross-validation/repair cycle so each stage is callable in isolation with a mocked LLM and scrape boundary. EXTRACTION COMPLETE (Batches A-G) - stage map: [`docs/design/23-orchestrator-refactor-map.md`](docs/design/23-orchestrator-refactor-map.md). Stage 0 setup → `fast_run_setup.py`; stage 1 data collection → `fast_run_collection.py`; stage 2 hiring → `fast_run_hiring.py`; stage 2B insights assembly → `insights_assembly.py`; stage 3 gap deepening → `fast_run_gaps.py`; stage 4 workbook → `fast_run_workbook.py`; stage 5 section writing → `fast_run_sections.py`; stage 6 cross-validation → `fast_run_validation.py`; stage 7 trust polish → `fast_run_trust.py`; stage 9 strategy → `fast_run_strategy.py`; stage 10 finalization → `fast_run_summary.py` (stage 8 deliberately inline). ~110 stage-level tests on previously-untestable behavior; `perform_fast_research` is now a ~295-line coordinator. Endgame: `C901` complexity budget DONE (max-complexity 25, grandfathered offenders); `FastRunContext` deliberately deferred (see map - explicit kwargs ARE the data-flow documentation; revisit for resume/checkpointing); remaining: research_agent per-module coverage toward 80%.
- `deep_research.DeepResearchOrchestrator._execute_consulting_research` - DONE (superseded by an earlier refactor this entry never recorded; verified 2026-06-12): the orchestrator is already split into discrete async helpers (`generate_report` → `_execute_with_retry` → `_execute_single` → `_poll_for_completion`) with dedicated suites (`tests/test_ai/test_execute_with_retry.py`, `test_deep_research_generate_report.py`) covering exactly the failure modes this bullet asked for

Target: all three monster files at 80%+ line coverage. This is a refactor for testability, not a new feature - the rule should be no behavior change, only seam introduction, and existing eval scores should remain identical.

### 24. Runtime & Key Diagnostics Robustness (Python 3.14) - DONE

Surfaced by a live standard run on a Python 3.14 interpreter: failures that degrade output silently or send debugging down the wrong path.

- **Recon event-loop fix - DONE**: the inline recon call used `asyncio.get_event_loop().run_until_complete(...)`, which raises `RuntimeError: no current event loop` on 3.14, so recon was skipped with only a warning. Switched to `asyncio.run(...)`. **Audit complete:** the three remaining inline `get_event_loop()` + `run_until_complete` copies (`ai_strategy_runtime.py`, `strategy_generation.py`, `research_agent.py` deep-research path) were RuntimeError-guarded but duplicated a deprecated pattern; all three now standardize on the single safe helper `primr.utils.async_utils.run_sync` (3.14-safe, refuses to run inside a live loop, reuses-or-creates the thread's loop). `run_sync` / `sync_context` keep their internally-guarded `get_event_loop()` - that is the one sanctioned location.
- **Key-source diagnostics - DONE** (PR #20): `keys list` / `doctor` show the resolved source of each key (OS env var vs user config vs local override) and warn when an env var shadows the `.env` value.
- **Synced-folder log hardening - DONE** (PR #19): chat-log writes are atomic (PID-suffixed temp + `atomic_replace` with retry) so OneDrive file locks can't corrupt the log. Cross-refs #14.

### 25. Skill Pack: JD-as-Evidence Input & Enterprise Role Discovery

Surfaced building a skill pack for a specialized, non-technical role at a large multi-brand retailer, where the richest grounding was a pasted job description the pipeline could not ingest, and posting discovery returned only front-line roles.

- **JD-as-evidence input - DONE (2026-06-19)**: `--from-jd PATH` / MCP `from_jd_path` ingests a local job description or role brief, sanitizes it, and writes `_hiring/operator_role_brief.md` before planning/authoring. JD-only single-role runs no longer require a company URL when the role brief is the evidence source, and `--roles-override` now still receives the JD context during authoring.
- **Enterprise role-discovery honesty: posting-incomplete warning DONE (2026-06-19)**: when discovered postings cluster in one narrow band (e.g. all store/front-line for a large org), the observed-roles set can silently under-represent specialized corporate roles. The planner now runs a pure, non-blocking posting-coverage assessment after merge; for mid-market-or-larger organizations where observed postings are dominated by one band, `role_plan.md` and the pack report surface `posting-incomplete` with concrete operator actions (`--from-jd`, `--career-url`, `--roles-add`, `--roles-override`, or richer segmented evidence). Reinforces the "postings are primary input" invariant.
- **Segmented career-site input DONE (2026-06-19)**: `primr skills --career-url URL` and MCP `career_urls` accept exact career / ATS URLs as deterministic hiring-source hints. Repeated URLs are structurally validated, fetched through the existing hiring SSRF guard, parsed via direct ATS adapters when possible, merged and deduped before planning, and can be used without `company_url` when only hiring evidence is available. This closes the multi-ATS gap without treating one discovered slice as full enterprise coverage or putting public company facts into the skill body.
- **Authoring quality patterns**: intake/elicitation opening, worked input→output example per skill, explicit scope guardrail, and human checkpoint are now baked into `author_skill.yaml` and guarded by `BODY-QUALITY`. The role-family reference is now generated once from structured role evidence and attached as `references/role-family.md` across every skill in the role family, replacing per-skill role-reference duplication that could drift. Cross-refs #15.
- **Cowork packaging refresh - DONE (2026-06-19)**: refreshed against Microsoft Learn's current Cowork docs. Plugin manifests still cap `agentSkills` at 20 entries, while OneDrive custom skills allow up to 50 user-created skills; companion files are supported up to 20 files / 5 MB each / 10 MB total per skill, and `SKILL.md` is capped at 1 MB. The packager now emits a valid Cowork zip by limiting the manifest/package to the first valid 20 skills while preserving the full unpacked Agent Skills tree, filters over-limit companions locally, and surfaces the cap in the pack report. Cross-refs #15.

### 26. Provider Expansion: API Keys, Billing-Verifiable Host Runners, Gateways, $0 Local Profile

There is no reason the pipeline must be Grok + Gemini; that pairing is the
measured default, not a dependency. Research verified against provider docs
on 2026-06-12 and refreshed for official host-account auth on 2026-06-17;
full catalog, integration traps, and phased delivery plan in
[`docs/design/provider-expansion.md`](docs/design/provider-expansion.md).

- **Phase A (1.x)**: refresh the model registry to the current generations
  (OpenAI gpt-5.5 / gpt-5.4 family, Anthropic claude-fable-5 / opus-4-8 /
  sonnet-4-6 / haiku-4-5) with capability flags the newest models require
  (`supports_temperature` - Fable 5 and Opus 4.7+ reject sampling params;
  tokenizer multiplier; native web-search tool routing for the browse stage
  via OpenAI Responses `web_search` / Anthropic `web_search_20260209`).
  Validate an openai-only and an anthropic-only recipe with one cheap live
  run each, eval-gated, before advertising them. Each recipe must state whether
  it can be the sub-dollar fallback default or only a premium option.
- **Phase A.1**: provider prompt-caching research and cost-safe design. Start
  with Anthropic's current prompt-caching docs, then compare OpenAI, Gemini,
  xAI, Bedrock, Foundry, and Vertex behavior. Ship no new cache controls until
  estimates include cache write/read multipliers, usage records expose cache
  reads and writes per provider, and tests prove caching is disabled when it
  would increase expected cost. No background pre-warming, cache keepalives,
  paid refresh loops, or 1-hour TTL defaults.
- **Phase B**: billing-verifiable host runners for sanctioned agent surfaces.
  This is not "use a consumer plan as an API key." Primr may emit bounded stage
  packets only through official local automation, connector, or agent-skill
  surfaces while keeping the harness in charge of order, spend approval,
  egress, disk writes, and eval. An official automation seam is necessary but
  not sufficient: before public promotion, Primr must either prove whether the
  authenticated host session is plan-backed or require the operator to
  acknowledge that metered API billing may apply. No unofficial proxies,
  browser-session scraping, credential reuse, or repo-owned account assumptions.
  The Codex `fast.source_relevance` adapter is shipped only as an internal/eval
  pilot; public CLI profiles remain `cloud|hybrid`, and its route metadata does
  not prove billing mode. The supported plan-native slice for users with no key
  or GPU is `primr prep` plus the portable `primr-zero` skill. Collection uses a
  hard no-model-call policy, host credentials stay inside the host, and zero
  incremental spend is promised only after the host is verified not to bill API
  usage or overages. Next work remains stage-scoped eval, trustworthy billing
  provenance or acknowledgment, and additional official runner adapters.
- **Phase C**: Bedrock (mantle endpoint, plain API-key auth) and Microsoft
  Foundry (`/openai/v1`, stock openai SDK) as base-URL + key profiles over
  the existing OpenAI-compatible provider - near-zero new code; doctor
  reachability probes; honest docs on gateway gaps (no Anthropic
  web_search through either gateway; batch lag on newest models).
- **Phase D (with 2.0 backend freedom)**: `--inference local` profile.
  Principles: support whatever the user has (selection from the server's
  actual model list, never hardcoded), Mac/Linux/Windows via HTTP only, and
  fit-check before use - model installed AND fits available memory (one-
  token probe, step down to smaller candidates on out-of-memory) AND
  effective context adequate (Ollama's `/v1` silently front-truncates;
  refuse corpus stages on too-small windows). A genuinely free tier,
  shipped with its measured quality delta (best 24 GB-class local models
  scored well below frontier in the June-2026 baseline, but local hardware is a
  moving target) stated next to the $0 API price. Re-run the eval whenever
  desk-side AI capacity materially improves; promotion is data-driven, not
  permanently capped by today's local models.

### 27. Measured Runtime Evolution

Make Primr faster and more defensible without turning language choice into a
rewrite program. The binding design, boundary contracts, benchmarks, adoption
gates, packaging strategy, and stop conditions live in
[`docs/design/runtime-language-boundaries.md`](docs/design/runtime-language-boundaries.md).

Ordered work:

1. **Truthful execution ownership - SHIPPED for local MCP/A2A.** Long MCP/A2A
   jobs run in supervised Python child processes. A job becomes terminally
   cancelled only after the owned worker exits; remote provider work is
   described separately when it cannot be interrupted. Hosted one-job
   containers still need to converge on the same packaged protocol.
2. **Production-shaped baseline.** Add phase wall time, overlap, local parse and
   extraction time, provider wait, peak memory, queue delay, cancellation
   latency, and recovery outcomes. Keep prompt and page bodies out of telemetry.
3. **Pipeline topology first.** Ship #19 overlap and remove duplicated work
   before evaluating another runtime.
4. **Parse-once HTML facade.** Build one versioned, immutable Python analysis
   result that supplies classification, text variants, structured blocks, and
   link candidates while enforcing a bounded input policy.
5. **Optional Rust challenger.** Build an internal PyO3 experiment only after
   the optimized Python reference exists. Ship an optional accelerator only if
   differential behavior is exact, supported-platform wheels exist, base Primr
   remains universal, and the documented p95, memory, corpus, and end-to-end
   gates pass.
6. **Free-threaded compatibility experiment.** Keep standard 3.14 supported.
   Treat 3.14t as a nonblocking compatibility and benchmark lane until the full
   dependency/platform matrix is validated and a material benefit is measured.
7. **Go trigger, not Go plan.** A thin Go admission service becomes eligible
   only after durable multi-user mode exists and measured Python dispatch,
   cold-start, memory, or p99 behavior violates an explicit SLO. Research
   workers and policy remain Python.
8. **Mojo/MAX trigger, not embedded Mojo.** Primr owns no accelerator kernel
   today. Evaluate MAX or another runtime externally through the existing
   OpenAI-compatible endpoint. Embedding requires a measured Primr-owned kernel,
   supportable cross-platform packaging, and license review.

Stop the native experiment if parse-once Python comes within 20 percent of the
candidate, HTML analysis is under 10 percent of measured scrape-stage wall
time, end-to-end `primr prep` collection improves less than 10 percent, output
contracts drift, or a supported platform lacks a wheel. Installing base Primr
must never require a Rust compiler.

---

## Engineering Standards & Toolchain

primr is a mature, shipping PyPI application (`py.typed`, 10,000+ tests, heavy native deps: playwright / patchright / curl_cffi / DrissionPage / pymupdf / pandas), not a greenfield internal service. The standards below are calibrated for that reality: adopt the high-leverage, low-risk discipline; defer code-reshaping behind non-regression ratchets; and decline the maximalist conventions that would churn a stable codebase or hurt downstream consumers. The buckets are explicit so the decisions are durable and don't get re-litigated.

**Decision principle:** modern where it pays, conservative where users feel it.
Python remains the default product and orchestration language, while stable
execution boundaries are language-neutral when measurements justify them.
Track the Python floor to the EOL line and the ceiling to current stable; gate
on reproducibility, supply-chain integrity, correctness, and
production-shaped performance; ratchet type-strictness, complexity, and
verification rather than flipping them globally; prefer ordinary Python
additions; preserve the universal base install; and treat every new native or
service toolchain as a reviewed architectural investment.

### Adopted (load-bearing today)

- Ruff as the single linter (`E/F/W/I/N/UP/B/C4/C90/SIM/RUF/PIE/PT/TCH`), line-length 100. CI hard-fails on lint violations under `src/primr/` and separately checks formatting across `src/` and `tests/`. `target-version = py312` matches the supported floor so local and hosted linting enforce one language baseline.
- mypy (authoritative config in `mypy.ini`, `python_version = 3.12`) on an
  incremental strict ratchet: a relaxed global with complex SDK-bound modules
  `ignore_errors`'d, plus a growing **strict allowlist** of fully verified
  modules. The skill-pack schema, planning, saved-plan, language-projection,
  command grammar, execution-dataflow, eval-validation, Markdown-safety,
  script-safety, and verifier boundaries now require both
  `disallow_untyped_defs` and `disallow_incomplete_defs`, as do credential
  instruction safety, logging, and hiring signals. The allowlist only grows.
  (The former `pyproject.toml` mypy block was dead config and has been removed.)
- Ships `py.typed` - primr is a good typing citizen for downstream importers.
- Property-based tests (Hypothesis) for core invariants; a hard-gated hardcoded-secret scanner in CI.
- No silent `xfail` rot: `xfail_strict = true` (an unexpectedly-passing xfail fails the run); the suite currently uses zero xfail markers.
- SSRF protection on every outbound URL (`primr.utils.security`); content sanitization for prompt-injection defense.
- Single source of version truth enforced by `tests/test_release_integrity.py` (pyproject ↔ `__version__` ↔ ROADMAP "Current State" ↔ `CITATION.cff`).
- No-real-company-data rule across the repo (see `docs/CONTRIBUTING.md`).
- **Anti-slop development contract** (`CLAUDE.md` at repo root, committed - distinct from `AGENTS.md`, which is the *operate-primr* product artifact): names the single seams (async via `run_sync`, console/logging/config/json/atomic-io, the closed HTTP-client set), the no-new-giant-file rule, the verify-current-APIs rule (the stale-API/hallucinated-package guard), the CLI verb convention, and the pre-PR slop check. `CLAUDE.md`/`AGENTS.md` follow the June-2026 split (Claude Code reads `CLAUDE.md` natively; `AGENTS.md` is the cross-tool operate-guide). Enforced, not aspirational: `tests/test_architecture.py` is a deterministic fitness suite carrying a **rise-only per-file line ceiling** (the 13 files >1,000 lines are pinned and may not grow; new files cap at 1,000 - the "no giant file" ratchet), a **single-JSON-library** gate (stdlib `json` only), and an agent-contract-exists check. Async-seam and config-as-leaf gates are deferred pending a small burndown; HTTP is deliberately *not* single-seam-gated (the 5-client multi-tier scraping stack is the design, not drift).
- **Architecture cohesion ratchet - P0 SHIPPED, P1 QUEUED:** the graph-backed
  [`architecture cohesion plan`](docs/design/24-architecture-cohesion-plan.md)
  balances the existing maximum-file-size gate with dependency direction and
  small-module justification. The first slice removed an unused empty module,
  reduced four package-inclusive import-cycle components to two, and made new
  or growing cycle components, empty modules, and unexplained sub-40-line
  modules fail architecture tests. Fresh interpreters verify both import orders
  against the local source tree. The subsequent skill-pack hardening slice
  applied the same boundary test: language lexing and execution dataflow now
  own cohesive security seams, while verifier placement moved into its
  existing asset registry; all six resulting modules stay below the
  approximate 800-line review threshold with directed dependencies and no
  compatibility shims. Evidence: 12,718 tests passed with 86.20
  percent branch coverage on 2026-07-14. Next, burn down the broad core
  component one verified back edge at a time, then merge only single-consumer
  helpers that lack an independent policy, trust, lifecycle, adapter, or test
  boundary.

### In progress - Phase 1: infrastructure & cheap gates

The current active engineering initiative. Each item is verified locally, then landed; findings are triaged (targeted ignore or downgraded to a Phase-2 ratchet) rather than force-passed.

- **Supported-Python window**: `requires-python = ">=3.12"`, EOL-driven - 3.10 reaches EOL Oct 2026 and 3.11 Oct 2027, while 3.12 carries security support to Oct 2028. CI runs a `3.12 / 3.13 / 3.14` **hard** matrix - all three fully supported (the full suite passes on each; validated locally on 3.12 and 3.14 at 8,391 passed, and the native-dep stack installs cleanly on standard 3.14). 3.14 classifier shipped; `.python-version` pins the dev default. Free-threaded 3.14t is not the default runtime or a release gate. Many locked native dependencies now publish `cp314t` artifacts, but Primr has not validated the complete supported platform matrix or demonstrated an end-to-end benefit. Maintain a nonblocking compatibility and benchmark lane when practical; adoption requires a shared-state audit, confirmation that required extensions do not silently restore the GIL, and a material measured throughput or CPU-stage gain.
- **Python-floor consistency gate**: setup, `primr init`, `primr doctor`, container images, AWS Lambda, Azure Functions, dependency guidance, Ruff, CI, and release builds all use the declared Python 3.12 floor. Release-integrity tests derive the runtime assertions from `requires-python`, so these surfaces cannot silently drift apart.
- **uv toolchain + reproducibility**: commit a `uv.lock`; CI installs via `uv sync --locked` so stale project metadata fails before tests; keep the proven setuptools build backend. The former `requirements.txt` / `pyproject` divergence is **resolved** - lower bounds (and the security floors) live in `[project.dependencies]`, `requirements.txt` has been removed, and `pyproject.toml` + `uv.lock` are the single dependency source (no hard upper caps except the intentional `ruff<0.16` / `a2a-sdk<0.4`).
- **Release integrity**: the PyPI workflow uses locked release tooling on Python 3.12, resolves an exact tag, requires that commit to be contained in `main` with a successful main-push CI run, requires a non-empty versioned changelog section, and compares published PyPI filenames and SHA-256 hashes with the built wheel/sdist before creating the GitHub release. Same-tag runs are serialized, strict documentation builds in CI, and release-integrity tests pin these contracts.
- **Security gates in CI**: wire the already-configured `bandit` (`.bandit`) and a dependency-vulnerability audit (`pip-audit`) as gates; attach a dependency manifest (`uv export`) to each GitHub release. Dependency freshness is handled by **manual review-and-bump** (driven by the `pip-audit` + Trivy hard gates surfacing anything actionable), not Dependabot - its auto-PRs were declined for this repo, so no bot-authored commits land. Action/dependency bumps are applied by hand when a gate or release flags them.
- **Coverage baseline + non-regression ratchet**: measured global branch coverage is **83%+** in recent CI (branch mode); CI gates at `--cov-branch --cov-fail-under=81` (margin for platform variance). Ratcheted up from 77 after a focused test push: the coverage job now installs the `a2a` extra so the a2a package is counted (its 165 tests previously ran only in the separate uncovered job), plus broad unit coverage across `research_orchestrator`, `utils.security`, `skill_pack.evidence`, `data.scrape`, `model_eval`, `mcp_server.skill_pack_tools`, the `agentic` modules, `hiring_signals`, the `scraping` helpers, `ai_strategy`, and `mcp_server.server`. A ratchet that only ever rises - not the brief's blanket 95%, which is the wrong target for heavy I/O / LLM glue. The largest remaining gap is `research_agent.py`, now unlocked by the Active Queue #23 split rather than mock-padding the old monster function.
- **pre-commit**: `.pre-commit-config.yaml` running `ruff check` + `ruff format --check` + a fast mypy hook + hygiene hooks; opt-in for contributors, CI stays the hard gate.
- **SLSA build provenance**: `release.yml` generates a signed SLSA provenance attestation (`actions/attest-build-provenance`) for the published wheel + sdist; publishing already uses OIDC trusted publishing (no static credentials). First exercised on the next `v*` tag.

### Phased ratchets (tracked, not yet started - Phase 2/3)

- **mypy strict expansion**: SHIPPED a 17-module strict allowlist in `mypy.ini`,
  including every skill-pack trust boundary touched by the 1.35.3 hardening,
  and consolidated the duplicate config by removing the dead `pyproject.toml`
  mypy block and setting the Python baseline to 3.12. Remaining: keep growing
  the allowlist module by module toward eventual `--strict`, and burn down the
  roughly 45 `ignore_errors` modules. Evaluate Astral `ty` as a fast local
  supplement, not the CI gate while it is preview.
- **One-time `ruff format` reflow** - SHIPPED. Formatted 173 files in a single behavior-preserving commit; `ruff format --check` is now enforced in pre-commit and CI. `E501` stays ignored deliberately: `ruff format` already wraps code lines, so the remaining >100-char lines are strings / URLs / comments where wrapping hurts readability - enforcing E501 there would be churn without value. `target-version = py312` now matches the supported floor; any resulting pyupgrade rewrites are enforced by the normal lint gate.
- **Complexity budget**: add `C901` + `max-complexity` once the documented monsters are refactored (`perform_fast_research` ~1900 lines, `_execute_consulting_research` ~270 lines - Active Queue #23).
- **Parse-don't-validate boundaries**: parse external data once at the system boundary into rich domain types - `NewType` / frozen dataclasses / Pydantic `strict=True, extra='forbid'` - so core logic never receives raw, possibly-invalid primitives. Targets the MCP / API input boundary first (most MCP inputs are JSON-schema-validated today); audit and fill gaps, not a blanket conversion.
- **Explicit invariant hardening + property tests** (chosen over the `deal` library - no new dep, fits primr's exception-based style): the load-bearing invariants are pinned with Hypothesis property tests. SHIPPED: skill-pack roster-cap merge (`_merge_and_cap` / `_drop_excess_to_cap` - partition, cap, observed-first, archetype-dedup, trim-priority), the SSRF guard result-shape (`is_safe_url` always `(True,None)` or `(False,msg)`), and `CostGuardHook` budget rule (`remaining ≥ 0`; BLOCK iff `spent + est > max`). Remaining: the scraping tier-escalation state machine (covered by the stateful-Hypothesis item below).
- **OpenSSF Secure Coding Guide audit**: a one-time pass against the OpenSSF Secure Coding Guide for Python (input neutralization, exception safety, logging hygiene, crypto via `cryptography` only, concurrency), recording conformance + any deliberate deviations. Complements the bandit/pip-audit gates already in CI.
- **Stateful + fault-injection testing**: SHIPPED - a Hypothesis `RuleBasedStateMachine` for the per-host tier circuit breaker (`tests/test_data/test_scraping/test_circuit_breaker_stateful.py`: failures ≤ attempts; any success ⇒ never skipped; skip ⇒ all-failures past threshold), and a fault-injection test that surfaced + closed a real redaction gap - `SecretMaskingFilter` now also masks secrets in **exception tracebacks** (`exc_text`), not just `getMessage()`. Remaining: a `RuleBasedStateMachine` for the job lifecycle, and broader malformed-payload / mid-stream-failure injection at the LLM seam (network/HTTP faults already covered by the recovery-regression suite).
- **Mutation testing on a core slice (`mutmut`)**: TRACKED - run `mutmut` against the highest-stakes modules (`utils/security`, `utils/cost_estimator`, `skill_pack/planner`, `utils/circuit_breaker`) to prove test efficacy beyond line coverage, triage surviving mutants, and harden weak tests. Deferred to a focused session (the value is in running + triaging, not just configuring); never a CI gate (prohibitively slow on the full suite).
- **Per-module coverage targets**: raise the 80% line-coverage target on core modules (`deep_research.py` 72%, `research_agent.py` 30%) as their refactors land.
- **Supply-chain hardening (Sigstore + Trivy + SBOM)** - SHIPPED. On top of the SLSA build-provenance attestation + OIDC trusted publishing: PEP 740 Sigstore attestations made explicit on the publish step; a CycloneDX JSON SBOM (`cyclonedx-py`) + pinned uv manifest attached to each release via a dedicated `sbom/` artifact (kept out of `dist/` so PyPI upload stays clean - also fixed a latent bug where the manifest in `dist/` would have failed the next publish); and a Trivy filesystem scan (vuln + misconfig; secret scanning omitted - it flags the deliberate fake fixtures, and real leaks are hard-gated by the hardcoded-secret property test) in CI, now a **HARD GATE**. Trivy's first real run found + fixed a CRITICAL (secret API keys declared via `ENV` in `openclaw/Dockerfile.primr`) and surfaced KSV-0118 ("default security context allows root") on the Cloud Run manifests. **Resolution (corrected from the original plan):** the runner image is *already* non-root - both `deploy/Dockerfile` and `openclaw/Dockerfile.primr` run `USER primr` (uid 1000), which Cloud Run honors at runtime. The original plan ("add a non-root `securityContext` to the manifest, then drop the ignore") is **infeasible**: Cloud Run *fully managed* does not expose `securityContext` in its v1 YAML schema (the RunV1 SecurityContext type carries only `runAsUser`, documented "Not supported by Cloud Run"), so adding `runAsNonRoot` is rejected by `gcloud run ... replace`. KSV-0118 is therefore a **permanent, platform-dictated false-positive**, justified-ignored in `.trivyignore` with the doc reference, pinned by a regression test (`tests/test_deploy/test_gcp_deployment.py::TestGCPSecurityContext`) that forbids adding a deploy-breaking `securityContext`, and documented inline in both manifests. With the baseline clean (the Trivy step exits 0 after the ignore), the scan was **promoted from signal-only to a hard gate**. Remaining: container image scan if/when images become a shipped artifact; formal SLSA L3 attestation review.
- **Model landscape refresh (May 30, 2026 audit; Sonnet refresh July 1, 2026)**: `claude-opus-4-8`, `claude-sonnet-5`, and `gemini-3.5-flash` registered in `config/models.py`. Sonnet 5 is now the Anthropic balanced default for routing, fallback, and the premium Sonnet writing eval slot; Sonnet 4.6 remains registered for explicit back-compat. Primr estimates Sonnet 5 at its post-intro Sonnet 4.6 rate so the scheduled 2026-09-01 price change cannot become a silent under-estimate, and dry-run token estimates add Anthropic's documented 30% Sonnet 5 tokenizer safety factor whenever a routed bucket uses Sonnet 5. The Anthropic provider now omits sampling parameters for Sonnet 5, preserves adaptive thinking by default, allows explicit adaptive-thinking disable/display config, drops unsupported legacy `thinking.budget_tokens`, rejects unsupported assistant-prefill requests locally for current Claude families, and maps optional `effort` values through `output_config.effort`. The PRO-tier repoint decision is now **wired for eval**: `config/eval_profiles.py` registers a head-to-head pair - `protier-gemini31pro` (reference, $2/$12) vs `protier-gemini35flash` (candidate, $1.50/$9) - same reasoning+utility, only the quality writer differs. **Eval-gated, billed, user-triggered**: run `primr eval <corpus> --profiles protier-gemini31pro protier-gemini35flash` against the standing corpus; repoint the default PRO/quality tier to `gemini-3.5-flash` only if its scorecard matches-or-beats 3.1 Pro at lower cost. It is **not** a writing-tier swap (dearer than `gemini-3.1-flash-lite`). Register `gemini-3.5-pro` (June) and `gemini-omni` once their API slugs go GA. Re-audit before each major eval per "Model Adaptability".

### Repository polish & external credibility (planned)

**Stated intent: elevate primr into a reference-grade repository** - not merely one that works, but one held up as an *example* of how a serious Python project is engineered. This is an explicit, prioritized goal of the maintainer, recorded here so it stays a tracked objective and not an afterthought: the bar is "a repo an examiner would point to as exemplary." The work below is what stands between the current (already strong) state and that bar.

A deliberate finish pass to close the gap between *already rigorous* and *reference-grade* - the small standard files and the **external, measurable** signals a top-tier public repo carries. Scoped tight on purpose: the load-bearing engineering (src layout, `py.typed`, typed ratchets, supply-chain gates, SLSA/SBOM, property/stateful/fault-injection tests) is already adopted above. This is the finish work, not a rebuild - sequence cheap wins first, the docs site last.

- **Retire `requirements.txt` as a second dependency source - DONE.** Deleted; `pyproject.toml` + `uv.lock` are the single dependency source (the per-release SBOM already emits a pinned `uv export` manifest, so no root pinned-manifest is needed). The June-2026 advisory bump proved the file had drifted - it never received the security floors. Stale references updated in the same change: the `test_clean_root` allowlist, the `pyproject` dependency-truth comment, and the `SECURITY_OPS` scan recipe (also corrected `safety` → the actual `pip-audit` gate). Closed the one live "two ways" violation in the tree.
- **OpenSSF Scorecard + badge - DONE** (distinct from the tracked OpenSSF *Secure Coding Guide* audit, a manual code pass): Scorecard is the automated repo-health scorer. `.github/workflows/scorecard.yml` runs `ossf/scorecard-action` on the default branch (push + weekly + on ruleset changes), uploads SARIF to the Security tab, and publishes to the public OpenSSF dataset; the README carries the badge (resolves after the first `main` run). primr should already score well (pinned actions, OIDC trusted publishing, SLSA provenance, the `main-safety` ruleset, hard-gated secret scanning) - Scorecard makes that *externally legible* and ratchets it. Remaining: review the first score and close any cheap findings (e.g. SHA-pin actions if the Pinned-Dependencies check dings tag pins).
- **CodeQL SAST - DONE** as a second, *semantic* security gate beside bandit/Trivy/pip-audit. `.github/workflows/codeql.yml` analyzes Python (`build-mode: none`) on push/PR to `main` + weekly; dataflow/taint findings land as code-scanning alerts in the same Security tab. Signal-only for now (the analyze job succeeds even with alerts); promote to a hard gate once the baseline is triaged clean (the same warn-then-hard path Trivy took).
- **`CITATION.cff`** - machine-readable citation metadata; GitHub renders a "Cite this repository" button and Zenodo/reference managers consume it. Fits primr's research framing and costs almost nothing.
- **`CODE_OF_CONDUCT.md` + `.editorconfig` - SHIPPED.** The Contributor Covenant completes the community-health set, and `.editorconfig` pins indentation, charset, and newline behavior across editors so contributors match the formatter without extra setup.
- **Published documentation site** (mkdocs-material on GitHub Pages) - **SHIPPED (strict)**. `mkdocs.yml` renders the `docs/*.md` corpus as a Material-themed, searchable site with a curated Diataxis nav (Getting started / How-to / Reference / Explanation / Design notes); `.github/workflows/docs.yml` builds it package-free (the `docs` extra only - no native runtime stack) and deploys to GitHub Pages via OIDC on every `docs/**` change. Home and all primary nav pages render clean. README has been tightened into a short project front door, with the detailed mode/cost matrix moved to `docs/RUN_MODES.md`, agent-host guidance moved to `docs/AGENT_INTEGRATION.md`, and detailed local contributor gates moved to `docs/CONTRIBUTING.md`. The root README now leads with use-fit, command selection, cost and budget semantics, and output shape. The deep interior cross-links to root files (`ROADMAP.md`, `CLAUDE.md`) and `deploy/` paths now use stable GitHub URLs; the orphaned eval and design docs are in the nav; and `mkdocs build --strict` is enforced locally and in the Pages workflow so broken links fail the build. Remaining follow-ups: (1) add the `mkdocstrings` API reference off the `py.typed` signatures (deferred to keep the docs build from importing the heavy runtime stack); (2) optional versioned docs (`mike`).

**Deliberate non-additions** (recorded so they aren't re-litigated):
- **Dependabot stays declined** - *validated* by the June-2026 advisory: the `pip-audit` + Trivy hard gates surfaced it and the floors were bumped by hand in `1.32.1`, with no bot-authored commits landing. The gates are the freshness mechanism.
- **`CODEOWNERS` / required-review rulesets stay deferred while single-maintainer** - they would gate the solo author against themselves; revisit on the first external collaborator. The light `main-safety` ruleset (block force-push + branch deletion, no required PR) is already active.

### AI / agent security posture

primr is an **LLM API client + adaptive scraper + MCP/A2A agent** - it does not train, fine-tune, or serve models. So the bulk of adversarial-ML security (training-time poisoning/backdoors, model extraction/stealing, membership/attribute inference, model inversion, watermarking, weight exfiltration, DP-SGD, confidential-compute/enclave serving, certified ℓp-robustness) is **structurally out of scope** - those are "you host the model" concerns, and for primr the model is a commodity API (the pipeline is the asset, not the weights). The real surface is four things: untrusted scraped content flowing into the LLM, LLM output driving downstream actions, the agentic tool surfaces (MCP/A2A), and API-key secrets.

Already shipped: SSRF guard on every outbound URL (`primr.utils.security`), content sanitization for prompt-injection defense, a hard-gated hardcoded-secret scanner, MCP JWT auth, A2A loopback/auth, `CostGuardHook` budget caps, and the supply-chain gates above. The threat model and per-threat control status live in [docs/SECURITY.md](docs/SECURITY.md). Status of the posture work:

- **Indirect prompt-injection hardening** - SHIPPED. `fence_untrusted` (`utils/content_sanitizer.py`) sanitizes + wraps untrusted retrieved content in an explicit "data, never instructions" fence; applied at the previously-unfenced boundaries (insights extraction, the Deep Research dossier + stage-1 website context, discovery notes). Backed by an injection red-team corpus (`tests/security/test_prompt_injection_corpus.py`). Remaining: an LLM-judged injection/jailbreak *eval* scorecard slice to measure evasion over time (deterministic corpus ships now).
- **Output / egress guardrails** - SHIPPED baseline, hardening continuing. `is_safe_url` guards every egress helper; `data/safe_http.py` validates every redirect hop before connecting for `fallback_sources._http_get`, `hiring_signals._http_get`, Wayback CDX/replay fetches, and async citation-resolution HEAD requests; `data/scraping/net.py` validates every redirect hop manually for sitemap and URL-existence checks; `HTTPClient.get/head` does the same while preserving pooled sessions; and the requests, httpx, and curl_cffi scraping tiers validate redirect hops while preserving their tier-specific transports. The "no fetch bypasses the SSRF guard" invariant is locked by `tests/security/test_egress_guardrails.py`; intermediate-redirect migration is complete. The shared safe HTTP seam resolves each hop once and connects to the validated IP literal with the original Host header and HTTPS SNI, closing the DNS-rebind check/connect gap for fallback, hiring, Wayback, and citation HEAD fetches. The tiered httpx scraper uses the same pinned connection artifact while preserving HTTP/2 behavior. Requests-family egress has a shared `PinnedHTTPAdapter`, so pooled `HTTPClient` calls and the tiered requests scraper connect through urllib3 to the validated IP literal while preserving retries, pooling, Host, SNI, and response contracts. The curl_cffi tier now passes vetted per-hop addresses to libcurl through `CurlOpt.RESOLVE` while keeping the logical URL and disabling environment proxy trust. Browser-backed Chromium tiers now pin the initial hostname with Chromium resolver rules, route through a local loopback egress proxy that validates and dials every HTTP request or HTTPS CONNECT target, disable QUIC, and keep Playwright-compatible route guards as defense-in-depth. Remaining SSRF hardening: no known DNS-rebind TOCTOU seam in tracked scraper fetch paths; future browser protocol additions must preserve the proxy/pinning invariant.
- **Secret / log redaction** - SHIPPED. `SecretMaskingFilter` on all log handlers (sink-level, not opt-in) + `mask_sensitive_data` (incl. xAI) applied in `chat_logger` before persist, with atomic writes. Provider patterns: xAI/Google/OpenAI/Anthropic/GitHub/AWS/Slack/JWT. Note: `usage_history.json` and `_run_state.json` are metadata-only (no secrets) - verified, no change needed.
- **Scoped threat model** - SHIPPED. `docs/SECURITY.md` documents the client/scraper/agent threat model (ATLAS-style table T1-T8), shipped controls, residual-risk acceptance, and coordinated disclosure.
- **Agentic trust boundaries (MCP/A2A)** - MCP Stage 1 SHIPPED (T8). MCP now enforces per-tool scopes at dispatch (`read`, `report`, `research`, `delegate`, `admin`) and honors OAuth `scope` plus Entra `scp` JWT claims while keeping legacy `write` tokens compatible for research/delegate but not report reads. A2A authenticated HTTP requests now bind the bearer token into the shared MCP auth context and enforce the matching `read`/`report`/`research` split for estimate, status, health, report reads, research, QA, and cancellation. MCP Stage 2 token approval is shipped for cost-cap-governed execution tools: estimate tools mint short-lived single-use tokens, and execution requires a matching token when server-side cost enforcement is active. A2A `estimate_research` now mints equivalent approval-token fields, and A2A `research_company` requires `max_estimated_cost_usd` plus a matching token when enforcement is active before creating a job. MCP structured invocation audit is shipped for tool calls and resource reads with hashed payloads and admin-readable recent events. MCP resource-read events record normalized resource kind, hashed resource URI, hashed result body, job id when present, granted scopes, duration, and outcome without persisting raw URI query values or resource bodies. A2A skill calls and task cancellation now write matching privacy-preserving audit events with transport, skill name, hashed message/result payloads, hashed caller id, granted scopes, duration, outcome, job id when present, and sanitized estimate/cap metadata without raw message text or approval tokens. MCP and A2A `research_company` execution now also activate the approved cap as a runtime `RunBudget`, so pre-flight approval and mid-run optional-spend checkpoints agree on the networked surfaces. All seven job-scoped consumption resources now cover artifact metadata, compact QA summaries, compact usage/cost summaries, compact source appendix summaries, compact scrape trace summaries, compact verification summaries, and compact calibration summaries without report body content. Trace summaries omit raw trace entries; verification summaries omit raw claims, source URLs, search queries, and explanations; calibration summaries omit raw claims, source URLs, evidence reviews, and rationales. MCP and A2A report reads now use explicit report-scoped paths or skills with bounded output negotiation. Remaining control-plane work: output negotiation that is not report-body specific and non-fast runtime budget visibility. Folds into Active Queue #11 (constrained agent permissions) and #21 (agent control-plane hardening).

Decision principle: secure the surface primr actually has - untrusted input, agent tool use, secrets, supply chain - and explicitly decline model-training/serving security primr will never own.

### Out of scope (rejected, with rationale)

So future contributors don't re-open these:

- **`requires-python >= 3.14` floor** - 3.14 is fully supported and a hard CI gate, but it is not the *floor*: the floor tracks the EOL line (3.12) so users on 3.12/3.13 aren't cut off. Raising the floor to 3.14 would strand them for no benefit.
- **Model-training / model-serving security** (poisoning, extraction, inference attacks, enclaves, certified robustness, weight protection) - primr trains and serves no models; see "AI / agent security posture" above for what *is* in scope.
- **Unmeasured free-threaded adoption (3.14t)** - Primr is predominantly
  scrape- and model-I/O-bound, free-threading does not provide crash isolation
  or durable queueing, and full platform/dependency validation is incomplete.
  Compatibility and benchmark experiments remain welcome; default adoption
  requires measured benefit and a shared-state audit.
- **Pure-Python-only or polyglot-by-default** - both rules optimize for
  ideology instead of Primr. The existing native stack remains load-bearing.
  Prefer Python for additions, but allow an optional, version-locked Rust
  accelerator after the runtime-boundary gates pass. Reserve Go for an
  independently valuable service boundary. Keep Mojo or MAX external until a
  real accelerator workload, supportable distribution, and license review
  justify tighter integration.
- **structlog everywhere / Pydantic-everywhere / dataclass → Pydantic conversion** - high churn, low payoff on a stable codebase that already has a `get_logger` abstraction and uses dataclasses deliberately. Structured output, if wanted, goes behind `get_logger`.
- **NASA Power-of-10 literalism** (forbid recursion, mandate "two asserts per public API", forbid post-`__init__` attributes) - dogmatic for an AI/scraping pipeline. Keep the spirit (complexity budget, boundary validation), not the letter.
- **>95% global branch coverage** - wrong target for I/O/LLM-heavy code; replaced by a measured ratchet + per-module targets.
- **Copier / multi-repo template** - a portfolio-level concern, not primr's. primr can instead serve as the *reference implementation* a template is later extracted from.

---

## Considered for Later

Concepts where the design is sketched but the work isn't queued for the next active cycle - either because they depend on an upstream item, the scope is large, or the value is real but not yet pressing.

### Strategy Delta Mode (incremental re-analysis)

Ongoing monitoring of a company should produce an incremental update against a
prior run rather than a full re-run. Given a previous report + its run state,
diff the freshly gathered signals (recon, hiring, external sources) against the
last snapshot and regenerate only the sections whose evidence materially
changed, emitting a "what changed since <date>" delta artifact alongside the
refreshed report.

- Depends on durable per-company run state and a changed-signal layer; connects
  to vendor-news caching (#13) and the per-user cache (#12).
- Must respect the single-job model - delta mode is still one job, not a daemon.
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
- VLM extraction is more expensive per page - only trigger on high-value pages
- `--vlm-budget N` flag to cap VLM calls per run (default: 10 pages)
- Cost estimator updated with VLM pricing

Scrape Tier Evolution:
- Managed Playwright service fallback (Scrapfly / Firecrawl / similar) when local browser tiers fail - handles infra/scaling edge cases without maintaining headless browser farms
- `MANAGED_SCRAPE_API_KEY` env var, used only after local tiers exhaust retries
- Network interception during Playwright runs: capture underlying JSON APIs (XHR/fetch) during page loads - often yields cleaner structured data than HTML parsing for financials, careers, and dynamically loaded content
- Intercepted API responses stored alongside HTML scrapes in `_raw_scrapes/` for downstream extraction

### Local Inference Mode (Full Pipeline)

Run the full Primr pipeline on local hardware with zero API costs. Initial target: RTX 4090 (24GB VRAM) with Ollama or any OpenAI-compatible local server that passes fit checks. Goal: a working `--inference local` mode that produces useful research output now, while keeping the architecture ready for desk-side AI appliances and workstation-class local models to become genuinely high-quality defaults later. Local starts stage-by-stage; it is promoted by eval, not by optimism or by a permanent "weaker tier" assumption.

What's already built (v1.23.0+):
- Ollama provider via `OpenAICompatibleProvider`, with registered models at zero marginal cost
- Local eval judge capability and named local model lists (`4090-report-race`, `4090-top10`, `installed-starter`) for eval sweeps
- Multi-model judge sweeps comparing every staged non-baseline profile
- Eval artifacts with backend metadata, coverage, and consensus tracking

Three execution profiles:
- `--inference cloud`: current behavior, all AI stages use cloud providers (default)
- `--inference hybrid`: local for high-volume/low-complexity stages, cloud for deep research and trust-critical synthesis - the sweet spot for most users with a GPU
- `--inference local`: all compatible stages on local inference, $0 API cost, runtime and quality measured per hardware profile

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
- Progress display shows which backend each stage is using: `Analysis (local: qwen3:32b)` vs `Analysis (cloud: grok-4.3)`

Validation approach:
- Run the eval harness on the standard company corpus: cloud baseline vs hybrid vs local
- On a 4090-class workstation, run the focused `4090-report-race` stage eval first: local website-summary candidates vs the current sub-dollar cloud baseline, then broaden only if the first pass is close enough to justify more GPU time
- Compare quality, runtime, and trust gate pass rates
- Start with hybrid (local for cheap stages, cloud for hard stages) before attempting full local
- Publish the eval results so the tradeoffs are explicit and data-driven
- If local quality is unacceptable for certain stages, that's a valid outcome for that hardware/model snapshot. Re-test as local models and desk-side AI hardware improve; hybrid mode still saves significant cost in the meantime.

Promotion criteria:
- Trust gate passes: citation coverage, section completeness, confidence-label quality
- Decision-utility within acceptable band of cloud baseline for replaced stages
- No silent fallback: if local can't meet requirements, fail clearly or require explicit hybrid
- Runtime documented: local runs may be slower or faster depending on hardware, but the tradeoff is reported rather than assumed

### Cross-Run Research Memory

Make research compound across runs by persisting extracted claims, citations, and hypotheses in a searchable store. Currently each run starts fresh. If you research 50 companies in the same industry, each run rediscovers the same industry context. Cross-run memory enables meta-research ("show AI strategy evolution across all fintech targets") and better hypothesis quality for repeat verticals. Three staged layers, build top-down:

**Layer 1 - Persistent company tracking (entry point):**
- `primr company track <name> <url>` - creates persistent local profile folder; shipped foundation stores URL, freshness status, retention classification, and bounded body-free run pointers under the per-user data directory
- `primr company list` / `primr company show <name>` - show tracked company profiles; shipped foundation reports tracked freshness once a local run pointer is recorded
- `primr improve --track` - auto-runs improvement pass on stale profiles (configurable staleness threshold)
- Profile folder stores bounded body-free run pointers; automatic pipeline attachment, confidence evolution, and gaps flagged across runs remain planned
- `primr company export <name>` - shipped foundation writes structured MD/JSON with profile metadata, stored run pointers when present, persisted hypotheses, confidence tags, and explicit missing-data gaps; full claim graph waits for layer 2

**Layer 2 - Claim store + priming:**
- SQLite-backed claim store (no external dependencies); each claim stored with company, section, text, confidence, citations, timestamp, embedding
- Embedding via local model (sentence-transformers) or API (Gemini embedding)
- `primr memory search "AI strategy fintech"` to query across all past runs
- `primr memory timeline "Company"` to show how understanding evolved across runs
- When starting a new run, query memory for related companies/industries and inject relevant prior findings as context for the analysis stage

**Layer 3 - Knowledge compounding + narrative evolution:**
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
- CLI is always the primary interface - cloud deployment is for organizational scale, not a replacement
- All research logic runs in the container, unchanged - the cloud layer is queue + storage + auth, not a rewrite
- `primr doctor` works in both local and deployed contexts
- Artifacts are downloadable as the same MD/DOCX/TXT files you get locally

### Post-Research Skill Processing (Anthropic Skills API)

Primr produces a strategic overview, an AI strategy document, and supporting artifacts. What happens next - turning those into a client-ready deliverable, an internal brief, a CRM enrichment payload - is different for every user. Today that workflow is manual: copy the `.md` output, paste it into Claude, run your own skill or prompt, iterate. This feature makes the handoff automatic and generic. Primr ships the plumbing to pipe its artifacts through any user-provided skill via the Anthropic Skills API. The skill itself is entirely the user's business.

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
- New module: `src/primr/ai/skills_api.py` - thin Anthropic Skills API client (upload, invoke, download results)
- New pipeline phase: `post_skill` - runs after report generation and QA, before final output summary
- Skill invocation uses the Messages API with `container.skills` and `code_execution` tool enabled so skills can run bundled scripts
- Multi-turn handling: skills that need multiple turns (pause_turn) are handled automatically
- File download via the Anthropic Files API for any artifacts the skill produces
- Output files land in the same output directory as the research artifacts, with a `_skill/` subfolder
- Cost tracking: skill API calls are tracked in the same usage/cost system as research calls
- `--dry-run` includes estimated skill processing cost (based on input token count of artifacts)

Security considerations:
- Skills run in Anthropic's cloud containers, not on the user's machine - the skill cannot access local files beyond what Primr explicitly sends
- Primr sends only the research artifacts (report, strategy, QA summary) - no API keys, no working directory contents, no scrape traces
- Users are responsible for the security of their own skills
- `primr doctor` warns if a configured skill ID is invalid or inaccessible

### Agentic Interoperability

The framing shift: from tool to role. Primr already does deep company research. The next evolution is positioning it as a composable role in multi-agent workflows - not just something a human runs, but a specialist that other agents can assign work to and build on. Today: "run primr on this company." Next: "assign the account strategist to this deal and let downstream roles build on its findings." The infrastructure (A2A protocol, MCP tools, subagent architecture) is already in place. What changes is the framing and how Primr presents itself to the broader agentic ecosystem.

- Role-aware output shaping: when called via A2A, adapt output to the requesting workflow's needs - a downstream agent building a proposal gets tighter focus on opportunities; one doing risk assessment gets constraints and gaps emphasized
- Extend AgentCard skills with output-format negotiation so callers can request the emphasis they need
- Expert perspective passes become named analyst roles that shape output tone, not just appended report sections
- Workflow composability: Primr as one role in a team, receives a company assignment, produces intelligence, and the next role picks it up - no orchestrator built into Primr; Primr is a specialist, not the coordinator

### Public Release Polish

PyPI publication, the external contribution workflow, and the strict documentation site have shipped. Remaining items for a broader public release push:

- Reduce `setup_env.py` to a thin wrapper around `primr init` once the PyPI install path is the default documented path
- README screen capture / GIF assets (asciinema or vhs recording of a real research run; refreshed DOCX screenshot; updated `docs/images/primr-demo.png`)

---

## Model Adaptability

AI models are released frequently. Primr's strategy for staying current without chasing hype:

1. **Eval harness** - `primr eval` runs a fixed company corpus across profile slots (one slot per provider × model × role-recipe) and generates a scorecard (cost, runtime, citation density, section completeness, confidence-label coverage)
2. **Data-driven adoption** - A candidate recipe is adopted only when it clears all of: total run cost <$1.00 (the budget gate), trust gate passes at or above current baseline, mean decision-utility score ≥ baseline. Soft signals (utility-per-dollar, hallucination rate, drift markers) are tiebreakers among recipes that clear the hard gates.
3. **Model registry** - New models are registered in `src/primr/config/models.py` with pricing, context limits, capability flags, cached-input rates where applicable, and backend/runtime metadata for local inference. Audit the registry before each major eval - registry drift produces wrong scorecards.
4. **No lock-in** - The pipeline stays backend-agnostic by design. Each model is swappable via the eval process rather than hard-coded ideology. The only hard constraint is the budget gate.

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
- [Anthropic's own multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) does NOT use a DAG - it's a simple orchestrator-worker pattern (lead agent spawns 3-5 subagents in parallel, waits, synthesizes). They got 90% speed improvement purely from parallelism, not graph orchestration.
- Multi-agent systems use ~15x more tokens than single-agent ([LangChain State of Agents](https://www.langchain.com/state-of-agent-engineering)), which directly conflicts with Primr's sub-$1-per-run target.
- [Production teams report](https://dev.to/isaachagoel/read-this-before-building-ai-agents-lessons-from-the-trenches-333i) the golden rule: "Can I code this without losing functionality?" Mechanical tasks (scraping, search) should be code, not agent orchestration.
- [Community consensus](https://community.latenode.com/t/coordinating-multiple-ai-agents-for-scraping-validation-and-reporting-does-the-complexity-actually-pay-off/60040): keep simple pipelines simple; multi-agent DAGs only justified for horizontal scaling or dynamic replanning.

**What Primr actually needs:**
The real bottlenecks are sequential page scraping and sequential search queries - both fixable with `asyncio.gather()`, no framework required. The verification agent is a single pipeline stage (now implemented via `--verify`), not a graph node. Phase overlap (external search starting after homepage instead of after all pages) is a scheduling optimization, not an architectural change.

**The decision:** Invest in targeted parallelism and a verification stage rather than a DAG framework. This matches how the best production research systems actually work - simple orchestration with parallel execution where it matters - while keeping Primr maintainable as a solo project.

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

# AI Strategy (default is one recon-informed integrated strategy)
primr "ExampleCo" https://example.co
primr "ExampleCo" https://example.co --platform azure
primr "ExampleCo" https://example.co --platform aws azure       # Multi-platform
primr "ExampleCo" https://example.co --platform ms              # Explicit Azure + private fan-out
primr "ExampleCo" https://example.co --no-ai-strategy

# DNS Intelligence (standalone, no API keys)
primr recon example.co                                          # Quick domain intel
primr recon example.co --json                                   # Structured output
primr recon example.co --full                                   # Everything

# Job management
primr --check-jobs      # Read-only cloud and latest-local status
primr --resume-latest   # Finalize completed or acknowledge terminal cloud jobs
primr --clear-jobs      # Confirm removal of all pending recovery records

# Operations
primr doctor
primr "ExampleCo" https://example.co --dry-run

# MCP Server
primr-mcp --stdio
primr-mcp --http --port 8000

# A2A Server
primr-a2a                                  # Standalone A2A on 127.0.0.1:9000 (auth required)
primr-a2a --host 127.0.0.1 --no-auth       # Local dev only - refuses non-loopback hosts
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
| 1.39.0 | Jul 2026 | **Native MCP 2026-07-28 specification support.** Migrated the MCP server to MCP Python SDK v2 (`mcp>=2.0.0,<3`): one server now serves modern stateless 2026-07-28 clients (automatic `server/discover`, `ttlMs`/`cacheScope` cache hints, `resources/templates/list` for the by_job family, spec-aligned `-32602` unknown-name errors) and legacy `initialize`-handshake clients on both stdio and streamable HTTP. Closes the fresh-install breakage window from the previously uncapped `mcp>=1.28.1` dependency. |
| 1.38.0 | Jul 2026 | **Multi-cloud provider routing: AWS Bedrock and Azure AI Foundry.** Research runs can now route stages through Bedrock (registered, priced Amazon Nova models) and Foundry (operator-declared deployment + pricing). Both are main-process only and refused inside supervised workers, keeping AWS/Azure credentials out of the lower-trust worker boundary; nothing is guessed into the cost gate. |
| 1.37.2 | Jul 2026 | **Latest Gemini models and documentation excellence.** Registers `gemini-3.6-flash` and `gemini-3.5-flash-lite` (July 2026 GA) as available, priced, eval-gateable models without changing any default tier. Brings the full docs surface current to 1.37.x, adds a complete/dated self-enforcing documentation index, and guards every internal Markdown link in CI. |
| 1.37.1 | Jul 2026 | **Zero-cost render parity and dependency hardening.** A standalone `primr render` verb converts any Markdown report to DOCX/TXT with no model calls, so the Primr Zero / host-assisted path ships the same `.md` + `.docx` deliverables as a provider-backed run. Bumps `pyasn1` to 0.6.4 (CVE-2026-59885/59886). |
| 1.37.0 | Jul 2026 | **Truthful strategy fulfillment and complete cost governance.** Integrated, standalone, batch, machine-readable, and monitoring surfaces now share canonical strategy and vendor-refresh outcomes. Estimates, budgets, provider submissions, actual-cost summaries, and partial exits stay aligned across fast, standard, and deep routes. Every AI Strategy path receives bounded cross-industry and observed-stack context, explicit refresh stays opt-in, the active Skills strategy reaches delivery, scrape-only success is unambiguous, and preflight performs no model generation. |
| 1.36.1 | Jul 2026 | **Fail-closed controller and operator contracts.** Strict self-update parsing and confirmation, versioned CLI machine errors, stable strategy snapshots, restart-bound approvals, truthful readiness, secure journal and audit continuity, exact trace ownership, single-replica Azure topology, and fail-closed deployment validation make existing workflows safer and easier to operate. |
| 1.36.0 | Jul 2026 | **Business-first strategy and governed recovery.** AI Strategy 2.1 leads with enterprise performance, value choices, measurable outcomes, non-AI alternatives, complete stack disposition, and workload-specific hybrid economics. Standalone strategy recovery is estimate-first and digest-bound. Batch research and enrichment use separate whole-operation quotes, exact approval, budgets, and retry policy. Atomic workspaces, cross-process leases, publication locks, job-local MCP strategy artifacts, duplicate-interaction prevention, and exact lite output caps harden concurrent execution. |
| 1.35.2 | Jul 2026 | **Acyclic controller boundaries and immutable supply chain.** Shared MCP and A2A consumers now type against a shared cross-transport controller contract, direct strategy requests honor the requested module and canonical Deep Research estimate, and architecture tests prevent concrete server imports outside composition roots. GitHub Actions and Python container bases are immutable pins. Managed-identity Azure stores, quote extraction, finite audit values, retry validation, and standalone exit handling are corrected. |
| 1.35.1 | Jul 2026 | **Truthful worker ownership and estimate-delivery parity.** Local MCP/A2A research now runs in supervised Python child processes with strict lifecycle events, cleanup-confirmed process-tree cancellation, immutable terminal state, lease-time journal reload, exact A2A task ownership, and worker-exit cancellation manifests. Full and premium MCP runs now deliver the single strategy target their estimates price, while unsupported integrated shapes fail before approval. |
| 1.35.0 | Jul 2026 | **Hard-zero host-assisted research and defensive local capacity.** Added `primr prep` for deterministic no-model evidence collection, a wheel-packaged `primr-zero` skill for plan-native synthesis, explicit billing verification, and bounded local-capacity busy guidance. Model-call guards, source provenance, evidence fencing, retry propagation, roadmap parsing, architecture maps, and code-graph freshness were hardened together. |
| 1.34.50 | Jul 2026 | **Durable background jobs and stable operator contracts.** Background Deep Research interactions remain recoverable until their owning output boundary verifies all required artifacts. CLI, MCP, A2A, hosted, and application APIs share a versioned body-free job-status projection. MCP jobs now write to isolated job directories with correlated manifests, while CLI and MCP artifact reads share a bounded newest-first inventory covering deliverables and diagnostics without fuzzy cross-run ownership. |
| 1.34.49 | Jul 2026 | **Recovery status clarity and durable explicit finalization.** `--check-jobs` is now read-only and shows both pending cloud work and the latest local run state. `--resume-latest` owns canonical output finalization and provider-terminal acknowledgement, retains recoverability on empty or partial output, reports mixed failures through nonzero exit codes, and keeps CLI help, dry-run guidance, API examples, and recovery documentation aligned. |
| 1.34.48 | Jul 2026 | **CLI clarity, runtime consistency, and release integrity.** Default dry-runs now end with concise lifecycle guidance, long phases show their supplied duration expectations, and init/doctor help is command-specific. Python 3.12 is enforced consistently across setup, diagnostics, containers, cloud templates, Ruff, CI, and release builds. Releases now require an immutable tag commit on green `main`, locked tooling, non-empty notes, strict documentation, and exact PyPI filename/hash verification. Calibration baseline decision artifacts and inspections also gain body-free gate recommendations, operator decision templates, explicit local/cloud cost policy, and trustworthy readback without applying a gate automatically. |
| 1.34.47 | Jul 2026 | **Report punctuation and baseline measurement.** Final Markdown shipping now normalizes long dash punctuation at the artifact boundary, including the old Deep Research runner path, while preserving URL semantics by percent-encoding long dash code points inside links. DOCX conversion strips the fast-report header metadata line before body rendering so the Strategic Overview date and website appear once. Calibration baseline artifacts and inspections now include an explicit measurement status block, and ready operator-curated multi-report baselines report `measured_operator_curated_multi_report_baseline` with representative coverage, evidence review, and judge agreement checks visible in JSON and Markdown. |
| 1.34.46 | Jul 2026 | **Internal: deep-run finalization seam (no behavior change).** The deep-research run's finalization tail - cost reconciliation, the estimated-vs-actual summary, the report trust row, usage recording, and the job summary - moved out of `research_agent.py` into a dedicated, unit-tested `deep_run_summary` module, mirroring the existing fast-run seam. Output, cost, and usage behavior are byte-identical; the extraction keeps the orchestrator under its size ceiling and gives the deep path a tested home for future trust/cost surfaces. |
| 1.34.45 | Jul 2026 | **Cost-estimate parity and deep-path trust visibility.** `--verify` (post-QA claim verification) is now priced by all three run-approval surfaces - the interactive confirm prompt, `--dry-run`, and the `--budget` pre-flight gate - through one shared estimate-shaping helper, and the confirm prompt now also prices `--grok-tier`. The always-on, judge-free "Label Citations" trust row (how many `(Confirmed)`/`(Reported)` claims cite a resolvable source) is machine-readable in the fast-run QA metrics and now renders on the deep and `--premium` paths too, which previously shipped with no trust summary at all. |
| 1.34.44 | Jul 2026 | **Post-release hardening.** A maintenance bug hunt over the 1.34.43 surfaces closed the last unfenced hiring-signal→prompt boundary (the block inside `insights.txt`, read unfenced by the AI-strategy and workbook-fallback prompts), made the interactive cost-confirm gate price `--strategy-type` documents like `--dry-run` already does, stopped estimates from dropping the AI-strategy cost when a strategy list also names `ai`, and fixed two stale `CostGuardHook` import examples in `docs/API.md`. |
| 1.34.43 | Jul 2026 | **Cost-accounting integrity, prompt-injection fencing, and observability.** A cost-control bug hunt fixed a per-vendor `--budget` overrun, an unlocked token-counter race, quadratic usage-history duplication, phantom DDG search cost, and a `sync_spend` double-count; `--dry-run` and the pre-flight gate now price `--strategy-type` documents. Remaining fast-run scraped-text prompt boundaries are now data-fenced, and hiring signals ride into the CLI Deep Research paths. `show-usage` gains a cost-variability regression signal, `output/` and `working/` self-document, and Windows state writes consolidate on the retrying `atomic_replace` seam. |
| 1.34.42 | Jul 2026 | **Internal agent-profile cost safety for remaining routed utility stages.** Internal/eval `agent` profile unavailability now fails closed for `fast.scrape_summary` and `fast.hiring_signals`: scrape summary writes deterministic source excerpts, hiring signals uses deterministic triage plus posting metadata, both stages record body-free `agent_profile_unavailable` route fallbacks, and neither stage silently calls a cloud LLM when no official host runner qualifies. This profile is not a public CLI surface. |
| 1.34.41 | Jul 2026 | **Sonnet 5, cost guardrails, and metadata-first output reads.** Claude Sonnet 5 is now registered and routed with conservative pricing, adaptive-thinking request shaping, assistant-prefill rejection, and a 30% dry-run tokenizer safety factor. xAI image generation and other hidden-spend paths now require explicit opt-in, security scanning remains clean for current code and secrets, authenticated MCP/A2A output reads stay metadata-first, and full report text moves to explicit report-body read paths with ownership and output negotiation. |
| 1.34.40 | Jun 2026 | **A2A research approval and budget parity.** `estimate_research` now returns the same approval-token fields as MCP `estimate_run`, and A2A `research_company` enforces `max_estimated_cost_usd` plus a matching approval token when cost-cap enforcement is active before any job is created. The accepted cap is propagated into `PipelineRunner` as the runtime budget, and A2A audit events record sanitized estimate/cap metadata without raw URLs, message text, or approval tokens. |
| 1.34.39 | Jun 2026 | **A2A label-calibration summary readback.** Added read-scoped `read_calibration_summary_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/calibration_summary/by_job/{job_id}` compact summary contract as MCP. The skill returns per-label traceability counts, inference source-copy counts, evidence-review count buckets, judge metadata, and judge-agreement metadata without raw claims, source URLs, evidence reviews, rationales, or report body content. |
| 1.34.38 | Jun 2026 | **A2A claim verification summary readback.** Added read-scoped `read_verification_summary_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/verification_summary/by_job/{job_id}` compact summary contract as MCP. The skill returns trust score, claim counts, status counts, first-party downgrade counts, and source-reference counts without raw claims, source URLs, search queries, explanations, or report body content. |
| 1.34.37 | Jun 2026 | **A2A scrape trace summary readback.** Added read-scoped `read_trace_summary_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/trace_summary/by_job/{job_id}` compact summary contract as MCP. The skill returns tier attempts, success rates, latency summaries, block counts, status counts, and validation health without URLs, final URLs, raw trace entries, page content, or report body content. |
| 1.34.36 | Jun 2026 | **A2A source summary readback.** Added read-scoped `read_source_summary_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/source_summary/by_job/{job_id}` compact summary contract as MCP. The skill returns citation counts, missing/unused references, domains, duplicate URL counts, and source rows without report body content. |
| 1.34.35 | Jun 2026 | **A2A usage summary readback.** Added read-scoped `read_usage_summary_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/usage_summary/by_job/{job_id}` compact summary contract as MCP. The skill returns cost, timing, approval, execution, artifact-count, hash, timestamp, and manifest metadata without approval tokens, caller ids, source URLs, manifest artifact paths, or report bodies. |
| 1.34.34 | Jun 2026 | **A2A QA summary readback.** Added read-scoped `read_qa_summary_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/qa_summary/by_job/{job_id}` compact summary contract as MCP. The skill returns QA score, status, count, parse-state, hash, timestamp, and artifact metadata without report body or detailed QA body content. |
| 1.34.33 | Jun 2026 | **A2A artifact metadata readback.** Added read-scoped `read_artifacts_by_job` to the A2A AgentCard and executor, backed by the same ownership-gated `primr://output/artifacts/by_job/{job_id}` compact metadata contract as MCP. The skill returns artifact names, paths, hashes, sizes, timestamps, missing-file state, and types without report body content. |
| 1.34.32 | Jun 2026 | **A2A compact scorecard readback.** Added read-scoped `read_stage_scorecard` to the A2A AgentCard and executor, backed by the same compact `primr://eval/stage_scorecard/{eval_id}` summary contract as MCP. The skill returns route, quality-score, status, blocker, and artifact metadata without prompt bodies, report bodies, quality-source bodies, or raw run-state content. |
| 1.34.31 | Jun 2026 | **Source-relevance eval evidence.** Added `--eval-source-relevance-fixture` to turn labeled source keep-list fixtures into body-free precision, recall, F1, exact-match, and stage quality evidence for `fast.source_relevance` scorecards. The host-agent source packet now also keeps untrusted source snippets in fenced evidence instead of embedding them in host-agent instructions. |
| 1.34.30 | Jun 2026 | **First internal host-agent pilot.** Added an internal/eval-only Codex CLI transport for `fast.source_relevance`. The runner uses official `codex exec`, a read-only sandbox, no approvals, disabled web search/shell-tool config, no persisted history, a JSON-array output schema, and bounded output/time limits. Route metadata records the declared host route category without prompt or response bodies, but it does not prove whether Codex authentication is plan-backed or API-key billed. If no runner qualifies under the internal agent profile, the stage keeps all sources and records `agent_profile_unavailable` instead of silently falling back to cloud API spend. The public CLI remains `cloud|hybrid`. |
| 1.34.29 | Jun 2026 | **Third routed utility stage.** Routed `fast.hiring_signals` through the capability-router bridge, passing the selected model into the existing hiring triage and extraction LLM seams while preserving fail-open behavior and the legacy utility fallback path. The stage now appends capped body-free `stage_routes` records with expected token budget, discovered/produced counts, duration, backend, profile, billing, and fallback metadata, and the hiring-signal artifact helpers are split out to keep the architecture line ratchet green. |
| 1.34.28 | Jun 2026 | **Second routed utility stage.** Routed `fast.scrape_summary` through the same capability-router bridge as source relevance, passing the selected model into the existing summarizer LLM seam and appending capped body-free `stage_routes` records with expected token budget, input page count, output summary count, duration, backend, profile, billing, and fallback metadata. |
| 1.34.27 | Jun 2026 | **Route usage metadata.** Added capped body-free `stage_routes` records in `_run_state.json`, including selected backend, profile, declared billing category, route/fallback reasons, expected stage token budget, latency, source counts, and failure class for the routed `fast.source_relevance` stage. This metadata describes routing policy and does not prove an external host session's actual billing basis. Extracted the relevance filter into `core/source_relevance.py` and lowered the `research_agent.py` architecture ratchet. |
| 1.34.26 | Jun 2026 | **First routed utility stage.** Added `--inference cloud|hybrid`, `ai/stage_routing.py`, and runtime capability-router consumption for `fast.source_relevance`; the stage logs safe route metadata, passes the selected model into `llm()`, and preserves today's role default as fallback. |
| 1.34.25 | Jun 2026 | **Long-context and cache-token estimate honesty.** Added detailed model cost breakdowns for live input, cached input, output, selected tier, and long-context surcharge; populated OpenAI GPT-5.x long-context tier metadata across mini/nano variants; surfaced cached-token estimate fields from historical usage while keeping pre-run cache savings at zero unless observed. |
| 1.34.24 | Jun 2026 | **Gemini provider-owned quota guidance.** Moved terminal Gemini quota copy into `GeminiProvider` through a provider-owned guidance object; the legacy `llm()` path now renders that guidance generically while preserving current operator-facing output and error behavior. |
| 1.34.23 | Jun 2026 | **xAI provider-owned browse seam.** Added `XAIProvider`, which inherits OpenAI-compatible Grok chat behavior and owns the xAI Responses API browse/search surrogate. The legacy `grok_browse_and_summarize` wrapper is now thin compatibility glue that mirrors provider usage into existing run cost counters. |
| 1.34.22 | Jun 2026 | **Production stage capability inventory.** Added `core/stage_inventory.py`, a typed backend-freedom inventory for fast-mode and premium deep-research stages with router-ready roles, reasoning/trust requirements, context and token estimates, accepted backend families, budget checkpoints, current backend ownership, promotion gates, and emitted artifacts. |
| 1.34.21 | Jun 2026 | **Representative baseline selection contract.** Calibration baseline readiness now requires explicit `primr.calibration_pack_selection.v1` metadata with non-empty representative tag requirements before a pack can be marked ready; latest-N manifests report `missing_representative_selection`, and baseline Markdown/JSON inspections surface representative selection readiness directly. |
| 1.34.20 | Jun 2026 | **A2A skill audit parity.** A2A skill invocations and task cancellation now append privacy-preserving audit events to the shared agent audit JSONL with transport, skill name, hashed arguments/results, hashed caller ids, granted scopes, duration, outcome, and job id when present, without storing raw message text, task ids, report paths, URLs, raw results, or caller ids. |
| 1.34.19 | Jun 2026 | **Docs and operator-guidance refresh.** Refreshed agent/operator docs, run-mode references, architecture/config cost guidance, security support policy, and roadmap test-count wording so default xAI plus Gemini costs, default AI Strategy generation, `--no-ai-strategy`, the `1.34.x` supported line, and the 10,000+ test suite are consistent across the repo. |
| 1.34.18 | Jun 2026 | **A2A skill-scope parity.** Authenticated A2A HTTP requests now bind the bearer token into the shared MCP auth context, and A2A skill dispatch enforces `read` for estimate/status/health operations and `research` for research, QA, and cancellation while preserving local loopback behavior and legacy `write` compatibility. |
| 1.34.17 | Jun 2026 | **Inference-label source-copy calibration.** Label calibration now checks cited `(Estimated)` and `(Hypothesis)` claims for deterministic source-copy leakage while keeping those labels exempt from traceability. Calibration sidecars, eval scorecards, CSV output, and baseline readiness artifacts now surface `source_copied` / `inference_source_copied` as report-only signals until a representative baseline defines acceptable behavior. |
| 1.34.16 | Jun 2026 | **MCP resource-read audit logging.** MCP `resources/read` calls now append privacy-preserving audit events with event type, normalized resource kind, hashed resource URI, hashed result body, job id when present, granted scopes, duration, and outcome. `primr://agent/audit/recent` now reports tool-call and resource-read events to local stdio callers and admin-scoped HTTP callers without storing raw URI query values, resource bodies, raw arguments, raw results, raw caller ids, or approval tokens. |
| 1.34.15 | Jun 2026 | **Job-scoped calibration summary resource.** MCP now exposes `primr://output/calibration_summary/by_job/{job_id}` for compact, ownership-gated label-calibration inspection. It summarizes attached `.calibration.json` artifacts and standard sidecars adjacent to owned report artifacts, returning per-label traceability counts, evidence-review count buckets, judge provenance, and judge-agreement metadata without returning raw claims, source URLs, evidence reviews, rationales, or report body content. |
| 1.34.14 | Jun 2026 | **Job-scoped verification summary resource.** MCP now exposes `primr://output/verification_summary/by_job/{job_id}` for compact, ownership-gated claim verification inspection. MCP verification runs attach same-run `verification.json` artifacts to job metadata, including fast-mode runs, CLI fast-mode runs now honor `--verify`, and the resource returns trust score, claim counts, status counts, first-party downgrade counts, and source-reference counts without returning raw claims, source URLs, search queries, explanations, or report body content. |
| 1.34.13 | Jun 2026 | **Job-scoped scrape trace summary resource.** MCP now exposes `primr://output/trace_summary/by_job/{job_id}` for compact, ownership-gated scrape trace inspection. Same-run trace JSONL files are attached to job metadata when present, and the resource returns tier attempts, success rates, latency summaries, block counts, status counts, and validation health without returning URLs, final URLs, raw trace entries, or page content. |
| 1.34.12 | Jun 2026 | **Job-scoped source appendix summary resource.** MCP now exposes `primr://output/source_summary/by_job/{job_id}` for compact, ownership-gated source appendix inspection. It returns citation counts, source definition counts, missing and unused citation numbers, duplicate URL counts, domains, and source URLs without returning report body content. |
| 1.34.11 | Jun 2026 | **Job-scoped usage summary resource.** MCP now exposes `primr://output/usage_summary/by_job/{job_id}` for compact, ownership-gated run manifest inspection. It returns cost, timing, approval, execution, parse, hash, timestamp, and artifact-count metadata without returning company URLs, approval tokens, manifest artifact lists, or full manifest content. |
| 1.34.10 | Jun 2026 | **Job-scoped QA summary resource.** MCP now exposes `primr://output/qa_summary/by_job/{job_id}` for compact, ownership-gated QA artifact inspection. It returns score/status/count fields, parse state, hashes, timestamps, and top-level keys without including detailed report or QA body text. |
| 1.34.9 | Jun 2026 | **Artifact resource documentation refresh.** Agent, API, security, hosted-agent, OpenClaw, bundled skill, artifact pipeline, README, and design docs now consistently direct integrations to `primr://output/artifacts/by_job/{job_id}` as the metadata-first handoff path before report-body reads. |
| 1.34.8 | Jun 2026 | **Job-scoped artifact metadata resource.** MCP now exposes `primr://output/artifacts/by_job/{job_id}` for compact, ownership-gated artifact metadata on completed jobs. It returns file names, paths, sizes, hashes, timestamps, classifications, and missing-file state without report body content, giving agents a safer first artifact-consumption resource. |
| 1.34.7 | Jun 2026 | **Calibration selection inspection.** `primr calibrate --inspect-selection <selection.json>` prints a zero-spend machine-readable inspection of curated selection files before manifest or judge work. The payload reports selected report count, required tags, present tags, missing tags, per-report tags, and next actions, keeping representative coverage as explicit operator metadata. |
| 1.34.6 | Jun 2026 | **Calibration selection templates.** `primr calibrate --pack-selection-template <selection.json>` writes a zero-spend curated selection starter from resolved reports, including the representative tag checklist while leaving report tags empty for operator curation. This makes representative baseline assembly explicit without inferring coverage from report prose. |
| 1.34.5 | Jun 2026 | **Calibration baseline remediation guidance.** `primr.calibration_baseline.v1` artifacts now include structured `next_actions` with missing report and sidecar counts, reason-specific remediation, suggested calibration commands, and an explicit policy to keep `PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY` unset until the pack is ready and the measured floor has been reviewed. Markdown baseline summaries render the same next-action and command guidance for operators. |
| 1.34.4 | Jun 2026 | **Skill-pack verifier cleanup and visible byline removal.** Generated skill-pack fallback verifier scripts now perform a real local structural artifact check instead of shipping placeholder verification code, fast-section future markers now use `[QUEUED]`, and Markdown, HTML, and plain-text report template renderers no longer add visible author or generator attribution lines. |
| 1.34.3 | Jun 2026 | **Calibration baseline readiness and local judge cost safety.** `primr calibrate --baseline-from <pack.json>` writes a zero-spend readiness artifact from a frozen calibration pack, with optional Markdown via `--baseline-md`, explicit not-ready reasons, traceability, evidence-review coverage, judge agreement, and report summaries. Explicit local calibration judging now fails closed on selected-model call failures instead of silently falling back to paid cloud judging; affected reports are recorded as calibration failures and no sidecar is written. |
| 1.34.2 | Jun 2026 | **Budget enforcement, redirect pinning completion, docs front door, and calibration baseline surfaces.** MCP `research_company` now propagates approved cost caps into the active run budget, non-fast Deep Research paths stop optional strategy spend once observed cost reaches the ceiling, and estimates explain runtime enforcement semantics. SSRF redirect hardening now reaches utility HTTP clients, tiered scrapers, curl_cffi, httpx, Google citation HEAD resolution, and browser tiers, including a loopback egress proxy for dynamic Chromium requests. Report validation now surfaces `--verify` contradictions in Report Trust, evidence-review calibration dimensions, cloud-vs-local judge agreement, and local `--pack-manifest` baseline selection. README/MkDocs were tightened into a strict docs front door, agent state moved under gitignored `docs/.agent/`, and resource-lifecycle fixes removed SQLite/event-loop warning leaks. |
| 1.34.1 | Jun 2026 | **Redirect-SSRF hardening.** The fail-open fetch fan-out previously followed redirects and validated only the final URL, so an attacker page could `302` through an internal address (loopback / RFC1918 / link-local / cloud metadata) that was connected before the post-hoc check. A new shared seam `data/safe_http.py` follows redirects manually and revalidates every hop through the central SSRF guard before connecting; `fallback_sources`, `hiring_signals`, and Wayback CDX/replay fetches delegate to it (also removing the duplicated keep-in-sync helpers where they existed). Pinned by hermetic tests that an internal redirect target is validated and never connected to, plus Wayback delegation tests. |
| 1.34.0 | Jun 2026 | **Label-honesty pass (epistemic grounding) and availability-to-backend routing.** New opt-in `PRIMR_LABEL_HONESTY=1` pre-ship pass that downgrades a `(Confirmed)`/`(Reported)` claim to `(Estimated)` when its cited source is judged not to support it: model judgment decides, the downgrade is a mechanical fail-safe rewrite that only lowers confidence, and every other verdict fails open. Closes the June-2026 calibration finding that labels traced to sources only ~0-8% of the time. Default-off (standard run byte-identical), writes a `_label_honesty.json` audit sidecar, never blocks shipping. The capability router can also now consume sanitized provider availability snapshots, and `primr doctor` surfaces the same availability view for configured cloud keys and local OpenAI-compatible services. |
| 1.33.4 | Jun 2026 | **Generic availability collectors and prompt-caching guardrails.** Backend-freedom availability now includes non-secret cloud provider configuration snapshots and generic local OpenAI-compatible service probes using the user's configured runtime, without storing API key values, raw endpoint URLs, account ids, or installed model names. The provider-expansion roadmap now requires Anthropic/OpenAI/Gemini/xAI/gateway prompt-caching research, estimator support for cache write/read pricing, usage accounting, and no paid pre-warming or keepalive behavior before any new cache controls ship. |
| 1.33.3 | Jun 2026 | **MCP invocation audit and provider availability.** MCP tool calls now append privacy-preserving JSONL audit events with hashed caller ids, argument/result hashes, approval-token provenance, cost metadata, duration, job id, and outcome. `primr://agent/audit/recent` exposes recent events to local stdio callers and admin-scoped HTTP callers without storing raw arguments, raw results, or approval tokens. The backend-freedom track also added a pure provider availability contract for quota windows, binding headroom, elapsed resets, stale last-known-good snapshots, and deterministic provider ranking before live quota collectors are wired. |
| 1.33.2 | Jun 2026 | **MCP approval tokens and release hardening.** MCP estimate tools now return short-lived, signed, single-use approval tokens bound to the cost-affecting argument shape; `research_company`, `generate_strategy`, and `generate_skill_pack` require matching tokens when server-side MCP cost-cap enforcement is active. The PyPI release workflow now builds on Python 3.12, matching the package floor, and PyPI metadata uses the modern `Apache-2.0` SPDX expression without deprecated license classifiers. |
| 1.33.1 | Jun 2026 | **Circuit breaker thread-safety.** Made the shared process-global circuit breaker thread-safe: an RLock guards per-key state and all read-modify-writes, and state-change listeners are notified outside the lock (no self-deadlock). The parallel section-writing and strategy pools no longer lose failure-count updates or skew failover/quota bookkeeping. |
| 1.33.0 | Jun 2026 | **Cost-guard, bug-hunt hardening, and Apache 2.0 relicense.** Extended `--budget` to recheck actual spend across all optional stages (research deepening, cross-validation enrichment and contradiction resolution, and multi-strategy generation). Three bug-hunt rounds fixed verified silent-data-loss and rendering defects: internal-source over-deletion, citation/heading false-block on code fences, EDGAR mis-resolution, `--from-plan` crash, leading-indentation collapse, `ref`/`source` citation merge, parenthesized-URL truncation, `References`-heading total truncation, 50K strategy-repair truncation, pipe-line table mis-detection, and math-asterisk italic. Documented the Open Knowledge Format as the findings-interchange shape. Relicensed from MIT to Apache 2.0. |
| 1.32.8 | Jun 2026 | **Skill pack draft quality release.** Released the accumulated `primr skills` quality work: clean Agent Skills frontmatter by default, stronger procedural skill bodies, role-family references, JD and segmented career-board evidence inputs, posting-coverage honesty, Cowork packaging caps, business-role archetypes, and safer archetype matching so weak fuzzy guesses do not steer draft skills into unrelated templates. |
| 1.32.7 | Jun 2026 | **4090 local report race.** Added a focused `4090-report-race` local eval model shortlist and documented the RTX 4090 path as a concrete `$0 API vs sub-dollar API` validation track. The goal is to answer whether a single 24 GB local GPU can clear Primr's trust, utility, provenance, and runtime bar before spending on repeated API report runs. |
| 1.32.6 | Jun 2026 | **Capability routing foundation.** Added the pure stage-level backend router for the backend-freedom workstream: `StageRequirements`, backend capability rows, cloud/agent/hybrid/local profiles, billing-mode guards, ordered route plans, and explicit rejection reasons. It is side-effect-free, fake-backend tested, and not yet wired into full-report execution. Also hardened the OpenClaw TypeScript adapter tests so macOS CI warms `npx --yes tsx` before adapter assertions instead of timing out on first cold start. |
| 1.32.5 | Jun 2026 | **Host-agent runner seam and account-backed roadmap alignment.** Added a bounded host-agent stage-packet contract with explicit billing policy, evidence fencing, normalized runner metadata, and fake-runner tests. Direct provider API keys remained the supported full-run path; official Codex/Claude Code style runners were planned opt-ins. Subsequent policy clarification keeps an embedded runner internal/eval-only until billing provenance is proven or explicitly acknowledged, with `primr-zero` as the supported plan-native path. No unofficial subscription proxies or browser-session scraping are allowed. MCP doctor now recognizes XAI, Gemini/Google, OpenAI, and Anthropic direct provider keys. |
| 1.32.4 | Jun 2026 | **Outbound URL validation hardening.** Released the pending security sweep for hosted image fetches, Google grounding redirects, and path containment, then closed additional SSRF seams across HTTP HEAD, AI preflight website checks, and Wayback replay fetches. Invalid URL ports now fail validation cleanly, post-redirect checks are covered by regression tests, MCP SSRF logs redact userinfo/query/fragment, and local plus remote gates passed with 84.98% branch coverage. |
| 1.32.3 | Jun 2026 | **Provider setup and preflight validation cleanup.** README, ROADMAP, and artifact docs now reflect current standard-run estimates, provider opt-in setup, and coverage wording. `primr init`, `doctor`, and config validation now accept any configured cloud LLM provider key at setup time, while the full-report preflight honestly allows XAI-only execution and fails fast for OpenAI-only or Anthropic-only full runs until the remaining backend-freedom work lands. Dry-run estimates now use the provider-routed standard estimate for OpenAI-only and Anthropic-only setups, price the utility bucket through `Role.UTILITY`, and avoid stale Grok/Gemini premium wording. |
| 1.32.2 | Jun 2026 | **Correctness bug-hunt round with regression tests.** Fixed 14 verified issues across security, scraping, AI provider parsing, output rendering, QA grading, budget accounting, resume handling, and dependency floors. Highlights: out-of-range URL ports no longer crash SSRF validation; modern OpenAI key forms are redacted; trailing-dot numeric IPs hit the SSRF backstop; cross-provider utility calls are mirrored into usage/cost accounting; Anthropic thinking blocks no longer break response parsing; DOCX table separators no longer render as data rows; citation bibliography headings accept trailing words; vision-tier empty-content errors are typed; CSV injection sanitization handles leading whitespace; `azure-identity` floor raised for GHSA-m5vv-6r4h-3vj9. |
| 1.32.1 | Jun 2026 | **Dependency security floors raised.** Trivy and pip-audit flagged June 16 advisories on server-surface dependencies; floors were raised for `starlette`, `python-multipart`, and `cryptography`, and the lockfile resolves to patched versions. No source behavior change; full suite green. |
| 1.32.0 | Jun 2026 | **Anti-brittle doctrine made enforceable + measured quality map; provider/registry audit; research framing (tradecraft 1-3).** **De-brittle (the headline):** committed `CLAUDE.md` dev contract + `tests/test_architecture.py` fitness gates (rise-only line ceiling, single-JSON, contract-exists); `docs/design/agentic-balance.md` standing rule (judgment+eval is the default, a regex content-gate is the FAIL driver) with the ROADMAP header routing every "add a rule / go agentic" decision through it; and three live brittle bugs removed - the scaffolding-leak ship gate demoted to a non-blocking warning, and the internal-label scan + `report_cleanup` made case-sensitive so legitimate lowercase prose ("our internal analysis") is no longer false-blocked or silently deleted. **Eval discipline + findings (~$2.17 spent, pre-registered `docs/design/eval-plan.md`):** ran a label-calibration baseline + three A/Bs - hypothesis-steered collection (tradecraft Step 4) and shared context-curation (`PRIMR_SECTION_EVIDENCE_CURATION`, flag-gated default-off) both evaluated as **washes**; a direct read confirmed the prose is already consultant-grade; the one *measured* quality gap is **epistemic grounding** (labels trace to sources only ~0-8%), which redefines #4 toward a label-honesty pass. Step 5 "argument-derived structure" **descoped** - report structure stays a curated rule (consistency is a deliverable feature). **Research framing (tradecraft 1-3):** `ResearchFraming` (`--purpose/--audience/--decision/--question`) threads operator intent into the workbook + section prompts; Day-1 hypothesis tree; `--plan` pre-spend checkpoint; budget-aware deepening; unframed runs byte-identical. **Providers/registry:** June-13 model-registry audit vs live docs; `primr keys set` covers every wired provider; `doctor` reports a provider usable only with key AND SDK; OpenAI temperature-reject retry; quality-per-dollar bake-off harness with a free-local-judge grader. **Surface/robustness:** `--json` result/estimate output; platform-independent SSRF canonicalization of obfuscated numeric IPs; actionable top-level CLI errors + opt-in shell completion; idempotent installers + `primr update` + passive update notice. Suite green on 3.12/3.13/3.14; every change shipped via CI-green PR. |
| 1.31.0 | Jun 2026 | **Measured epistemics + the orchestrator refactor completed (#23).** **Epistemics (panel-review high tier):** `--verify` is now evidence-based - claims are classified against FETCHED page snippets (capped pages, SSRF-guarded) instead of search-result titles, with source provenance tracked per claim and a deterministic downgrade when support is first-party-only (the company's own domain can no longer corroborate itself); the label-calibration harness (`qa/label_calibration.py`) samples labeled claims per report and audits `(Confirmed)`/`(Reported)` traceability against fetched source text with injectable fetch/judge seams (per-label precision, `no_source` counts against, unfetchable excluded); `primr refine` gained an independent anti-Goodhart acceptance check - each iteration is audited by the calibration harness (an instrument its objective can't see) and reverted when label traceability degrades. **Orchestrator refactor (#23) COMPLETE:** all ten stages of `perform_fast_research` (~1,900 lines) extracted across seven no-behavior-change batches into eleven stage modules (`core/fast_run_*.py`, `insights_assembly.py`), each with a hermetic suite (~110 stage tests + a 17-test coordinator-contract suite pinning the wiring: recovery-executor handoff, session threading, pool-identity mutation chain, early exits); the function is a ~295-line coordinator; extraction surfaced and fixed three latent defects (a stale re-export import, two type lies mypy couldn't see inside the monster); `C901` complexity budget enabled at max-complexity 25 with a shrink-only grandfather list - `perform_fast_research` went from the #1 complexity offender off the list entirely. **CLI hardening:** argparse prefix abbreviation disabled - `primr --qa-` (a typo) used to silently run the full QA summary; invalid flags now exit non-zero (found by the Hypothesis CLI property test). Suite: 9,601 passing, branch coverage 83.9% (ratchet 81), ruff/mypy/bandit/format clean across the line. |
| 1.30.0 | Jun 2026 | **Nine Active Queue items closed, a root-caused production-hang fix, and the 2.0/3.0 version plan.** **Observability & cost (#5, #12, #13):** cached-input tokens plumbed end-to-end (all four providers → session counters → `UsageRecord` → `primr show-usage` per-run/lifetime cache hit rate); actual-cost reporting is cache-aware; `--budget $N` per-run ceiling (pre-flight refusal + mid-run checkpoint that skips strategy generation at the cap); `show-usage` adds per-company history, per-mode totals, observed-mode listing, and a vendor-research freshness table; `primr doctor --scraper-stats` aggregates per-tier success rate / latency p95 / content quality from scrape traces; new per-user cache (`PRIMR_CACHE_DIR` → `%LOCALAPPDATA%\primr` / XDG) with vendor research migrated out of site-packages and shared across invocation dirs (one ~$0.50 DR file per vendor instead of per-folder regeneration); `PRIMR_VENDOR_NEWS_TTL_DAYS` drives all freshness gates; doctor gains a File Locations section. **Resilience (#6, #24 + hang fix):** all 14 production `grok_llm` call sites + the `llm()` utility dispatch route through the circuit-breaker failover seam (quota events fail over across providers instead of killing the run); the remaining inline `get_event_loop()` copies standardize on `run_sync`; and a live run that py-spy showed blocked 3.5h in `ssl.read` exposed that the google-genai SDK has **no default HTTP timeout** - every genai client now carries a finite request timeout (`PRIMR_GEMINI_HTTP_TIMEOUT_MS`, default 5 min) with a repo-invariant test so unguarded constructions fail the suite. **Quality loop (#7, #8, #10, #11):** diminishing-returns detector stops cross-validation regeneration after consecutive low-improvement rewrites (summary persisted to `cross_validation.json`); section/batch writing prompts split into byte-identical cached prefix + volatile suffix for provider prompt caching - validated on a live post-release-candidate run at **73% cache hit rate** with all trust gates PASS at ~split into byte-identical cached prefix + volatile suffix for provider prompt caching (measurable via the new cache-rate plumbing).78 actual cost; `primr refine "Company"` ships the QA iteration loop (Orient→Gather→Consolidate→Prune; stops at `--target-grade`, diminishing returns, or max iterations) writing through the new `ArtifactWriteGuard` - an enforced allowlist that converts "the LLM only edits the report" from policy to `PermissionError` (run state + pipeline dirs denied unconditionally). **Panel-review fixes:** a six-persona product review (consultant, engineer, enterprise architect, eval scientist, non-technical owner, dev-tools reviewer) drove doc-drift fixes (tier count 9, unified test counts), the confidence-label vocabulary defect (samples used bracketed `[Confidence: Inferred]`, outside the canonical `(Confirmed)/(Reported)/(Estimated)/(Hypothesis)` vocabulary the scorer counts), honest QA-score framing (it measures artifact discipline, not factual accuracy - `compute_quality_score()` factored as the single scoring API), MCP cost-cap enforcement defaulting ON for the HTTP transport (serve-time published, `mcp_server/cost_caps.py`), and a README repositioned around the differentiated signal layer (DNS recon + hiring signals → inference). **Docs:** Version Plan (1.x → 2.0 → 3.0 with exit criteria + dependency-ordered build sequence) and five breakdown design docs under `docs/design/`. ~150 new tests across four PRs; every PR shipped with the full 9,400+ suite green and the 81% branch-coverage ratchet held. |
| 1.29.3 | Jun 2026 | **Security hardening + correctness fixes (post-review sweep).** Closed a batch of review findings across the skill-pack, MCP, scraping, and prompt-construction paths. **Skill pack:** bundled-file CONTENT is now validated, not just its path - `scan_bundled_content` runs the injection + hardcoded-path filters over every authored `references/*.md` / `scripts/*.py` and AST-scans Python helpers for process/network/eval/secret/destructive constructs (HARD `SEC-BUNDLE`, fail-closed), with a defense-in-depth drop in the packager; `validate_role` now scans `display_name` / `confidence` / `summary` (emitted into SKILL.md frontmatter) for injection; SEC-INJECT's narrowed run/execute pattern regained coverage of demonstrative-framed command/script injection and literal destructive payloads while keeping the benign-prose guards. **MCP:** `generate_skill_pack` now routes `report_path` / `destination` through the shared `PathValidator` and fails closed when `PRIMR_ENFORCE_MCP_COST_CAPS` is set without a cap; the cost estimate uses the effective roster size (so `roles_override` / `roles_add` can't slip past a cap sized for `roles_count`); server allowed-roots widened to include `working/` for legitimate evidence reuse. **Prompt injection:** `fence_untrusted` neutralizes forged fence delimiters/markers in untrusted content and adds a per-call nonce so the data-fence can't be closed early. **DoS:** bounded the informal-cite scaffolding-scan regex (the one pattern missed when cross-ref/workbook were bounded) to kill quadratic scanning on adversarial markdown. **Correctness:** fixed duplicate-page double-counting on the fallback fan-out timeout path; EDGAR ticker index keeps the primary listing on duplicate-title share classes instead of last-write-wins; trigger-optimizer no longer scores train-on-train when the held-out split collapses. Azure Container App MCP auth + hiring-signal SSRF + PDF metering confirmed already-fixed and pinned with regression guards. ~45 new tests; ruff + mypy + bandit clean. |
| 1.29.2 | Jun 2026 | **Skill pack: four-tier quality overhaul + post-review hardening.** Shipped a staged refinement closing most of the gap to Anthropic's skill-creator workflow (1.29.0/1.29.1 were superseded - 1.29.0 yanked for an inadvertent third-party product name in test fixtures, scrubbed and re-shipped). Tier 1 (default, no added cost): holistic rosters (a plausible reserve guarantees the universal business functions appear alongside named practices; `_merge_and_cap` dedupes plausible against KEPT observed archetypes), task-named skills enforced via the new `NAME-PRODUCT` validator, `DESC-PUSHY` rewritten to count enumerated trigger intents, thin bodies auto-expanded, cross-role overlaps auto-resolved by HARD-finding identity. Tier 2 (`--optimize-triggers`): measured trigger-description optimization against a blind discovery simulator with a held-out split (`skill_pack/trigger_eval.py`). Tier 3 (default): progressive disclosure via `references/*.md`, `scripts/*.py`, `evals/*.json` bundled files (`BundledFile` + `BUNDLE-PATH` validation, written to both the Claude tree and the Cowork zip behind a shared slug-traversal guard). Tier 4 (`--with-evals`): with-skill-vs-baseline behavioral eval with per-skill `evals.json` (`skill_pack/behavioral_eval.py`); validated at +33-78% over baseline on real evidence. SEC-INJECT patterns tightened so benign domain prose no longer drops good roles. New `tests/test_no_brand_leak.py` CI guard (base64-encoded denylist, no plaintext names) blocks real-company/brand tokens in `src/` and `tests/`. ~60 new tests. |
| 1.28.0 | Jun 2026 | **Artifact-pipeline prompt hardening, first-party feed recovery, and an 82% coverage ratchet.** (1) Closed the last Artifact Pipeline Hardening bullet (Active Queue #2): the long-form writer + regeneration prompts now explicitly forbid the internal-scaffolding markers the ship-time gate strips, sourced from a single `qa.report_analyzer.SCAFFOLDING_PROHIBITION_GUIDANCE` constant co-located with `scan_scaffolding_leakage` so the upstream instruction and the downstream gate cannot drift; spliced into both `section_prompts.py` writers and both `research_agent.py` regenerators (the strategy regenerator also gained the plain-text "What to validate:" rule). Parity locked by a deterministic test; runtime tracked by `writer_output_clean` + the eval drift metric. (2) Advanced Verified Page Access (Active Queue #3): `fallback_sources.fetch_feed_content` adds the host's own RSS/Atom feeds as a first-class recovery source in the blocked-origin fan-out - HTML `<link rel="alternate">` autodiscovery + common-path sweep, same-site-filtered (defense-in-depth on the SSRF guard), RSS 2.0 / Atom / RSS 1.0-RDF parsed namespace-agnostically with `defusedxml` (untrusted-XML safe; 5 MB body cap; no new dependency), content:encoded preferred over short teasers, cross-feed item dedup. (3) Global branch coverage 78.65% → **82.05%** (gate ratcheted 77 → 81): the coverage job now installs the `a2a` extra so the 165 a2a tests are counted, plus ~630 new unit tests across `research_orchestrator`, `utils.security` (incl. 100 adversarial SSRF cases - no vuln found), `skill_pack.evidence`, `data.scrape`, `model_eval`, `mcp_server.{skill_pack_tools,server}`, the `agentic` modules, `hiring_signals`, the `scraping` helpers, and `ai_strategy`. |
| 1.27.1 | May 2026 | **Skill pack: operator roster curation.** Four-flag curation surface - `--plan-only` to inspect, `--from-plan` to author from a saved plan, `--roles-add "A, B"` to augment the discovered plan with operator-supplied labels (materialized as `provenance: override`), `--roles-skip "X, Y"` to drop named roles (matches display name or kebab-case slug, exact, case-insensitive). The four compose: `--from-plan PATH --roles-add ...` augments a saved plan; `--roles-skip ...` + `--roles-add ...` swaps roles in a single command. `--roles-override` (existing) bypasses planning entirely; with curation flags it warns and ignores them. Cap-aware merge with operator-priority - plausible roles trim first, then observed, then never operator-added; trimmed entries flow to `gap_flagged`. Name + archetype dedupe between add and discovered (existing role wins to preserve citations; operator can force with skip + add). Empty roster after curation is a hard error. Plan artifact gains "## Operator-Added Roles" and "## Operator-Skipped Roles" sections; pack report shows the operator-added count; CLI completion message reports the full breakdown (observed / plausible / added / skipped). `RolePlan` schema gains `operator_added: list[Role]` and `operator_skipped: list[str]` fields; `RoleEvidence` provenance vocabulary unchanged. MCP `generate_skill_pack` tool gains `roles_add` and `roles_skip` array params. 21 new curation tests covering the full composition matrix and edge cases (cap overflow, dedup, skip-removes-everything hard error, unmatched-skip warning, override+curation mutex). |
| 1.27.0 | May 2026 | **Skill pack: holistic input layer + planning architecture rebuild.** Hiring-signal gathering expanded from 4 ATS providers to 8 (added Workday with corpus-driven URL discovery + bounded blind probing, Workable widget API, Recruitee offers API, Jobvite RSS) plus a new DuckDuckGo web-search fallback that fires when every other path comes up empty. New two-call planning step (`src/primr/skill_pack/planner.py`) replaces the single `discover_roles` call: Call A extracts observed roles backed by posting citations, Call B infers plausible roles backed by research citations + industry classification, archetype-based merge with observed-wins dedupe. `IndustryClassification` (LLM-resolved, no heuristics) drives plausible-role gating - common org-shape roles (Marketing, Sales, Customer Success, Finance, HR) become plausible only when company stage is Mid-market or larger. Inspectable `role_plan.md` + `role_plan.json` artifacts persisted to the working dir; `--plan-only` writes the plan and exits, `--from-plan` authors against a saved plan. `RoleProvenance` enum (posting/research/industry/override) preserved end-to-end; authoring prompt branches grounding emphasis per provenance. `MAX_ROLES` raised 8 → 15 for holistic packs. New CLI flags: `--plan-only`, `--from-plan`, `--roles-override`, `--allow-recon-only`. Hard-failure mode when both posting and research evidence are empty (skill packs are job-posting-first). Pack report now shows observed/plausible split, industry classification, per-role provenance, and citation excerpts. 30+ new tests; ruff clean. |
| 1.26.0 | May 2026 | **Skill pack subsystem (`primr skills`).** A first-class workflow for producing QA-refined Agent Skills artifacts grounded in primr's recon + hiring evidence. Top N roles × M skills (configurable, defaults 5 × 3), archetype-grounded authoring with deep per-company customization, deterministic ASKILL-* validation, capped per-skill refinement loop (default 2 iterations with diminishing-returns stop), and pack-level coherence pass. Emits both an unpacked Claude/Cursor/VS Code `roles/<slug>/SKILL.md` tree and a Microsoft 365 Copilot Cowork sideload `.zip` (manifest v1.28, deterministic UUID v5, programmatic icon generation) from one byte-identical set of SKILL.md files. Multi-provider image generation for the Cowork icon (Grok Imagine → Gemini Imagen → OpenAI image → programmatic Pillow gradient+shape → solid PNG). Authoring prompt + validator encode Anthropic's published authoring discipline: third-person descriptions (DESC-VOICE), "pushy" multi-trigger guidance (DESC-PUSHY), gerund-form names (NAME-GERUND), workflow checklist pattern, Template-pattern Output Format, explain-WHY style, concision-over-padding default. New CLI subcommand `primr skills "<Company>" <url>` and MCP tool `generate_skill_pack`. Legacy `--strategy-type skills` still works and logs a pointer at the new command. Also: vendor-news freshness gate tightened from 14d to 7d (`is_vendor_research_current`). 53 new tests; ruff and mypy clean. |
| 1.25.2 | May 2026 | **Refactor for testability + 50+ new test files.** Extracted helper modules from the three monsters so each pipeline stage is callable in isolation: `core/` got `cli_batch`, `cli_doctor`, `cli_init`, `cli_parser`, `cli_recovery`, `fast_mode_helpers`, `report_cleanup`, `resilience_listeners`, `run_state_io`, `section_parsing`, `section_planning`, `section_prompts`, `strategy_artifacts`; `ai/` got `citation_resolution`, `file_search_resources`, `job_persistence`; plus `output/artifact_validation` and `pipeline/llm_failover`. Coverage on the three monsters: cli.py 78%→82% (passed 80% target); deep_research.py 64%→72%; research_agent.py 27%→30%. Remaining 80% gap on deep_research/research_agent now tracked as roadmap item #20 - needs further orchestrator-level refactors (perform_fast_research ~1900 lines, _execute_consulting_research ~270 lines). CI: re-enabled tests/test_qa and tests/test_output (previously excluded for unknown historical reasons, pass cleanly today). Dead-code removal: utils/defensive.py, utils/memory_profiler.py; utils/retrieve_research.py moved to scripts/. No behavior change. |
| 1.24.4 | May 2026 | **Cost estimator now reflects cross-provider routing.** `_estimate_fast_mode_cost` hardcoded the Grok 4.20-nr writing model and always reported the legacy ~$5.67 number, even when GEMINI_API_KEY was set and the live pipeline correctly routed bulk writing to gemini-3.1-flash-lite. Now defers to `pick_model_for_role(Role.WRITING)` for FAST / HYBRID tiers (still respects `--grok-tier max` as the explicit Grok-everywhere opt-in). Dry-run for the v1.24.x sub-$1 default now correctly reports ~$0.76 baseline / ~$1.01 with 2-vendor AI strategy. Updated stale `routing.py:pick_model_for_role` docstring that still described v1.23.0 behavior. Tests deterministic via env monkeypatch; +3 cross-provider tests. |
| 1.24.3 | May 2026 | Re-release of v1.24.2 - prior release had a `primr.__version__` mismatch with pyproject.toml that broke the integrity check; v1.24.2 was yanked. Same content as v1.24.2. |
| 1.24.2 | May 2026 | (Yanked.) **Artifact drift cleanup (roadmap #1).** Offline scan of 16 recent reports surfaced 240 leaked `[workbook]` markers, 87 `[cross-ref ...]` markers, and 65 bold-wrapped `**What to validate:**` lines. Three root causes fixed at the canonicalization seam: cross-ref strip was colon-only (missed space-separated form, the dominant variant); workbook strip missed bare `[workbook]` and space-separated `[workbook ARDA/prior]`; section normalizer didn't match bold-wrapped validate lines. Verified on five historical reports: 28+51 leaked markers stripped to 0; bold-validate now dedups at the per-section writer boundary. Added `ReportAnalyzer.analyze_scaffolding_leakage()` covering all four categories plus informal `[cite: label]` markers. Bonus: removed a hardcoded vendor-domain URL categorizer (leftover from an early test report); fixed `lstrip("www.")` → `removeprefix("www.")` typo introduced in the same patch. +11 tests. |
| 1.24.1 | May 2026 | Re-release of v1.24.0 with sanitized docs (generic placeholder for eval-target company). |
| 1.24.0 | May 2026 | **Sub-$1 default.** Cross-provider eval picked Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing as the new default - verified at $0.79/run (vs $3.49 on the previous Grok-only hybrid, 4.4x cheaper with trust gate PASS and faster runtime). `pick_model_for_role` uses a provider-aware fallback chain: WRITING/UTILITY prefer GEMINI > OPENAI > ANTHROPIC > XAI; REASONING prefers XAI (Grok 4.3 cached) > GEMINI > OPENAI > ANTHROPIC. OpenAI-only users get gpt-5.4-nano writing + o4-mini reasoning; Anthropic-only users get Haiku + Sonnet. XAI-only stays on legacy ~$4.27/run. Phase 5 enrichment loop got a 5-min per-section deadline (had been unbounded). `grok_llm` extended with cross-provider dispatch. OpenAI provider uses `max_completion_tokens` for gpt-5.x family. Eval profile slot registry in `model_eval.py` + `src/primr/config/eval_profiles.py` with 11 candidate slots. Roles split: PRO -> REASONING + WRITING + UTILITY in `routing.py`; `EvalRecipeOverride` contextvar for per-run recipe forcing. Decision audit in `docs/EVAL_V1_24_0.md`. |
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

**Intended Use**: Primr is designed for legitimate research purposes - understanding companies, evaluating opportunities, and making informed decisions. It is not intended for competitive intelligence gathering that violates laws or ethical standards, mass surveillance, or any malicious purpose.
