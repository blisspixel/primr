# Changelog

All notable changes to Primr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

## [1.22.0] - 2026-05-03

### Grok 4.3 onboarded as flagship reasoning model

- **`grok-4.3` registered** in `ModelRegistry` ($1.25/$2.50 per 1M with $0.20 cached input, 1M context, always-on reasoning, no non-reasoning variant). HYBRID and MAX tiers now route reasoning stages to 4.3; FAST stays on 4.1; legacy `grok-4.20-*` IDs remain registered for resume of in-flight runs.
- **`ModelConfig` extended** with `cost_per_1m_input_tokens_cached`. `calculate_cost` now accepts `cached_input_tokens` and bills the cached portion at the discount rate when the model exposes one.
- **Analysis fallback chain reordered** to `(4.3 → 4.20 → 4.1 → Flash)`.
- **`docs/MODEL_ONBOARDING.md`** added — five-step playbook (verify → register → wire → test → eval-gate) for future model additions, with Grok 4.3 as the worked example. Referenced from `README.md`.

### Utility-tier LLM calls migrated to Grok when XAI_API_KEY is set

- `llm()` now routes scraping summaries / link selection / generic "fast" calls to Grok 4.1-NR when `XAI_API_KEY` is set. Grok 4.1-NR is 2.5x cheaper input and 6x cheaper output than Gemini Flash and lives on the same key the standard pipeline already uses.
- The standard pipeline no longer requires a Gemini key — `XAI_API_KEY` alone is sufficient. `GEMINI_API_KEY` is now only needed for `--premium` mode (or as a utility-tier fallback when no xAI key is set).
- Surfaced when a stalled Gemini Flash link-selection call hung the first 4.3 comparison run; the cross-provider dependency was a historical artifact, not a deliberate design.

### Provider abstraction and routing layer

- **`src/primr/ai/providers/`** new package: `Provider` ABC, `ChatResponse`, `ProviderUnavailableError`, `QuotaExhaustedError`, shared `_UsageAccumulator`, plus three concrete provider classes:
  - `OpenAICompatibleProvider` — single class for any OpenAI-shaped endpoint, parameterized by `base_url` and `api_key_env`. xAI / OpenAI / Ollama / vLLM / llama.cpp all become one-line registry entries.
  - `GeminiProvider` — wraps `google.genai`, translates message lists into `system_instruction` + `contents`, raises `QuotaExhaustedError` on daily limits.
  - `ProviderRegistry` (`registry.py`) — auto-detects which providers are configured from env keys.
- **`src/primr/ai/routing.py`** — single source of truth for "which model for which role". `pick_model_for_role(role)` and `get_provider_for_model(name)` replace the previous scattered `if XAI_API_KEY` checks.
- **`grok_llm`, `ContinuousReasoningSession`, and `llm()`** delegate to providers internally; public signatures unchanged.
- **`primr doctor`** gains a "Providers" section listing each configured provider and the roles it serves.
- **60+ new tests** across `test_providers.py`, `test_provider_registry.py`, `test_routing.py`, `test_grok_client.py`, `test_llm_dispatch.py`. Full suite remains green: 4945 pass, 28 skipped (optional deps).
- **`docs/MODEL_ONBOARDING.md`** gains an "Adding a new provider" section covering OpenAI-compatible vs distinct-SDK cases.

### Eval-gating of the 4.3 default flip

The default flip from 4.20-hybrid to 4.3-hybrid was made on mechanical wiring + vendor recommendation. The full 4-way scorecard sweep (fast / hybrid / max / premium against the 4.20-hybrid baseline) is queued as the first item in the v1.23.0 roadmap.

## [1.21.2] - 2026-04-30

### Output Directory and Recon Platform Defaults

- **`--output-dir` now applies to the research pipeline.** The CLI parser already accepted the flag, but the main research handler did not pass it through. Reports and strategy documents now write to the requested directory across standard, fast, deep, and strategy-only paths.
- **Custom output folders are client-clean.** When `--output-dir` is set, Markdown and DOCX deliverables are written there; TXT mirrors and artifact validation diagnostics are kept under the run diagnostics folder instead of cluttering the client folder.
- **Recon platform selection now uses strong infrastructure signals only.** DNS productivity, email, and certificate signals such as Microsoft 365, Google Workspace, Google Trust, AWS SES, and AWS ACM remain available as recon context but no longer declare a primary AI strategy cloud.
- **Fallback strategy posture is Microsoft + private cloud/NVIDIA.** If recon is unclear or skipped, Primr defaults to `azure private` instead of a generic agnostic or accidental all-cloud posture.

## [1.21.1] - 2026-04-29

### Skill async-monitoring guidance: behavioral, not tool-specific

