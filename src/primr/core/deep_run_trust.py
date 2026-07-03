"""Deep-run report trust summary (trust-visibility parity with the fast path).

The fast path surfaces an always-on report trust summary (``fast_run_trust``),
including the deterministic label-citation coverage row added for every run.
The deep and complete Deep-Research paths shipped without any trust summary, so
a ``--premium`` / ``--mode deep`` run gave the user no label-traceability
signal at all. This builds the same judge-free signal from the finished deep
report so both paths get equivalent trust visibility.

Pure and network-free: it reads only the finished report text and reuses the
same ``summarize_label_citation_coverage`` seam the fast path computes from, so
the two paths cannot describe the signal differently. Report-only - a signal,
never a gate - matching ``docs/design/agentic-balance.md``.
"""

from __future__ import annotations

from primr.qa.label_calibration import (
    label_citations_trust_row,
    summarize_label_citation_coverage,
)


def build_deep_report_trust_stats(report_content: str) -> list[tuple[str, str]]:
    """Return ``(label, value)`` trust rows for a finished deep-run report.

    Currently the deterministic label-citation coverage row: how many
    ``(Confirmed)``/``(Reported)`` claims carry a resolvable citation (the
    ``no_source`` slice). Returns an empty list when the report has no
    traceable-class claims, so the caller skips the panel entirely rather than
    showing a meaningless ``0/0``. The row itself comes from the shared
    ``label_citations_trust_row`` formatter, so this reads identically to the
    fast path's ``Label Citations`` row.
    """
    if not report_content or not report_content.strip():
        return []
    coverage = summarize_label_citation_coverage(report_content)
    row = label_citations_trust_row(
        int(coverage["traceable_cited"]), int(coverage["traceable_total"])
    )
    return [row] if row else []
