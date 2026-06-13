"""Machine-readable (JSON) CLI output helpers.

Centralizes the ``--json`` output contract so stdout stays a clean, stable JSON
object for agents and CI. The builders are pure (testable); ``emit_json`` is the
single place a JSON result is written to stdout.

Contract: in ``--json`` mode, stdout carries exactly one JSON object on success
(exit 0). Progress chrome is suppressed so it cannot interleave with the JSON.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from primr.utils.cost_estimator import CostEstimate


def cost_estimate_json(
    estimate: CostEstimate, *, mode_label: str, ai_strategy: bool
) -> dict[str, object]:
    """Structured cost estimate for ``--dry-run --json`` (estimate-first for agents)."""
    data: dict[str, object] = dataclasses.asdict(estimate)
    data["mode_label"] = mode_label
    data["includes_ai_strategy"] = ai_strategy
    return data


def research_result_json(
    result_path: str | None,
    *,
    company: str | None,
    website: str | None,
    mode: str,
) -> dict[str, object]:
    """Structured result summary for a completed/failed research run.

    Reports status, the run inputs, and the produced artifacts (Markdown plus a
    sibling DOCX when present) with a cheap word count. Paths are absolute so a
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
        try:
            out["word_count"] = len(report.read_text(encoding="utf-8").split())
        except OSError:
            pass
        docx = report.with_suffix(".docx")
        if docx.exists():
            out["docx_path"] = str(docx.resolve())
    return out


def emit_json(obj: dict[str, object]) -> None:
    """Write a JSON object to stdout (the single ``--json`` emission point)."""
    print(json.dumps(obj, indent=2, ensure_ascii=False))
