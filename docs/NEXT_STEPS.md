# Next Steps

Released baseline: **v1.39.33**

Next implementation candidate: **v1.40.0**

This is Primr's canonical executable queue. It states the next bounded change,
the order in which later release gates unlock, and the evidence required to
advance. It does not assign delivery dates or effort estimates. Version labels
are candidate ship points, not calendar commitments.

Use one source for each kind of information:

| Question | Source of truth |
|----------|-----------------|
| What should be implemented next? | This file |
| What must unlock before a later release band? | [`ROADMAP.md`](https://github.com/blisspixel/primr/blob/main/ROADMAP.md) |
| Why is a workstream designed this way? | [`docs/design/`](design/README.md) |
| What has already shipped? | [`CHANGELOG.md`](CHANGELOG.md) |
| What must the product remain? | [Company Analyst Product Contract](design/company-analyst-product-contract.md) |

When these sources disagree, correct the stale source in the same pull request.
Do not create another active queue in a design document or issue description.

## Product filter

Every release must strengthen the same product: a bare company-and-website
invocation produces an evidence-grounded long-form Strategic Overview and
selected YAML strategy documents as reliable Markdown and Word artifacts.
Primr is a research and consulting-prep tool whose reports mix cited facts with
reasoned strategy that is usually not public. It is not only a fact checker:
quality means grounded research plus sharper, more specific, more useful
strategic thinking, never just more verifiable statements. Primr Zero stays the free-first agent-host path. Provider-backed execution
stays estimate-first, explicitly approved, and budget-governed.

Architecture, providers, ledgers, memory, and agent protocols are supporting
capabilities. They advance only when they improve report quality, execution
choice, safety, reliability, or maintainability without creating a second
product.

## Current executable card

v1.39.33 is the released baseline. It states plainly that Primr's reports mix
cited facts with reasoned strategy and that Primr is not only a fact checker.
v1.39.32 refocuses v1.40 on making the
Strategic Overview, AI Strategy, and skill pack better, checked by side by
side reads instead of human fact adjudication. In v1.39.31, every default route uses the current
provider flagship (Grok 4.7, Gemini 3.8 Flash and 4 Argon, Gemini 3.5
Flash-Lite, GPT-6 Luna and 6.1 Terra, Claude Haiku and Sonnet 5.5) by owner
decision rather than a measured promotion, and estimates disclose scheduled
price changes. In v1.39.30 the evaluator harness adds an
`authority_without_support` variant, so v1.40 judges are also tested on
whether a trust cue substitutes for support. In v1.39.29, `AGENTS.md` is the single agent guide and
`CLAUDE.md` imports it; the operator guide is `clients/primr-operator.md`.
In v1.39.28, Word reports open with the title and
Executive Summary; recorded collection counts move to one closing note, and
writer section envelopes are parsed at the section boundary instead of leaking
as prose. Ambiguous envelopes withhold the polished DOCX. v1.39.27 makes
`primr doctor` warn when OpenAI's
free model list reports a shutdown date the registry does not record; the
check is report-only. v1.39.26 adds the library-only evaluator
validation harness described below and takes reviewed dependency updates; no
judge has been measured with it and it arms no gate. v1.39.25 raises the transitive filelock,
virtualenv, and dnspython security floors, routes OpenAI-only reasoning to
GPT-5.6 Terra after the o4-mini shutdown, and replaces retired OpenAI and xAI
image models. It does not advance the report-quality gate. v1.39.24 refreshes
current provider catalogs and standard/cache prices, fixes prompt-tier accounting and gateway ceilings, and
retains evaluated report defaults. It binds judge comparisons to the original
claims, verdicts, and source captures, rejects incomplete local judge plans, and
excludes failed or changed artifacts from agreement counts. It retains bounded
ingestion, native PDF containment, explicit browser sandbox defaults, and the
patched telemetry/environment dependency floors. It retains provider-specific
model retirement checks, explicit spend gates, the MCP session-resource security
floor, maintained Python 3.11-3.15 support, and the updated direct Gemini catalog.
Keyless startup, diagnostics, streams, collection signatures, and Word evidence
labels now follow the interface rules. Research stages have typed ownership
boundaries and an acyclic first-party import graph. Dependency proposals remain
reviewed and maintainer-authored. These maintenance changes do not advance the
report-quality or backend-promotion gate. The additional security review confines
agent artifact reuse by current-job ownership, bounds HTTP body expansion,
protects Windows scrape paths, and repairs QA and cloud-runner integration.

### v1.40.0 candidate: better reports, AI strategies, and skill packs

**Objective:** make the three things Primr produces as good as they can be:
the Strategic Overview, the AI Strategy, and the skill pack. Strategy analysis
is reasoned judgment, not a set of checkable facts, so quality comes from
better research, synthesis, and writing, not from a validation program.

**Why this is next:** the previous card spent the band building and
validating judges and still could not finish, because it waited on people
adjudicating facts. A report can be fully sourced and still be a list of
facts. The product is the analysis.

**What good looks like:**

- A clear governing view of the company, carried through the report rather
  than restated in every section.
- Specific to this company: its names, numbers, mechanisms, and tensions, not
  consultant boilerplate that would fit any firm.
- Each section adds something new; frameworks support the view instead of
  repeating it.
- Load-bearing claims are well sourced and honestly qualified; ordinary
  context is written plainly, without a hedge on every sentence.
- The AI Strategy and skill pack build on the same company understanding and
  are just as specific.

**How changes are checked:** read the before and after outputs for the same
companies side by side, blind to which is which, and keep the change when it
reads better. Model judges may help as a second opinion, not a verdict. Hard
floors stay automated and blocking: valid citations, valid Markdown and Word
artifacts, and spend and egress limits. Any paid run needs a fresh estimate,
explicit approval, and a cost cap.

**Explicitly outside this card:** provider promotion, unapproved paid runs, a
deterministic prose-quality gate, memory, and a new public command.

**Next, in order (2026-10-28):**

1. Read recent local outputs of all three artifacts and list their most
   visible weaknesses.
2. Fix the biggest ones in the prompts and YAML definitions that own them.
3. Compare before and after on the same companies, using frozen evidence
   where possible so the comparison is free.

## Follow-through after v1.40

1. **Keep improving the artifacts.** The contract's next slices (the company
   working model, then working-model-informed writing) advance when side by
   side reads show they make the reports better.
