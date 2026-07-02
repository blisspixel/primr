"""Fast-run finalization: summary display, run-state metrics, usage recording.

Extracted verbatim from the tail of ``perform_fast_research`` (roadmap #23,
Batch A — no behavior change, seam introduction only). This is the stage with
the clearest boundary in the whole orchestrator: pure computation plus
side effects (console output, run-state update, usage history, job summary),
no LLM calls, no mutation of pipeline state.

Everything the stage needs arrives as explicit parameters, so it is fully
unit-testable with mocked console/tracker/session counters.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from primr.config.config import OUTPUT_DIR
from primr.config.models import PrimrModels
from primr.core.run_state_io import _update_run_state
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import JobSummary, log_job_summary

logger = get_logger("core.fast_run_summary")

_TIER_LABELS = {
    "fast": "Grok 4.3 (low-effort)",
    "hybrid": "Grok 4.3 hybrid",
    "max": "Grok 4.3 max",
}


def _strategy_display_label(strat_key: str) -> str:
    """Human label for a strategy path key ('ai_azure' -> 'AI Strategy (AZURE)')."""
    if strat_key.startswith("ai"):
        vendor_suffix = f" ({strat_key.split('_', 1)[1].upper()})" if "_" in strat_key else ""
        return f"AI Strategy{vendor_suffix}"
    return strat_key.replace("_", " ").title()


def finalize_fast_run(
    *,
    start_time: float,
    docx_path: str | None,
    strategy_paths: dict[str, str],
    output_dir: str | Path | None,
    company_name: str | None,
    display_name: str,
    folder_path: str,
    written_sections_count: int,
    total_words: int,
    validated_source_count: int,
    pages_scraped: int,
    grok_tier: str,
    report_trust_stats: list[tuple[str, str]],
    strategy_trust_stats: list[tuple[str, list[tuple[str, str]]]],
    search_query_count: int,
) -> str | None:
    """Finalize a fast-mode run: display, persist metrics, record usage.

    Returns the primary output path (markdown fallback when it exists,
    else the DOCX path) — the value ``perform_fast_research`` returns.
    """
    from primr.ai.grok_client import get_grok_session_usage
    from primr.core.research_agent import _compute_session_llm_cost

    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

    if docx_path:
        console.success_box("Report ready", str(Path(docx_path).resolve()))
    else:
        console.warn("Report DOCX held back by artifact gate; review the saved MD/TXT artifacts")

    for strat_key, strategy_path in strategy_paths.items():
        # AI strategy keys: "ai" or "ai_azure" — show vendor suffix
        label = _strategy_display_label(strat_key)
        resolved_strategy_path = Path(strategy_path).resolve()
        if str(resolved_strategy_path).lower().endswith(".docx"):
            console.success_box(label, str(resolved_strategy_path))
        else:
            console.warn(
                f"{label} DOCX held back by artifact gate; "
                f"saved {resolved_strategy_path.name} instead"
            )

    # Cost summary from Grok session usage (per-model, cache-aware pricing)
    grok_usage = get_grok_session_usage()
    actual_cost = _compute_session_llm_cost()

    date_str = datetime.now().strftime("%m-%d-%Y")
    fallback_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
    fallback_md = fallback_dir / f"{company_name or display_name}_Strategic_Overview_{date_str}.md"
    primary_output_path = str(fallback_md) if fallback_md.exists() else docx_path

    artifacts_passed = bool(docx_path) and all(
        str(path).lower().endswith(".docx") for path in strategy_paths.values()
    )
    completion_label = (
        "Fast mode complete" if artifacts_passed else "Fast mode complete with warnings"
    )
    console.ok(f"{completion_label} in {time_str}")

    # Cache hit rate rides along for post-hoc analysis (roadmap #5): the
    # sub-$1 default depends on it, and the show-usage regression signal
    # needs the per-run value preserved outside usage_history too.
    _cache_hit_rate = (
        min(grok_usage.get("cached_input_tokens", 0), grok_usage["input_tokens"])
        / grok_usage["input_tokens"]
        if grok_usage.get("input_tokens")
        else 0.0
    )
    _update_run_state(
        folder_path,
        report_sections=written_sections_count,
        report_words=total_words,
        external_sources_validated=validated_source_count,
        strategy_artifacts=len(strategy_paths),
        artifact_gate_passed=artifacts_passed,
        actual_cost_usd=round(actual_cost, 4),
        cache_hit_rate=round(_cache_hit_rate, 4),
    )

    if report_trust_stats:
        console.trust_summary("Report Trust", report_trust_stats)
    for trust_title, trust_stats in strategy_trust_stats:
        console.trust_summary(trust_title + " Trust", trust_stats)

    # Per-model token + cost breakdown. The old single "Grok tokens" line
    # mislabeled cross-provider calls (a recipe's Opus/Sonnet/Gemini usage) as
    # "Grok", which made a run's cost impossible to audit. Show each model that
    # actually ran, its tokens, and its priced cost, so the total is verifiable.
    from primr.ai.grok_client import get_grok_session_usage_by_model

    by_model = get_grok_session_usage_by_model()
    model_rows: list[tuple[str, str]] = []
    for mname, t in sorted(by_model.items(), key=lambda kv: -kv[1]["input_tokens"]):
        try:
            mcost = PrimrModels.calculate_cost(
                mname,
                t["input_tokens"],
                t["output_tokens"],
                cached_input_tokens=t.get("cached_input_tokens", 0),
            )
        except KeyError:
            mcost = 0.0
        model_rows.append(
            (mname, f"{t['input_tokens']:,} in / {t['output_tokens']:,} out  ~${mcost:.2f}")
        )

    summary_items: list[tuple[str, Any]] = [
        ("Mode", "fast (" + _TIER_LABELS.get(grok_tier, "Grok") + ")"),
        ("Pages", str(pages_scraped)),
        ("External", str(validated_source_count)),
        ("Duration", time_str),
    ]
    summary_items.extend(model_rows or [("LLM tokens", "0 in / 0 out")])
    summary_items.extend(
        [
            ("Actual Cost", f"~${actual_cost:.2f}"),
            ("Artifact Gate", "PASS" if artifacts_passed else "WARN"),
        ]
    )
    if strategy_paths:
        strat_labels = [_strategy_display_label(k) for k in strategy_paths]
        summary_items.append(("Strategies", ", ".join(strat_labels)))
    console.summary(summary_items)

    # Save usage to history
    from primr.data.search_utils import active_search_cost_per_query
    from primr.utils.usage_tracker import get_usage_tracker

    tracker = get_usage_tracker()
    tracker.record_usage(
        mode="fast",
        company=display_name,
        input_tokens=grok_usage["input_tokens"],
        output_tokens=grok_usage["output_tokens"],
        search_queries=search_query_count,
        duration_seconds=elapsed,
        pipeline_cost=actual_cost,
        cached_input_tokens=grok_usage.get("cached_input_tokens", 0),
        # Fast mode defaults to free DDG search; only a paid provider (Google
        # CSE) bills per query. Without this, ~30 free searches persist ~$1 of
        # phantom cost into the history that feeds future estimates.
        search_cost_per_query=active_search_cost_per_query(),
    )
    tracker.save()

    # Log job summary
    job_summary = JobSummary.create(
        company=display_name,
        mode="fast",
        duration_seconds=elapsed,
        api_calls=0,
        total_tokens=grok_usage["input_tokens"] + grok_usage["output_tokens"],
        sections_generated=written_sections_count,
        output_path=primary_output_path,
    )
    log_job_summary(job_summary)

    return primary_output_path
