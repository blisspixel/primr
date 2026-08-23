# Architecture Cohesion and Agent-Maintainability Plan

Status: P0 complete, P1 in progress, evidence refreshed 2026-08-22

## Goal

Keep Primr easy to understand and extend under repeated human and agent-driven
change. A module should exist because it owns one coherent reason to change,
not merely because another file reached a line threshold. The plan therefore
targets both failure modes: oversized coordinators and fragmented helper files
that add navigation without an independent boundary.

## What the repository shows

The current package-inclusive AST graph and repository inventory show:

- 461 non-`__init__` Python source modules, with a median size of 272 physical
  lines. Thirty-six are below 60 lines, 68 are below 100, and 12 exceed 1,000.
  Primr is therefore not globally dominated by tiny files. It has local
  fragmentation and local concentration at the same time.
- `core/` remains the clearest navigation problem: 105 non-`__init__` modules,
  a 223-line median, and the largest resolved import-cycle component.
- Three first-party import-cycle components remain after P0 and the current P1
  batches: an 11-module CLI/research orchestration component, a five-module
  model-routing component, and a three-module first-party extraction
  component. CI pins their exact memberships and permits only shrinkage.
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

Produce the exact edge ledger for the package-inclusive core
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

## Completed work and maintenance-lane next task

P0 completed on 2026-07-14 without adding a source module. Four
package-inclusive cycle components fell to two, the unused empty module was
removed, both import orders pass in fresh interpreters against the local source
tree, and the repository passed 12,718 tests at 86.20 percent branch coverage.

The first P1 batch completed on 2026-08-13. `Command` and `CLIConfig` now live
in the 202-line `cli_contract.py` owner used by parsing, budgeting, dry-run,
planning, and vendor workflows. `core.cli` still re-exports both names, so the
public import surface is unchanged. Moving this real shared contract and
removing the reciprocal budget/dry-run label dependency reduced the largest
component from 24 modules to 22 and lowered `cli.py` from 2,774 to 2,573 lines.
It added one substantive contract module, not a forwarding shim.

The second P1 batch completed on 2026-08-22 without adding a production
module. Ten modules left the broad component, reducing it from 22 members to
12. The detached members are `cli_init`, `cli_vendor`, `cli_errors`,
`cli_plan`, `section_regeneration`, `fast_run_collection`, `fast_run_gaps`,
`fast_run_setup`, `fast_run_summary`, and `refine`.

The batch removed implementation back edges rather than hiding imports:
`cli` now injects doctor and update callbacks at its composition boundary;
plan, refinement, regeneration, source relevance, workspace allocation, and
session-spend reads call their existing behavior owners directly. Required
public compatibility imports remain available, while tests now import private
doctor and init helpers from their owning modules. Direct owner tests,
composition tests, and both fresh-interpreter import orders cover each removed
pair. The production-module delta is zero, `cli.py` fell from 2,478 to 2,449
lines, and `research_agent.py` fell from 4,276 to 4,262 lines.

Before the second batch, the component contained `primr`, `cli`, `cli_dispatch`,
`cli_doctor`, `cli_errors`, `cli_init`, `cli_plan`, `cli_update`, `cli_vendor`,
`deep_research_runner`, the eight `fast_run_*` stage modules, `refine`,
`research_agent`, `research_orchestrator`, and `section_regeneration`. It now
contained only `primr`, `cli`, `cli_dispatch`, `cli_doctor`, `cli_update`,
`deep_research_runner`, `fast_run_sections`, `fast_run_strategy`,
`fast_run_trust`, `fast_run_validation`, `research_agent`, and
`research_orchestrator`.

The third P1 batch completed on 2026-08-22 without adding a production module.
`fast_run_validation` now receives its report reviewer from the
`research_agent` composition boundary and imports section regeneration and
observed spend directly from their existing owners. This removes the stage
from the broad component, reducing it from 12 members to 11. The remaining
membership is `primr`, `cli`, `cli_dispatch`, `cli_doctor`, `cli_update`,
`deep_research_runner`, `fast_run_sections`, `fast_run_strategy`,
`fast_run_trust`, `research_agent`, and `research_orchestrator`.

The same batch hardened the owned stage rather than preserving known defects:
model-shaped review output is normalized and bounded before use, abandoned
enrichment workers cannot hold interpreter shutdown open, and the optional
cross-validation diagnostic is atomic and fail-open. A shared hostname helper
also replaces every remaining raw string comparison used to exclude
first-party search results, so `www` and subdomain variants cannot be counted
as independent evidence. Direct stage, helper, composition, and both
fresh-interpreter import-order tests pin the behavior. The production-module
delta is zero; `research_agent.py` falls from 4,262 to 4,260 lines and
`fast_run_validation.py` grows from 475 to 515 while remaining a cohesive stage
well below the new-file ceiling.

The next P1 batch should extract one behavior-owned seam from the remaining
11-module component, with `fast_run_sections` the current lowest-risk
candidate. The later P3 `ai/deep_research.py` split remains binding and must
preserve its public facade and provider lifecycle behavior. Do not create an
interface file solely to make the graph look cleaner.

### Safety-boundary cohesion addendum

The 2026-07-15 skill-pack hardening work applied the same boundary test before
release. `eval_validation.py` fell from 923 lines to 340 by moving language
lexing into the 687-line `code_comment_projection.py` trust boundary.
`command_grammar.py` fell from 940 lines to 625 by moving cross-sentence
execution and persistence analysis into the 342-line
`execution_dataflow.py` boundary. `script_safety.py` fell from 878 lines to
749 by moving verifier placement and registry policy into the existing
296-line `verifier_asset.py` owner.

The source-module delta is two. Both additions own independently changing
security grammars, depend in one direction on lower-level lexical policy, and
have direct regression tests as well as packaging-boundary tests. No
compatibility shim or mutually dependent fragment was introduced. This work
does not replace P1, whose scope remains the broad core import component.
