# Next Steps

Released baseline: **v1.39.13**

Next implementation candidate: **v1.39.14**

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
Primr Zero stays the free-first agent-host path. Provider-backed execution
stays estimate-first, explicitly approved, and budget-governed.

Architecture, providers, ledgers, memory, and agent protocols are supporting
capabilities. They advance only when they improve report quality, execution
choice, safety, reliability, or maintainability without creating a second
product.

## Current executable card

### v1.39.14 candidate: remove one orchestration back edge

**Objective:** reduce the remaining 11-module core import-cycle component by
moving one behavior-owned dependency in `fast_run_sections` to its proper
owner. Preserve every public CLI, MCP, A2A, report, estimate, and approval
contract.

**Why this is next:** the quality and backend milestones depend on stable,
directly testable stage boundaries. This is the lowest-risk remaining
architecture slice and requires no provider call or paid evaluation.

**Order of work:**

1. Recompute the package-inclusive import graph and record the exact back edge.
2. Audit public imports and compatibility consumers before moving behavior.
3. Pass immutable values or an existing protocol from the composition root.
4. Remove the back edge without adding a forwarding-only module.
5. Add direct owner tests and preserve compatibility tests at the public seam.
6. Run focused architecture tests, then the complete release gate.
7. Ship as v1.39.14 only if every exit criterion below passes. Otherwise keep
   v1.39.13 current and update this card with the observed blocker.

**Exit criteria:**

- The largest strongly connected component falls below 11 modules and cannot
  grow in CI.
- Production module count does not rise unless a new module passes the boundary
  test in the [architecture cohesion plan](design/24-architecture-cohesion-plan.md).
- Golden artifacts, estimates, provider selection, approval, and budget behavior
  are unchanged.
- New behavior is exercised through its owning module, not only through a large
  coordinator.
- Ruff, formatting, mypy, strict docs, security checks, package checks, the full
  test suite, and the branch-coverage floor pass.

**Explicitly outside this card:** report prompt changes, provider promotion,
paid evaluation, broad `deep_research.py` decomposition, memory, and new public
commands.

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

### Python 3.15 readiness

The exact preview interpreter runs as a hard Linux CI lane. Unsafe synchronous
Playwright, Patchright, and Playwright-backed vision tiers fail closed while
safe collection fallbacks remain available.

Promotion to stable support requires all of the following:

1. An official final Python 3.15 release is available.
2. Locked dependencies install on each claimed platform, including Windows.
3. Browser-backed tiers pass without native crashes.
4. The full test matrix passes and package classifiers, installation guidance,
   and CI move together.

Until those gates pass, Python 3.12 through 3.14 remain the stable support
matrix and Python 3.15 remains an explicitly limited preview.

### Documentation integrity

Every user-facing patch updates the smallest appropriate surface:

- Keep the root README as the front door.
- Put operator procedures in task guides.
- Keep only the current executable card here.
- Keep dependency order and long-range gates in the roadmap.
- Move completed implementation detail to the changelog.
- Update examples whenever the CLI or machine-readable contract changes.

## Version gates after v1.39.14

Later bands advance in dependency order. A version is cut when its exit criteria
hold, not because a date or effort estimate was written down.

| Candidate | Capability gate | Depends on |
|-----------|-----------------|------------|
| **v1.40** | Fully decidable epistemic and analyst-quality corpus, followed by a recorded hard-gate decision | Stable report contract and quality instrumentation |
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
prose-invariant structure. Content quality requires pre-registered,
agreement-validated evaluation plus human review. Every paid evaluation or run
requires an exact estimate, explicit approval, and a cost cap.
