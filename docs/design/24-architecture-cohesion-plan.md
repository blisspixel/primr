# Architecture Cohesion and Agent-Maintainability Plan

Status: P0 complete, P1 queued, evidence refreshed 2026-07-14

## Goal

Keep Primr easy to understand and extend under repeated human and agent-driven
change. A module should exist because it owns one coherent reason to change,
not merely because another file reached a line threshold. The plan therefore
targets both failure modes: oversized coordinators and fragmented helper files
that add navigation without an independent boundary.

## What the repository shows

The current medium-trust code graph at commit `2d0cccf` is schema-valid,
artifact-consistent, and passes 10 of 10 spot checks. Its automation records
show:

- 416 non-`__init__` Python source modules, with a median size of 275 physical
  lines. Thirty are below 60 lines, 62 are below 100, and 13 exceed 1,000.
  Primr is therefore not globally dominated by tiny files. It has local
  fragmentation and local concentration at the same time.
- `core/` is the clearest navigation problem: 79 modules, a 222-line median,
  only 29 percent of resolved internal imports staying within the package, and
  one resolved import-cycle component spanning 23 core modules.
- Four first-party import-cycle components are present. Two are narrow pairs:
  `ai.deep_research` with `ai.file_search_resources`, and `config.models` with
  `config.settings`. Two are broad components spanning orchestration, routing,
  configuration, data, QA, and provider code.
- Ten low-blast, single-consumer modules under 80 lines have no directly mapped
  test. Manual review found different outcomes: `worker_environment.py` owns a
  least-privilege secrets boundary; `temporary_files.py` owns file lifetime;
  `hiring_signal_routing.py` owns body-free telemetry; and
  `cli_validation_policy.py` owns provider-key policy. Their small size alone
  is not evidence for merging. `strategy_loop.py` is a real consolidation
  candidate because its strategy-progress helpers have one consumer and no
  independent policy boundary. `data/scraping/compat.py` is empty and unused.
- The current architecture fitness suite has a useful maximum-file-size
  ratchet, but its prescribed response is always to split. Without a matching
  cohesion and dependency-direction rule, that one-sided incentive can create
  the exact file proliferation this plan is intended to prevent.

Graph limitations remain explicit. Dynamic dispatch, dependency injection,
local imports, and protocol implementation edges are partial. Every proposed
refactor must verify the relevant source and tests before editing.

## What current external evidence says

- [SlopCodeBench, revised 2026-05-07](https://arxiv.org/abs/2603.24755)
  evaluates iterative agent changes rather than one-shot patches. It reports
  structural erosion in 77 percent of trajectories and rising verbosity in
  75.5 percent; explicit quality prompting improves the initial state but not
  the degradation rate. Repository fitness functions and reviewable boundaries
  are therefore more credible controls than prompt rules alone.
- [DORA's 2025 AI-assisted development report](https://dora.dev/research/2025/dora-report/)
  characterizes AI as an amplifier of the underlying engineering system. That
  supports strengthening dependency direction, tests, and review signals before
  increasing autonomous change volume.
- [Google's small-change guidance](https://google.github.io/eng-practices/review/developer/small-cls.html)
  says smallness is conceptual rather than a simplistic line count. The
  matching [code-health standard](https://google.github.io/eng-practices/review/reviewer/standard.html)
  requires each change to leave overall code health no worse. Primr should
  measure focused change scope and architecture drift, not reward file count.
- [Sawada et al., revised 2026-05-09](https://arxiv.org/abs/2605.06464)
  examined more than 1,000 agent-generated files across 100 repositories and
  found that humans performed the large majority of subsequent maintenance.
  Clear ownership and navigability remain human-facing production requirements.

## Boundary test

A small module is justified when at least one of these is true:

1. It owns a security, cost, filesystem-lifetime, protocol, or trust invariant.
2. It is an adapter around an optional or replaceable external dependency.
3. It has two or more production consumers with a stable public contract.
4. It provides an isolated deterministic seam whose tests would otherwise need
   to mock an orchestrator.
5. It is a composition root that deliberately absorbs wiring.

Otherwise, a single-consumer helper should normally live with the cohesive
behavior that changes with it. A large module may be split only when the new
boundary passes the same test. Moving lines without improving dependency
direction, independent testability, or change ownership is not a refactor.

## Ranked implementation plan

### P0: Make dependency direction a fitness function

1. Remove the unused empty compatibility module.
2. Break the two narrow import cycles without adding new source modules:
   resource cleanup must not import its high-blast consumer, and model pricing
   must not import the settings object that already depends on model defaults.
   Package re-export edges exposed two more pre-existing components during
   checker review. Break those by locating the shared legacy configuration
   exception in the existing dependency-leaf types module and importing the
   URL-security submodule directly, rather than hiding package edges from the
   graph.
3. Add an AST-based import-cycle ratchet to `tests/test_architecture.py`.
   Existing broad components are an explicit burn-down baseline; any new cycle
   or growth fails. Package `__init__.py` re-export edges are included. Add a
   no-empty-source-module rule, with `__init__.py` excluded from that rule.

Acceptance criteria:

- Resolved first-party cycle components fall from four to two.
- No source module is added; the empty module is removed.
- Import order is clean in fresh interpreters.
- Architecture tests explain both the maximum-size and cohesion rules.
- Ruff, format, mypy, focused tests, and repository coverage remain green.

### P1: Burn down the broad core cycle by dependency direction

Produce the exact edge ledger for the package-inclusive 25-module core
component and remove one verified back edge per atomic change. Prefer passing
immutable values or a small existing protocol from orchestrator to stage over
importing an orchestrator from a stage. Do not create interface files solely
to move an import.

Acceptance criteria for each batch:

- The largest strongly connected component shrinks and never grows.
- Source module count is non-increasing unless the new module owns a boundary
  under the boundary test above.
- Public CLI, MCP, and A2A behavior is unchanged.
- Tests cover the moved behavior through its owning module, not only through a
  large coordinator.

### P2: Consolidate unjustified single-consumer helpers

Verify `core/strategy_loop.py` against `core/fast_run_strategy.py` and its one
caller. If they share the same change reason, move the helpers into the stage
owner, preserve public compatibility only where an external import exists, and
delete the helper module. Review the remaining graph candidates one at a time;
keep the security, policy, filesystem-lifetime, and telemetry seams named above.

Acceptance criteria:

- Each consolidation removes at least one navigation hop and one source file.
- No destination crosses its pinned line ceiling or gains unrelated
  responsibilities.
- Direct tests identify the new owner and preserve behavior.
- There are no compatibility shims without a verified external consumer.

### P3: Continue large-file reduction by behavior, not quotas

The 13 pinned oversized modules remain debt, but extraction is valuable only
when it produces directed dependencies and isolated tests. Prioritize
`research_agent.py`, `deep_research.py`, and `cli.py` by blast radius and churn.
For every extraction, record the old and new cycle size, import fan-out,
direct-test mapping, and module-count delta. Reject an extraction that merely
turns one long file into several mutually dependent files.

## Completed first task and next task

P0 completed on 2026-07-14 without adding a source module. Four
package-inclusive cycle components fell to two, the unused empty module was
removed, both import orders pass in fresh interpreters against the local source
tree, and the repository passed 12,718 tests at 86.20 percent branch coverage.
The next task is P1: produce the exact internal edge ledger for the remaining
25-member core component and remove its lowest-risk back edge as one atomic,
behavior-preserving change.
