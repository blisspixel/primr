# Core Package

`primr.core` owns the CLI and the orchestration that turns one company request
into research artifacts. Collection belongs in `primr.data`, model execution in
`primr.ai`, rendering in `primr.output`, and analysis gates in `primr.qa`.

## Concern map

| Area | Modules | Responsibility |
|------|---------|----------------|
| CLI surface | `cli.py`, `cli_*.py` | Parsing, noun/verb dispatch, preflight, estimates, budgets, recovery, and command output |
| Shared run entry | `research_agent.py` | CLI research dispatch, recon integration, mode selection, and final run coordination |
| Default pipeline | `fast_run_setup.py`, `fast_run_collection.py`, `fast_run_hiring.py`, `fast_run_gaps.py`, `fast_run_workbook.py`, `fast_run_sections.py`, `fast_run_validation.py`, `fast_run_trust.py`, `fast_run_strategy.py`, `fast_run_summary.py` | Ten extracted, independently tested fast-pipeline stages |
| Stage support | `insights_assembly.py`, `fast_mode_helpers.py`, `section_*.py`, `report_cleanup.py` | Pure assembly, planning, parsing, prompting, and cleanup helpers used by the stage modules |
| Deep and premium paths | `research_orchestrator.py`, `deep_research_runner.py`, `deep_run_summary.py`, `deep_run_trust.py` | Structured and Deep Research orchestration, trust processing, and finalization |
| Stage capabilities | `stage_inventory.py`, `stage_route_comparison.py`, `stage_eval_scorecard.py` | Production requirements plus body-free route and evaluation evidence |
| Source selection | `source_relevance.py`, `source_relevance_eval.py`, `context_curation.py` | Source filtering, bounded context preparation, and evaluation fixtures |
| Strategy | `ai_strategy.py`, `ai_strategy_runtime.py`, `strategy_*.py` | Strategy prompt assembly, generation loops, platform context, and artifacts |
| Workspace and state | `workspace.py`, `run_state_io.py`, `resilience_listeners.py` | Working directories, durable local state, events, and recovery signals |
| Domain types | `report_models.py`, `research_framing.py`, `hypothesis_tree.py` | Report data, operator framing, and hypothesis structures |
| Composition | `container.py` | Dependency injection for replaceable clients and stores |

## Current execution shape

```text
primr.core.cli:main
        |
        +-> validate input, run preflight, estimate, enforce approval/budget
        |
        v
research_agent.perform_research
        |
        +-> scrape request: site corpus and insights
        +-> default full request: extracted fast_run stages
        +-> deep or premium request: Deep Research orchestration
        |
        v
output rendering, QA, verification, inventory, and usage records
```

The public command choices are the default full run, `--mode scrape`,
`--mode deep`, and the opt-in `--premium` path. Internal names such as
`scrape-only`, `deep-research`, `structured`, and `complete` are compatibility
and dispatch details, not additional user-facing pipelines.

The detailed fast-stage data flow is documented in
`docs/design/23-orchestrator-refactor-map.md`. Current command selection and
cost behavior are documented in `docs/RUN_MODES.md`.

## Package boundaries

- New orchestration enters through the existing run and stage seams instead of
  creating another site-to-report workflow.
- Billable execution remains behind estimate, approval, and runtime budget
  policy.
- Async-to-sync calls use `primr.utils.async_utils.run_sync`.
- Console, logging, configuration, and atomic state writes use the shared seams
  named in the root `CLAUDE.md`.
- MCP and A2A background job ownership stays in their transport packages; core
  supplies research operations and artifacts.
