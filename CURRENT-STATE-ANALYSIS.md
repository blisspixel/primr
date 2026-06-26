# Current State Analysis

## Vision

Primr is a CLI-first, local-first company research system. The product value is
the full artifact pipeline: recon, scraping, hiring signals, research
deepening, synthesis, validation, packaging, and handoff. The user-facing bar is
not "a model wrote text"; it is a serious strategic artifact with evidence,
uncertainty labels, cost controls, and reusable outputs for humans and agents.

## Agentic Balance

The governing line is stable:

- Deterministic rules own structure, spend, egress, disk writes, packaging, and
  referential validity.
- Model judgment owns content decisions where a fixed path cannot generalize.
- Quality is measured with evals and calibration, not asserted by brittle prose
  regexes.
- Any billable run needs estimate-first approval. This cycle used only local
  tests and static checks, so spend is `$0.00`.

## Quality Standard

The development contract is `CLAUDE.md`: use the existing seams, do not grow
monster files, keep examples free of real company data, do not add authorship
attribution, and run the same gates CI runs. The relevant skill-pack standard is
to generate useful, grounded Agent Skills with clean frontmatter, substantive
workflow bodies, concrete output formats, role evidence, and safe bundled
resources.

## 2026-06-26 Startup Alignment and External Research

The current startup review re-read `README.md`, `ROADMAP.md`, `CLAUDE.md`,
`docs/design/agentic-balance.md`, `docs/design/engineering-excellence.md`,
`docs/design/2.0-agent-control-plane.md`, `docs/design/2.0-backend-freedom.md`,
`docs/design/1x-completion.md`, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`,
`docs/EVAL.md`, `docs/CONTRIBUTING.md`, `docs/CHANGELOG.md`,
`PROGRESS-LOG.md`, `SKILLS.md`, `NOTES.md`, and the touched MCP/runtime budget
code.

Current external best-practice check confirms the repo's control-plane order:

- MCP's authorization guide recommends authorization when a server exposes
  sensitive resources, needs per-user audit, requires user consent, or supports
  enterprise access control:
  <https://modelcontextprotocol.io/docs/tutorials/security/authorization>.
- MCP security guidance and current specifications emphasize user consent,
  tool safety, authorization, and scope-aware protected resources:
  <https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices>
  and <https://modelcontextprotocol.io/specification/2025-11-25>.
- OWASP's agentic AI guidance and Microsoft Zero Trust AI threat modeling both
  point to least-privilege tools, explicit confirmation for high-risk actions,
  and logging/audit for tool use:
  <https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/>
  and <https://learn.microsoft.com/en-us/security/zero-trust/sfi/threat-modeling-ai>.
- OpenTelemetry's 2026 GenAI guidance treats model calls, token usage, and
  tool calls as observable operations while making full content capture opt-in:
  <https://opentelemetry.io/blog/2026/genai-observability/>.
- Anthropic's long-running-agent guidance reinforces the local loop pattern:
  use persistent artifacts, verify completion externally, and keep the harness
  simple instead of trusting self-declared done:
  <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>.

This makes the next best local slice the MCP runtime budget propagation fix,
not a new provider integration or paid eval. It closes a documented HIGH
control-plane gap with deterministic code and local tests.

## 2026-06-26 Control Plane Slice: MCP Runtime Budget Enforcement

Shipped in this slice:

- `research_company` now passes the approved `max_estimated_cost_usd` into the
  background `PipelineRunner` as `budget_usd` after the existing cost-cap and
  approval-token checks succeed.
- `PipelineRunner.run_research` activates `utils.run_budget.set_run_budget()`
  for approved caps, so the MCP fast path consults the same mid-run budget
  checkpoints as the CLI `--budget` path.
- Uncapped MCP runs clear any stale process budget before starting, so a
  previous failed or older-process leak cannot accidentally constrain a new
  no-cap run.
- The runner clears the process-global run budget in a `finally`, so a
  completed, cancelled, or failed MCP job cannot leak budget state into the next
  job.
- Regression tests prove the cap reaches the runner, the fast path sees the
  active budget, and exception paths clear it.

Current estimate:

- 2.0 control-plane pillar: about 72% complete. MCP scopes, approval tokens,
  invocation audit, and fast-path runtime budget propagation are now shipped.
  A2A parity, richer job-scoped artifact resources, and non-fast runtime budget
  checkpoints remain.
- Full 2.0 release: still about 35% complete. Backend freedom and durable
  research memory remain the larger release blockers.

Spend: `$0.00`. Validation passed: focused MCP runner/tool/approval/cost-cap
tests, full MCP suite, Ruff check, Ruff format check, mypy on `src/primr`,
Bandit, pip-audit, MkDocs build, architecture/release-integrity tests, and the
CI-shaped coverage gate (`10210 passed, 39 skipped, 5 deselected`, 85.22%
branch coverage).

## 2026-06-25 Quality Slice: Label-Honesty Pass (1.x #4 / step 3)

The roadmap's order of operations puts 1.x quality completion ahead of the 2.0
pillars, and the June-2026 calibration eval pinned a single *measured* quality
deficiency: epistemic grounding. `(Confirmed)` labels traced to their cited
source only ~8% of the time and `(Reported)` ~0%. The measurement half already
existed (`qa/label_calibration.py`); this slice ships the mechanical fix.

Shipped in this slice:

- `qa/label_honesty.py`: a pure, injectable pass that re-judges each
  traceable-class claim against its cited source and downgrades the untraceable
  ones to `(Estimated)`. Judgment decides whether the source supports the claim;
  the downgrade is mechanical and fail-safe (confidence only lowers, every other
  verdict keeps the label). `LabeledClaim` gained a `label_span` so the exact
  occurrence is rewritten without re-scanning.
- Opt-in wiring into the trust stage behind `PRIMR_LABEL_HONESTY`; default-off,
  byte-identical standard run, `_label_honesty.json` audit sidecar, never blocks
  shipping.
- Released as `1.34.0` (new opt-in feature).

This is doctrine-clean per `agentic-balance.md`: determinism on the rewrite,
judgment on whether the source supports the claim, quality measured by
calibration, and no hard gate armed from a lone judge. The open follow-up is
the agreement-validated calibration baseline that would justify promoting the
pass toward default.

## Current Roadmap Focus

Backend freedom is the active 2.0 unblocker. The completed local slices now
cover the deterministic routing skeleton:

- Bounded host-agent stage packets in `ai/host_agent_runner.py`.
- Pure stage capability routing in `ai/capability_routing.py`.
- Pure provider quota and availability normalization in
  `ai/provider_availability.py`.
- Generic user-owned availability collection in
  `ai/provider_availability_collectors.py`.
- Availability-to-backend annotation in `ai/capability_routing.py`, which marks
  backend rows unavailable and attaches sanitized metadata before routing.
- Sanitized `primr doctor` visibility for the same generic availability
  snapshots.

The current priority is still not a paid live probe. The next local-safe step is
production plumbing around the pure seam: wire official quota/status collectors
only where providers expose supported zero-token status surfaces, then adopt the
router stage by stage. Full-report execution should keep today's defaults until
eval proves each route before it is advertised.

Current estimate:

- 2.0 backend-freedom pillar: about 35-38% complete. Routing, host-runner
  packets, availability math, generic collection, backend annotation, and
  doctor visibility are tested. Remaining work is official live collectors,
  stage requirement declarations, production execution adoption, host-runner
  pilots, hybrid eval, and local profile fit checks.
- Full 2.0 release: about 35% complete. Control-plane and backend-freedom
  infrastructure are furthest along; durable research memory remains the
  largest unstarted pillar.

## 2026-06-24 Refinement: Deeper Anthropic Agent Skills Best Practices
Approved plan executed for the skill_pack generator (primr skills). Changes embed
the exact patterns from research (Anthropic engineering post + best-practices
guide + user query):

- Skills as folders (SKILL.md + references/ + scripts/ + evals/).
- Narrowly scoped (one capability per skill, one category).
- Verification skills high leverage (bias for at least one verifier per role; planner updated to include in universal; authoring MUST + default script guarantee via seam).
- Use scripts for deterministic work ("solve, don't punt" - emit real .py; default verify script for verifiers).
- Gotchas section as highest-signal, seeded from real evidence/failures, living (update over time) - structural via attached references/gotchas.md (no body regex).
- Trigger descriptions ("Use when..." with concrete user phrasing, not summaries).
- Progressive disclosure (lean SKILL.md, point to extra files; we always attach role-family, gotchas, composition refs).
- Compose small skills (name references, no giant orchestrators).
- Measure usage (via trigger/behavioral evals, pack report adherence counts; structural for gotchas via attached files; no new mechanism per answer).

All changes strictly follow agentic-balance.md: determinism on structure/referential validity (validators only for kebab, injection, min length, required markers, bundled paths); judgment on content (prompt-driven); quality measured by evals (existing trigger + behavioral), not new brittle regex content gates. Recent pass removed body-scanning regex for Gotchas presence (now structural via deterministically attached references/gotchas.md).

primr self-suggestion (claude-code/skills/primr/SKILL.md + references/gotchas.md) aligned as exemplar: trigger-rich description, references/ dir with living Gotchas, modeling BP (cost gate, async, no brittle, folders, etc.). Root skills/ kept thin as designed.

Generator now produces production-grade, non-slop skills matching the condensed takeaway. No new giant files, use existing seams (BundledFile, role_references, prompt + structural validators + evals), zero external spend in this cycle, full tests + gates pass.

Current focus (loop continuing): complete any remaining PLANNED from ROADMAP §15 (e.g. verifiable intermediate outputs), update additional root skills if fits, full folder + verification by default in generator.

Alignment confirmed with README (skill pack as first-class), ROADMAP (deeper BP, anti-brittle), CLAUDE.md (one seam, no monster, verify APIs, tests with code), agentic-balance (no brittle, prompt + eval).

## 2026-06-24 Control Plane Slice: MCP Per-Tool Authorization

After re-reading README, ROADMAP, `CLAUDE.md`, `docs/design/agentic-balance.md`,
`docs/design/2.0-agent-control-plane.md`, and `docs/SECURITY.md`, the highest
leverage next slice is the first 2.0 control-plane stage: enforce capability
scopes at the actual MCP tool-dispatch boundary.

Shipped in this slice:

- New central MCP tool policy for `read`, `research`, `delegate`, and `admin`.
- OAuth `scope` and Entra `scp` JWT claims honored for least-privilege tokens.
- Legacy no-scope `read` / `write` JWTs retained through a compatibility alias,
  so existing authenticated clients do not break while new clients can be
  explicitly read-only.
- HTTP auth context now bridges the SDK-authenticated user into tool dispatch
  through request-local context storage instead of a shared mutable server
  field.
- Structured `insufficient_scope` tool responses include required, granted, and
  missing scopes.
- Security docs and ROADMAP now mark T8 MCP Stage 1 shipped while leaving
  approval tokens, structured invocation audit, and A2A parity as next work.

Current estimate:

- Next patch release readiness: this is a coherent `1.33.x` patch slice once
  full CI gates are green.
- 2.0 control-plane pillar: about 35% complete. Per-tool authz is the required
  base. Approval provenance and invocation audit remain.
- Full 2.0 release: about 20-25% complete. Control-plane Stage 1 helps, but
  backend freedom and the research-memory layers still carry most of the
  remaining release mass.

Spend: `$0.00`. Full local validation now passes: `git diff --check`,
`ruff check src/primr/`, `ruff format --check src/ tests/`, full `mypy`,
Bandit, `pip-audit`, and `uv run pytest tests/ -q` (10119 passed, 42 skipped).

## 2026-06-25 Control Plane Slice: MCP Approval Tokens

The next control-plane slice is now implemented for MCP cost-cap-governed
execution tools. This follows the roadmap order: scope authz first, approval
provenance second, audit later.

Shipped in this slice:

- `estimate_run`, `estimate_strategy`, and `estimate_skill_pack` return
  short-lived server-issued `approval_token` fields.
- `research_company`, `generate_strategy`, and `generate_skill_pack` require a
  matching token when server-side MCP cost-cap enforcement is active.
- Tokens are HMAC-signed, single-use, TTL-bound, and tied to the target tool,
  cost-affecting approval-shape hash, and approved max cost.
- Argument-swap and replay attempts return structured MCP errors before paid
  execution starts.
- Platform alias normalization moved out of the pinned `tools.py` module, and
  `tools.py` stays within its pinned architecture ceiling.

Current estimate:

- 2.0 control-plane pillar: about 60% complete. MCP per-tool authz and approval
  provenance are shipped for the primary paid execution paths. Structured audit,
  A2A parity, and approval coverage for any non-cost-cap-governed paid paths
  remain.
- Full 2.0 release: about 25-30% complete. Control-plane work is advancing, but
  backend freedom and durable research memory still carry most release mass.

Spend: `$0.00`. Latest online check aligned this priority with current MCP
authorization guidance and OWASP agentic guidance: least-privilege scopes,
approval for high-impact actions, and complete mediation in downstream systems.
Full local validation passes: ruff, format check, mypy, Bandit, pip-audit, and
`uv run pytest tests/ -q` (10126 passed, 42 skipped).

Follow-up: PyPI latest is `1.33.1`, matching `pyproject.toml`, so no
same-version publish is appropriate. The release workflow now builds under
Python 3.12, matching the declared package floor, and
`tests/test_release_integrity.py` pins that the PyPI workflow cannot drift back
to Python 3.11.

Release follow-up: current source is now bumped to `1.33.2` for publication.
The done work is represented in both `docs/CHANGELOG.md` and the ROADMAP
changelog table, and PyPI metadata uses the modern Apache 2.0 SPDX expression
without deprecated license classifiers.

The supplied agentic-systems guide reinforces the next control-plane step:
structured invocation audit logging. Approval tokens already cover bounded
action for spend-governed MCP tools; the next slice should persist who invoked
which tool, granted scopes, approval token id, normalized argument hash,
estimated cost, result status, and job id. That addresses idempotency,
approval provenance, execution traces, and side-effect visibility without
adding brittle content-quality gates.

## 2026-06-25 Control Plane Slice: MCP Invocation Audit

The MCP control-plane audit slice is now implemented for tool calls.

Shipped in this slice:

- Every MCP tool call records an append-only JSONL audit event through the
  registered tool-dispatch seam.
- Events include timestamp, transport, tool name, hashed HTTP caller id,
  stdio actor marker, granted scopes, argument hash, result hash, approval
  token id, estimated/max cost, job id, duration, status, error type, and error
  code.
- Raw tool arguments, raw results, raw URLs, raw client ids, and full approval
  tokens are not stored.
- `primr://agent/audit/recent` exposes recent events to local stdio callers and
  admin-scoped HTTP callers.
