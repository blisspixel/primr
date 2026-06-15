# Changelog

All notable changes to Primr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Context engineering (flag-gated, eval-pending)

- **Relevance-ranked section evidence (`PRIMR_SECTION_EVIDENCE_CURATION=1`).** The
  section writer's evidence subset was a blind first-100k-chars truncation of the
  scraped corpus, shared across sections. New `core/context_curation.py`
  `rank_corpus_by_relevance()` instead keeps the *most-relevant* 100k — corpus
  `[Page:]` blocks ranked by term-overlap with the analysis workbook (which
  already distilled the run's themes) — so the budget is spent on signal, not
  scrape order. Shared across sections (preserves the cached prompt prefix from
  the #8 split); deterministic and dependency-free; conservative fallbacks (no
  page markers / empty reference / corpus within budget → prior behavior). It is
  context *assembly* (a relevance rank), not a content gate, and its effect is
  **eval-gated** (`docs/design/eval-plan.md` Eval 4): default off is
  byte-identical, so this ships as an opt-in to be validated by an A/B before any
  default change.
  - **Evaluated (n=1, ~$1.4): WASH — stays default-off.** A/B on a large
    content-dense company (corpus ~360k chars, so curation dropped ~72%): blind
    pairwise grade tied on every section. Relevance-ranking the corpus subset
    doesn't change brief quality even when it fires hard. Combined with the Step 4
    result, this shows quality isn't bottlenecked by *which evidence reaches the
    writer* — it rides on the workbook + writer prompts. The feature stays merged
    but off (no harm; a seam for a future per-section-routing version). Next real
    quality lever: the analysis/section prompts (content depth, #4), not plumbing.

### Artifact shipping — de-brittle (content gates become signals)

- **Leaked-label scan no longer false-blocks legitimate lowercase prose.** The
  forbidden-output scan ran case-insensitively, so a report saying "based on our
  internal analysis" or "in the analysis context of X" was blocked from shipping
  because it matched the internal workbook labels `Internal Analysis` /
  `Analysis Context` / `Internal ROI Model`. Those labels now match
  **case-sensitively** (a new `_FORBIDDEN_LEAKED_LABELS` set), so only the exact
  Title-Case leaked form is caught and ordinary lowercase content ships
  untouched. The bracketed/filename tokens (`[Source:]`, `vendor-research-*.txt`,
  ...) stay case-insensitive — their delimiters never occur in prose, so they
  can't false-block. (agentic-balance: don't gate real content.)
- **Scaffolding-leak detection is now a non-blocking warning, not a ship gate.**
  A leaked internal marker (`[workbook]`, bold `**What to validate:**`, informal
  `[cite: label]`) no longer withholds the polished DOCX; it is surfaced (logged)
  and eval-tracked (`## Artifact Drift`) while the deliverable ships. A regex
  cannot be a quality moat — content quality is enforced upstream (the writer
  prompt) and measured by eval, per the standing rule in
  `docs/design/agentic-balance.md`. Blocking is reserved for what a rule can
  legitimately judge: structural/referential validity (citation resolution,
  duplicate/empty sections) and unambiguous internal-token leaks (raw
  `[Source:]`/`[Workbook:]`). `_validate_output_markdown` gains a `warnings`
  field; the regression corpus asserts the scaffolding fixture ships with a
  warning instead of being blocked.

### Provider setup

- **`primr keys set` now covers every wired provider.** The OpenAI and Anthropic
  providers were wired in `ai.providers` (and `primr doctor` lists them), but
  `primr keys set anthropic` / `openai` failed with "Unknown key" because the
  key-alias map had drifted. Added `anthropic`/`claude` and `openai`/`gpt`
  aliases (so the keys also show in `primr keys list`), plus a test pinning that
  the keys surface never drifts from the provider registry again.

### Security

- **Platform-independent SSRF guard for obfuscated numeric IPs.** The SSRF guard
  now canonicalizes octal / hex / decimal / short-form IPv4 literals itself
  (e.g. `0177.0.0.1`, `0x7f.0.0.1`, `2130706433`, `127.1`) and blocks those
  resolving to loopback/private/reserved/metadata, instead of trusting the OS
  resolver (whose decoding varies - macOS does not decode octal dotted-quad).
  Applied as an additive backstop in `is_safe_url` and the MCP `URLValidator`.

### Machine-readable output

- **`--json` for scripting and agents.** `primr <co> <url> --json` emits a
  single JSON result summary (status, report/DOCX paths, word count) to stdout;
  `primr <co> <url> --dry-run --json` emits the cost estimate as JSON
  (estimate-first). `--json` implies quiet so progress chrome never interleaves
  with the JSON. (`primr recon --json` already existed.)

### CLI robustness

- **Actionable errors instead of raw tracebacks.** An unexpected failure that
  reaches the top of the CLI now prints a short message that routes you to
  `primr doctor`, offers `--verbose` for the full traceback, and links the issue
  tracker, rather than dumping a stack trace. Ctrl-C exits cleanly (code 130,
  "Cancelled") instead of a `KeyboardInterrupt` traceback.
- **Shell tab completion (opt-in).** If `argcomplete` is installed, `primr`
  offers tab completion for its subcommands and flags; enable it with
  `activate-global-python-argcomplete` (or `register-python-argcomplete primr`).
  With `argcomplete` absent it is a no-op, so it adds no dependency.

### Research framing (tradecraft Step 1)

- **Operator framing now shapes the analysis, not just the strategy appendix.**
  A new `ResearchFraming` (purpose, audience, the decision it informs, the core
  question, plus discovery notes) is resolved once and threaded into the
  analysis workbook and every section prompt. Previously `--discovery-notes`
  reached only the final strategy stage. New flags: `--purpose`
  (`general`/`sales_pursuit`/`diligence`/`competitive_intel`/`partnership`),
  `--audience`, `--decision`, `--question`. Unframed runs are unchanged: framing
  renders to an empty prompt block, so prompts stay byte-identical (and the
  cached section-prompt prefix stays cacheable). See
  `docs/design/research-tradecraft.md`.
- **Day-1 hypothesis tree (Step 2).** When a run is framed, primr forms a MECE
  issue tree of build-to-refute hypotheses from the cheap signal layer before
  the analysis workbook, writes it as an inspectable `hypothesis_tree.{md,json}`
  artifact, and prepends it so the workbook is hypothesis-driven. Unframed runs
  are unchanged (no extra cost). Using the tree to steer collection is a later
  step.
- **`--plan` checkpoint (Step 3).** `primr <co> <url> --plan` previews the
  framing, the Day-1 hypothesis tree (from free DNS recon + the cheap signal
  layer), and the proposed report outline, writes `plan.md` +
  `hypothesis_tree.{md,json}` to the working folder, and exits before any
  expensive collection or writing - a pre-run alignment step (no spend beyond a
  cheap Day-1 pass).
- **Budget-aware research deepening (tradecraft Step 4).** Research
  deepening (gap analysis + extra searches/scrapes) is an optional spend stage,
  so it now honors an active `--budget`: when actual LLM spend has already
  reached the ceiling, deepening is skipped and the report ships with the sources
  already collected, recorded in `gap_analysis.md` rather than silently dropped.
  Mirrors the Phase-6 strategy checkpoint - the irreversible act (spend) is
  gated, never the reasoning. This is the budget gate `agentic-balance.md` calls
  the prerequisite for going agentic on collection.
- **Hypothesis-steered gap analysis (tradecraft Step 4).** On a framed run the
  Day-1 hypothesis tree is now built once before the deepening stage and threaded
  into gap analysis, so the extra searches *test under-evidenced branches*
  ("which working hypothesis is unproven, and what evidence would confirm or
  refute it") instead of filling generic data gaps. The same tree is reused by
  the analysis workbook instead of being rebuilt. This is a prompt-level change
  (judgment, upstream) with the GAP/QUERY/PRIORITY output contract unchanged;
  unframed runs keep a byte-identical gap prompt and form no tree.

### Install / update quality-of-life

- **`primr update`** — self-upgrade to the latest PyPI release; detects pipx
  vs pip and runs the right command, reporting before/after version.
  `primr update --check` checks without installing; `-y` skips the prompt.
- **Passive update notice** — a one-line "update available" hint after a
  successful research run and in `primr doctor`. Cached ~24h in the per-user
  dir, fail-safe (never blocks a run), opt-out via `PRIMR_NO_UPDATE_CHECK`.
  Uses `requests` (already a core dep) — bandit-clean, no new dependency.
- **Idempotent installers** — `scripts/install.{ps1,sh}` now upgrade an
  existing install on re-run, verify the result, and surface `primr update`.

### Engineering: anti-slop development contract + fitness gates

- **`CLAUDE.md`** committed at the repo root as the canonical development
  contract (un-ignored from `.gitignore`): the single seams to use, the
  no-new-giant-file rule, the verify-current-APIs rule, the CLI verb
  convention, and the pre-PR slop check. Distinct from `AGENTS.md`, which
  stays the *operate-primr* product guide (a disambiguation header now points
  dev-agents to `CLAUDE.md`); `CONTRIBUTING.md` references it. Follows the
  June-2026 `CLAUDE.md`/`AGENTS.md` split (Claude Code reads `CLAUDE.md`
  natively; `AGENTS.md` is the cross-tool standard). The contract also conforms
  to the repo's own context-map schema, activating six previously-dormant
  `test_context_map_*` property tests (they skipped while no `CLAUDE.md` was
  committed): required sections, negative constraints, verification commands,
  progressive disclosure, and the Quick Start token budget.
- **`tests/test_architecture.py`** — deterministic architectural fitness
  suite: a rise-only per-file line ceiling (14 files >1,000 lines pinned and
  blocked from growing; new files cap at 1,000), a single-JSON-library gate
  (stdlib `json` only), and an agent-contract-exists check. Design doc:
  `docs/design/engineering-excellence.md`.
- **Two monster files split to hold the line ceiling (no behavior change).**
  The June-13 registry audit pushed `config/models.py` past its ceiling, so the
  ~760-line `ModelRegistry` data block (the part you edit when a provider ships
  or retires a model) moved to a new `config/model_registry.py` and is
  re-exported from `config/models.py` — every `from primr.config.models import
  ModelRegistry/ModelConfig/ModelType/GrokTier` keeps working, and adding model
  entries no longer trips the ratchet. The `keys` subcommand handler
  (`_create_keys_parser` + `_run_keys`, ~130 lines) moved out of `core/cli.py`
  into `core/cli_keys.py` (`create_keys_parser` / `run_keys`), matching the
  existing `cli_doctor`/`cli_batch` extraction pattern (Active Queue #23).

### Design docs

- **Decision: report section structure stays a curated rule (tradecraft Step 5
  descoped).** A strategic brief's *shape* is a known, stable thing — consistency
  is a feature of a deliverable, and per-run structural variability trades
  reliability for "rolling the dice." The `company_overview.yaml` scaffold is
  researched/iterated *offline*, not re-derived per run; by Principle 1 it does
  not demonstrably fall short, so it stays a rule. The agentic judgment for #4
  lives in the *content within* sections (depth, insight, Pyramid "so what",
  constrained-evidence reasoning), not in choosing sections. Recorded in
  `agentic-balance.md` (structure carve-out), `research-tradecraft.md` (Step 5),
  and ROADMAP #4.
- `docs/design/research-tradecraft.md` — plan to shift the pipeline's
  *collection and analysis* from collection-first to hypothesis-first (framing,
  Day-1 hypothesis tree, plan checkpoint), keeping the deliverable structure a
  curated scaffold.
- `docs/design/eval-plan.md` — pre-registered, cheapest-first plan for the
  pending paid evals (label-calibration baseline ~$0.10, framed-vs-unframed
  ~$1.58/co, content-depth ~$4-5/co) with exact commands, instruments, and
  go/no-go acceptance criteria, so a paid run yields a decision, not a vibe.
- **Eval result — tradecraft Step 4 (framed-vs-unframed) = NO-GO for default
  (~$0.69 spent, n=1).** First paid A/B confirmed the hypothesis-steering *fires*
  correctly but produced *no quality lift* (blind pairwise wash, slightly
  favoring unframed) at neutral cost — steered collection trades breadth for depth
  and fights the broad fixed structure. Step 4 stays opt-in; not promoted; no
  further collection-steering built on it. The label-calibration baseline also
  ran (~$0.00) and flagged low label-traceability worth re-measuring at scale.
  Next candidate lever recorded: *context curation* at the analysis/writing stage
  (the ~1.9M-token prompts are the real bottleneck), not more collection-steering.
- **Eval finding — epistemic grounding is the one real quality lever (~$2.17
  total spend across all evals).** Label-calibration at scale (3 reports, incl.
  large content-dense briefs with 25+ "Reported" claims): Confirmed 8% / Reported
  0% source-traceability (`unfetchable=0` — sources fetched, claims didn't trace).
  Combined with the two wash results (collection-steering, context-curation) and a
  direct read confirming the prose is already consultant-grade, the data-backed
  map is: prose strong, evidence-plumbing exhausted, **grounding systemically
  deficient**. The next quality work is a label-honesty pass (verify each claim
  against its source, downgrade ungrounded labels — like `--verify`), validated
  for ~$0 via calibration on existing reports. Recorded in `eval-plan.md` Eval 1.
- `docs/design/agentic-balance.md` — the standing rule-vs-judgment decision aid
  (primr targets NVIDIA "Level 2": deterministic control flow, model judgment at
  fixed decision points). Now spells out the failure mode in both directions —
  brittle *content* rules (regex gating quality) are a documented FAIL driver,
  grounded in June-2026 sources (Microsoft red-team taxonomy, the eval-layering
  guides) — and the litmus test for which side of the line a change sits on. The
  ROADMAP header now routes every "add a rule or go agentic" decision through
  this doc and asks contributors to keep it current.
- `docs/design/engineering-excellence.md` — anti-slop enforcement plan.

## [1.29.2] - 2026-06-05

### Skill pack - hardening (post-1.29.1 code review)

- `behavioral_eval.grade_output`: strict verdict coercion - string verdicts
  like "false"/"no"/"0" no longer count as passes (every non-empty string is
  truthy in Python), and grader length-mismatch is logged instead of silently
  skewing the with/baseline delta.
- `refiner.auto_resolve_overlaps`: revert decision now compares HARD finding
  identity, not count - a re-scope that swaps one HARD finding for a different
  one is correctly reverted.
- `validator`: removed generic words (`front`/`door`/`functions`) from the
  NAME-PRODUCT brand set (false-flagged task names like `front-desk-triage`);
  DESC-PUSHY intent counter no longer splits on "and" (which over-counted and
  let thin descriptions pass); SEC-INJECT patterns tightened so benign domain
  prose ("ignore previously assigned licenses", "run the scripts/x.py helper")
  no longer trips the injection guard while real injection is still caught.
- `planner._merge_and_cap`: plausible roles are deduped against the archetypes
  of KEPT observed roles only, so a reserved business-function slot is not lost
  to an observed role the reserve bumps to gap.
- `authoring._parse_bundled_files`: the double-escaped-`\n` normalization runs
  only for markdown references, never for `scripts/*.py` / `evals/*.json` where
  a literal backslash-n is meaningful.
- `pipeline`: failing roles are now dropped BEFORE the opt-in trigger/behavioral
  passes, so no LLM budget is spent on roles that are then discarded.
- `packager`: a shared folder-slug safety check guards both the Claude tree and
  the Cowork zip against path traversal.
- New `tests/test_no_brand_leak.py` CI guard fails the build if a denylisted
  real-company / third-party brand token appears in `src/` or `tests/`.

## [1.29.1] - 2026-06-05

Supersedes 1.29.0 (yanked): removed an inadvertent third-party product name
from internal test fixtures and one prompt example. No functional change.

### Skill pack - four-tier quality overhaul

A staged refinement of the skill-pack pipeline that closes most of the gap
against Anthropic's skill-creator workflow (see ROADMAP #15). Tiers 1 and 3
are on by default at no extra LLM cost; Tiers 2 and 4 are opt-in measured
proof loops behind CLI flags.

**Tier 1 — roster + authoring quality (default, no added cost):**

- **Holistic rosters.** `plan_plausible_roles.yaml` now produces a roster
  spanning BOTH the company-specific named practices/services (highest
  priority — a flagship branded offering named in the research always earns a
  role) AND the universal functions every Mid-market+ org runs (Sales,
  Marketing, Customer Success, HR/People, Operations, Finance,
  Legal/Compliance, IT). `_merge_and_cap` reserves a fraction of the roster
  (`PLAUSIBLE_RESERVE_FRACTION`, default 0.4) for plausible org-shape roles so
  a one-function posting set can't crowd them out; observed (posting) roles
  still take the leading slots and win ties, and reserve-displaced observed
  roles flow to `gap_flagged` rather than being silently dropped.
- **Task-named skills, not product names.** `author_skill.yaml` forbids bare
  product/feature titles (`azure-front-door`, `aks`); the skill names the
  capability the product is used for (`configuring-edge-traffic-routing`),
  product in the body. New SOFT validator `NAME-PRODUCT` flags violations.
- **`DESC-PUSHY` counts trigger intents, not keywords.** Previously counted
  hits from a fixed verb lexicon and false-flagged well-formed enumerations
  using verbs outside the list (perform / prepare / conduct). Now counts the
  distinct enumerated intents after the trigger phrase, broadened verb set as
  a fallback only.
- **Thin bodies are refined, not just flagged.** `refine_role` treats a
  too-short body (under the 150-word floor) as an actionable finding worth one
  expansion turn; the authoring prompt states the minimum with "add a worked
  example, don't pad" guidance.
- **Cross-role overlaps are auto-resolved.** `auto_resolve_overlaps` re-scopes
  one skill of each `PACK-OVERLAP-LLM` / `PACK-TRIGGER` pair (conservative:
  only the second is touched, reverted if it gains a HARD finding) instead of
  only reporting them. Toggle `SkillPackConfig.auto_resolve_overlaps`.

**Tier 2 — measured trigger optimization (`--optimize-triggers`, opt-in):**

- New `skill_pack/trigger_eval.py`: per skill, generate should/should-not-
  trigger queries, score the description against a blind discovery simulator,
  and rewrite it when below threshold — kept only if it beats the original on
  a held-out split. The rigorous replacement for the `DESC-PUSHY` heuristic
  (Anthropic's published description-optimization loop). Results in the report.

**Tier 3 — progressive disclosure (default):**

- Skills can ship bundled resources alongside `SKILL.md`: `references/*.md`
  (load-on-demand deep material) and `scripts/*.py` (deterministic helpers —
  "solve, don't punt"). New `BundledFile` on the `Skill` schema; authoring may
  emit them; the packager writes them to both the Claude tree and the Cowork
  `.zip`. `BUNDLE-PATH` validates paths (`references/*.md`, `scripts/*.py`,
  `evals/*.json`, single subdir, no traversal); unsafe paths dropped.

**Tier 4 — behavioral evaluation (`--with-evals`, opt-in):**

- New `skill_pack/behavioral_eval.py`: per skill, generate task cases +
  objective assertions, run each task WITH the skill vs WITHOUT, grade both
  blind, and report the with-skill-vs-baseline pass-rate delta — proving the
  skill changes output, not just that it is well-formed. Also writes
  `evals/evals.json` per skill (Anthropic's published structure). Expensive,
  so gated and off by default. Results surfaced in the pack report.

## [1.28.0] - 2026-06-02

### Artifact pipeline — prompt hardening (Active Queue #2 closed)

- Writer and regeneration prompts now explicitly forbid the internal-scaffolding
  markers the ship-time gate strips (`[workbook]`/`[Analysis Workbook]`,
  `[cross-ref ...]`/`[see ## ...]`, informal `[cite: label]`, bold
  `**What to validate:**`), sourced from a single
  `qa.report_analyzer.SCAFFOLDING_PROHIBITION_GUIDANCE` constant co-located with
  `scan_scaffolding_leakage` so the upstream instruction and the downstream gate
  cannot drift. Spliced into both `section_prompts.py` writers and both
  `research_agent.py` regenerators (the strategy regenerator also gained the
  plain-text "What to validate:" rule). Parity locked by a deterministic test;
  runtime tracked by `writer_output_clean` (`_shipping_repair.json`) + the eval
  `## Artifact Drift` metric.

### Verified page access — first-party RSS/Atom feed recovery (Active Queue #3)

- `fallback_sources.fetch_feed_content` adds the host's own RSS/Atom feeds as a
  first-class source in the blocked-origin fallback fan-out — HTML
  `<link rel="alternate">` autodiscovery + common-path sweep, same-site-filtered
  (defense-in-depth on the SSRF guard), RSS 2.0 / Atom / RSS 1.0-RDF parsed
  namespace-agnostically with `defusedxml` (untrusted-XML safe; 5 MB body cap;
  no new dependency), `content:encoded` preferred over short teasers, cross-feed
  item dedup. Wired into `gather_fallback_content` as `source="feed"`.

### Test coverage + CI

- Global branch coverage 78.65% → **82.05%**; CI ratchet raised 77 → 81. The
  coverage job now installs the `a2a` extra so the 165 a2a tests are counted,
  plus ~630 new unit tests across `research_orchestrator`, `utils.security`
  (incl. 100 adversarial SSRF cases — no vuln found), `skill_pack.evidence`,
  `data.scrape`, `model_eval`, `mcp_server.{skill_pack_tools,server}`, the
  `agentic` modules, `hiring_signals`, the `scraping` helpers, and `ai_strategy`.
- **Dependabot removed** (`.github/dependabot.yml` deleted) in favor of manual
  review-and-bump backed by the pip-audit + Trivy hard gates. Applied the
  pending action bumps by hand: `actions/checkout` v4→v6, `actions/setup-python`
  v5→v6, `astral-sh/setup-uv` v5→v7, `actions/upload-artifact` v4→v7,
  `actions/download-artifact` v4→v8.

### Artifact pipeline hardening

- **Scaffolding-leak shipping gate**: the leak scan (bare `[workbook]` /
  `[cross-ref]` refs, bold `**What to validate:**` lines, informal `[cite: label]`)
  was promoted from a QA warning to a configurable ship-time gate. Factored into
  the pure `qa.report_analyzer.scan_scaffolding_leakage()` and wired into
  `output.artifact_validation._validate_output_markdown`; leaks above
  `PRIMR_MAX_SCAFFOLDING_LEAKS` (default 0) withhold the polished DOCX (MD/TXT +
  sidecar still written). Canonicalization runs upstream, so a healthy run sits
  at 0 and never trips — the gate only fires on a regression. Eval harness now
  tracks `scaffolding_leaks` per report + `total_scaffolding_leaks` per profile,
  surfaced in a scorecard `## Artifact Drift` section and a CSV column.
- **Upstream cause of bold `What to validate:` lines** addressed: the section
  prompts now instruct the writer to emit that line as plain text (no
  bold/italics/bullet) in both `section_prompts.py` OUTPUT CONTRACT blocks and
  the `research_agent.py` regeneration prompt, reducing the rate the bold form
  is produced at all.
- **Citation-integrity shipping gate**: new pure
  `qa.report_analyzer.scan_citation_integrity()` flags inline `[cite: N]` (incl.
  grouped `[cite: 1, 2]`) with no matching `## Sources` entry; wired into the
  same validator with a configurable `PRIMR_MAX_DANGLING_CITATIONS` (default 0).
  The deterministic backstop behind the upstream LLM citation repair, which
  keeps the original possibly-still-dangling report when it cannot reach zero.
  Covers report and strategy docs (both ship through the same validator).
- **Section-structure shipping gate**: new pure
  `qa.report_analyzer.scan_section_structure()` flags duplicate top-level `##`
  headings (merge/regeneration artifacts) and empty sections (a `##` heading
  with no body); wired into the same validator with a configurable
  `PRIMR_MAX_STRUCTURE_DEFECTS` (default 0). Required-section *presence* is
  deliberately not gated — it is report-type-dependent and too false-positive-
  prone to block shipping on; it stays a QA-scoring signal. Validated against
  the regression corpus so it does not false-block clean long-form reports.
- **Repair observability**: `report_cleanup.compute_repair_report(before, after)`
  (reusing the ship-time scaffolding scanner) measures how much the silent
  deterministic cleanup actually changed — scaffolding markers removed, chars
  stripped, and whether the raw writer output was already clean. Wired at the
  report cleanup seam to log a one-line summary and persist `_shipping_repair.json`.
  This is the measurement foundation for "push consistency upstream": the
  `writer_output_clean` signal makes the cleanup's load-bearing-vs-safety-net
  status trackable so prompt hardening can target the repairs that actually fire.
- **Artifact regression corpus**: `tests/fixtures/artifacts/` (placeholder
  companies) + `manifest.json` of expected gate outcomes, exercised by the
  data-driven harness `tests/test_output/test_artifact_corpus.py` — which also
  renders the clean fixtures end-to-end through `markdown_to_docx` +
  `_validate_output_docx`. A completeness test fails if a fixture is added
  without a manifest entry. Sanitized real artifacts can be dropped in later
  with no test-code changes.

### Skill pack

- **Agent-handoff metadata in `SKILL.md` frontmatter**: a primr-namespaced
  `metadata` block (role, provenance, confidence, an approximate
  `primr-context-tokens` budget, and `primr-refresh-via: mcp:primr/generate_skill_pack, a2a:primr`)
  makes each generated skill self-describing to a consuming agent without
  inferring its capability/cost contract. Grounded entirely in pack data; on by
  default, opt out via `SkillPackConfig(emit_agent_metadata=False)`.
- **Fixed a latent Windows bug**: the Claude-tree `SKILL.md` was written via
  `Path.write_text` (CRLF translation) while the Cowork zip used raw LF, so the
  documented "byte-identical SKILL.md" invariant silently broke on Windows. The
  Claude-tree write now uses `newline="\n"` so it holds cross-platform.

### Model eval wiring (Gemini 3.5 Flash PRO-tier decision)

- Registered a head-to-head eval pair in `config/eval_profiles.py` —
  `protier-gemini31pro` (reference, Gemini 3.1 Pro writer) vs
  `protier-gemini35flash` (candidate, Gemini 3.5 Flash writer) — isolating the
  quality-writer model so the scorecard can answer whether to repoint the PRO
  tier. The default pipeline is unchanged; the repoint is eval-gated and the run
  is billed/user-triggered (`primr eval ... --profiles protier-gemini31pro protier-gemini35flash`).

### Supply-chain hardening

- **Fixed a latent release-breaking bug**: the dependency manifest was written
  into `dist/`, which the PyPI publish step uploads verbatim — twine would have
  rejected the non-distribution file and failed the next release. SBOM artifacts
  now go in a separate `sbom/` artifact, attached to the GitHub release but never
  to PyPI; `dist/` holds only the wheel + sdist.
- **CycloneDX SBOM**: releases now ship a standard CycloneDX JSON SBOM
  (`cyclonedx-py`, invocation validated locally) alongside the pinned uv
  requirements manifest.
- **PEP 740 Sigstore attestations** made explicit (`attestations: true`) on the
  PyPI publish step (default-on for Trusted Publishing; pinned so it can't
  silently regress), complementing the existing SLSA build-provenance attestation.
- **Trivy supply-chain scan** added to CI (filesystem vuln + misconfig,
  HIGH/CRITICAL, unfixed-ignored), now a **hard gate** — complements the
  pip-audit + bandit hard gates. It immediately earned its keep:
  - **Fixed (CRITICAL ×3)**: `openclaw/Dockerfile.primr` declared secret API
    keys via `ENV` (bakes secret-named vars into image layers); removed — they
    are runtime-provided.
  - **KSV-0118 resolved as a platform false-positive (corrected from the
    initial triage)**: verified against the Cloud Run v1 YAML schema that
    fully-managed Cloud Run does not expose a container `securityContext`
    (the RunV1 type carries only `runAsUser`, "Not supported by Cloud Run"), so
    `runAsNonRoot` is rejected by `gcloud run ... replace` — no manifest change
    can clear it. Non-root is already enforced by the image (`deploy/Dockerfile`
    + `openclaw/Dockerfile.primr` run `USER primr`, uid 1000). The `.trivyignore`
    entry is now a permanent, doc-cited false-positive, pinned by a regression
    test (`TestGCPSecurityContext`) that forbids adding a deploy-breaking
    `securityContext`, with inline rationale in both manifests.
  - With the baseline clean (Trivy exits 0 after the ignore), the scan was
    **promoted from signal-only to a hard gate** (`continue-on-error` removed).

### Hygiene ratchets

- **Removed deprecated `datetime.utcnow()`** across the codebase (deprecated in
  3.12+, scheduled for removal; the project tests on 3.14). New
  `primr.utils.timeutils` exposes `utcnow()` (timezone-aware) and `utcnow_naive()`
  (naive, behaviour-identical to the old call). The SQLite-backed monitoring /
  tenancy / knowledge-graph stores were migrated to `utcnow_naive()` on purpose:
  they persist offset-free ISO-8601 strings compared lexically in SQL, so an
  aware datetime would append `+00:00` and silently break `WHERE ts >= ?`
  comparisons and `fromisoformat` round-trips against existing rows. Behaviour
  is byte-for-byte preserved; verified by running the affected suites with
  `-W error::DeprecationWarning`.
- **One-time `ruff format` reflow** (173 files, behavior-preserving) and
  `ruff format --check` now enforced in pre-commit + CI. `E501` stays ignored
  deliberately (ruff format wraps code; remaining long lines are strings/URLs).
- **ruff `target-version` → `py312`** (matches the floor). Applied the surfaced
  `UP035` fix; deferred the PEP 695 generic rewrites (`UP046`/`UP047`) via
  documented ignores (TypeVar generics are correct; the bulk unsafe-rewrite
  isn't worth the risk now).
- **mypy config consolidated + strict ratchet made real**: `mypy.ini` is the
  authoritative config — the duplicate `[tool.mypy]` block in `pyproject.toml`
  was **dead config that never took effect** (and described a strict allowlist
  that wasn't applied); removed it and added a pointer. Bumped `python_version`
  to 3.12 and added the first genuine strict allowlist (`disallow_untyped_defs` +
  `disallow_incomplete_defs`): `skill_pack.{schema,config,planner,industry}`,
  `utils.content_sanitizer`, `utils.logging_config`, `data.hiring_signals`.
- Complexity budget (`C901`) remains deferred until the monster functions are
  refactored (Active Queue #23) — a meaningful cap would otherwise require
  noqa-ing the known offenders.

### Verification ratchets

- **Invariant property tests** (Hypothesis) pinning the load-bearing correctness
  invariants, chosen over the `deal` library (no new dependency; fits the
  exception-based style): skill-pack roster-cap merge
  (`tests/skill_pack/test_invariant_properties.py` — partition, cap, observed
  priority, archetype-dedup-for-plausible, trim-priority order), the SSRF guard
  result shape (`tests/security/test_invariant_properties.py` —
  always `(True, None)` or `(False, <non-empty>)`), and the `CostGuardHook`
  budget rule (`tests/agentic/test_costguard_properties.py` — `remaining ≥ 0`;
  BLOCK iff `spent + max(0, estimate) > max_cost`). The roster property test
  also sharpened the documented contract (observed-vs-observed archetype repeats
  are intentional; dedup applies to plausible roles only).
- **Stateful property test** for the per-host tier circuit breaker
  (`tests/test_data/test_scraping/test_circuit_breaker_stateful.py`): a
  `RuleBasedStateMachine` driving arbitrary attempt sequences and asserting
  failures ≤ attempts, any-success ⇒ never-skipped, skip ⇒ all-failures-past-threshold.
- **Fault-injection hardening**: closed a real redaction gap surfaced by the
  fault lens — `SecretMaskingFilter` now also masks secrets inside **exception
  tracebacks** (`exc_text`), not just the log message. A secret raised in an
  exception and logged with `exc_info=True` no longer leaks to the log file.

### AI / agent security posture

Completes the in-scope security work from `docs/SECURITY.md` (threat model
T1-T7). No change to research-pipeline behavior beyond defensive sanitization.

- **Indirect prompt-injection hardening (T1)**: new `fence_untrusted()` in
  `utils/content_sanitizer.py` sanitizes untrusted retrieved content and wraps it
  in an explicit "data, never instructions" fence. Applied at the previously
  unfenced external-content→prompt boundaries: insights extraction
  (`data/insights_extractor.py`), the Deep Research dossier + stage-1 website
  context (`ai/deep_research.py`), and operator discovery notes are now sanitized
  (`prompts/composer.py`). Backed by `tests/security/test_prompt_injection_corpus.py`.
- **Egress guardrails (T2/T6)**: locked the "no fetch bypasses `is_safe_url`"
  invariant across all three egress helpers with
  `tests/security/test_egress_guardrails.py` (loopback / RFC1918 / link-local /
  cloud-metadata all refused, initial + post-redirect).
- **Chat-log secret redaction (T3)**: `utils/chat_logger.py` now runs
  `mask_sensitive_data` over prompt + response before persisting and writes
  atomically (temp + `os.replace`); errors go through the logger, not `print`.
- **Threat model (T1-T8)**: `docs/SECURITY.md` rewritten as a scoped MITRE-ATLAS
  threat model — explicitly declares model-training/serving security out of scope
  (primr owns no weights), documents per-threat control status + residual risk,
  and refreshes supported versions / disclosure. Linked from README + docs index.
- Drive-by: fixed genuine pre-existing typing/dead-code nits in touched files
  (`ContextVar[dict | None]` annotation; `.items()`→`.values()` where keys unused).

### Engineering standards & toolchain hardening

Infrastructure and supply-chain work; no runtime behavior change to the research
pipeline. See ROADMAP "Engineering Standards & Toolchain" for the full plan.

- **Python floor raised to 3.12** (`requires-python>=3.12`, EOL-driven: 3.11
  reaches EOL Oct 2027, 3.12 covered to Oct 2028). 3.11 dropped from classifiers,
  CI matrix, and `setup_env.py` interpreter discovery. **Breaking for 3.11-only
  users.** CI now runs a `3.12 / 3.13 / 3.14` hard matrix — all fully supported
  (full suite passes on each; native-dep stack installs cleanly on 3.14).
  Free-threading (3.14t) remains a non-goal.
- **uv toolchain**: committed `uv.lock` + `.python-version`; CI installs via
  `uv sync --frozen`; setuptools build backend retained. Dependency lower bounds
  reconciled from `requirements.txt` into `pyproject.toml`.
- **Security gates in CI**: `bandit` (medium severity/confidence) and `pip-audit`
  now block; `.github/dependabot.yml` (weekly pip + github-actions); SLSA build
  provenance attestation (`actions/attest-build-provenance`) + a pinned dependency
  manifest attached to each release (publishing already used OIDC). Fixed the
  findings that gate bandit rather than suppressing: `hashlib.md5(..., usedforsecurity=False)`
  for content-dedup hashing; untrusted sitemap XML parsing switched to `defusedxml`.
- **Coverage ratchet**: measured global branch coverage 78%; CI gates at
  `--cov-branch --cov-fail-under=77` (non-regression floor).
- **pre-commit** (`.pre-commit-config.yaml`): ruff + mypy + hygiene hooks (opt-in).
- **`xfail_strict = true`**: an unexpectedly-passing xfail fails the run (the
  suite uses zero xfail markers).

### Model registry refresh (May 30, 2026 audit)

- **Claude Opus 4.7 -> 4.8** (`claude-opus-4-8`, GA May 28; identical $5/$25
  pricing) — canonical Anthropic slug swapped repo-wide.
- **Gemini 3.5 Flash** (`gemini-3.5-flash`, GA May 19; $1.50/$9 + $0.15 cached)
  registered as available. Not a default: it's a PRO-tier replacement candidate
  (cheaper + stronger than 3.1 Pro), eval-gated. Default pipeline unchanged.
  Gemini 3.5 Pro (June) + Omni pending their API slugs.

## [1.27.1] - 2026-05-29

### Skill pack: operator roster curation

The v1.27.0 planning architecture decides "what roles should exist at this company" by analyzing job postings + research. Operators still need to override that decision when they know something the data doesn't show — augment with specific roles ("the discovered list misses Account Executive"), prune roles they don't want ("drop Marketing Manager"), or do both at once ("swap Marketing Manager for Demand Generation Manager"). v1.27.0 covered the binary cases (full override via `--roles-override`, accept-as-is via `--from-plan`) but had no augmentation surface — the only way to do partial curation was to hand-edit `role_plan.json`. v1.27.1 closes that gap.

#### Four-flag curation surface

- `--plan-only`: run the planning step, write `role_plan.md` + `role_plan.json`, exit before authoring (existing).
- `--from-plan PATH`: load a previously-persisted plan and skip planning (existing).
- `--roles-add "A, B"` (new): comma-separated list of role labels to APPEND to the discovered roster. Each label is materialized as a `Role` with `provenance: override`, archetype matching applied so authoring picks up the closest scaffolding.
- `--roles-skip "X, Y"` (new): comma-separated list of role labels or kebab-case slugs to REMOVE from the discovered roster. Match is exact, case-insensitive, against either `display_name` or `name`. Unmatched names log a warning so typos are visible.

The four compose:
- `--from-plan PATH --roles-add "..."` → load plan, append added roles, author the union
- `--from-plan PATH --roles-skip "..."` → load plan, drop skipped roles, author the rest
- `--from-plan PATH --roles-add "..." --roles-skip "..."` → load plan, drop skipped first, then append added
- `--roles-add "..."` alone → plan normally, append added before cap
- `--roles-skip "..."` alone → plan normally, drop skipped after merge
- `--plan-only --roles-add ... --roles-skip ...` → plan, apply curation, persist the curated plan, exit
- `--roles-override "..."` + `--roles-add/skip "..."` → override wins, curation flags warned and ignored (mutually exclusive per design)

#### Cap-aware merge with operator priority

When operator additions push the roster over `MAX_ROLES=15`, trim order is deterministic and operator-favoring:

1. Plausible roles trim first (research / industry provenance)
2. Observed roles trim next (posting provenance)
3. Operator-added roles never trim

Trimmed entries flow to `gap_flagged` so the plan artifact records what got dropped.

#### Name + archetype dedup

When `--roles-add "Marketing Manager"` lands in a roster that already contains a Marketing Manager (or any role with archetype `marketing-manager`), the existing role wins — its posting/research citations are richer than the bare operator label. The add is silently skipped with a one-line log. Operators who want to force a specific variant can combine `--roles-skip "Marketing Manager"` with `--roles-add "Demand Generation Manager"` to swap.

#### Hard failure modes

- **Clash between add and skip**: `SkillPackConfig.validate()` raises `ValueError` if the same name appears in both lists (normalized).
- **Curation leaves empty roster**: `apply_curation` raises `RuntimeError` rather than shipping an empty pack.
- **Add list exceeds MAX_ROLES alone**: rejected at config validation.

#### Artifact changes

- `role_plan.md` gains `## Operator-Added Roles` and `## Operator-Skipped Roles` sections.
- `role_plan.json` `RolePlan` schema gains `operator_added: list[Role]` and `operator_skipped: list[str]` fields. `load_plan` hydrates them on `--from-plan`.
- Pack report (`<Company>_Skills_Pack_Report.md`) Role Composition section adds an `Operator-added (via --roles-add): N` line and an `Operator-skipped (via --roles-skip): N (<names>)` line when applicable.
- CLI completion message reports the full breakdown: `Roles: 7 (5 observed, 0 plausible, 2 added; target 5)`.

#### MCP

`generate_skill_pack` tool gains `roles_add: array[string]` and `roles_skip: array[string]` params alongside the existing `roles_override` / `plan_only` / `from_plan_path` / `allow_recon_only`. Backward compat preserved.

#### Tests

21 new curation tests in `tests/skill_pack/test_curation.py` covering: normalization, role materialization, cap trim order (plausible → observed → never override), the full composition matrix (add-alone / skip-alone / add+skip swap / add dedup by name / add dedup by archetype / cap overflow), and edge cases (empty roster hard error, unmatched skip warning, config-level clash detection, add-exceeds-cap rejection, dedup within `roles_add` and `roles_skip` lists). All pass; ruff clean.

## [1.27.0] - 2026-05-29

### Skill pack: holistic input layer + planning architecture rebuild

The skill pack subsystem treats job postings as primary input and research as supporting context. Two problems showed up against real services / reseller / consultancy companies: (1) the input layer covered only four ATS providers, missing Workday-using companies entirely; (2) the single-call discovery layer collapsed observed roles and inferred roles into one list with no provenance, making it impossible to distinguish "this role appears in actual postings" from "this role plausibly exists given the business model." Both gaps are fixed.

#### Input layer

Hiring-signal gathering (`src/primr/data/hiring_signals.py`) expands from 4 ATS providers to 8:

- **Workday** with two discovery paths: corpus-driven URL extraction (when the scrape already saw a `myworkdayjobs.com` URL, hit the exact endpoint directly) and bounded blind discovery (4 datacenters × 5 site-ids per slug candidate). Posts to the public `/wday/cxs/{tenant}/{site}/jobs` JSON endpoint and fails closed on schema mismatch.
- **Workable** via the public widget API at `apply.workable.com/api/v1/widget/accounts/{slug}`.
- **Recruitee** via the public offers API at `{slug}.recruitee.com/api/offers/`.
- **Jobvite** via the public RSS feed at `jobs.jobvite.com/{slug}/jobs?format=rss`.

New **DuckDuckGo web-search fallback** (`_discover_via_web_search`) fires only when the ATS chain + HTML careers-page crawl both return zero postings. Filters results to known job-board hosts (LinkedIn, Indeed, Glassdoor, Workday boards, the ATS hosts) and returns metadata-only postings. The no-bodies branch was extended to populate `signals.roles` from posting titles when bodies aren't recoverable, so the skill pack discovery layer still sees role-type signal even when posting hosts block automated scraping.

iCIMS and BambooHR are still not covered as dedicated providers — they have no clean public JSON APIs, and the existing HTML fallback handles them.

#### Planning architecture

`src/primr/skill_pack/planner.py` replaces the single-call `discover_roles` with a two-call planning step:

- **Call A — observed roles**: extracts roles from hiring signals only. Every role MUST carry at least one verbatim posting citation or it's dropped. Provenance: `posting`. Confidence: `Confirmed`.
- **Call B — plausible roles**: infers roles from recon + research evidence + an `IndustryClassification` (business model, vertical, stage, employee estimate, citations). Every plausible role MUST carry at least one specific research citation OR an explicit business-model + stage rationale. Common org-shape roles (Marketing, Sales, Customer Success, Finance, HR) become plausible only when company stage is Mid-market or larger. Generic VP and Chief-X titles are forbidden without specific evidence. Provenance: `research` or `industry`. Confidence: `Inferred` or `Speculated`.

Merge is archetype-based with observed-wins dedupe. The split is signal-driven — no hard ratio. Rich postings + thin research yields observed-dominant; thin postings + rich research yields plausible-dominant. Cap is `roles_count`; overflow goes to `gap_flagged` so operators can re-run with `--roles-override` to promote any of them.

`IndustryClassification` resolution is LLM-only (deterministic heuristics were considered and rejected): first parse structured fields from a primr strategic report when one is supplied via `--from-report`, otherwise run a single cheap LLM classification call. `source` field on the result records which path produced it.

#### Artifacts

The planning step writes two artifacts into the working directory before authoring begins:

- `role_plan.md` — human-readable view with industry classification, evidence summary, observed roles + citations, plausible roles + citations, gap-flagged roles, final roster, and operator next-step hints.
- `role_plan.json` — machine view used by `--from-plan`. Includes the full role payload, evidence, citations, industry, and provenance per role.

The pack report (`<Company>_Skills_Pack_Report.md`) now shows the observed/plausible split, industry classification, per-role provenance with citation excerpts, and a reference back to `role_plan.md`.

#### Authoring

`author_role_skills` branches the authoring prompt on `RoleEvidence.provenance` so observed roles ground in posting evidence, research-inferred roles ground in research citations and named practices, industry-inferred roles ground in business-model typicality, and operator overrides pass through cleanly. A new `provenance_guidance` placeholder in `author_skill.yaml` injects the per-provenance steering text.

#### CLI

- `--plan-only` — run through the planning step, persist `role_plan.md` / `role_plan.json`, exit before authoring.
- `--from-plan PATH` — load a previously-persisted plan and author against its `final_roster` verbatim. Supports the plan → inspect → author workflow.
- `--roles-override "Role A, Role B, ..."` — bypass planning entirely; up to `MAX_ROLES` labels.
- `--allow-recon-only` — opt in to the degraded recon-only path when both posting and research evidence are empty (the default is hard failure with a clear error message).

#### Configuration

- `MAX_ROLES` raised from 8 to 15 for holistic packs that mix observed and plausible roles.
- New `SkillPackConfig` fields: `allow_recon_only`, `roles_override`, `plan_only`, `from_plan_path`.
- New `RoleProvenance` enum (`posting` / `research` / `industry` / `override`) carried on `RoleEvidence` end-to-end.
- New `IndustryClassification` and `RolePlan` dataclasses in `schema.py`; `SkillPack` carries an optional `plan` reference.

#### Hard failure on empty inputs

`discover_roles` and `plan_roles` now raise `EmptyHiringEvidenceError` when both posting evidence and research evidence are empty unless `allow_recon_only=True` is passed. Prevents the silent shipping of thin recon-only packs against services / reseller / consultancy companies where DNS fingerprints can't reveal the revenue-generating role layer.

#### Tests

- 13 new planner tests in `tests/skill_pack/test_planner.py` (observed/plausible split, merge+cap behavior, hard-failure path, allow-recon-only proceeds, plan roundtrip persistence).
- 17 new provider tests in `tests/test_data/test_hiring_signals_new_providers.py` (Workday corpus discovery + bounded discovery + POST parsing, Workable, Recruitee, Jobvite, web-search filtering, title cleanup).
- Existing `tests/test_data/test_hiring_signals.py` updated to mock the web-search fallback explicitly.
- Existing `tests/skill_pack/test_pipeline.py` mock updated to recognize the new planning prompts.
- Full suite: 7917 passed, 31 skipped, 0 failed. Ruff clean.

## [1.24.4] - 2026-05-16

### Cost estimator now reflects cross-provider routing

The dry-run estimator for the standard pipeline (`primr "X" url --dry-run`) was reporting the legacy ~$5.67/run number even when both `GEMINI_API_KEY` and `XAI_API_KEY` were configured — the v1.24.x cross-provider routing that picks `gemini-3.1-flash-lite` for bulk writing was implemented in `pick_model_for_role` but never threaded through the estimator. `_estimate_fast_mode_cost` was calling `PrimrModels.get_grok_models(tier)` directly, which always returns Grok models regardless of which keys are set.

Fixed by deferring writing-model resolution to `pick_model_for_role(Role.WRITING)` for the FAST and HYBRID tiers. `--grok-tier max` still uses Grok-everywhere — that flag is the explicit user opt-in to the all-Grok stack. The estimate now reports:

- Standard run, no AI strategy: ~$0.76 (matches the README's $0.79 claim and the v1.24.0 stage-1 eval)
- Standard + verify: ~$0.78
- Standard + 1-vendor AI strategy: ~$0.89
- Standard + 2-vendor AI strategy (typical default): ~$1.01
- `--grok-tier max`: ~$3.38 (Grok-everywhere, as before)

The displayed mode notes now also show the actual resolved model pair (`grok-4.3 reasoning + gemini-3.1-flash-lite writing`) rather than the hardcoded `4.20-nr writing` string.

### Docs

- Updated stale `routing.py:pick_model_for_role` docstring that still described v1.23.0 single-provider behavior. The actual code has run the v1.24.x cross-provider chain since v1.24.0.

### Tests

- Three test cases that assumed Grok-only writing (`test_max_tier_cheaper_writing_than_hybrid`, `test_fast_tier_cost_range`, `test_hybrid_tier_cost_range`) were rewritten to monkeypatch env vars to a deterministic state and to assert the correct relationship for both XAI-only and Gemini+XAI configurations.
- Added `test_hybrid_cheaper_than_max_with_gemini` and `test_hybrid_tier_cost_range_with_gemini` as forward-looking regression guards for the v1.24.x routing.

## [1.24.3] - 2026-05-16

Re-release of v1.24.2: prior release had `primr.__version__` still at `1.24.1` while `pyproject.toml` was at `1.24.2`, breaking the package-version integrity check. v1.24.2 was yanked from PyPI; v1.24.3 is the clean release.

### Artifact drift cleanup (roadmap item #1)

Internal scaffolding markers were leaking into shipped reports more often than the roadmap previously estimated. A scan of 16 recent reports found 240 `[workbook]` markers, 87 `[cross-ref ...]` markers, and 65 bold-wrapped `**What to validate:**` lines that should never reach a deliverable. Three root causes, all fixed:

- **`[cross-ref ...]` cleanup was too narrow.** The strip regex in `_clean_fast_report_output` required a colon (`\[cross-ref:`), so the space-separated variant the model actually emits most often (`[cross-ref Financial Profile]`) sailed through. Broadened to match colon-separated, space-separated, and bare forms. Verified on five historical reports: 28 leaked instances stripped to 0.
- **`[workbook]` cleanup missed the bare and space-separated forms.** The existing regexes caught `[Workbook: ...]`, `[workbook section ...]`, and `[Workbook §...]` but missed bare `[workbook]` and `[workbook ARDA/prior sections]` — the variants the model emits when treating workbook as a literal source citation. Replaced with one inclusive `[workbook(?:[\s:§]...)?\]` regex. Verified: 51 leaked instances stripped to 0.
- **Bold-wrapped `**What to validate:**` lines bypassed normalization.** `_normalize_generated_section_payload` matched `^What to validate:` but not `**What to validate:**`, so bolded variants leaked into the body alongside a separately-appended default trailing line. New regex recognizes optional leading/trailing bold or italic emphasis and dedups into the single canonical trailing line.

### ReportAnalyzer scaffolding-leakage check

Added `analyze_scaffolding_leakage()` to `ReportAnalyzer` covering the four leak categories above plus informal `[cite: workbook]` / `[cite: bbb]` cite labels that should never ship. Surfaced as a warning block in `generate_report()` when `total_leaked > 0`; clean reports stay terse.

### Bonus fixes

- `analyze_urls_and_sources()` had a hardcoded vendor domain as the "company_website" category — a leftover from one early test report that was meaningless for every other run. Replaced with a generic `primary_host` derived from the most-cited non-news, non-LinkedIn domain.
- Fixed a `lstrip("www.")` bug in the same area (would have stripped any leading `w` or `.` character, not the literal prefix) — switched to `removeprefix("www.")`.

### Tests

- +5 normalization tests in `tests/test_core/test_fast_mode_research.py` covering bold-wrapped validate lines (with content, fully bolded, bare), space-separated cross-ref, and bare workbook variants.
- +6 ReportAnalyzer tests in `tests/test_qa/test_report_analyzer_deterministic.py` covering each leak category and the combined total.

## [1.24.1] - 2026-05-13

Re-release of v1.24.0 with sanitized docs (generic placeholder for eval-target company). No code changes.

## [1.24.0] - 2026-05-13

### Sub-$1 default via cross-provider eval

Cross-provider eval picked Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing as the new default — verified at $0.79/run (vs $3.49 on the previous Grok-only hybrid, 4.4x cheaper with trust gate PASS and faster runtime). Default auto-selects when both `XAI_API_KEY` and `GEMINI_API_KEY` are configured; XAI-only setups stay on the legacy ~$4.27/run path.

### Provider-aware role routing

- `pick_model_for_role` uses a provider-aware fallback chain: WRITING/UTILITY prefer GEMINI > OPENAI > ANTHROPIC > XAI; REASONING prefers XAI (Grok 4.3 cached) > GEMINI > OPENAI > ANTHROPIC.
- OpenAI-only users get gpt-5.4-nano writing + o4-mini reasoning; Anthropic-only users get Haiku + Sonnet.
- `grok_llm` extended with cross-provider dispatch so writing-tier calls reach the right provider when the resolved model is non-Grok.
- OpenAI provider switched to `max_completion_tokens` for the gpt-5.x family.
- PRO role split into REASONING + WRITING + UTILITY in `routing.py`; `EvalRecipeOverride` contextvar added for per-run recipe forcing.

### Eval profile slot registry

`src/primr/core/model_eval.py` + `src/primr/config/eval_profiles.py` gain a profile slot registry with 11 candidate slots — one slot per (provider × model × role-recipe). New models register a slot, run the corpus once, and score against existing baselines without re-doing prior work.

### Pipeline resilience

Phase 5 enrichment loop got a 5-minute per-section deadline (had been unbounded). Stops runaway regeneration loops without affecting the common case.

Full decision audit in `docs/EVAL_V1_24_0.md`.

## [1.23.0] - 2026-05-08

### Multi-provider foundation

- **OpenAI integration** via `OpenAICompatibleProvider`. `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano` registered with cached-input pricing. `OPENAI_API_KEY` auto-detected. `reasoning_effort` plumbed through provider kwargs.
- **Ollama / local-inference** via `OpenAICompatibleProvider`. `qwen3-coder:30b`, `qwen2.5:32b`, `deepseek-r1:32b`, `qwen3:7b` registered at zero marginal cost. `OLLAMA_BASE_URL` env honoured; `api_key_default="ollama"` so the OpenAI SDK accepts the call.
- **Anthropic Claude provider** as a separate class (`src/primr/ai/providers/anthropic.py`). System-message translation, retry/backoff, billing-exhaustion detection raising `QuotaExhaustedError`, cache-aware token tracking. `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5` registered.
- **Quota-aware fallback infrastructure** in `ModelCircuitBreaker.execute_with_fallback()` — consumes `QuotaExhaustedError`, marks the provider exhausted with midnight-UTC reset, advances through cross-provider chains. Per-call-site integration into the production pipeline is scoped to v1.24.0.
- **Prompt-cache token plumbing.** Providers extract cached counts from xAI / OpenAI (`prompt_tokens_details.cached_tokens` / `cached_tokens`) and Anthropic (`cache_read_input_tokens` / `cache_creation_input_tokens`). `_UsageAccumulator` aggregates them; `get_usage()` exposes them. Bridging into per-run `UsageRecord` and `primr show-usage` is scoped to v1.24.0.

### Skills Ideation strategy (`--strategy-type skills`)

- New YAML-defined strategy at `src/primr/prompts/strategies/skills.yaml` that ideates a top-5 roles x top-3 skills hypothesis grounded in DNS recon and hiring signals.
- **Per-role `SKILL.md` emission** via `src/primr/output/skills_generator.py`. Selecting `--strategy-type skills` produces both the strategy markdown/DOCX *and* `output/<Company>_Skills_Ideation_<date>/roles/<slug>/SKILL.md` files with proper `name` / `description` frontmatter — drop-in loadable by Claude Code, Copilot Studio, or any skill-aware agent host.
- **YAML strategy context loader extended** to also pull `_recon_context.txt` and `_hiring/hiring_signals.md`. This change strengthens the existing Customer Experience, Modern Security, and Data Fabric strategies as a side effect — they now see recon and hiring signals which previously only reached the AI strategy path.
- Sparse-signal companies pivot to industry-baseline mode and say so explicitly rather than fabricating roles, per the YAML's mandatory Signal Strength section.

### Anthropic correctness fixes

- Opus 4.7 context window corrected to 1M (was 200K), output corrected to 128K (was 32K).
- Sonnet 4.6 context window corrected to 1M (was 200K).
- Haiku 4.5 output corrected to 64K (was 16K), `supports_thinking=True`.
- Removed bogus `cache_control_blocks` provider-kwarg passthrough — Anthropic prompt caching is configured at the message-content level (cache_control directives inside content blocks), not as a top-level API parameter. The previous plumbing would have raised `TypeError` if a caller actually used it.
- Opus 4.7 tokenizer-inflation caveat (~35% more tokens than 4.6 for the same input) documented in `ModelRegistry`.

### Misc fixes

- `--help` no longer crashes Python 3.10 on Windows when stdout decodes as UTF-8 — replaced the lone `×` (multiplication sign) in the skills strategy description with `x`.
- `UTILITY_FALLBACK_CHAIN` now references `PrimrModels.GROK_MODEL_WRITING` instead of the hardcoded `"grok-4.20-non-reasoning"` string.
- mypy fix in `core/cli.py` xAI key-verification branch.

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
