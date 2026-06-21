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

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from primr.pipeline.llm_failover import LLMRole, call_with_failover
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured
from primr.utils.run_budget import skip_stage_if_over_budget

logger = get_logger("core.fast_run_strategy")


@dataclass(frozen=True)
class StrategyPhaseResult:
    """Outputs of the strategy stage that the orchestrator threads onward."""

    strategy_paths: dict[str, str] = field(default_factory=dict)
    strategy_trust_stats: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)


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
    grok_reasoning: str,
    grok_writing: str,
    folder_path: str,
    output_dir: str | None,
    diagnostics_dir: str | None,
    write_txt: bool,
    recovery_executor,
    total_phases: int,
) -> StrategyPhaseResult:
    """Generate strategy documents (AI per-vendor + YAML-defined) if requested."""
    # Lazy import: research_agent imports this module, so the prompt-build,
    # enrichment, and output helpers (which stay there until their own
    # extraction) must be resolved at call time to avoid a circular import.
    from primr.core.research_agent import (
        _build_ai_strategy_prompt,
        _build_strategy_prompt_from_yaml,
        _compute_session_llm_cost,
        _enrich_strategy_content,
        _get_or_generate_vendor_research,
        _prepare_strategy_for_output,
        _save_strategy_output,
    )

    strategy_paths: dict[str, str] = {}
    strategy_trust_stats: list[tuple[str, list[tuple[str, str]]]] = []

    # --budget checkpoint: skip strategy generation (the most expensive optional
    # stage) when actual spend has already reached the --budget ceiling.
    if has_strategies and skip_stage_if_over_budget(
        _compute_session_llm_cost(), "strategy generation"
    ):
        has_strategies = False

    if not has_strategies:
        return StrategyPhaseResult(strategy_paths, strategy_trust_stats)

    console.phase_banner(
        6, total_phases, "Strategy (Grok)", "Generating strategy documents", "3-8 min"
    )

    # --- AI Strategy (per vendor) ---
    # When multiple platforms are active (common when recon detects
    # both AWS and Azure), run the per-vendor strategies concurrently.
    # The shared company context (report + insights + gap analysis +
    # workbook) is identical across vendors; only the vendor-specific
    # research docs differ. Running them in parallel roughly halves
    # wall-clock time on multi-platform runs.
    if ai_strategy and platforms:

        def _run_ai_strategy_for_vendor(vendor: str):
            """Run the full per-platform AI strategy pipeline.

            Returns (strategy_path, trust_stats_tuple, path_key) on
            success, or None on failure. All console output is
            prefixed with the vendor label so concurrent runs remain
            distinguishable in the CLI.
            """
            strategy_prompt = _build_ai_strategy_prompt(
                company_label, vendor, discovery_notes_content
            )

            context_parts = [f"--- Company Report ---\n{report_content[:50_000]}"]

            # Enrich with working-folder artifacts (insights, gap analysis, workbook)
            for artifact_name, artifact_limit in [
                ("insights.txt", 20_000),
                ("gap_analysis.md", 15_000),
                ("analysis_workbook.md", 20_000),
            ]:
                artifact_path = os.path.join(folder_path, artifact_name)
                if os.path.exists(artifact_path):
                    try:
                        with open(artifact_path, encoding="utf-8") as fh:
                            artifact_content = fh.read()[:artifact_limit]
                            if artifact_content.strip():
                                context_parts.append(f"--- {artifact_name} ---\n{artifact_content}")
                    except Exception as e:
                        logger.warning("Failed to read artifact %s: %s", artifact_name, e)

            vendor_doc_paths = (
                _get_or_generate_vendor_research(vendor) if vendor.lower() != "agnostic" else []
            )
            for vdp in vendor_doc_paths:
                if vdp and os.path.exists(vdp):
                    try:
                        with open(vdp, encoding="utf-8") as fh:
                            context_parts.append(
                                f"--- {os.path.basename(vdp)} ---\n{fh.read()[:30_000]}"
                            )
                    except Exception as e:
                        logger.warning("Failed to read vendor doc %s: %s", vdp, e)

            combined_strategy_prompt = (
                "Use the following context documents to inform your analysis:\n\n"
                + "\n\n".join(context_parts)
                + "\n\n---\n\n"
                + strategy_prompt
            )

            vendor_label = f" ({vendor.upper()})" if len(platforms) > 1 else ""
            try:
                from primr.pipeline.integration import strategy_with_recovery

                def _do_strategy(_prompt=combined_strategy_prompt):
                    return call_with_failover(
                        LLMRole.WRITING,
                        _prompt,
                        preferred_model=grok_writing,
                        max_tokens=32_000,
                    )

                with console.timed_operation(f"AI Strategy{vendor_label} via Grok"):
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
                console.warn(f"AI Strategy{vendor_label} failed: {strat_err} — skipping")
                log_structured(
                    "warning",
                    "Fast mode strategy failed",
                    vendor=vendor,
                    error=str(strat_err),
                )
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
                        grok_reasoning=grok_reasoning,
                        grok_writing=grok_writing,
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
                        model=grok_writing,
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
                        logger.warning(
                            "Parallel AI strategy worker for %s raised: %s",
                            v,
                            e,
                        )

    # --- YAML-defined strategies (customer_experience, security, data_fabric, etc.) ---
    if strategy_types:
        import yaml as _yaml

        for stype in strategy_types:
            if stype == "ai":
                continue  # already handled above

            # --budget checkpoint: each YAML strategy is a full WRITING call plus
            # enrichment/polish (real spend). Stop generating further strategies
            # once an active --budget ceiling is reached; strategies already
            # produced still ship. Mirrors the stage-entry gate above and the
            # Phase-2 deepening / Phase-5 cross-validation checkpoints.
            if skip_stage_if_over_budget(
                _compute_session_llm_cost(), "remaining strategy generation"
            ):
                break

            # Load strategy YAML config (name matches filename)
            yaml_path = Path(__file__).parent.parent / "prompts" / "strategies" / f"{stype}.yaml"

            if not yaml_path.exists():
                console.warn(f"Strategy YAML not found: {stype}.yaml — skipping")
                continue

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    strategy_config = _yaml.safe_load(f)
            except Exception as e:
                console.warn(f"Failed to load {stype}.yaml: {e} — skipping")
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

            # Build context with report + working-folder artifacts.
            # Recon + hiring signals are particularly important for the
            # `skills` strategy (and generally strengthen CX, security,
            # and data-fabric strategies as well).
            yaml_context_parts = [f"--- Company Report ---\n{report_content[:50_000]}"]
            for artifact_name, artifact_limit in [
                ("insights.txt", 20_000),
                ("gap_analysis.md", 15_000),
                ("analysis_workbook.md", 20_000),
                ("_recon_context.txt", 10_000),
                ("_hiring/hiring_signals.md", 15_000),
            ]:
                artifact_path = os.path.join(folder_path, artifact_name)
                if os.path.exists(artifact_path):
                    try:
                        with open(artifact_path, encoding="utf-8") as fh:
                            artifact_content = fh.read()[:artifact_limit]
                            if artifact_content.strip():
                                yaml_context_parts.append(
                                    f"--- {artifact_name} ---\n{artifact_content}"
                                )
                    except Exception as e:
                        logger.warning("Failed to read artifact %s: %s", artifact_name, e)

            combined_prompt = (
                "Use the following context documents to inform your analysis:\n\n"
                + "\n\n".join(yaml_context_parts)
                + "\n\n---\n\n"
                + strategy_prompt
            )

            try:
                from primr.pipeline.integration import strategy_with_recovery

                def _do_yaml_strategy(_p=combined_prompt):
                    return call_with_failover(
                        LLMRole.WRITING,
                        _p,
                        preferred_model=grok_writing,
                        max_tokens=32_000,
                    )

                with console.timed_operation(f"{display_name_strat} via Grok"):
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
                console.warn(f"{display_name_strat} failed: {strat_err} — skipping")
                log_structured(
                    "warning",
                    "Fast mode strategy failed",
                    strategy=stype,
                    error=str(strat_err),
                )
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
                        grok_reasoning=grok_reasoning,
                        grok_writing=grok_writing,
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
                        model=grok_writing,
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

                # Skills Ideation strategy: also emit per-role SKILL.md
                # files in a sibling directory so the artifacts are
                # drop-in loadable by Claude Code / Copilot Studio /
                # any skill-aware agent host. Failure here never blocks
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
                                "content — per-role SKILL.md files not emitted"
                            )
                    except Exception as skill_err:
                        logger.warning("Skills Ideation per-role emission failed: %s", skill_err)

    if strategy_paths:
        console.phase_complete("Strategy (Grok)")
    else:
        console.warn("Strategy generation skipped — no strategies generated")

    return StrategyPhaseResult(strategy_paths, strategy_trust_stats)