- Tests cover successful audit writes, cost-cap approval failures, scope
  denial, privacy of raw URLs/tokens/client ids, and the local/admin resource
  gate.

Current estimate:

- 2.0 control-plane pillar: about 70% complete. MCP per-tool authz, approval
  provenance, and invocation audit are shipped for MCP tools. A2A parity,
  richer job-scoped artifact resources, and approval coverage for any
  non-cost-cap-governed paid paths remain.
- Full 2.0 release: about 30-35% complete. Backend freedom and durable research
  memory still carry most release mass.

Spend: `$0.00`. Latest online check aligned this priority with current MCP
guidance: MCP tool implementations should log tool usage for audit purposes,
the MCP roadmap lists enterprise audit trails and observability as a priority,
and current OpenTelemetry GenAI guidance treats tool invocations as first-class
observable operations while defaulting away from full content capture.

## 2026-06-25 Backend Freedom Slice: Provider Availability Contract

The quotabot review produced one directly useful transfer for primr: treat
quota and service availability as normalized routing data, not as provider UI
or scattered exception text. The implementation is intentionally pure and free
to validate before any live provider collector is added.

Shipped in this slice:

- `ai/provider_availability.py` defines `QuotaWindow`,
  `ProviderQuotaSnapshot`, and `AvailabilityDecision`.
