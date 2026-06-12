"""Tests for confidence-label calibration (epistemics measurement, 1.x step 1)."""

import json

from primr.qa.label_calibration import (
    CalibrationReport,
    LabeledClaim,
    calibrate_claims,
    extract_labeled_claims,
    parse_sources_appendix,
)

REPORT = """## Executive Summary
Revenue reached $50M in 2025. (Confirmed) [cite: 1]
Headcount grew to 500 across three offices. (Reported) [cite: 2, 3]
Margins are likely compressing. (Estimated — triangulated from filings)
An unannounced product line is in development. (Hypothesis)
A claim with a label but no citation at all. (Confirmed)

## Market Landscape
The market is consolidating. (Reported) [cite: 9]

## Sources
1. https://news.example.com/revenue
2. https://trade.example.org/headcount
[3] https://filings.example.gov/10k
"""


class TestSourcesAppendix:
    def test_parses_both_entry_formats(self):
        mapping = parse_sources_appendix(REPORT)
        assert mapping[1] == "https://news.example.com/revenue"
        assert mapping[3] == "https://filings.example.gov/10k"

    def test_missing_appendix_falls_back_to_whole_doc(self):
        mapping = parse_sources_appendix("1. https://a.example/x\n")
        assert mapping[1] == "https://a.example/x"


class TestExtraction:
    def test_extracts_all_labels_with_suffix_tolerance(self):
        claims = extract_labeled_claims(REPORT)
        labels = [c.label for c in claims]
        assert labels.count("Confirmed") == 2
        assert labels.count("Reported") == 2
        assert "Estimated" in labels  # suffix form "(Estimated — ...)" counted
        assert "Hypothesis" in labels

    def test_citations_resolved(self):
        claims = extract_labeled_claims(REPORT)
        revenue = next(c for c in claims if "Revenue" in c.sentence)
        assert revenue.cite_numbers == (1,)
        assert revenue.source_urls == ("https://news.example.com/revenue",)
        headcount = next(c for c in claims if "Headcount" in c.sentence)
        assert headcount.cite_numbers == (2, 3)
        assert len(headcount.source_urls) == 2

    def test_unresolvable_citation_yields_no_urls(self):
        claims = extract_labeled_claims(REPORT)
        market = next(c for c in claims if "consolidating" in c.sentence)
        assert market.cite_numbers == (9,)
        assert market.source_urls == ()

    def test_section_attribution(self):
        claims = extract_labeled_claims(REPORT)
        market = next(c for c in claims if "consolidating" in c.sentence)
        assert market.section == "Market Landscape"

    def test_per_label_cap(self):
        many = (
            "## S\n"
            + ("A fact. (Confirmed) [cite: 1]\n" * 30)
            + "\n## Sources\n1. https://a.example\n"
        )
        claims = extract_labeled_claims(many, max_per_label=5)
        assert len([c for c in claims if c.label == "Confirmed"]) == 5

    def test_appendix_lines_not_sampled(self):
        doc = "## Sources\n1. https://a.example (Confirmed)\n"
        assert extract_labeled_claims(doc) == []


class TestCalibration:
    def _claims(self):
        return extract_labeled_claims(REPORT)

    def test_inference_labels_exempt(self):
        report = calibrate_claims(
            self._claims(), fetch_fn=lambda u: "text", judge_fn=lambda c, t: True
        )
        estimated = [r for r in report.results if r.claim.label == "Estimated"]
        hypothesis = [r for r in report.results if r.claim.label == "Hypothesis"]
        assert all(r.verdict == "exempt" for r in estimated + hypothesis)

    def test_traceable_when_judge_supports(self):
        report = calibrate_claims(
            self._claims(), fetch_fn=lambda u: "source text", judge_fn=lambda c, t: True
        )
        revenue = next(r for r in report.results if "Revenue" in r.claim.sentence)
        assert revenue.verdict == "traceable"

    def test_untraceable_when_judge_rejects(self):
        report = calibrate_claims(
            self._claims(), fetch_fn=lambda u: "source text", judge_fn=lambda c, t: False
        )
        revenue = next(r for r in report.results if "Revenue" in r.claim.sentence)
        assert revenue.verdict == "untraceable"

    def test_no_source_counts_against_precision(self):
        report = calibrate_claims(
            self._claims(), fetch_fn=lambda u: "text", judge_fn=lambda c, t: True
        )
        uncited = next(r for r in report.results if "no citation" in r.claim.sentence)
        assert uncited.verdict == "no_source"
        # Confirmed: 1 traceable + 1 no_source -> precision 0.5
        assert report.precision("Confirmed") == 0.5

    def test_unfetchable_excluded_from_precision(self):
        report = calibrate_claims(self._claims(), fetch_fn=lambda u: "", judge_fn=lambda c, t: True)
        revenue = next(r for r in report.results if "Revenue" in r.claim.sentence)
        assert revenue.verdict == "unfetchable"
        # Confirmed decidable set = only the no_source claim -> precision 0.0
        assert report.precision("Confirmed") == 0.0

    def test_fetches_deduped(self):
        calls = []

        def counting_fetch(url):
            calls.append(url)
            return "text"

        claims = [
            LabeledClaim("Confirmed", "a (Confirmed) [cite: 1]", "S", (1,), ("https://a.example",)),
            LabeledClaim("Reported", "b (Reported) [cite: 1]", "S", (1,), ("https://a.example",)),
        ]
        calibrate_claims(claims, fetch_fn=counting_fetch, judge_fn=lambda c, t: True)
        assert calls.count("https://a.example") == 1

    def test_precision_none_when_label_absent(self):
        report = CalibrationReport(results=[])
        assert report.precision("Confirmed") is None

    def test_report_serializes_to_json(self):
        report = calibrate_claims(
            self._claims(), fetch_fn=lambda u: "text", judge_fn=lambda c, t: True
        )
        encoded = json.loads(json.dumps(report.to_dict()))
        assert encoded["per_label"]["Confirmed"]["sampled"] == 2
        assert encoded["per_label"]["Estimated"]["exempt"] == 1
        assert isinstance(encoded["claims"], list)


class TestEndToEndFile:
    def test_calibrate_report_file(self, tmp_path):
        from primr.qa.label_calibration import calibrate_report_file

        path = tmp_path / "AcmeCo_Strategic_Overview.md"
        path.write_text(REPORT, encoding="utf-8")
        report = calibrate_report_file(
            str(path), fetch_fn=lambda u: "text", judge_fn=lambda c, t: True
        )
        assert report.precision("Reported") is not None