2. **Then compare backends.** Use frozen evidence and output contracts, record
   quality, reliability, latency, and measured cost, and make an explicit
   promotion decision. Preserve preview status when evidence is inconclusive.

Maintenance that may ship as patch releases meanwhile: client-facing report
polish found in real output, a model-currency recheck against the provider
catalogs before each release, and reviewed dependency updates.

The [evaluation plan](design/eval-plan.md) owns measurement design. These steps
do not authorize paid runs or create another active release card.

## Parallel readiness lanes

These lanes may produce independently safe patch releases, but they do not
reorder the current executable card or bypass their promotion evidence.

### OpenRouter preview

The optional paid route is wired through CLI, MCP, A2A, supervised workers,
estimation, request-level price ceilings, privacy controls, exact-cost capture,
and runtime budget accounting. v1.39.13 makes dry-run budget decisions explicit:
`--budget 10` reports a $10 per-run ceiling, whether the estimate fits, and
whether launch is executable. A smaller ceiling reports launch as blocked.

Remaining promotion gate:

1. Keep hermetic routing, accounting, and budget regressions green.
2. Run representative report-quality and estimate-versus-actual comparisons
   only after an exact estimate, explicit approval, and a cost cap.
3. Retain preview status unless quality, reliability, and accounting evidence
   support promotion. A configured key or successful one-off run is not enough.

The Primr ceiling is per run. An OpenRouter account or key spending limit is a
separate defense-in-depth control and does not replace Primr approval.

### Maintained Python support

The maintenance lane covers Python 3.11 through 3.15, with newest stable 3.15
for development, release tooling, containers, and primary platform checks.
Native dependencies must install across the claimed matrix. Browser sync
runtime checks retain a fail-closed boundary for unverified greenlet builds;
3.15 needs greenlet 3.5.6 or newer. The isolated native fuzz engine remains on
its hash-pinned CPython 3.13 wheel, with its own audit. These runtime changes do
not promote a provider or report-quality gate.

### Documentation integrity

The explicit `primr draft --local BUNDLE` path produces an unvalidated draft
from frozen prep text using an installed model. Keep runtime isolation, source
excerpt review, transactional MD/DOCX artifacts, and truthful coverage in the
free regression gate. Local draft and self-comparison eval rows remain
review-only; full-report or backend promotion still depends on the quality
instruments and independent comparisons above.