- Headroom is computed from the most constrained quota window, so one tight
  requests-per-minute or weekly host-plan bucket can govern routing.
- Elapsed reset windows count as fresh quota, preventing stale quota reads from
  keeping a provider marked exhausted after its reset boundary.
- Stale last-known-good snapshots preserve routing signal but rank behind fresh
  snapshots.
- Tests cover binding windows, reset handling, exhausted headroom thresholds,
  missing quota windows, stale snapshot behavior, and validation/clamping.

Current estimate:

- 2.0 backend-freedom pillar: about 30% complete. Stage capability routing,
  host-agent packet shape, local judge detection, and quota availability
  headroom are now pure and tested. The remaining work is production wiring:
  live provider collectors, router integration, stage-by-stage requirement
  declarations, first host-runner pilots, hybrid eval, and local eval.
- Full 2.0 release: about 35% complete. Control-plane is the furthest along;
  backend freedom now has the right deterministic seams; durable research
  memory still carries substantial remaining release mass.

Spend: `$0.00`. Validation passed for the new availability slice and the full
repo gate: focused provider tests, focused MCP audit tests, full MCP server
tests, ruff, format check, CI-shaped mypy, Bandit, pip-audit, MkDocs build, and
the CI-equivalent coverage run (`10134 passed, 39 skipped, 5 deselected`,
85.13% branch coverage).

