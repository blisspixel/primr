"""Machine-readable (JSON) CLI output helpers.

Centralizes the ``--json`` output contract so stdout stays a clean, stable JSON
object for agents and CI. The builders are pure (testable); ``emit_json`` is the
single place a JSON result is written to stdout.

Contract: in ``--json`` mode, stdout carries exactly one JSON object, including
truthful nonzero structured results. Progress chrome cannot interleave with it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

from primr.core.cli_command_output import emit_json as _emit_json

if TYPE_CHECKING:
    from primr.core.strategy_outcome import StrategyOutcome
    from primr.core.vendor_refresh_outcome import VendorRefreshOutcome
    from primr.utils.cost_estimator import CostEstimate


def emit_json(obj: dict[str, object]) -> None:
    """Keep the established import surface while delegating JSON emission."""
    _emit_json(obj)


def cost_estimate_json(
    estimate: CostEstimate,
    *,
    mode_label: str,
    ai_strategy: bool,
    budget_enforcement: dict[str, object] | None = None,
    inference: dict[str, object] | None = None,
) -> dict[str, object]:
    """Structured cost estimate for ``--dry-run --json`` (estimate-first for agents)."""
    data: dict[str, object] = dataclasses.asdict(estimate)
    data["mode_label"] = mode_label
    data["includes_ai_strategy"] = ai_strategy
    if budget_enforcement is not None:
        data["budget_enforcement"] = budget_enforcement
    if inference is not None:
        data["inference"] = inference
    return data


def research_result_json(
    result_path: str | None,
    *,
    company: str | None,
    website: str | None,
    mode: str,
    strategy_outcome: StrategyOutcome | None = None,
    vendor_refresh_outcome: VendorRefreshOutcome | None = None,
    fulfillment_status: str | None = None,
    outcome_state_status: str | None = None,
    run_state_path: str | None = None,
) -> dict[str, object]:
    """Structured result summary for a completed/failed research run.

    Reports base-artifact status, aggregate fulfillment, run inputs, and
    produced artifacts with a cheap text word count. Paths are absolute so a
    caller in another directory can open them directly.
    """
    out: dict[str, object] = {
        "status": "completed" if result_path else "failed",
        "company": company,
        "website": website,
        "mode": mode,
        "report_path": None,
        "docx_path": None,
        "word_count": None,
    }
    if result_path:
        report = Path(result_path)
        out["report_path"] = str(report.resolve())
        if report.suffix.lower() in {".md", ".txt"}:
            try:
                out["word_count"] = len(report.read_text(encoding="utf-8").split())
            except (OSError, UnicodeDecodeError):
                out["word_count"] = None
        docx = report if report.suffix.lower() == ".docx" else report.with_suffix(".docx")
        if docx.exists():
            out["docx_path"] = str(docx.resolve())
    if fulfillment_status is not None:
        out["fulfillment_status"] = fulfillment_status
    if outcome_state_status is not None:
        out["outcome_state_status"] = outcome_state_status
        out["run_state_path"] = run_state_path
    if strategy_outcome is not None:
        out.update(strategy_outcome.as_run_state())
    if vendor_refresh_outcome is not None:
        out.update(vendor_refresh_outcome.as_run_state())
    return out
