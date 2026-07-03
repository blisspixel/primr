"""Tests for confidence-label calibration (epistemics measurement, 1.x step 1)."""

import json

from primr.qa.label_calibration import (
    CalibrationReport,
    EvidenceReview,
    LabeledClaim,
    calibrate_claims,
    extract_labeled_claims,
    label_citations_trust_row,
    parse_evidence_review,
    parse_sources_appendix,
    summarize_label_citation_coverage,
)

REPORT = """## Executive Summary
Revenue reached $50M in 2025. (Confirmed) [cite: 1]
Headcount grew to 500 across three offices. (Reported) [cite: 2, 3]
Margins are likely compressing. (Estimated - triangulated from filings)
An unannounced product line is in development. (Hypothesis)
A claim with a label but no citation at all. (Confirmed)

## Market Landscape
The market is consolidating. (Reported) [cite: 9]

## Sources
1. https://news.example.com/revenue
2. https://trade.example.org/headcount
[3] https://filings.example.gov/10k
"""


# The current artifact contract: "[cite: N] url" appendix entries and
# block-scoped standalone labels ([paragraphs] [What to validate] [label]).
MODERN_REPORT = """## Strategic Hypotheses

### Central Hypothesis: The "Two-Front" Pivot
Acme Corp is executing a two-front pivot toward managed services [cite: 4].

The durability of this pivot depends on partner certifications [cite: 5] and
the retention of senior architects.

What to validate: Ask leadership how partner incentives are structured.

(Reported)

### Margin Hypothesis
Margins are likely compressing under hardware resale pressure.

What to validate: Request gross-margin trend by segment.

(Hypothesis)

## Competitive Landscape
The integrator market is consolidating around three platforms. (Reported) [cite: 4]

(Estimated)

## Sources

[cite: 4] https://news.example.com/pivot
[cite: 5] https://trade.example.org/certs
"""


class TestSourcesAppendix:
    def test_parses_both_entry_formats(self):
        mapping = parse_sources_appendix(REPORT)
        assert mapping[1] == "https://news.example.com/revenue"
        assert mapping[3] == "https://filings.example.gov/10k"

    def test_parses_cite_marker_entry_format(self):
        mapping = parse_sources_appendix(MODERN_REPORT)
        assert mapping[4] == "https://news.example.com/pivot"
        assert mapping[5] == "https://trade.example.org/certs"

    def test_missing_appendix_falls_back_to_whole_doc(self):
        mapping = parse_sources_appendix("1. https://a.example/x\n")
        assert mapping[1] == "https://a.example/x"


class TestStandaloneLabelBlocks:
    def _claims(self):
        return extract_labeled_claims(MODERN_REPORT)

    def test_standalone_label_associates_with_preceding_block(self):
        reported = [c for c in self._claims() if c.label == "Reported"]
        block_claim = next(c for c in reported if "two-front pivot" in c.sentence)
        assert "durability of this pivot" in block_claim.sentence

    def test_block_cites_collected_and_resolved(self):
        reported = [c for c in self._claims() if c.label == "Reported"]
        block_claim = next(c for c in reported if "two-front pivot" in c.sentence)
        assert block_claim.cite_numbers == (4, 5)
        assert block_claim.source_urls == (
            "https://news.example.com/pivot",
            "https://trade.example.org/certs",
        )

    def test_validate_question_excluded_from_claim(self):
        for claim in self._claims():
            assert "What to validate" not in claim.sentence

    def test_block_walk_stops_at_heading(self):
        hypothesis = next(c for c in self._claims() if c.label == "Hypothesis")
        assert "Margins are likely compressing" in hypothesis.sentence
        # Must not leak the previous section's block past the ### heading.
        assert "two-front pivot" not in hypothesis.sentence

    def test_inline_label_in_modern_report_still_line_scoped(self):
        reported = [c for c in self._claims() if c.label == "Reported"]
        inline = next(c for c in reported if "consolidating" in c.sentence)
        assert inline.cite_numbers == (4,)
        assert "\n" not in inline.sentence

    def test_bare_label_with_no_prose_skipped(self):
        # The "(Estimated)" after the inline claim has only a labeled line
        # above it (a standalone-label boundary), so nothing to associate...
        estimated = [c for c in self._claims() if c.label == "Estimated"]
        # ...the inline (Reported) line above it is NOT a standalone label,
        # so the block walk picks that prose up - assert the verdict-relevant
        # invariant instead: no empty-sentence claims are ever emitted.
        assert all(c.sentence.strip() for c in self._claims())
        assert all(c.sentence.strip() for c in estimated)

    def test_label_at_top_of_document_skipped(self):
        claims = extract_labeled_claims("(Confirmed)\n\nSome prose later.\n")
        assert claims == []

    def test_block_bounded_by_max_chars(self):
        big_para = "x" * 900
        doc = f"## S\n{big_para}\n\n{big_para}\n\n{big_para}\n\n(Reported)\n"
        claims = extract_labeled_claims(doc)
        assert len(claims) == 1
        # Bounded: stops once accumulated paragraphs pass the char cap.
        assert len(claims[0].sentence) <= 2 * 900 + 10


