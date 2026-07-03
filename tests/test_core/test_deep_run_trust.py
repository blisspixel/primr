"""Tests for the deep-run report trust summary helper.

Pins that ``build_deep_report_trust_stats`` surfaces the same always-on,
judge-free label-citation coverage row the fast path shows - so a deep /
``--premium`` run reports label traceability with identical wording - and that
an empty report or a report with no traceable-class claims yields no panel
(rather than a meaningless ``0/0``).
"""

from __future__ import annotations

from primr.core.deep_run_trust import build_deep_report_trust_stats

# Confirmed x2 (revenue cited via [cite: 1]; the no-citation line uncited),
# Reported x1 (headcount cited via [cite: 2]) -> 2 of 3 traceable claims cite
# a resolvable source.
_MIXED_REPORT = (
    "## Findings\n\n"
    "Revenue reached $50M. (Confirmed) [cite: 1]\n\n"
    "Headcount grew to 500. (Reported) [cite: 2]\n\n"
    "A claim with no citation. (Confirmed)\n\n"
    "## Sources\n\n"
    "1. https://a.example/revenue\n"
    "2. https://b.example/headcount\n"
)


class TestBuildDeepReportTrustStats:
    def test_empty_content_returns_no_rows(self):
        assert build_deep_report_trust_stats("") == []

    def test_whitespace_content_returns_no_rows(self):
        assert build_deep_report_trust_stats("   \n\t  ") == []

    def test_no_traceable_claims_returns_no_rows(self):
        # (Estimated) is not a traceable-class label; nothing to under-cite,
        # so the panel is omitted entirely rather than shown as 0/0.
        report = "## Findings\n\nThe market may consolidate. (Estimated)\n"
        assert build_deep_report_trust_stats(report) == []

    def test_counts_cited_over_total_traceable_claims(self):
        assert build_deep_report_trust_stats(_MIXED_REPORT) == [
            ("Label Citations", "2/3 Confirmed/Reported cite a source")
        ]

    def test_all_traceable_claims_cited(self):
        report = "Revenue hit $9M. (Confirmed) [cite: 1]\n\n## Sources\n\n1. https://a.example/x\n"
        assert build_deep_report_trust_stats(report) == [
            ("Label Citations", "1/1 Confirmed/Reported cite a source")
        ]

    def test_row_wording_matches_fast_path_verbatim(self):
        # The fast path (fast_run_trust) renders the identical value phrasing;
        # both surfaces must read the same, so pin the exact suffix.
        rows = build_deep_report_trust_stats(_MIXED_REPORT)
        label, value = rows[0]
        assert label == "Label Citations"
        assert value.endswith("Confirmed/Reported cite a source")