## 2026-06-25 Backend Freedom Slice: Generic Availability Collectors

The next backend-freedom step is now the generic collector layer, not
provider-specific account wiring. This keeps Primr useful for any user's
capacity shape: direct API keys, sanctioned host allocation, local
OpenAI-compatible services, or gateways later, without baking in personal
accounts or repo-owned credentials.

Shipped in this slice:

- `ai/provider_availability_collectors.py` translates known cloud provider
  configuration into `ProviderQuotaSnapshot` rows without reading or storing API
  key values.
- The same module probes local OpenAI-compatible services through the existing
  `/v1/models` detector and reports model count plus chat-model availability
  without storing raw endpoint URLs or installed model names.
- Aggregation skips the registry's Ollama credential-default row and reports a
  single generic local OpenAI-compatible snapshot, so users can bring Ollama, LM
  Studio, llama.cpp server, vLLM, LocalAI, or a gateway-compatible local server.
- Tests assert secret values, local hostnames, and installed model names do not
  appear in snapshots, even on probe failures.
- README, ROADMAP, backend-freedom docs, provider-expansion docs, changelog,
  progress log, and skill memory now draw the same line: use what the user has,
  never what the repo owns.

Current estimate:

- 2.0 backend-freedom pillar: about 32-35% complete. Pure routing,
  provider-availability math, host-agent packet shape, local model detection,
  and generic availability collectors are now tested. Remaining work is
  production integration: official cloud quota/status collectors, capability
  rows fed from availability decisions, stage-by-stage route adoption,
  host-runner pilots, hybrid eval, and local profile fit checks.