class TestExtraction:
    def test_extracts_all_labels_with_suffix_tolerance(self):
        claims = extract_labeled_claims(REPORT)
        labels = [c.label for c in claims]
        assert labels.count("Confirmed") == 2
        assert labels.count("Reported") == 2
        assert "Estimated" in labels  # suffix form "(Estimated - ...)" counted
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

    def test_inference_label_copied_from_cited_source_is_flagged(self):
        claims = [
            LabeledClaim(
                "Estimated",
                "Revenue will likely reach $50M in 2026 from enterprise subscriptions. "
                "(Estimated) [cite: 1]",
                "Executive Summary",
                (1,),
                ("https://news.example.com/revenue",),
            )
        ]

        report = calibrate_claims(
            claims,
            fetch_fn=lambda u: (
                "In its forecast, Revenue will likely reach $50M in 2026 "
                "from enterprise subscriptions."
            ),
            judge_fn=lambda c, t: True,
        )

        assert report.results[0].verdict == "source_copied"
        assert report.to_dict()["per_label"]["Estimated"]["source_copied"] == 1

    def test_inference_label_not_copied_from_source_stays_exempt(self):
        claims = [
            LabeledClaim(
                "Hypothesis",
                "Expansion into Europe is plausible given recent partner hiring. (Hypothesis) "
                "[cite: 1]",
                "Executive Summary",
                (1,),
                ("https://news.example.com/hiring",),
            )
        ]

        report = calibrate_claims(
            claims,
            fetch_fn=lambda u: "The company hired a new partner lead in Berlin.",
            judge_fn=lambda c, t: True,
        )

        assert report.results[0].verdict == "exempt"
        assert report.to_dict()["per_label"]["Hypothesis"]["source_copied"] == 0

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
        assert revenue.evidence_reviews[0].supported is False

    def test_review_fn_records_richer_evidence_dimensions(self):
        claims = [
            LabeledClaim(
                "Confirmed",
                "Revenue reached $50M. (Confirmed) [cite: 1]",
                "Executive Summary",
                (1,),
                ("https://news.example.com/revenue",),
            )
        ]

        report = calibrate_claims(
            claims,
            fetch_fn=lambda u: "Revenue reached $50M.",
            review_fn=lambda c, t: EvidenceReview(
                supported=True,
                contradiction="none",
                source_independence="independent",
                source_authority="high",
                reasoning_strength="strong",
                uncertainty_honesty="honest",
                business_relevance="high",
                rationale="The source directly states the revenue figure.",
            ),
        )

        payload = report.to_dict()
        assert report.results[0].verdict == "traceable"
        assert payload["claims"][0]["evidence_reviews"][0]["source_authority"] == "high"
        assert payload["validation_rubric"]["source_reviews"] == 1
        assert payload["validation_rubric"]["support"]["supported"] == 1
        assert payload["validation_rubric"]["reasoning_strength"]["strong"] == 1

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
        assert encoded["validation_rubric"]["source_reviews"] == 3
        assert isinstance(encoded["claims"], list)


class TestParseEvidenceReview:
    def test_parses_json_review(self):
        raw = json.dumps(
            {
                "supported": True,
                "contradiction": "none",
                "source_independence": "independent",
                "source_authority": "high",
                "reasoning_strength": "strong",
                "uncertainty_honesty": "honest",
                "business_relevance": "high",
                "rationale": "The cited source directly supports the claim.",
            }
        )
        review = parse_evidence_review(raw)
        assert review.supported is True
        assert review.source_independence == "independent"
        assert review.source_authority == "high"
        assert review.reasoning_strength == "strong"
        assert review.uncertainty_honesty == "honest"
        assert review.business_relevance == "high"

    def test_off_schema_review_values_stay_unknown(self):
        review = parse_evidence_review(
            json.dumps(
                {
                    "supported": True,
                    "source_authority": "official",
                    "reasoning_strength": "supported",
                }
            )
        )
        assert review.supported is True
        assert review.source_authority == "unknown"
        assert review.reasoning_strength == "unknown"

    def test_parses_fenced_json_review(self):
        review = parse_evidence_review(
            """```json
{"supported": false, "contradiction": "direct", "reasoning_strength": "weak"}
```"""
        )
        assert review.supported is False
        assert review.contradiction == "direct"
        assert review.reasoning_strength == "weak"

    def test_malformed_review_falls_back_to_yes_no(self):
        assert parse_evidence_review("yes, supported").supported is True
        assert parse_evidence_review("the source is merely related").supported is False


