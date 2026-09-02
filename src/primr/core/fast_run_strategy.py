"""Fast-run strategy-generation stage (roadmap #23, Batch C).

Extracted from stage 9 (Phase 6 banner) of ``perform_fast_research``. Contains
the --budget checkpoints (at stage entry, and again per YAML strategy so a
multi-strategy run stops generating once the ceiling is reached), the per-vendor
AI strategy closure with its parallel dispatch, and the YAML-defined strategy
loop (customer_experience, security, data_fabric, skills, ...).

The LLM-prompt/enrich/output helpers stay in research_agent (lazy-imported)
until their own extraction, mirroring the Batch A/B pattern.

Side effects preserved from the original: phase banner/completion, strategy
QA console lines, run-budget warning, per-strategy artifact writes via
``_save_strategy_output``, and legacy per-role SKILL.md emission for the
``skills`` YAML strategy.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from primr.core.strategy_context import read_stable_vendor_context_block
from primr.core.strategy_outcome import (
    StrategyOutcome,
    StrategyOutcomeTracker,
    expected_strategy_targets,
    persist_strategy_outcome,
    strategy_target,
)
from primr.core.strategy_prompt_parts import (
    AI_STRATEGY_ARTIFACTS,
    YAML_STRATEGY_ARTIFACTS,
    build_strategy_context_prefix,
    build_strategy_prompt_parts,
    read_artifact_blocks,
)
from primr.core.vendor_refresh_outcome import (
    VendorRefreshOutcome,
    VendorRefreshTracker,
    persist_vendor_refresh_outcome,
)
from primr.core.vendor_research import (
    get_or_generate_vendor_research_sync,
    get_vendor_research_path,
)
from primr.pipeline.llm_failover import LLMRole, call_with_failover
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured
from primr.utils.run_budget import skip_stage_if_cost_would_exceed, skip_stage_if_over_budget

logger = get_logger("core.fast_run_strategy")


def _read_stable_research_block(
    path_value: str | Path,
    *,
    header: str,
    context_kind: str,
) -> str | None:
    """Read one bounded vendor input through the shared stable snapshot seam."""

    return read_stable_vendor_context_block(
        path_value,
        header=header,
        context_kind=context_kind,
    )


def _read_cached_agnostic_research_block() -> str | None:
    """Return existing cross-industry context without generating or refreshing it."""

    try:
        path = get_vendor_research_path("agnostic")
    except Exception as exc:
        logger.warning(
            "Could not locate cached cross-industry AI Strategy context (%s)",
            type(exc).__name__,
        )
        log_structured(
            "warning",
            "Fast mode strategy context unavailable",
            context_kind="cross_industry",
            failure_type=type(exc).__name__,
        )
        return None
    return _read_stable_research_block(
        path,
        header="Cross-industry AI research",
        context_kind="cross_industry",
    )


@dataclass(frozen=True)
class StrategyPhaseResult:
    """Outputs of the strategy stage that the orchestrator threads onward."""

    strategy_paths: dict[str, str] = field(default_factory=dict)
    strategy_trust_stats: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)
    vendor_refresh_tasks_started: int = 0
    strategy_outcome: StrategyOutcome = field(
        default_factory=lambda: StrategyOutcome("not_requested", (), (), (), ())
    )
    vendor_refresh_outcome: VendorRefreshOutcome = field(
        default_factory=lambda: VendorRefreshOutcome("not_requested", (), (), (), (), ())
    )


def run_strategy_phase(
    *,
    has_strategies: bool,
    ai_strategy: bool,
    platforms: list[str] | None,
    strategy_types: list[str] | None,
    company_label: str,
    website: str | None,
    report_content: str,
    analysis_workbook: str,
    validated_source_urls: list[str],
    discovery_notes_content: str | None,
    refresh_vendor_research: bool,
    grok_reasoning: str,
    grok_writing: str,
    folder_path: str,
    output_dir: str | None,
    diagnostics_dir: str | None,
    write_txt: bool,
    recovery_executor,
    total_phases: int,
    base_report_complete: bool = True,
) -> StrategyPhaseResult:
    """Generate strategy documents only after the base report is complete."""
    # Lazy import: research_agent imports this module, so the prompt-build,
    # enrichment, and output helpers (which stay there until their own
    # extraction) must be resolved at call time to avoid a circular import.
    from primr.core.research_agent import (
        _build_ai_strategy_prompt,
        _build_strategy_prompt_from_yaml,
        _compute_session_llm_cost,
        _enrich_strategy_content,
        _prepare_strategy_for_output,
        _save_strategy_output,
    )

    strategy_paths: dict[str, str] = {}
    strategy_trust_stats: list[tuple[str, list[tuple[str, str]]]] = []
    vendor_refresh_tasks_started = 0
    requested_strategies = (["ai"] if ai_strategy else []) + [
        name for name in strategy_types or [] if name != "ai" or not ai_strategy
    ]
    outcome_tracker = StrategyOutcomeTracker(
        expected_strategy_targets(requested_strategies, tuple(platforms or ()))
    )
    refresh_tracker = VendorRefreshTracker(
        tuple(dict.fromkeys(platforms or ())) if refresh_vendor_research and ai_strategy else ()
    )

    if not base_report_complete:
        outcome_tracker.mark_remaining_skipped()
        refresh_tracker.mark_remaining_skipped()
        strategy_outcome = outcome_tracker.snapshot()
        refresh_outcome = refresh_tracker.snapshot()
        persist_strategy_outcome(folder_path, strategy_outcome)
        persist_vendor_refresh_outcome(folder_path, refresh_outcome)
        console.warn("Optional strategy generation skipped because the base report is incomplete")
        return StrategyPhaseResult(
            strategy_paths,
            strategy_trust_stats,
            vendor_refresh_tasks_started,
            strategy_outcome,
            refresh_outcome,
        )

    from primr.config.models import DEEP_RESEARCH_COST

    vendor_refresh_cost = DEEP_RESEARCH_COST.standard_task_cost

    def observed_fast_spend() -> float:
        refresh_tasks_started = refresh_tracker.snapshot().started_count
        return _compute_session_llm_cost() + refresh_tasks_started * vendor_refresh_cost

    # --budget checkpoint: skip strategy generation (the most expensive optional
    # stage) when actual spend has already reached the --budget ceiling.
    if has_strategies and skip_stage_if_over_budget(observed_fast_spend(), "strategy generation"):
        has_strategies = False
        outcome_tracker.mark_remaining_skipped()
        refresh_tracker.mark_remaining_skipped()

    if not has_strategies:
        refresh_outcome = refresh_tracker.snapshot()
        persist_vendor_refresh_outcome(folder_path, refresh_outcome)
        return StrategyPhaseResult(
            strategy_paths,
            strategy_trust_stats,
            vendor_refresh_tasks_started,
            outcome_tracker.snapshot(),
            refresh_outcome,
        )

    from primr.ai import stage_routing
    from primr.core.cli_labels import model_provider_label

    writing_model = grok_writing
    reasoning_model = grok_reasoning
    provider_label = model_provider_label(writing_model)
    phase_label = f"Strategy ({provider_label})"
    console.phase_banner(6, total_phases, phase_label, "Generating strategy documents", "3-8 min")
    strategy_route = None
    strategy_usage_before = None
    strategy_route_start = time.monotonic()
    try:
        strategy_route = stage_routing.resolve_stage_model(
            "fast.strategy_generation",
            legacy_model_type="writing",
        )
        log_structured(
            "info", "Strategy generation route selected", **strategy_route.log_metadata()
        )
        if getattr(strategy_route, "execution_mode", "llm") == "unavailable":
            failure = stage_routing.stage_route_failure_class(strategy_route)
            stage_routing.record_stage_route_usage(
                folder_path,
                strategy_route,
                outcome="fallback",
                input_items=len(requested_strategies),
                output_items=0,
                duration_seconds=time.monotonic() - strategy_route_start,
                failure_class=failure,
            )
            console.warn(f"Strategy generation skipped ({failure}) — no writing backend available")
            outcome_tracker.mark_remaining_skipped()
            refresh_tracker.mark_remaining_skipped()
            refresh_outcome = refresh_tracker.snapshot()
            persist_vendor_refresh_outcome(folder_path, refresh_outcome)
            return StrategyPhaseResult(
                strategy_paths,
                strategy_trust_stats,
                vendor_refresh_tasks_started,
                outcome_tracker.snapshot(),
                refresh_outcome,
            )
        if strategy_route.model_name:
            writing_model = strategy_route.model_name
        # Prefer a routed reasoning model for enrichment when available.
        try:
            reasoning_route = stage_routing.resolve_stage_model(
                "fast.analysis_workbook",
                legacy_model_type="reasoning",
            )
            if (
                reasoning_route.model_name
                and getattr(reasoning_route, "execution_mode", "llm") != "unavailable"
            ):
                reasoning_model = reasoning_route.model_name
        except Exception as reasoning_route_err:
            logger.debug("Strategy reasoning route resolution skipped: %s", reasoning_route_err)
        strategy_usage_before = stage_routing.capture_stage_usage()
    except Exception as e:
        logger.warning("Strategy generation route resolution failed: %s", e, exc_info=True)

    # --- AI Strategy (per vendor) ---
    # When multiple platforms are active (common when recon detects
    # both AWS and Azure), run the per-vendor strategies concurrently.
    # The shared company context (report + insights + gap analysis +
    # workbook) is identical across vendors; only the vendor-specific
    # research docs differ. Running them in parallel roughly halves
    # wall-clock time on multi-platform runs.
    if ai_strategy and platforms:
        # Built once so the cached prefix is byte-identical across vendors
        # (roadmap #8: providers' implicit prefix caching keys on it) and the
        # parallel vendor closures don't re-read the same artifacts.
        ai_context_prefix = build_strategy_context_prefix(
            report_content, read_artifact_blocks(folder_path, AI_STRATEGY_ARTIFACTS)
        )

        # Resolve optional cache inputs before strategy workers start. Explicit
        # refreshes use a shared provider client and usage tracker, neither of
        # which is safe to mutate concurrently. Strategy writing can still fan
        # out after this small serial context phase.
        vendor_doc_paths_by_vendor: dict[str, list[str]] = {}
        for vendor in dict.fromkeys(platforms):
            vendor_doc_paths: list[str] = []
            if vendor.lower() != "agnostic" or refresh_vendor_research:
                force_refresh = refresh_vendor_research
                if force_refresh and skip_stage_if_cost_would_exceed(
                    observed_fast_spend(),
                    vendor_refresh_cost,
                    f"vendor research refresh ({vendor})",
                ):
                    force_refresh = False
                    refresh_tracker.mark_skipped(vendor)
                try:
                    if force_refresh:
                        # Freshness-aware: reuse a cache within the freshness
                        # window, regenerate only when stale or missing. Fast mode
                        # uses the grounded lite AI-news engine (cheap by design).
                        vendor_doc_paths = get_or_generate_vendor_research_sync(
                            vendor,
                            force_refresh=False,
                            allow_auto_refresh=True,
                            task_observer=refresh_tracker.observer(vendor),
                            lite=True,
                        )
                    else:
                        vendor_doc_paths = get_or_generate_vendor_research_sync(
                            vendor,
                            force_refresh=False,
                            allow_auto_refresh=False,
                            lite=True,
                        )
                except Exception as exc:
                    if force_refresh:
                        refresh_tracker.observe(vendor, "failed")
                    console.warn(
                        f"AI Strategy ({vendor.upper()}): vendor research context unavailable; "
                        "continuing without it"
                    )
                    log_structured(
                        "warning",
                        "Fast mode vendor strategy context unavailable",
                        vendor=vendor,
                        failure_type=type(exc).__name__,
                    )
            vendor_doc_paths_by_vendor[vendor] = vendor_doc_paths
        vendor_refresh_tasks_started = refresh_tracker.snapshot().started_count
        cached_agnostic_block = _read_cached_agnostic_research_block()

        def _run_ai_strategy_for_vendor(vendor: str):
            """Run the full per-platform AI strategy pipeline.

            Records results by mutating the closure's strategy_paths /
            strategy_trust_stats; returns None early on budget stop or
            failure so other vendors run independently. All console output
            is prefixed with the vendor label so concurrent runs remain
            distinguishable in the CLI.
            """
            # --budget checkpoint: each vendor strategy is a full WRITING call
            # plus enrichment (real spend), and the stage-entry gate cannot see
            # spend that accrues while other vendors run. Re-check per vendor,
            # mirroring the per-document check in the YAML loop; strategies
            # already produced still ship.
            target = strategy_target("ai", vendor)
            if skip_stage_if_over_budget(observed_fast_spend(), f"AI strategy ({vendor})"):
                outcome_tracker.mark_skipped(target)
                return None

            strategy_prompt = _build_ai_strategy_prompt(
                company_label, vendor, discovery_notes_content
            )

            vendor_doc_paths = vendor_doc_paths_by_vendor[vendor]
            vendor_blocks: list[str] = []
            for vdp in vendor_doc_paths:
                if not vdp:
                    continue
                vendor_block = _read_stable_research_block(
                    vdp,
                    header=f"{vendor.upper()} AI research",
                    context_kind="vendor_specific",
                )
                if vendor_block:
                    vendor_blocks.append(vendor_block)
            refreshed_agnostic_included = (
                refresh_vendor_research and vendor.lower() == "agnostic" and bool(vendor_blocks)
            )
            if cached_agnostic_block and not refreshed_agnostic_included:
                vendor_blocks.append(cached_agnostic_block)

            cached_prefix, volatile_suffix = build_strategy_prompt_parts(
                ai_context_prefix, strategy_prompt, vendor_blocks
            )
            combined_strategy_prompt = cached_prefix + volatile_suffix

            vendor_label = f" ({vendor.upper()})" if len(platforms) > 1 else ""
            try:
                from primr.pipeline.integration import strategy_with_recovery

                def _do_strategy(_prompt=combined_strategy_prompt):
                    return call_with_failover(
                        LLMRole.WRITING,
                        _prompt,
                        preferred_model=writing_model,
                        max_tokens=32_000,
                    )

                with console.timed_operation(f"AI Strategy{vendor_label} via {provider_label}"):
                    _strat_result = strategy_with_recovery(
                        recovery_executor, _do_strategy, folder_path
                    )
                    if _strat_result.success:
                        strategy_content = _strat_result.output
                    else:
                        raise RuntimeError(
                            _strat_result.skip_reason or "Strategy recovery exhausted"
                        )
            except Exception as strat_err:
                console.warn(f"AI Strategy{vendor_label} failed: {strat_err} - skipping")
                log_structured(
                    "warning",
                    "Fast mode strategy failed",
                    vendor=vendor,
                    error=str(strat_err),
                )
                outcome_tracker.mark_failed(target)
                return  # abandon this vendor; others run independently

            if strategy_content and strategy_content.strip():
                strategy_content = re.sub(
                    r"\n*_?Disclaimer:\s*Grok is not a financial advi[sc]er[^\n]*\n?",
                    "\n",
                    strategy_content,
                    flags=re.IGNORECASE,
                ).strip()
                strategy_content = re.sub(
                    r"\[Word count:\s*[\d,]+\]",
                    "",
                    strategy_content,
                    flags=re.IGNORECASE,
                )

                # Enrich: cross-validate → evidence search → polish
                try:
                    strategy_content = _enrich_strategy_content(
                        strategy_content,
                        company_label,
                        vendor,
                        "AI Strategy",
                        list(validated_source_urls),
                        set(validated_source_urls),
                        analysis_workbook,
                        website,
                        grok_reasoning=reasoning_model,
                        grok_writing=writing_model,
                    )
                except Exception as enrich_err:
                    log_structured(
                        "warning",
                        "Strategy enrichment failed, keeping original",
                        vendor=vendor,
                        error=str(enrich_err),
                    )

                strategy_content, strategy_qa, rejected_strategy_sources = (
                    _prepare_strategy_for_output(
                        strategy_content,
                        company_label,
                        vendor,
                        "AI Strategy",
                        list(validated_source_urls),
                        model=writing_model,
                    )
                )
                qa_gate = "PASS" if strategy_qa["qa_gate_passed"] else "WARN"
                console.info(
                    f"Strategy QA: placeholders={strategy_qa['placeholder_refs']}, "
                    f"sources={strategy_qa['source_urls']}/{strategy_qa['citation_defs']}, "
                    f"missing={strategy_qa['missing_citations']}, "
                    f"invalid={strategy_qa['invalid_source_urls'] + len(rejected_strategy_sources)}, "
                    f"budget={'OK' if not strategy_qa['budget_inconsistent'] else 'WARN'}, gate={qa_gate}"
                )
                if strategy_qa["source_urls"] == 0:
                    console.warn("Strategy QA: no explicit source URLs detected in strategy output")
                strategy_trust_stats.append(
                    (
                        f"AI Strategy ({vendor.upper()})" if len(platforms) > 1 else "AI Strategy",
                        [
                            ("Gate", qa_gate),
                            ("Sources", f"{strategy_qa['source_urls']} valid"),
                            (
                                "Citation Gaps",
                                str(strategy_qa["missing_citations"]),
                            ),
                            (
                                "Invalid Sources",
                                str(
                                    strategy_qa["invalid_source_urls"]
                                    + len(rejected_strategy_sources)
                                ),
                            ),
                            (
                                "Budget Check",
                                "WARN" if strategy_qa["budget_inconsistent"] else "OK",
                            ),
                        ],
                    )
                )

                strategy_path = _save_strategy_output(
                    strategy_content,
                    company_label,
                    vendor,
                    strategy_label="AI_Strategy",
                    output_dir=output_dir,
                    diagnostics_dir=diagnostics_dir,
                    write_txt=write_txt,
                )
                if strategy_path:
                    key = f"ai_{vendor}" if len(platforms) > 1 else "ai"
                    strategy_paths[key] = strategy_path
                    outcome_tracker.mark_completed(target)
                else:
                    outcome_tracker.mark_failed(target)
            else:
                outcome_tracker.mark_failed(target)

        # Dispatch per-platform strategy workers. One platform = run
        # inline (no pool overhead). Multiple platforms = ThreadPool
        # with one worker per platform, capped at 3 for rate-limit
        # safety. grok_llm + network IO releases the GIL so threads
        # genuinely overlap.
        if len(platforms) == 1:
            _run_ai_strategy_for_vendor(platforms[0])
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=min(len(platforms), 3)) as _strat_pool:
                _strat_futures = {
                    _strat_pool.submit(_run_ai_strategy_for_vendor, v): v for v in platforms
                }
                for _sf in as_completed(_strat_futures):
                    v = _strat_futures[_sf]
                    try:
                        _sf.result()
                    except Exception as e:
                        outcome_tracker.mark_failed(strategy_target("ai", v))
                        logger.warning(
                            "Parallel AI strategy worker for %s raised: %s",
                            v,
                            e,
                        )

    # --- YAML-defined strategies (customer_experience, security, data_fabric, etc.) ---
    if strategy_types:
        import yaml as _yaml

        # Built once, lazily on the first strategy that actually runs:
        # byte-identical cached prefix across all YAML strategies (roadmap #8),
        # artifacts read once instead of once per strategy type, and no file IO
        # when every type is skipped. Recon + hiring signals are included -
        # they particularly strengthen the `skills` strategy (and generally
        # the CX, security, and data-fabric strategies as well).
        yaml_context_prefix: str | None = None

        for stype in strategy_types:
            if stype == "ai":
                continue  # already handled above

            target = strategy_target(stype)

            # --budget checkpoint: each YAML strategy is a full WRITING call plus
            # enrichment/polish (real spend). Stop generating further strategies
            # once an active --budget ceiling is reached; strategies already
            # produced still ship. Mirrors the stage-entry gate above and the
            # Phase-2 deepening / Phase-5 cross-validation checkpoints.
            if skip_stage_if_over_budget(observed_fast_spend(), "remaining strategy generation"):
                outcome_tracker.mark_remaining_skipped()
                break

            # Load strategy YAML config (name matches filename)
            yaml_path = Path(__file__).parent.parent / "prompts" / "strategies" / f"{stype}.yaml"

            if not yaml_path.exists():
                console.warn(f"Strategy YAML not found: {stype}.yaml - skipping")
                outcome_tracker.mark_failed(target)
                continue

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    strategy_config = _yaml.safe_load(f)
            except Exception as e:
                console.warn(f"Failed to load {stype}.yaml: {e} - skipping")
                outcome_tracker.mark_failed(target)
                continue

            meta = strategy_config.get("meta", {})
            display_name_strat = meta.get("name", stype.replace("_", " ").title())
            output_filename = meta.get("output_filename", f"{{company_name}}_{stype}")
            # Build label for filename from YAML meta
            file_label = output_filename.replace("{company_name}_", "").replace(
                "{company_name}", ""
            )
            if not file_label:
                file_label = stype.replace(" ", "_")

            strategy_prompt = _build_strategy_prompt_from_yaml(
                strategy_config, company_label, discovery_notes_content
            )

            if yaml_context_prefix is None:
                yaml_context_prefix = build_strategy_context_prefix(
                    report_content, read_artifact_blocks(folder_path, YAML_STRATEGY_ARTIFACTS)
                )
            cached_prefix, volatile_suffix = build_strategy_prompt_parts(
                yaml_context_prefix, strategy_prompt
            )
            combined_prompt = cached_prefix + volatile_suffix

            try:
                from primr.pipeline.integration import strategy_with_recovery

                def _do_yaml_strategy(_p=combined_prompt):
                    return call_with_failover(
                        LLMRole.WRITING,
                        _p,
                        preferred_model=writing_model,
                        max_tokens=32_000,
                    )

                with console.timed_operation(f"{display_name_strat} via {provider_label}"):
                    _yaml_strat_result = strategy_with_recovery(
                        recovery_executor, _do_yaml_strategy, folder_path
                    )
                    if _yaml_strat_result.success:
                        strategy_content = _yaml_strat_result.output
                    else:
                        raise RuntimeError(
                            _yaml_strat_result.skip_reason or "Strategy recovery exhausted"
                        )
            except Exception as strat_err:
                console.warn(f"{display_name_strat} failed: {strat_err} - skipping")
                log_structured(
                    "warning",
                    "Fast mode strategy failed",
                    strategy=stype,
                    error=str(strat_err),
                )
                outcome_tracker.mark_failed(target)
                continue

            if strategy_content and strategy_content.strip():
                strategy_content = re.sub(
                    r"\n*_?Disclaimer:\s*Grok is not a financial advi[sc]er[^\n]*\n?",
                    "\n",
                    strategy_content,
                    flags=re.IGNORECASE,
                ).strip()
                strategy_content = re.sub(
                    r"\[Word count:\s*[\d,]+\]",
                    "",
                    strategy_content,
                    flags=re.IGNORECASE,
                )

                # Enrich: cross-validate → evidence search → polish
                # Use strategy display name (e.g. "Customer Experience") not "agnostic"
                try:
                    strategy_content = _enrich_strategy_content(
                        strategy_content,
                        company_label,
                        display_name_strat,
                        display_name_strat,
                        list(validated_source_urls),
                        set(validated_source_urls),
                        analysis_workbook,
                        website,
                        grok_reasoning=reasoning_model,
                        grok_writing=writing_model,
                    )
                except Exception as enrich_err:
                    log_structured(
                        "warning",
                        "Strategy enrichment failed, keeping original",
                        strategy=stype,
                        error=str(enrich_err),
                    )

                strategy_content, strategy_qa, rejected_strategy_sources = (
                    _prepare_strategy_for_output(
                        strategy_content,
                        company_label,
                        display_name_strat,
                        display_name_strat,
                        list(validated_source_urls),
                        model=writing_model,
                    )
                )
                qa_gate = "PASS" if strategy_qa["qa_gate_passed"] else "WARN"
                console.info(
                    f"Strategy QA: placeholders={strategy_qa['placeholder_refs']}, "
                    f"sources={strategy_qa['source_urls']}/{strategy_qa['citation_defs']}, "
                    f"missing={strategy_qa['missing_citations']}, "
                    f"invalid={strategy_qa['invalid_source_urls'] + len(rejected_strategy_sources)}, "
                    f"budget={'OK' if not strategy_qa['budget_inconsistent'] else 'WARN'}, gate={qa_gate}"
                )
                if strategy_qa["source_urls"] == 0:
                    console.warn("Strategy QA: no explicit source URLs detected in strategy output")
                strategy_trust_stats.append(
                    (
                        display_name_strat,
                        [
                            ("Gate", qa_gate),
                            ("Sources", f"{strategy_qa['source_urls']} valid"),
                            (
                                "Citation Gaps",
                                str(strategy_qa["missing_citations"]),
                            ),
                            (
                                "Invalid Sources",
                                str(
                                    strategy_qa["invalid_source_urls"]
                                    + len(rejected_strategy_sources)
                                ),
                            ),
                            (
                                "Budget Check",
                                "WARN" if strategy_qa["budget_inconsistent"] else "OK",
                            ),
                        ],
                    )
                )

                strategy_path = _save_strategy_output(
                    strategy_content,
                    company_label,
                    "agnostic",
                    strategy_label=file_label,
                    output_dir=output_dir,
                    diagnostics_dir=diagnostics_dir,
                    write_txt=write_txt,
                )
                if strategy_path:
                    strategy_paths[stype] = strategy_path
                    outcome_tracker.mark_completed(target)
                else:
                    outcome_tracker.mark_failed(target)

                # Skills Ideation strategy: also emit per-role SKILL.md
                # files in a sibling directory so the artifacts are
                # compatible with Claude Code, Copilot Studio, and any
                # skill-aware agent host. Failure here never blocks
                # the strategy doc itself.
                #
                # DEPRECATION: This is the v1.23 inline path. The
                # v1.26+ canonical command is `primr skills <Company>
                # <url>` which adds QA refinement, pack-level
                # coherence, and a sideload-ready Microsoft 365
                # Cowork .zip alongside the Claude tree. The legacy
                # parser-based path stays here for backward compat
                # until removal in a later release.
                if stype == "skills" and strategy_path:
                    try:
                        from primr.output.skills_generator import write_skill_files

                        roles_root = (
                            Path(strategy_path).with_suffix("").parent / Path(strategy_path).stem
                        )
                        written = write_skill_files(strategy_content, roles_root)
                        if written:
                            console.info(
                                f"Skills Ideation: emitted {len(written)} per-role "
                                f"SKILL.md files under {roles_root.name}/roles/"
                            )
                            console.info(
                                "Tip: `primr skills <Company> <url>` produces a "
                                "QA-refined skill pack with a Microsoft 365 Copilot "
                                "Cowork .zip alongside the Claude tree."
                            )
                        else:
                            console.warn(
                                "Skills Ideation: no role blocks parsed from strategy "
                                "content - per-role SKILL.md files not emitted"
                            )
                    except Exception as skill_err:
                        logger.warning("Skills Ideation per-role emission failed: %s", skill_err)
            else:
                outcome_tracker.mark_failed(target)

    if strategy_paths:
        console.phase_complete(phase_label)
    else:
        console.warn("Strategy generation skipped - no strategies generated")

    refresh_outcome = refresh_tracker.snapshot()
    persist_vendor_refresh_outcome(folder_path, refresh_outcome)
    if strategy_route is not None:
        from primr.ai import stage_routing as stage_routing_mod

        stage_routing_mod.record_stage_route_usage(
            folder_path,
            strategy_route,
            outcome="selected" if strategy_paths else "fallback",
            input_items=len(requested_strategies),
            output_items=len(strategy_paths),
            duration_seconds=time.monotonic() - strategy_route_start,
            failure_class=None if strategy_paths else "no_strategies_generated",
            usage_delta=stage_routing_mod.stage_usage_delta(strategy_usage_before)
            if strategy_usage_before is not None
            else None,
        )
    return StrategyPhaseResult(
        strategy_paths,
        strategy_trust_stats,
        vendor_refresh_tasks_started,
        outcome_tracker.snapshot(),
        refresh_outcome,
    )
