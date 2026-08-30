# Next Steps

This is Primr's canonical execution brief. It answers what to implement next.
`ROADMAP.md` owns long-range direction and the backlog; design documents own
rationale and contracts; `docs/CHANGELOG.md` owns completed implementation
history.

Last reviewed: 2026-08-30.

The [Company Analyst Product Contract](design/company-analyst-product-contract.md)
is the governing feature filter: the bare company-and-website invocation,
evidence-grounded long-form Strategic Overview, YAML-defined strategy
documents, reliable Word delivery, and free-first or approximately $1 approved
execution remain the product. Architecture, backends, ledgers, memory, and
agent surfaces are supporting work.

## Current release objective

Keep billable execution and network egress fail closed while finishing
architecture ownership without changing the flagship report behavior. The
v1.39.10 terminal follow-through extends the v1.39.9 approval contract to
update, init, doctor fix, key setup, shared capability detection, and the
legacy module launcher. Unavailable input fails closed without selecting a
default-yes action. The v1.39.7 ownership batch removed the fast validation
back edge, hardened that optional stage, and made external-evidence hostname
boundaries consistent without changing report behavior. The prior v1.39.5
audit closed cumulative eval budgeting, direct Gemini compatibility-call
accounting, Accordion response and current-budget handling, the agentic
orchestrator's SSRF hook input, and URL-secret redaction on browser and A2A
logs.

Paid-run governance, approval, provider lifecycle, partial recovery, API
currency, run-scoped actual-cost persistence, model-backed improvement gates,
and accepted-job recovery receipts remain complete. The current work is the
zero-spend architecture-cohesion slice below: make report research, provider
lifecycle, writing, and delivery easier to maintain and test before adding
another quality-sensitive stage. No report run or cloud judge is required.

## Completed foundation: report contract correctness

**Status:** complete in this slice; no model spend.

**Deliverable:** align runtime, estimates, and documentation for the active
Standard and Deep/Premium paths.

Required outcomes:

- Premium does not silently discard operator context files.
- Deep/Premium `--verify` either executes after a report is produced or is not
  priced and advertised for that route.
- `target_pages` has an enforceable meaning or is removed with every page-count
  promise that depends on it.
- Architecture and run-mode docs identify active Standard, active Premium,
  compatibility-only, and experimental surfaces.
- The active Accordion path has hermetic tests for input forwarding,
  verification dispatch, pacing, partial recovery, and cleanup.

**Acceptance:** focused tests, Ruff, mypy, strict docs, full non-integration
suite, and the branch-coverage ratchet pass. No billable call is required.

## Completed: zero-spend provider/API currency checkpoint

**Status:** complete after the August 13 re-audit; no model spend.

**Deliverable:** keep the model registry, pricing boundaries, API transport,
storage choices, prompt caching, retry behavior, and actual-cost accounting
aligned with current official provider contracts.

The first audit correctly confirmed Grok 4.6 as the current xAI flagship and
GPT-5.6 Sol/Terra/Luna as the current OpenAI family, but it closed this card too
early. A fresh primary-source check found stale Grok 4.20 price/context data,
the removed Google Interactions `outputs` schema in response parsing, and File
Search uploads that were not awaited before paid research began. Correct the
registry, current `steps` parsing with an explicit legacy fallback, upload
operation lifecycle, SDK floor, retention wording, tests, and cost guidance
before this checkpoint could return to complete. Those corrections and their
hermetic regressions now pass.