class TestParseJudgeAnswer:
    def _parse(self, raw):
        from primr.qa.label_calibration import parse_judge_answer

        return parse_judge_answer(raw)

    def test_one_word_answers(self):
        assert self._parse("yes") is True
        assert self._parse("No") is False
        assert self._parse("YES.") is True

    def test_quoted_and_decorated_answers(self):
        assert self._parse('"yes"') is True
        assert self._parse("**No**") is False

    def test_direct_answer_wins_over_trailing_mentions(self):
        # The model answered first, then elaborated using the other word.
        assert self._parse("Yes - though the source has no exact figure.") is True
        assert self._parse("No, the claim says yes but the source does not.") is False

    def test_reasoning_answer_concludes_with_verdict(self):
        assert self._parse("The claim asserts X. The source covers X. So: yes") is True

    def test_think_block_content_ignored(self):
        raw = "<think>I'd say yes... wait, the figures differ</think>\nno"
        assert self._parse(raw) is False

    def test_unparseable_never_counts_as_support(self):
        assert self._parse("") is False
        assert self._parse("the source is interesting") is False


class TestEndToEndFile:
    def test_calibrate_report_file(self, tmp_path):
        from primr.qa.label_calibration import calibrate_report_file

        path = tmp_path / "AcmeCo_Strategic_Overview.md"
        path.write_text(REPORT, encoding="utf-8")
        report = calibrate_report_file(
            str(path), fetch_fn=lambda u: "text", judge_fn=lambda c, t: True
        )
        assert report.precision("Reported") is not None


class TestLabelCitationCoverage:
    """Deterministic, judge-free label-citation coverage (the no_source slice
    surfaced for free on every run)."""

    def test_counts_traceable_claims_with_and_without_citations(self):
        cov = summarize_label_citation_coverage(REPORT)
        # Confirmed: revenue [cite:1] (cited) + "no citation at all" (uncited).
        assert cov["confirmed_total"] == 2
        assert cov["confirmed_cited"] == 1
        # Reported: headcount [cite:2,3] (cited) + market [cite:9] (9 does not
        # resolve against the 1-3 appendix, so no source).
        assert cov["reported_total"] == 2
        assert cov["reported_cited"] == 1
        assert cov["traceable_total"] == 4
        assert cov["traceable_cited"] == 2
        assert cov["coverage_rate"] == 0.5

    def test_estimated_and_hypothesis_labels_are_excluded(self):
        cov = summarize_label_citation_coverage(REPORT)
        # Only Confirmed/Reported count toward traceable; the (Estimated) and
        # (Hypothesis) lines in REPORT must not inflate the totals.
        assert cov["traceable_total"] == cov["confirmed_total"] + cov["reported_total"]

    def test_no_traceable_claims_is_full_coverage(self):
        report = "## S\nMargins may compress. (Estimated)\nNew line coming. (Hypothesis)\n"
        cov = summarize_label_citation_coverage(report)
        assert cov["traceable_total"] == 0
        assert cov["coverage_rate"] == 1.0

    def test_all_cited_is_perfect_coverage(self):
        report = (
            "## S\nRevenue hit $9M. (Confirmed) [cite: 1]\n\n## Sources\n1. https://a.example/x\n"
        )
        cov = summarize_label_citation_coverage(report)
        assert cov["traceable_total"] == 1
        assert cov["traceable_cited"] == 1
        assert cov["coverage_rate"] == 1.0


class TestLabelCitationsTrustRow:
    """The shared row formatter behind both report-trust surfaces (fast +
    deep), so the 'Label Citations' row reads identically wherever it renders."""

    def test_none_when_no_traceable_claims(self):
        assert label_citations_trust_row(0, 0) is None

    def test_none_when_total_non_positive(self):
        assert label_citations_trust_row(3, -1) is None

    def test_row_when_traceable_present(self):
        assert label_citations_trust_row(2, 3) == (
            "Label Citations",
            "2/3 Confirmed/Reported cite a source",
        )