Every user-facing patch updates the smallest appropriate surface:

- Keep the root README as the front door.
- Put operator procedures in task guides.
- Keep only the current executable card here.
- Keep dependency order and long-range gates in the roadmap.
- Move completed implementation detail to the changelog.
- Update examples whenever the CLI or machine-readable contract changes.

### Protocol and plugin currency

Track specification revisions, SDK releases, and host-client acceptance
separately. Current MCP core compatibility does not imply Tasks, OAuth
discovery, or every client extension. Agent Plugins schema validity does not
prove executable availability, writable state, host authorization, or runtime
support. Use the [compatibility review](ROADMAP_REVIEW.md) as a dated evidence
snapshot, then recheck primary sources when upgrading. Keep transport and
installed-layout regressions in the normal free release gate.

## Version gates after v1.39.33

Later bands advance in dependency order. A version is cut when its exit criteria
hold, not because a date or effort estimate was written down.

| Candidate | Capability gate | Depends on |
|-----------|-----------------|------------|
| **v1.40** | Visibly better Strategic Overviews, AI Strategies, and skill packs, confirmed by side by side reads | Stable report contract |
| **v1.41** | Measured host-versus-cloud promotion decision and honest single-provider full-report execution | v1.40 measurements |
| **v1.42** | Durable agent job lifecycle and remaining MCP/A2A control-plane parity | Stable provider execution and existing authorization contract |
| **v1.43** | Governed run history, retention/deletion/export, evidence anchors, and a shadow finding/inference ledger | v1.40 measurements and v1.42 consumption boundaries |
| **v1.44+** | Claim-aware section packets, progressive artifacts, and further cost levers | Representative ledger evaluation |
| **v2.0** | Measured analyst quality, backend freedom, and safe delegation hold together | Completion of the required 1.x pillars |
| **v2.x** | Strategy Delta and measured repeat-engagement continuity | Proven report lift without weaker freshness, privacy, uncertainty, or cost |
| **v3.0** | VLM-first extraction, vertical compounding, and stable post-artifact handoff | Mature 2.x evidence and contracts |

## Release and version update protocol

Use this order for every release. It keeps planned versions distinct from
published versions and prevents package, docs, tag, and registry drift.

1. **Name the candidate.** Put one candidate version and one executable card in
   this file. Keep `ROADMAP.md` Current State on the latest published version.
2. **Implement atomically.** Record user-facing changes under Changelog
   `[Unreleased]`. Do not pre-claim completion in the roadmap.
3. **Prove the exit criteria.** Run focused regressions first, then the complete
   release gate. Record paid measurements only when separately approved.
4. **Choose the final semantic version.** Use a patch for compatible fixes and
   polish, a minor for a compatible capability, and a major only for the stated
   product-contract gate.
5. **Synchronize version surfaces in one release change.** Update
   `pyproject.toml`, `src/primr/__init__.py`, `uv.lock`, `CITATION.cff`, plugin
   manifests, the OpenClaw image default, roadmap Current State and release
   ledger, the docs index currency line, and the dated changelog heading.
6. **Advance this queue.** Mark the released baseline and name the next
   candidate card before merging the release change.
7. **Merge through a green pull request.** Delete the feature branch and verify
   the exact merge commit through the independent `main` workflows.
8. **Publish from the green commit.** Tag that exact commit, let trusted
   publishing create GitHub and PyPI artifacts, and verify their hashes.
9. **Verify the installed product.** Upgrade the supported local launcher,
   confirm `primr --version`, and run a nonbillable smoke check.

If any publication or verification step fails, do not advance Current State or
the next executable card. Correct the release record before starting new work.

## Explicitly not next

- Another README expansion or competing roadmap summary.
- A provider promotion based on connectivity alone.
- A deterministic prose-quality gate or a lone LLM judge.
- A claim-aware rewrite before the representative ledger evaluation.
- Memory before retention, deletion, provenance, and freshness rules.
- A generic orchestration framework, daemon, SaaS surface, or new runtime
  without a measured product bottleneck.

## Standing validation policy

Use free local validation first. Deterministic checks guard spend, egress,
filesystem writes, schemas, citation resolution, version integrity, and other
prose-invariant structure. Content quality is judged by reading whole
outputs side by side, blind where practical; model judges are a second
opinion, not a gate. Every paid evaluation or
run requires an exact estimate, explicit approval, and a cost cap.