**Acceptance:** official source URLs and audit date recorded; no unsupported
model or pricing claim; exact 200k xAI boundary priced correctly for every
active xAI model; current Google `steps` responses and upload operations tested
hermetically; current model registered without silent promotion;
transport/storage/cache decisions tested; dry-run remains network- and
model-call-free. Primary sources: [xAI pricing](https://docs.x.ai/developers/pricing),
[Gemini Interactions changelog](https://ai.google.dev/gemini-api/docs/changelog),
[Deep Research](https://ai.google.dev/gemini-api/docs/deep-research), and
[File Search](https://ai.google.dev/gemini-api/docs/file-search).

## Completed: zero-spend correctness and resilience

**Status:** complete in this slice; no model spend.

**Deliverable:** close the active runtime defects found after the report and
provider currency audits:

- require estimate-bound approval on ordinary CLI and every MCP transport;
- make every advertised dry run incapable of entering a billable delegate;
- prevent duplicate provider jobs after an accepted interaction becomes
  uncertain and retain resources until terminal state;
- fail closed when paid capability routing cannot resolve;
- return and acknowledge durable Markdown when optional DOCX rendering fails;
- verify the actual text artifact for custom destinations;
- clean temporary inputs and unknown-age provider resources conservatively;
- preserve exact usage and cost across retry, refusal, incomplete, and
  tool-only provider responses; and
- reject misleading full-success states for materially incomplete reports.

**Acceptance:** regression tests reproduce each defect without network access,
Ruff and mypy pass, branch coverage remains above 80 percent, the file-size
ratchet does not rise, and all non-integration CI gates pass. No provider call,
model call, dependency install, or paid evaluation is part of this item.

## Completed: zero-spend run-cost audit closure

**Status:** complete in this slice; no model spend.

**Resolution:** completed research manifests now persist a run-scoped usage
delta after optional verification. Failed and cancelled jobs retain `null`
when cost cannot be measured, while a durably published paid Premium partial
reconciles its tracked model usage and accepted Deep Research task once.

**Deliverable:** make the audit trail truthful after execution, including
non-happy paths, without weakening the approval or recovery contracts:

- persist a run-scoped actual-cost delta for completed MCP/A2A research jobs;
- include verification-stage usage when verification ran after the main
  finalizer;
- retain estimate and non-secret approval facts on failed or cancelled jobs,
  while reporting actual cost as unavailable when it cannot be measured
  honestly; and
- reconcile token usage plus the accepted Deep Research task charge before a
  paid partial Premium artifact returns.

**Acceptance:** success manifests and compact usage summaries agree on
estimate, approval binding, ceiling, and actual cost; terminal manifests never
invent a zero; paid partial returns write usage history exactly once; process
and worker-protocol tests prove the values survive isolation; Ruff, mypy,
architecture, and branch-coverage gates remain green. No provider call, model
call, dependency install, or paid evaluation is required.

## Completed: model-backed improvement governance

**Status:** complete in this slice; no model spend.

`primr improve <path> --improve-agentic` and `primr refine "Company"` now
produce bounded dry-run quotes, require explicit approval, honor `--budget`,
reserve the quoted stage cost before model work, and provide one-object JSON
estimate, refusal, and result contracts. Refine prices its maximum nine section
regenerations and three bounded acceptance audits; it normally stops earlier.
Plain `primr improve <path>` remains deterministic, local, and ungated.

## Optional later: paired report-quality baseline

**Status:** designed but explicitly deferred. No budget is approved. Run only
when the operator decides the product question is worth paid measurement.

**Deliverable:** five representative company profiles run through both
Standard and Premium, producing ten blinded artifacts evaluated on identical
pre-registered dimensions.

Measure evidence support, contradiction handling, source authority and
independence, uncertainty and label honesty, argument arc, repetition,
terminology consistency, and citation resolution. Use agreement-validated
judges plus human adjudication of disagreements. Do not add regex content gates
or assume serial or concurrent writing wins before measurement.

**Acceptance:** every selected dimension is decidable, every judge disagreement
is adjudicated, structural citations resolve, and the body-free decision record
states whether Premium provides a meaningful quality lift. See
[`design/premium-quality-eval.md`](design/premium-quality-eval.md).

**Cost guard if later approved:** stage at cumulative ceilings of $5, $15, and
$25. The $25 figure is an absolute maximum, not an expected budget or target.
Prefer local scoring, estimate every exact command, and obtain explicit
approval before execution. A positive Premium quality claim still requires all
five pairs; if they cannot fit under the approved ceiling, stop as
inconclusive.

## Next executable slice: architecture ownership without behavior drift

**Status:** the v1.39.7 architecture batch remains implemented and locally
validated after the v1.39.10 terminal and launcher polish. The full
non-integration suite passed with 14,644 tests, 57 skips, and 5 deselections.
The most recent measured branch coverage was 86.86 percent against the 81
percent floor. The
first P1 batch
reduced the largest import-cycle component from 24 modules to 22, the second
reduced it from 22 to 12, and this batch reduces it
from 12 to 11. The stage now receives its reviewer through composition and
uses the existing regeneration and spend owners directly. Malformed review
results, abandoned enrichment workers, and optional diagnostic-write failures
degrade safely. Every remaining raw URL-string filter was replaced with one
tested hostname-boundary helper so first-party variants and subdomains cannot
be treated as independent external evidence.

**Deliverable:** publish the validation ownership batch recorded in
[`design/24-architecture-cohesion-plan.md`](design/24-architecture-cohesion-plan.md).
The next behavior-owned extraction should remove one remaining fast-stage back
edge, with `fast_run_sections` the lowest-risk candidate from the current
graph. Then reduce `ai/deep_research.py` into a few one-way, behavior-owned
boundaries:

1. public compatibility facade;
2. provider interaction, polling, job, and File Search lifecycle; and
3. Premium dossier, sequential section writing, and assembly.

Deprecate or quarantine dormant single-call, architect, executor, aggregator,
and manual Accordion surfaces only after public-API and CLI compatibility are
audited. The ownership split and compatibility work do not require a paid
baseline because they must preserve behavior. Preserve serial Premium writing,
and defer changes to citation, contradiction, repetition, terminology, or
other report-quality behavior until a measured baseline justifies them.

**Acceptance:** no golden-artifact or eval regression, one-way dependencies,
no mutually dependent micro-modules, and coverage rises on the extracted seams.
The boundary test is
[`design/24-architecture-cohesion-plan.md`](design/24-architecture-cohesion-plan.md).

## Parallel portability lane

**Agent Plugins v1 status:** implemented in the current slice. The experimental
portable package is generated from canonical Primr skills using root
`plugin.json`, `skills/`, and `mcp.json`, with pinned-schema and drift tests.
Keep the Claude package as a host adapter, claim only smoke-tested clients, and
never let plugin loading or skill invocation bypass Primr's estimate and
approval contract. Revalidate when the Working Draft changes.

**OKF v0.2 status:** design contract updated in the current slice. Keep the
polished report unchanged and use OKF only as the future findings-interchange
shape for memory, claim-store export, and handoff. Implement serialization
when those consumers exist. Primr confidence remains distinct from OKF
verification. See
[`design/open-knowledge-format.md`](design/open-knowledge-format.md).

**Run-scoped epistemic ledger status:** design adopted, not a current execution
card. The planned native contract evolves the existing source index with
digest-bound evidence anchors, then adds run-local findings and strategic
inferences in shadow mode. A small declarative ontology may compile type and
relation legality into structural validators, but models or humans still own
semantic support, contradiction, qualification, and supersession. This does
not change the current architecture-ownership slice, reopen the v1.40
calibration decision, advertise new artifacts, or make report prose depend on
the ledger. See
[`design/run-epistemic-ledger.md`](design/run-epistemic-ledger.md).

## Later, in dependency order

1. Complete the fully decidable epistemic and analyst-quality baseline for the
   bare company-and-website run after an exact estimate and explicit spend
   approval. No budget is currently approved.
2. Controlled live host-versus-cloud source-relevance comparison, after spend
   approval and the quality instruments above.
3. Residual single-provider execution cleanup.
4. MCP Tasks and remaining control-plane parity where client demand is clear.
5. Finish research-memory layer 1: automatic pipeline attachment, retention,
   deletion, freshness, and export; then add source receipts, exact-when-owned
   evidence anchors, and a shadow run-scoped finding/inference ledger. Measure
   it against the v1.40 corpus before any writer promotion.
6. Promote claim-aware section packets only from representative evidence, then
   continue progressive artifacts, cost levers, and measured runtime overlap.
7. Promote repeat-engagement memory only when it improves the next company
   report without weakening freshness, uncertainty, privacy, or cost. Keep
   Strategy Delta and selective regeneration in 2.x.

The version ladder remains v1.40 quality readiness, v1.41 backend freedom,
v1.42 control-plane completion, and v1.43 run continuity plus the shadow
ledger. v2.0 requires measured analyst quality, backend freedom, and safe
delegation together; indexed memory joins that release only if representative
evaluation proves report lift.

## Explicitly not next

- A new `--long` alias or overlapping product tier.
- Naive independent chapter fan-out for lower wall-clock time.
- A deterministic prose-quality gate or a lone LLM judge.
- An OKF wrapper around the narrative report or a new OKF platform.
- Canonical prose memory, report-to-claim re-extraction as the target, or a
  claim-aware report rewrite before the shadow ledger clears representative
  evaluation.
- A generic belief/argument graph, RDF stack, ontology service, or semantic
  relation validator built before the run finding/inference records exist.
- Deletion of importable compatibility APIs without a compatibility audit.
- A generic agent orchestration framework, daemon, or new implementation
  language without a measured product bottleneck.

## Standing validation policy

Use free local validation first. Deterministic checks guard spend, egress,
disk, schemas, citation resolution, and other prose-invariant structure.
Content quality is measured through pre-registered, agreement-validated
evaluation and human review. Every paid evaluation requires an exact estimate,
an explicit cost cap, and approval before launch.