- Full 2.0 release: about 35% complete. Control-plane is still furthest along;
  backend freedom has the core deterministic seams; durable research memory
  remains the largest unstarted pillar.

Spend: `$0.00`. Validation passed for this slice: focused provider
availability/local tests, ruff on touched files, mypy on the touched AI modules,
the CI-equivalent full coverage gate (`10141 passed, 39 skipped, 5 deselected`,
85.14% branch coverage), release-integrity test, docs build, package build,
twine metadata check, Bandit, and pip-audit. `1.33.4` is ready for commit,
push, tag, and CI release verification.

## 2026-06-25 Local Backend Freedom Slice: Availability-to-Backend Bridge

The next local-only step after `1.33.4` is complete: provider availability
snapshots can now feed the capability router without live provider calls.

Implemented locally:

- `backend_with_availability()` annotates one `BackendCapabilities` row from a
  matching `ProviderQuotaSnapshot`.
- `backends_with_availability()` applies that adapter across a route candidate
  set.
- Cloud backends match snapshots by sanitized `metadata["provider"]` or backend
  id.
- Local backends can match the generic `local_openai_compatible` snapshot, so
  Ollama, LM Studio, llama.cpp server, vLLM, LocalAI, and similar services share
  one local availability path.
- Availability metadata is deliberately small and sanitized: no raw endpoint
  URL, installed model name, API key material, account id, or raw exception
  payload is copied into routing metadata.
