# #23 Orchestrator Refactor: Stage Map for `perform_fast_research`

Companion to [1x-completion.md](1x-completion.md) workstream 2. This is the
verified structural map the extraction works from — line numbers are
approximate (they drift with each extraction; anchor by the stage banner
comments and named calls). Rules: **no behavior change**, one batch per PR,
full suite green per slice, eval scores unchanged.

## Stage map (inputs → outputs → side effects)

| # | Stage | Anchor | Notes |
|---|-------|--------|-------|
| 0 | Setup & model resolution | — | **EXTRACTED** → `core/fast_run_setup.resolve_fast_run_setup()` (frozen `FastRunSetup`) |
| 1 | Data collection | `fetch_web_content` call → external validation pools | Highest complexity: parallel pools with deadlines, quality filtering. **Extract LAST** |
| 2 | Hiring signals | `gather_hiring_signals` | **EXTRACTED** → `core/fast_run_hiring.collect_hiring_block()` |
| 2B | Combined insights build | writes `insights.txt` | **EXTRACTED** → `core/insights_assembly.py` (pure assembly; both build sites call it, file write stays in orchestrator) |
| 3 | Gap analysis + deepening | `_fast_gap_analysis` → gap pools | Mutates source_urls/external_* sets and REBUILDS external_sources_raw + insights.txt |
| 4 | Analysis workbook | `_build_fast_analysis_prompt` | **EXTRACTED** → `core/fast_run_workbook.generate_analysis_workbook()` — returns `(workbook, reasoning_session)` so the lazily-constructed session still reaches stage 6 |
| 5 | Section writing | `_group_sections_by_part` → per-part pools | Exec summary popped + written last with ALL prior sections; default-arg closure binding; per-part frozen snapshots |
| 6 | Cross-validation + enrichment | `_fast_cross_validate` → weak-section loop | Regex find+splice mutates report_content serially; per-section 300s deadline; diminishing-returns detector; reuses stage-4 session |
| 7 | Trust polish + citation repair | `_polish_fast_report_for_trust` chain | **EXTRACTED** → `core/fast_run_trust.polish_and_gate_fast_report()` (frozen `FastTrustResult`); the LLM polish/repair helpers stay in research_agent (lazy-imported) until their own extraction |
| 8 | Artifact assembly | `_convert_deep_research_to_docx` | Thin (~25 lines). DECISION: kept inline — extracting a 25-line wrapper around an already-extracted function adds indirection without testability gain; fold into the eventual FastRunContext pass |
| 9 | Strategy generation | budget checkpoint → vendor closures | **EXTRACTED** → `core/fast_run_strategy.run_strategy_phase()` (frozen `StrategyPhaseResult`); budget checkpoint, per-vendor closures + parallel dispatch, YAML loop all moved verbatim |
| 10 | Summary & usage | — | **EXTRACTED** → `core/fast_run_summary.finalize_fast_run()` |

## The thread (locals consumed across many stages → future run-context object)

`display_name`, `folder_path`, `grok_reasoning`, `grok_writing`,
`grok_reasoning_effort`, `reasoning_session` (lazy at 4, reused at 6),
`source_urls` + `source_urls_seen` (mutated 1/3/6), `external_sources_raw`
(built 2B, rebuilt 3, read 4/5/9), `raw_corpus` (immutable after 1),
`analysis_workbook` (4 → 5/6/9), `report_content` (5, mutated 6/7),
`written_sections`, `validated_source_count`/`validated_source_urls`,
`pages_scraped`. Introduce a frozen-ish `FastRunContext` dataclass only after
several stages are out — premature centralization couples stages that are
about to move.

## Tangle points (handle with care)

1. **External-sources mutation across the gap phase** — preserve O(1)
   `source_urls_seen` dedup and the rebuild-don't-mutate pattern for
   `external_sources_raw`.
2. **Closure capture in cross-validation enrichment** — `_enrich_section_work`
   uses default-arg binding (late-binding trap) and feeds mutations back to
   outer scope; thread parameters explicitly when extracting.
3. **Per-part frozen snapshots in section writing** — `prior_sections =
   list(written_sections)` before each pool; exec summary gets ALL priors.
4. **Regex splice loop in cross-validation** — sections spliced serially into
   `report_content`; later patterns depend on earlier splices. Never
   parallelize/reorder.
5. **Lazy reasoning-session construction** — stage 4 creates it, stage 6
   reuses it; extraction must pass the session as shared context.
6. **Function-wide try/except** — swallows everything and returns None; when
   stages move out, keep their internal try/excepts intact and leave the
   outer catch-all's semantics unchanged until a deliberate later decision.
7. **Deadline + shutdown pattern** (`wait=False, cancel_futures=True` +
   `detach_running_workers`) — copy precisely; it prevents hung-thread exit
   blocks.

## Extraction order (batched; each batch one PR)

- **Batch A (lowest risk) — DONE:** stage 10 (fast_run_summary.py), stage 0
  (fast_run_setup.py); stage 8 deliberately kept inline (see table)
- **Batch B (deterministic polish) — DONE:** stage 7 (fast_run_trust.py),
  stage 2B (insights_assembly.py)
- **Batch C (contained closures) — DONE:** stage 9 (fast_run_strategy.py),
  stage 4 (fast_run_workbook.py), stage 2 (fast_run_hiring.py)
- **Batch D (section context):** stage 5
- **Batch E (research deepening):** stage 3
- **Batch F (data collection, last):** stage 1

After F: introduce `FastRunContext`, raise research_agent per-module
coverage target to 80%, enable `C901` complexity budget repo-wide, then the
same treatment for `deep_research._execute_consulting_research` (~270 lines,
split dossier phase from section-writing phase).

## Already-extracted helpers the stages delegate to

`fast_mode_helpers` (QA metrics, assembly, parsing guards),
`section_planning` / `section_prompts` / `section_parsing`,
`report_cleanup` (polish/citations/repair), `strategy_artifacts`,
`run_state_io`, `pipeline.integration` (recovery wrappers),
`strategy_generation` (enrich/prepare/save), `data.hiring_signals`,
`fast_run_summary` (stage 10).
