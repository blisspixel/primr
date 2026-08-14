"""Deep-run finalization: cost reconciliation, summary display, usage record.

Extracted verbatim from the tail of ``perform_deep_research`` - no behavior
change, seam introduction only, the same move that ``fast_run_summary`` made for
the fast pipeline. This is the deep path's clearest boundary: per-model cost
reconciliation (pipeline Flash/Pro plus flat Deep-Research task cost), the
estimated-vs-actual summary, the always-on report-trust row, usage-history
recording, and the observability job summary. No LLM calls; everything it needs
arrives as explicit parameters, so it is unit-testable with mocked
client/tracker/console.

Keeping it here (rather than inline in the already-large ``research_agent``)
also gives the deep path a single place to grow trust/measurement surfaces
without pressing that file against its architecture line ceiling.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from primr.core.strategy_outcome import StrategyOutcome
from primr.core.vendor_refresh_outcome import VendorRefreshOutcome
from primr.utils.console import console
from primr.utils.observability import JobSummary, log_job_summary


def publish_partial_deep_report(
    result: Any,
    company_name: str,
    output_dir: str | Path,
    diagnostics_dir: str | Path | None,
    write_txt: bool,
) -> str | None:
    """Publish a paid partial result and close its persisted provider job."""
    from primr.output.output_utils import save_incomplete_markdown_report

    report_path = save_incomplete_markdown_report(
        result.raw_content,
        company_name,
        output_dir,
        diagnostics_dir,
        write_txt,
    )
    interaction_id = getattr(result, "pending_interaction_id", "")
    if report_path and isinstance(interaction_id, str) and interaction_id:
        from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

        if not acknowledge_pending_job_after_outputs(interaction_id, [report_path]):
            console.warn("The completed provider job remains recoverable.")
    return report_path


def record_deep_terminal_status(
    folder_path: str,
    report_path: str | None,
    *,
    elapsed: float,
    time_str: str,
) -> str:
    """Stamp run-state from a durable artifact, not from provider success."""
    from datetime import datetime

    from primr.core.run_state_io import _append_run_event, _update_run_state

    shipped = False
    if report_path:
        path = Path(report_path)
        shipped = path.is_file() and path.stat().st_size > 0
    if shipped:
        console.ok(f"Complete in {time_str}")
        _update_run_state(
            folder_path,
            status="completed",
            current_phase="complete",
            completed_at=datetime.now().isoformat(),
            duration_seconds=elapsed,
        )
        _append_run_event(folder_path, "complete", "completed", f"Run completed in {time_str}")
        return "completed"
    console.warn("Deep research produced no durable report")
    _update_run_state(
        folder_path,
        status="failed",
        current_phase="error",
        completed_at=datetime.now().isoformat(),
        duration_seconds=elapsed,
    )
    _append_run_event(folder_path, "error", "failed", "No durable primary report was written")
    return "failed"


def resolve_deep_report_artifacts(
    docx_path: str | None,
    durable_paths: list[Path],
) -> tuple[str | None, list[Path], str | None]:
    """Choose the shipped, acknowledgment, and verification artifacts."""
    report_path = docx_path
    if report_path is None and durable_paths:
        markdown = next((path for path in durable_paths if path.suffix.lower() == ".md"), None)
        report_path = str(markdown or durable_paths[0])
    acknowledgment_paths = list(durable_paths)
    if not acknowledgment_paths and report_path:
        acknowledgment_paths.append(Path(report_path))
    verification_path = next(
        (str(path) for path in durable_paths if path.suffix.lower() == ".txt"),
        report_path,
    )
    return report_path, acknowledgment_paths, verification_path


def finalize_deep_run(
    *,
    mode: str,
    mode_label: str,
    result: Any,
    ai_strategy: bool,
    platforms: tuple[str, ...],
    lite_strategy: bool,
    strategies: list[str] | None,
    strategy_deep_research_tasks_started: int,
    refresh_vendor_research: bool,
    vendor_refresh_tasks_started: int,
    strategy_outcome: StrategyOutcome,
    vendor_refresh_outcome: VendorRefreshOutcome,
    time_str: str,
    elapsed: float,
    display_name: str,
    docx_path: str | None,
) -> None:
    """Reconcile cost, show the summary, and record usage for a deep-mode run.

    Side effects preserved from the original inline block: the "Report Trust"
    panel (when there are traceable claims), the estimated-vs-actual summary
    line, the usage-history record, and the observability job summary.
    """
    # Get actual usage from AI client (per-model accurate cost)
    from primr.ai.client import get_client
    from primr.core.deep_budget import (
        count_main_deep_research_tasks,
        deep_research_flat_cost,
    )

    client = get_client()
    usage = client.get_usage_summary()

    # Pipeline portion (Flash + Pro, per-model accurate)
    pipeline_cost = usage.get("total_cost", 0.0)
    total_input = usage.get("total_input_tokens", 0)
    total_output = usage.get("total_output_tokens", 0)

    # Deep Research portion uses Primr's per-task planning estimate because
    # exact agentic token and tool usage is not available before completion.
    dr_tasks = count_main_deep_research_tasks(mode) + strategy_deep_research_tasks_started
    dr_cost = deep_research_flat_cost(dr_tasks)
    vendor_refresh_cost = deep_research_flat_cost(vendor_refresh_tasks_started)

    actual_cost = pipeline_cost + dr_cost + vendor_refresh_cost

    from primr.utils.cost_estimator import estimate_cost

    strategy_names = strategies if strategies else ["ai"] if ai_strategy else []
    planned_vendor_refreshes = (
        len(platforms) if refresh_vendor_research and "ai" in strategy_names else 0
    )
    pre_estimate = estimate_cost(
        mode,
        ai_strategy,
        use_historical=False,
        num_vendors=len(platforms),
        lite_strategy=lite_strategy,
        strategy_types=strategies,  # replace-vs-add mirrored in estimator
        vendor_research_refreshes=planned_vendor_refreshes,
    )

    # Use sections_written for accurate count
    section_count = (
        result.sections_written if result.sections_written > 0 else len(result.section_results)
    )

    # Count unique citations from generated content ([cite: N] format)
    citation_count = 0
    all_content = result.raw_content or ""
    if not all_content and result.section_results:
        all_content = "\n".join(result.section_results.values())
    if all_content:
        cite_numbers = set()
        for match in re.findall(r"\[cite:\s*([\d,\s]+)\]", all_content):
            for num in match.split(","):
                num = num.strip()
                if num:
                    cite_numbers.add(num)
        citation_count = len(cite_numbers)

    # Always-on judge-free label-citation trust signal (fast-path parity).
    from primr.core.deep_run_trust import build_deep_report_trust_stats

    _deep_trust = build_deep_report_trust_stats(all_content)
    if _deep_trust:
        console.trust_summary("Report Trust", _deep_trust)

    # Summary stats with estimated vs actual comparison
    summary_items = [
        ("Mode", mode_label),
        ("Chapters", str(section_count)),
        ("Citations", str(citation_count)),
        ("Duration", time_str),
        ("Est. Cost", f"${pre_estimate.total_cost:.2f}"),
        ("Actual Cost", f"~${actual_cost:.2f}"),
    ]
    target_pages = getattr(result, "target_pages", 0)
    if target_pages:
        summary_items.extend(
            [
                ("Length Target", f"~{target_pages} pages"),
                ("Length Produced", f"~{getattr(result, 'actual_pages', 0)} pages"),
                (
                    "Length Target Attained",
                    "Yes" if getattr(result, "target_attained", False) else "No",
                ),
            ]
        )
    if any(target.startswith("ai:") for target in strategy_outcome.expected_targets):
        summary_items.append(("AI Strategy", "Yes"))
    if vendor_refresh_tasks_started:
        summary_items.append(
            (
                "Vendor Refresh",
                f"{vendor_refresh_tasks_started} task(s)  ~${vendor_refresh_cost:.2f}",
            )
        )
    if strategy_outcome.status != "not_requested":
        summary_items.append(("Strategy Status", strategy_outcome.status.upper()))
    if vendor_refresh_outcome.status != "not_requested":
        summary_items.append(("Vendor Refresh Status", vendor_refresh_outcome.status.upper()))
    console.summary(summary_items)

    # Save usage to history
    from primr.utils.usage_tracker import get_usage_tracker

    tracker = get_usage_tracker()
    tracker.record_usage(
        mode=mode,
        company=display_name,
        input_tokens=total_input,
        output_tokens=total_output,
        search_queries=result.search_queries_count,  # Actual count from API
        duration_seconds=elapsed,
        pipeline_cost=pipeline_cost,
        # Vendor refresh submissions persist separate usage rows immediately.
        # Excluding them here keeps global history free of duplicate spend.
        deep_research_cost=dr_cost,
    )
    tracker.save()

    # Log job summary for observability
    job_summary = JobSummary.create(
        company=display_name,
        mode=mode,
        duration_seconds=elapsed,
        api_calls=0,  # Deep Research doesn't expose API call count
        total_tokens=total_input + total_output,
        sections_generated=section_count,
        output_path=docx_path,
    )
    log_job_summary(job_summary)