- `primr doctor` now shows the same sanitized availability view for configured
  cloud providers, absent keys, and local OpenAI-compatible service status.

Current estimate:

- 2.0 backend-freedom pillar: about 35-38% complete. The pure route planner now
  accepts availability decisions and doctor exposes those signals, but
  production execution still needs official quota/status collectors where
  supported and stage-by-stage route adoption.
- Full 2.0 release: still about 35% complete because durable research memory
  and production execution adoption remain substantial.

Spend: `$0.00`. Validation for this local slice passed with focused
capability-routing, provider-availability, and doctor tests plus ruff, format,
mypy, architecture checks, and diff checks on the touched paths. No GitHub or
PyPI upload was performed.

## Quality Rubric for this work
- Correctness: structural + prompt + tests.
- No brittle: only prose-invariant checks.
- Simplicity: incremental on existing.
- Maintainability: comments reference agentic-balance.
- All changes TDD-ish, self-reviewed as senior principal (HATE slop).

All via existing seams (BundledFile, role_references, authoring prompt +
body_quality markers, validator signals, packager report). No new giants, no
second seams, deterministic structure preserved, zero external spend. Tests +
full gates (ruff/mypy/pytest) updated. This advances ROADMAP §15 and directly
implements the user's condensed takeaway for higher-leverage, higher-quality
emitted skills. CURRENT-STATE now reflects the generator produces skills that
are small, composable, trigger-clear, script-equipped, verifier-rich, Gotchas-
living, and progressively disclosed.

## 2026-06-26 Budget Policy Honesty

The budget-control surface is now explicit about the distinction between
estimate gates and runtime optional-stage checkpoints.

Current state:

- `--budget` always refuses to start when the pre-flight estimate exceeds the
  approved ceiling.
- Fast full-report runs have runtime checkpoints for optional spend:
  research deepening, cross-validation enrichment, contradiction resolution,
  and strategy generation.
- Premium, deep, scrape, and non-fast structured paths are estimate-gated only
  until their execution paths gain equivalent spend checkpoints.
- CLI human output, CLI JSON output, and MCP `estimate_run` all expose this
  distinction through one shared `core.budget_policy` helper.
- `cli.py` no longer owns budget activation details; `core.cli_budget` keeps the
  pinned CLI file smaller and easier to reason about.

Alignment:

- Matches current 2026 agent-control best practices: estimate first, bind
  approval to explicit semantics, make high-impact spend behavior machine
  readable, and avoid pretending a control exists where the runtime cannot yet
  enforce it.
- Preserves the local-first, single-job model and introduces no new provider
  calls or paid validation.

Remaining:

- Add real runtime checkpoints to premium, deep, scrape, and non-fast
  structured paths.