- **`claude-code/skills/primr/SKILL.md` "Async monitoring"** rewritten as a four-tier preference list, ordered from cleanest to fallback: (1) background launch with completion notification if the host supports it, (2) phase-marker streaming from the log if the host can tail-and-emit, (3) a one-shot sanity check at +5min to catch first-phase failures, (4) honest "I'll check back in about an hour" when no async primitives are available. Same change in `AGENTS.md` (regenerated from the skill body). The earlier copy implied the agent should statelessly wait for the user to ping — the new copy lets the agent pick the lightest mechanism its host actually supports.
- **No prescribed tool names.** The skill describes what the agent should *want* (one event on completion, light progress signals, early-fail catch) without assuming a specific Claude Code tool exists. Hosts with stronger async primitives (Claude Code's `run_in_background`, `Monitor`) get the cleaner experience; portable hosts get the honest "back in an hour" path.
- **Explicit "what not to do"** section: no sub-minute polling, no promised heartbeat cadence the host can't deliver, no treating "still running at 60 minutes" as failure.

## [1.21.0] - 2026-04-29

### Native AI-tool integration: Claude Code plugin, AGENTS.md, per-host clients

primr now ships full agent-host integration mirroring the [recon](https://github.com/blisspixel/recon) layout. After `pip install primr`, AI-tool integration is one paste away — no install subcommand, no JSON-merge tooling, no host-specific glue inside the CLI.

- **`claude-code/` plugin directory** — `.claude-plugin/plugin.json`, `.mcp.json` (registers `primr mcp` over stdio), and `skills/primr/SKILL.md` with three `references/` files. Installable via `/plugin marketplace add blisspixel/primr` then `/plugin install primr@blisspixel-primr` once a marketplace catalog is registered.
- **`clients/` directory** — copy-pasteable MCP snippets for Kiro (`clients/kiro/mcp.json`), Windsurf (`clients/windsurf/mcp_config.json`), Cursor, VS Code + Copilot, and Claude Desktop. Each entry uses the unified `{"command": "primr", "args": ["mcp"]}` shape. README documents per-host file paths plus the macOS GUI-PATH gotcha.
- **`AGENTS.md` at repo root** — same body as `SKILL.md` minus the frontmatter, in the [agents.md](https://agents.md) standard format. Auto-detected by Kiro, Codex, Aider, Jules, and any other tool that loads `AGENTS.md` without configuration.
- **`primr mcp` subcommand** — single-binary entry point matching the recon `recon mcp` pattern. `primr mcp` defaults to `--stdio` (the canonical Claude Code use case); `primr mcp --http --port 8000` still works. The legacy `primr-mcp` console script is preserved for backwards compatibility.
- **SKILL.md is agentskills.io-compliant** — same file works in Claude Code skills, Kiro skills, and any other host that follows the open Agent Skills standard. Encodes the cost gate, async-on-next-turn lifecycle, mode/tier/platform selection heuristics, hypothesis memory pattern, and behavioral deferral rules ("vague research → use the host's web search; DNS-only → shell out to dig").
- **README "Use primr from your AI tool" section** — leads with the one-line "tell Claude to fetch this URL and save the skill" install for users who don't want the full plugin, plus the plugin install commands for users who do.

### Why this shape

We considered (and ruled out) shipping `primr install-skill` and `primr install-mcp` subcommands. The recon project's pattern proved better: skills live at stable raw GitHub URLs, the AI is the installer ("fetch this URL"), and per-host config snippets are copy/paste rather than auto-merged into user-owned files like `~/.claude.json`. Less primr code, no risk of corrupting user config, and the same `SKILL.md` works across Claude Code, Kiro, and any other agentskills.io-compliant host.

## [1.20.4] - 2026-04-29

### Critical: PyPI Wheels 1.20.1 – 1.20.3 Were Missing Data Files

PyPI installs of `primr` 1.20.1 through 1.20.3 crashed on the first research run with `FileNotFoundError: ... primr/config/prompts.json`. Source checkouts were unaffected. The wheel was packaging only `py.typed` because `[tool.setuptools.package-data]` in `pyproject.toml` did not include the JSON or YAML files that live inside the `primr` package.

- **Fix in `pyproject.toml`** — `[tool.setuptools.package-data]` now ships `config/*.json`, `prompts/*.yaml`, `prompts/shared/*.yaml`, and `prompts/strategies/*.yaml` alongside `py.typed`. Local `python -m build` confirms 14 data files plus `py.typed` are present in the resulting wheel (vs. 1 file in the broken builds).
- **Anyone on 1.20.1 – 1.20.3 from PyPI must upgrade**: `pip install -U primr`.

### `--version` Flag

- `primr --version` now prints `primr <semver>`, sourced from `primr.__version__`. Previously argparse rejected the flag with "unrecognized arguments: --version".

## [1.20.3] - 2026-04-29

### Live Key Validation in `primr init`

- **Pasted keys are now verified before they are saved.** `_validate_key_live(provider, value)` in `src/primr/core/cli.py` makes a cheap `models.list()` call against Gemini (`google-genai`) or xAI (`openai` SDK pointed at `https://api.x.ai/v1`). On 401/403/"invalid key" responses, the user sees a clear "rejected by provider" message and is offered up to two retries. Network/transient failures fall back to "could not verify" and let the user retry or skip without a hard block.
- **Replace path for already-configured keys.** Previously, init silently skipped any key whose value looked configured (length ≥ 10), which left no obvious way to recover from a bad paste. Init now shows the masked existing key and asks "Replace? (only if the saved key is wrong) [y/N]" — defaulting to no, so the common path stays one keystroke. Saying yes drops into the same paste-and-validate flow used for first-time setup.
- **No-token validation.** `models.list()` is metadata-only, so verification has zero token cost. Tests covering init/keys flows still pass (99/99).

## [1.20.2] - 2026-04-29

### Friendlier Missing-Key UX

- **No more "open the .env file" prompt for missing keys.** When `primr "Company" url` is run without API keys configured, primr now offers to set them up inline: each key prompt explains *why* it's needed (with cost estimates) and *where to get one* (with a hint about free tiers/credits), and the user pastes the key directly into a hidden prompt. Pasted keys are saved to the per-user config file — no manual `.env` editing.
- **Auto-launches when validation fails.** `src/primr/core/cli.py` now detects validation failures whose only errors are missing API keys, and offers the guided init flow inline if stdin/stdout is a TTY. After keys are saved, the original command continues automatically — users do not have to re-run their command.
- **Updated suggestion copy** in `src/primr/utils/config_validation.py` so the missing-key error leads with `primr init` rather than a "set this in .env" instruction.

## [1.20.1] - 2026-04-26

### PyPI Release Infrastructure

- **`.github/workflows/release.yml`** — release workflow that triggers on tag push (`v*`) and supports manual dispatch from the Actions tab. Two-stage pipeline: `build` verifies the tag version matches `pyproject.toml`, builds sdist + wheel via `python -m build`, runs `twine check` on the distribution metadata, and uploads artifacts; `publish` targets the `pypi` environment so deploys can be gated on review and uses the PyPI trusted-publisher OIDC flow (no API token in repo secrets).
- **PyPI listing metadata already in place**: `pyproject.toml` carries the project URLs (Homepage, Documentation, Repository, Bug Tracker), classifiers (Development Status, Intended Audience, Python versions, Topics), keywords, and MIT license. First PyPI publish picks all of this up automatically.

### Repo Cleanup

- **Root `.md` reduced to `README.md` and `ROADMAP.md`.** `CHANGELOG.md`, `CONCURRENCY.md`, `CONTRIBUTING.md`, and `SECURITY.md` moved into `docs/`. All internal links updated (README, `docs/INDEX.md`, `docs/CHANGELOG.md` self-link, `MANIFEST.in`). `ROADMAP.md` stays at root because the agentic `RoadmapAPI`, MCP `agentic_resources` / `agentic_tools` modules, and the roadmap property tests all hardcode `Path("ROADMAP.md")`.
- **`CLAUDE.md` removed from version control** (added to `.gitignore`, untracked via `git rm --cached`). It is project-level instructions for the local Claude Code workflow — useful locally, noise for anyone reading the public repo who does not use Claude Code. The local file on disk is untouched.
- **ROADMAP entry queued**: when shipping to PyPI, fold `setup_env.py`'s post-install steps (`.env` template creation, Playwright/Patchright browser install, Python version validation, doctor handoff) into a `primr init` subcommand so PyPI installs get the same convenience as source installs without a separate top-level script.

## [1.20.0] - 2026-04-26

### Continuous Reasoning Session — Now Default

After an n=3 paired-comparison pilot (rich/mid/sparse signal density, blind LLM judge), the continuous-reasoning topology is now the default for the standard Grok 4.20 pipeline. Workbook generation (Phase 3) and cross-validation (Phase 5) share a single Grok session so the validator inherits the corpus + workbook reasoning instead of re-reading the report cold.

- **New class `ContinuousReasoningSession`** in `src/primr/ai/grok_client.py`: multi-turn Grok session that preserves message history across stages, with the same retry/error/token-tracking semantics as the existing `grok_llm` helper. One session per primr run.
- **Wired into the standard Grok pipeline**: workbook generation and cross-validation share the session. Section writing (Phase 4) is intentionally unchanged — it stays parallel + fresh-call per section since the topology change is targeted at sequential reasoning handoffs, not parallel sub-agents.
- **`--continuous-reasoning` is on by default.** Pass `--no-continuous-reasoning` to revert to the fresh-call topology for a single run, or set `PRIMR_CONTINUOUS_REASONING=0` (or `false`/`no`/`off`) to disable across all runs on the machine.
- **Lazy session construction with proper `role:system`**: the session is constructed at the workbook stage so the workbook's system prompt becomes a real `role:system` message at session init. (An earlier implementation that folded the system prompt into the first user turn measurably degraded workbook quality during the pilot; the fix is in.)
- **Pilot results that drove the default-change decision**: workbook quality improved 3/3 by blind judge, cross-validation quality improved 2/3 (one close call), final report quality improved 2/3 with one judge call complicated by a separate baseline-pipeline drift issue (now its own ROADMAP entry — "Artifact Drift in the Standard Pipeline"). Quantified drift reduction independent of judge opinion: bare leaked-instruction lines drop from an average of 5.3 per baseline report to 1.0 per continuous report (~81% fewer). Cost delta ranged −3.7% to +32% across runs (average ~+12%); never catastrophic, well under the 40% pre-flip gate.

## [1.19.0] - 2026-04-21

### Hiring-Signal Gathering — Job Posts as Strategic Input

- **New module `src/primr/data/hiring_signals.py`**: after the main-site scrape, Primr discovers a company's open job postings and extracts strategic signals — tech-stack frequency, initiatives, culture cues, notable absences. Job posts are one of the most honest signals a company emits about what they're actually building right now.
- **ATS board APIs first**: Greenhouse (`boards-api.greenhouse.io`), Lever (`api.lever.co`), Ashby (`api.ashbyhq.com`), and SmartRecruiters (`api.smartrecruiters.com`) public job-board endpoints are probed in parallel against slug candidates derived from the company name, website hostname, and any recon-supplied ATS hints. First provider returning a non-empty board wins.
- **HTML careers-page fallback**: when no ATS matches, Primr crawls the company's own careers page via the popup-free external orchestrator, extracts individual posting URLs with a regex scan, and fetches up to 15 bodies.
- **LLM triage**: a small Grok call picks up to 15 postings biased toward senior, engineering, product, data, security, and platform roles; retail, sales SDR, and entry-level roles are down-weighted. Deterministic title-based ranker as fallback when the LLM call fails.
- **Batched LLM extraction**: one Grok reasoning call over the aggregated JD text produces structured JSON — roles & locations, tech-stack frequency map, strategic initiatives, culture signals, locations, hiring volume, notable absences, and a one-paragraph summary. Robust JSON parser handles fenced blocks and prose-embedded JSON.
- **Downstream integration**: extracted signals are threaded into `insights.txt` and the raw external-sources bundle so every downstream phase — gap analysis, workbook, section writing, cross-validation, and Phase 6 strategy — sees them. The rebuild that happens during Phase 2 gap-filling preserves the hiring block.
- **Artifacts persisted to `<working>/_hiring/`**: human-readable `hiring_signals.md`, structured `hiring_signals.json`, full `postings_index.json`, and raw JDs under `raw/jd_NNN_<slug>.txt` for auditability.
- **Fail-open at every stage**: no ATS match and no careers page → the phase records `source: none` and continues. LLM triage or extraction failure → skeleton artifact with counts but empty signals. Companies that don't publish jobs produce reports unchanged.
- **Cost/time**: ~$0.01 and +1-2 min baked into `--dry-run`. Disable entirely with `PRIMR_SKIP_HIRING_SIGNALS=1`.
- **40 new unit tests** at `tests/test_data/test_hiring_signals.py`: slug guessing, HTML stripping, JSON parse robustness, every ATS provider parser (including malformed-response handling), HTML fallback link extraction, triage fallback, extraction coercion, render_for_prompt, end-to-end with fully-mocked HTTP + LLM, env-toggle skip, recon-hint priority, and posting staleness.

### Scraping Resilience — Routing Around Bot Protection

- **Recon moved to external `recon-tool` package**: the embedded `src/primr/recon/` module was deleted; primr now depends on the standalone `recon-tool` (PyPI) so recon work can evolve in its own repo. `primr recon <domain>` CLI shorthand still works via mount of `recon_tool.cli:app`. `dnspython` removed as a primr dependency (owned by recon-tool now).
- **Patchright stealth-browser tier** (`src/primr/data/scraping/stealth_browser.py`): real-Chrome + persistent per-host user-data-dir, bypasses Kasada / Akamai / PerimeterX challenges that blank plain Playwright. Two-phase: headless first, headed only if headless returns a challenge shell.
- **First-time browser install is automatic**: on first scrape that needs Patchright, primr runs `python -m patchright install chromium` in a subprocess with a one-line CLI notice. No manual setup required — baked into install.
- **Global headed-popup budget** (default `0`, opt in per run with `PRIMR_MAX_HEADED_POPUPS=N`): single shared counter across the Patchright stealth tier and the orchestrator's adaptive Playwright retry. At the default of 0 no visible-browser windows ever open; blocked pages go straight to public-data fallbacks. Set `N` to allow up to N total popups for a run. On Linux the budget is automatically treated as 0 unless `DISPLAY` or `WAYLAND_DISPLAY` is set, so headless servers skip the visible-browser path entirely.
- **Shared popup budget covers adaptive retry** (`src/primr/data/scraping/headed_budget.py`): the orchestrator's per-host adaptive browser retry (Playwright / Playwright Aggressive) now consumes the same counter as the Patchright stealth tier, so validation passes can't independently pop a new window per soft-blocked URL.
- **No more host-pinning to headed mode**: `HostState.browser_headed_preferred` sticky flag removed — a successful headed retry no longer locks the host into headed mode for subsequent pages. The host falls through to fallback tiers on later requests.
- **Tiny, minimized, off-screen popup**: when Patchright does go headed, the Chrome window is resized to 320x200 via CDP, minimized to the taskbar, and positioned off-screen before navigation starts. Chrome profile `Preferences` is also sanitized to prevent saved maximized state from overriding.
- **Low-value URL filter**: Glassdoor, Indeed, G2, Capterra, LinkedIn, Twitter/X, Reddit, privacy/terms/cookie paths etc. skip Patchright entirely. No popup possible on those.
- **External-source orchestrator** (`get_external_orchestrator`): web-search validation and discovery scrapes use a popup-free orchestrator (Patchright stripped from tier list). Blocked external sources are silently skipped.
- **Per-host rate-limit memory** (`src/primr/data/scraping/rate_limit_state.py`): 429 responses record a 20-minute cooldown (expandable on repeat) at `logs/rate_limit_state.json`. Subsequent scrapes on cooldown hosts skip live fetch and go straight to public-data fallbacks with a clear user-facing message.
- **Public-data fallback fan-out** (`src/primr/data/fallback_sources.py`): when the origin is blocked or returns zero pages, primr fetches content in parallel from Wayback Machine (CDX API), live sister subdomains (investor./ir./newsroom./press.), SEC EDGAR 10-K filings, Wikipedia REST API, and xAI Grok surrogate synthesis. Fails open — any one source returning content produces a report.
- **Grok surrogate** (`grok_browse_and_summarize` in `primr.ai.grok_client`): uses xAI's Responses API with `web_search` agent tool to fetch URLs or synthesize equivalent content from public sources when direct fetch fails. Returns citations. Opt-out via `PRIMR_DISABLE_GROK_SURROGATE=1`.
- **"Thin website data" threshold widened**: 3 rich fallback pages totalling 60K+ chars no longer trigger the "thin" branch — char volume is the real signal, not page count.
- **Wayback parallelized and bounded**: CDX lookups run concurrently across candidate URLs with a hard 75s total deadline; can't starve the fan-out budget.
- **New tests**: `tests/test_data/test_fallback_sources.py` (12), `tests/test_data/test_scraping/test_rate_limit_state.py` (9). Existing `tests/test_data/test_external_sources.py` patch paths updated for new orchestrator routing.

## [1.18.0] - 2026-04-10

### Recon Integration — DNS Intelligence Pre-Flight
- **Recon as first-class module**: DNS intelligence tool relocated from standalone `recon/` into `src/primr/recon/`, fully integrated into primr's package, linting, type checking, and CI
- **`primr recon` subcommand**: Standalone DNS intelligence lookups — `primr recon acme.com` returns company name, email provider, tenant ID, 156 SaaS service fingerprints, email security score, and 20 signal intelligence rules. Supports `--json`, `--md`, `--services`, `--full`, batch mode, and `primr recon doctor`
- **Auto-platform detection**: Recon runs automatically before scraping, detects cloud platform(s) from DNS fingerprints (AWS Route 53, Azure DNS, GCP DNS, etc.), and auto-selects `--platform` value. Override with explicit `--platform` flag
- **Recon context injection**: Detected services, signal intelligence, email security, auth type, and infrastructure insights injected as context into all strategy types (AI, Security, CX, Data Fabric)
- **`--cloud-vendor` renamed to `--platform`**: Cleaner flag name. `--cloud-vendor` kept as deprecated alias with warning
- **`--platform ms` shorthand**: Expands to `azure private` for the common Microsoft + NVIDIA combo
- **`--skip-recon` flag**: Opt out of DNS pre-flight step
- **`CloudVendor` → `Platform` enum rename**: `CloudVendor` kept as deprecated alias for backward compatibility
- **Pipeline integration**: Recon results logged, recorded in `_run_state.json`, included in `--dry-run` cost estimates ($0.00, ~2-3 seconds)
- **Property-based tests**: 4 correctness properties validated with Hypothesis (platform mapper purity/ordering, formatter section presence/determinism)
- **156 fingerprints**: 13 new detections including Box, Egnyte, Glean (Enterprise AI Search), Datadog, New Relic, PagerDuty, Render, Ping Identity, CyberArk, Lakera (LLM Guardrails), Cato Networks (SASE), Rippling, Deel
- **20 signal rules**: 7 new signals including Zero Trust Posture, AI Security Posture, Shadow IT Risk, Startup Tool Mix, Dual Email Provider, Observability & SRE, File Collaboration Sprawl
- **Certificate transparency**: Passive subdomain discovery via crt.sh integration
- **SRV record detection**: Skype for Business, XMPP, CalDAV, CardDAV
- **Expanded DKIM**: ESP selectors for Mailchimp, SendGrid, Mailgun, Postmark, Mimecast
- **Custom signals**: User-defined signals via `~/.recon/signals.yaml` (additive, mirrors fingerprint extensibility)

## [1.16.0] - 2026-03-23

This release consolidates all work from v1.7.0 through v1.16.0. See [ROADMAP.md](../ROADMAP.md) for the detailed changelog.

### Added
- **A2A Protocol Integration** — Agent-to-agent communication with AgentCard, executor, client, hooks, and 165 dedicated tests
  - Standalone `primr-a2a` server or co-hosted `primr-mcp --http --a2a`
  - `delegate_to_agent` MCP tool for calling external A2A agents
  - Governance hooks: SSRF, cost budget, content sanitization
- **Grok 4.20 Hybrid Tier** — 4.20 reasoning + 4.1 writing as new default, `--grok-tier` flag (fast/hybrid/max), per-model cost tracking, calibrated estimates
- **Private Cloud Vendor** — NVIDIA-first, on-prem AI strategy via `--cloud-vendor private`
- **Agentic Architecture** (v1.7.0) — Hypothesis tracking, subagents (scraper, analyst, writer, QA), hook system (cost guard, SSRF guard, QA gate), orchestrator, research memory, Claude Skills
- **Output Improve Mode** — `primr improve <path>` for deterministic cleanup + optional `--improve-agentic` review pass
- **Versioned Eval Workflow** — `primr --eval` with scorecards, auto-staging, LLM-judge overlays (cloud and local), multi-model sweeps
- **Fast Mode as Default** — Auto-detects Grok 4.1 when `XAI_API_KEY` set; `--premium` for Gemini + Deep Research
- **Startup Banner** — Animated ANSI gradient with 5-layer terminal fallback, cross-platform
- **Adaptive Output Shipping Gate** — Deterministic salvage pass, DOCX pre/post validation, strategy-only reruns
- **Agentic Pipeline** — Adaptive search depth, source quality filtering, dynamic section selection, 2 new report sections (23 total)
- **Deep Research Refactor** — Shared parsing/polling/execution modules, durable async recovery, `--resume-latest`, `--resume-local`
- **Shared AI Error Policy** — Unified sync/async retry classification
- **Scraping Reliability** — Adaptive lazy-load scrolling, strict quality gate, scrape trace logging, external search caps
- **Content Sanitization** (v1.8.1) — Prompt injection protection
- **Interactive Research Mode** (v1.11.0) — Expanded external search, MCP progress subscriptions
- **Multi-Cloud-Vendor AI Strategy** (v1.12.0) — `--cloud-vendor aws azure` for multi-vendor strategy documents
- **Strategy Enrichment** — Cross-validation, evidence search, section regeneration, polish pass, pre-ship repair
- **Gemini 3.1 Pro Preview** — Registered with tiered pricing in ModelRegistry
- **All Strategy Types in Fast Mode** — `--strategy-type` works with Grok pipeline, YAML configs auto-discovered

### Fixed
- **Silent Failure Audit** — 45+ bare `except: pass` and DEBUG-level error handlers upgraded across 23 modules
- **Report Quality** — Duplicate section elimination, coherence pass rewrite (guard threshold 0.92→0.96), contradiction resolution
- **Scraping Robustness** (v1.12.1) — PDF routing, bug fixes
- **SharedBrowser** (v1.11.2) — ETA progress, UI polish
- **Deep Research Progress** (v1.11.1) — Visibility and failure recovery

### Changed
- Default pipeline uses Grok 4.20 hybrid (was Grok 4.1)
- Strategy `max_tokens` raised from 16K to 32K
- Executive summary written last (with full report context)
- Parallel external source search (`ThreadPoolExecutor(max_workers=3)`)
- Framework section word targets raised from 600 to 800

## [1.6.0] - 2026-02-03

### Added
- **Serverless Cloud Deployment** - Full job-based ephemeral execution for AWS, Azure, and GCP
  - Job runner contract with manifest-as-commit pattern
  - Artifact storage abstraction (S3, Blob Storage, GCS)
  - Control plane API (submit, status, cancel, results)
  - Event-driven queue boundary (SQS FIFO, Service Bus, Pub/Sub)
  - State reconciliation for stuck/orphaned jobs
  - Comprehensive SSRF protection (RFC1918, metadata IPs, DNS rebinding)
  - Per-API-key rate limiting and quota enforcement
  - OpenTelemetry tracing with job_id correlation
  - Structured JSON logging with sensitive data redaction

- **AWS (Primary - Production Ready)**
  - Lambda control plane + Fargate job runner
  - ECR lifecycle policy (keep last 10 images)
  - S3 lifecycle rules (IA transition after 30 days, version cleanup)
  - SQS dead-letter queue for failed messages
  - Step Functions with least-privilege IAM roles
  - X-Ray tracing on reconciler Lambda
  - CloudWatch alarms (Lambda errors, DynamoDB throttling, DLQ, queue age)

- **Azure (Reference Implementation)**
  - Container Apps control plane + Container Apps Jobs runner
  - Cosmos DB autoscale (400-4000 RU/s)
  - Managed identity with RBAC roles
  - Application Insights for monitoring and tracing

- **GCP (Reference Implementation)**
  - Cloud Run control plane + Cloud Run Jobs runner
  - Dedicated service account (not default App Engine SA)
  - Least-privilege IAM roles
  - Firestore composite indexes for efficient reconciler queries
  - Cloud Scheduler with dedicated service account for OIDC auth

### Documentation
- docs/CLOUD_DEPLOYMENT.md - Serverless deployment guide
- Updated README.md with cloud deployment section
- Updated ROADMAP.md with v1.6.0 completion

## [1.5.1] - 2026-02-02

### Added
- JWT signature verification (HMAC-SHA256/384/512)
- Security headers middleware
- Request ID tracking
- Rate limit headers
- API key rotation with grace periods
- API key expiration support
- Security utilities module
- Security operations guide

### Fixed
- Removed dead code in deep_research.py
- Fixed Python 3.10 compatibility in MCP server modules
- Added missing COMMON_PAGE_PATTERNS re-export in scrape.py
- Fixed exception chaining in multiple modules
- Fixed ambiguous variable names
- Fixed multiple statements on one line in browsers.py
- Removed duplicate method definitions in qa/integration.py
- Fixed import shadowed by loop variable in type_guards.py

### Changed
- CORS now restricts origins, methods, and headers
- JWT tokens require valid signatures
- Admin tokens hashed before comparison

### Documentation
- docs/SECURITY_REVIEW_2026-02-02.md
- docs/SECURITY_OPS.md

## [1.5.0] - 2026-02-02

### Added
- Typed error hierarchy with automatic retry classification
- Circuit breaker with per-host failure tracking and monitoring
- OpenTelemetry integration for distributed tracing
- Configuration validation with early startup checks
- State machine specifications for tier escalation and job lifecycle
- Unified async/sync boundary handling via `async_utils` module
- 282 property-based tests using Hypothesis

### Changed
- Migrated all error classes to typed error hierarchy
- Legacy error names (AIError, ScrapingError, etc.) now alias to typed classes
- All errors now have `user_message()`, `debug_message()`, and `guidance` attributes
- Error formatting utilities updated to use typed hierarchy

### Documentation
- CONCURRENCY.md - Threading model documentation
- docs/STATE_MACHINES.md - State machine specifications
- docs/MIGRATION.md - Error hierarchy documentation
- docs/INDEX.md - Unified documentation index

## [1.4.1] - 2026-02-02

### Added
- Open Claw integration with skills, workflows, and adapters
- 3 skills: primr-research, primr-strategy, primr-qa
- Lobster workflow for orchestrated research with approval gates
- New MCP resources for Open Claw integration
- Run manifest generation for audit trail
- 163 new tests for Open Claw integration

### Documentation
- docs/OPENCLAW.md - Open Claw integration guide

## [1.3.2] - 2026-01-30

### Added
- **Preflight validation** - Research pipeline now validates all dependencies and API keys BEFORE starting expensive operations
  - Checks Gemini API key validity
  - Checks Google Search API key and engine ID with actual API call
  - Checks Playwright browser installation
  - Fails fast with clear error messages instead of failing mid-pipeline
- **Input validation** - Added comprehensive validation across all modules:
  - AI client: temperature bounds (0.0-2.0), prompt non-empty, thinking level validation
  - HTTP client: URL format validation, timeout bounds checking
  - Config: AIConfig and ScrapingConfig now have `validate()` methods
- **Thread-safe job tracking** - Job tracking file operations now use file locking to prevent corruption from concurrent writes
- **Atomic file writes** - Job tracking uses temp file + rename pattern for crash safety
- **14 new hardening tests** - Tests for input validation, error context, thread safety

### Changed
- **`primr doctor` now tests APIs** - Actually calls Google Search API to verify configuration works, not just that keys exist
- **Better error context** - ScrapingError and SearchError now include HTTP status codes and additional context
- **Improved quota detection** - AI client now catches more quota error patterns (daily limit, rate limit exceeded, etc.)
- **Cleanup retry logic** - Temp file cleanup now retries up to 3 times with delays (helps on Windows with file locks)
- **External source logging** - LLM validation results now logged at INFO level so users can see why sources were accepted/rejected

### Fixed
- **Bare except handler** - Fixed `except:` in qa/command.py to `except Exception:` (was catching KeyboardInterrupt)
- **Silent validation failures** - External source validation failures now logged at WARNING level
- **Empty API response handling** - AI client now properly handles None responses and extracts text from candidates

## [1.3.1] - 2026-01-30

### Fixed
- **Critical: File Search Store billing leak** - Stores were not being deleted because they contained documents. Fixed by implementing two-step cleanup: delete documents first, then delete store. Cleaned up 72 orphaned stores from December 2025.
- **File descriptor leaks** - Fixed 3 instances where `tempfile.mkstemp()` file descriptors were not being closed, which could cause "too many open files" errors over time.
- **Database connection leaks** - Fixed connection leaks in `CompanyMonitor`, `KnowledgeGraph`, and `TenantManager` where new SQLite connections were created on each operation but never closed. Now uses persistent connections with proper `close()` methods.
- **Silent error swallowing** - Improved error logging in browser cleanup code (browsers.py) - bare `except: pass` patterns now log errors at debug level for troubleshooting.
- **Gemini resource cleanup** - `primr doctor` now checks for orphaned File Search Stores and Context Caches that could be incurring costs.

### Added
- `scripts/check_gemini_resources.py` - Utility script to inspect and clean up Gemini resources
  - `--delete-stores --force-empty` to properly delete File Search Stores with documents
  - `--delete-caches` to remove explicit context caches
- File Search Store lifecycle tests (14 tests) to prevent future billing leaks

### Changed
- All File Search Store operations now use try/finally blocks to ensure cleanup
- `FileSearchStoreManager.delete_store()` now properly deletes documents before store
- Improved error logging when store cleanup fails

## [1.3.0] - 2026-01-26

### Added
- Multiple strategy document types (AI, Customer Experience, Security & Compliance, Data Fabric)
- `--list-strategies` command to show available strategy frameworks
- `--strategy-type` option for generating specific strategy documents
- Enhanced build configuration with proper version constraints
- Comprehensive security review and hardening (January 2026)
- XXE protection with secure XML parsing
- SSRF protection with URL validation
- Input validation across all user inputs
- Auto-detection of Python 3.11+ in setup wizard

### Changed
- Python requirement updated from 3.10 to 3.11+
- Updated project description to better reflect company intelligence focus
- Improved dependency management with version constraints
- Enhanced README with clearer pipeline explanation and mode descriptions
- Consolidated scraping logic into single `fetch_web_content()` function
- Better documentation of scraping tier escalation
- Setup wizard now auto-restarts with correct Python version if needed

### Fixed
- Deep Research connection drop recovery with automatic polling
- AI Strategy retry capability with `--ai-strategy-only` flag
- Windows PATH configuration in setup wizard
- Build artifact cleanup for network/sync drives

### Security
- All critical vulnerabilities addressed (see docs/SECURITY_REVIEW_2026-01-21.md)
- Secure XML parser prevents XXE attacks
- URL validation blocks SSRF attempts
- Comprehensive input validation

## [1.2.4] - 2025-12-23

### Added
- Quality assessment system for generated reports
- Automatic QA scoring with color-coded grades
- `--qa` and `--qa-recent` commands for manual QA
- Job recovery system for Deep Research

### Changed
- Improved CLI output with better progress indicators
- Enhanced error messages and user guidance

## [1.2.0] - 2025-12-19

### Added
- AI Strategy document generation with cloud vendor customization
- `--ai-strategy-only` flag for retry capability
- `--cloud-vendor` option (azure, aws, gcp)
- Batch processing with `--csv` flag

### Changed
- Unified pipeline architecture (modes are stopping points, not separate implementations)
- Improved scraping resilience with tier escalation
- Better handling of WAF-protected sites

## [1.1.0] - 2025-11-15

### Added
- Deep Research mode for external source validation
- Vision tier for JavaScript-heavy sites
- Automatic link discovery and selection

### Changed
- Refactored scraping into tiered approach (HTTP → Stealth → Browser → Vision)
- Improved cost estimation with `--dry-run`

## [1.0.0] - 2025-10-01

### Added
- Initial release
- Basic scraping and report generation
- Gemini API integration
- DOCX report output