- Decide whether the inert `CostGuardHook` orchestration path should receive
  real spend accounting or be removed.

Validation status:

- Focused tests, full MCP suite, architecture/release integrity, Ruff, format,
  mypy, Bandit, pip-audit, and focused budget-module coverage pass.
- Full non-manual/non-integration suite timed out after 10 minutes twice in
  this workspace, once with global coverage and once without. No failing
  assertion output was produced and no Primr pytest workers remained running.

Spend: `$0.00`.

## 2026-06-26 Informal Citation Cleanup Precision

Artifact cleanup no longer treats every bracket containing `cite:` as an
informal citation marker.

Current state:

- Report cleanup and strategy citation normalization share
  `_normalize_informal_cite_brackets()`.
- The helper only rewrites brackets that begin with `cite:` or `cites:`.
- Bracketed prose such as `[we cite: revenue doubled]` is preserved.
- Writer scaffolding such as `[cite: workbook]` is still stripped or normalized
  through the existing citation cleanup flow.

Validation status:

- Focused cleanup/citation suites passed with 201 tests.
- Architecture/release integrity, Ruff, format, and mypy passed.

Spend: `$0.00`.

## 2026-06-26 Fenced-Code Artifact Cleanup

Final artifact cleanup now respects Markdown fenced code blocks for the
scaffolding cleanup path.

Current state:

- `core.report_cleanup` has one shared helper for applying transforms only
  outside Markdown fenced code blocks.
- Final report cleanup preserves literal code examples containing `[workbook]`,
  `[cite: workbook]`, `[cross-ref ## ...]`, `[Analysis: ...]`,
  `[External Sources]`, vendor-research filenames, and word-count markers.
- Strategy cleanup inherits the same fence-aware behavior, including the
  post-citation unresolved section cross-reference strip.
- The same markers are still removed from prose, so shipping artifacts keep the
  existing safety-net cleanup without silently corrupting examples.

Validation status:

- Focused cleanup/citation suites passed with 203 tests.
- Architecture/release integrity, Ruff, format, mypy, Bandit, pip-audit, and
  diff hygiene passed.

Spend: `$0.00`.

## 2026-06-26 Empty-Platform Estimate Clamp

CLI cost estimates now handle the internal empty-platform edge case without
under-pricing AI strategy work.

Current state:

- CLI parsing still normally resolves omitted platforms to recon/default
  behavior.
- If tests or internal callers construct `CLIConfig(platforms=())` while
  AI strategy is enabled, dry-run and `--budget` pre-flight estimates now count
  at least one vendor.
- MCP estimates already had this clamp; CLI estimates now match.

Validation status:

- Focused dry-run, budget, and budget-policy tests pass with 40 tests.
- Ruff check passes on the touched source/test files.

Spend: `$0.00`.

## 2026-06-26 Wayback Per-Hop Redirect Guard

Archived-content recovery now uses the shared SSRF-safe HTTP seam.

Current state:

- `data/scraping/wayback.py:_fetch()` delegates to `data.safe_http.safe_http_get()`.
- Wayback CDX lookups and archived replay fetches now validate the initial URL
  and every redirect hop before connecting.
- Wayback keeps its existing target URL validation before it asks CDX for
  snapshots.
- `NOTES.md` no longer lists Wayback among the remaining intermediate-redirect
  SSRF seams; older scraping clients and the async citation resolver remain.

Validation status:

- Focused Wayback, safe HTTP, and fallback-source tests pass with 99 tests.
- Ruff check, Ruff format check, architecture/release-integrity tests, mypy,
  Bandit, pip-audit, MkDocs build, and diff hygiene pass. MkDocs emitted only
  the repo's existing non-strict link warnings, and the generated `_site`
  directory was removed.
- The CI-shaped non-manual coverage gate passed with `10224 passed, 39 skipped,
  5 deselected` and 85.24% branch coverage.

Spend: `$0.00`.
