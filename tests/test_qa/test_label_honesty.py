"""Tests for the label-honesty pass (epistemic grounding, 1.x step 3 / #4).

The pass downgrades traceable-class confidence labels whose cited sources were
fetched and judged NOT to support the claim. Judgment decides; the downgrade is
a mechanical, fail-safe rewrite. Every effect is injectable, so the whole pass
is exercised here with deterministic fetch/judge seams and no network or LLM.
"""

from primr.qa.label_calibration import (
    LabeledClaim,
    calibrate_claims,
    extract_labeled_claims,
)
from primr.qa.label_honesty import (
    HONEST_DOWNGRADE_LABEL,
    LabelHonestyResult,
    apply_label_downgrades,
    apply_label_honesty,
    plan_label_downgrades,
)

# Inline labels (label on the claim's own line) plus the inference labels that
# must never be touched, with a Sources appendix in the current contract form.
INLINE_REPORT = """## Strategic Overview

Acme grew revenue to $50M in 2025. [cite: 1] (Confirmed)

Acme is the market leader in route optimization. [cite: 2] (Reported)

Acme will likely expand into Europe next year. (Estimated)

A bold move into hardware is plausible given recent hires. (Hypothesis)

## Sources

[cite: 1] https://acme.example/investors
[cite: 2] https://news.example/acme-leader
"""

# Standalone block-scoped label: the label trails the block it scopes,
# [paragraphs] [What to validate: ...] [label].
STANDALONE_REPORT = """## Margins

Acme gross margin is about 60% [cite: 1].

What to validate: confirm the figure against the latest 10-K.

(Confirmed)

## Sources

[cite: 1] https://acme.example/margins
"""


def _fetch(url: str) -> str:
    return {
        "https://acme.example/investors": "Acme reported revenue of $50M for fiscal 2025.",
        "https://news.example/acme-leader": "An unrelated article about regional weather.",
        "https://acme.example/margins": "The page discusses hiring, not margins.",
    }.get(url, "")


def _judge_supports_if_50m(claim: str, source_text: str) -> bool:
    # Supports only when the source text actually carries the figure.
    return "$50M" in source_text or "50M" in source_text


class TestLabelSpan:
    def test_inline_span_points_at_label_token(self):
        claims = extract_labeled_claims(INLINE_REPORT, max_per_label=50)
        confirmed = next(c for c in claims if c.label == "Confirmed")
        start, end = confirmed.label_span
        assert INLINE_REPORT[start:end] == "(Confirmed)"

    def test_standalone_span_points_at_label_token(self):
        claims = extract_labeled_claims(STANDALONE_REPORT, max_per_label=50)
        confirmed = next(c for c in claims if c.label == "Confirmed")
        start, end = confirmed.label_span
        assert STANDALONE_REPORT[start:end] == "(Confirmed)"

    def test_directly_built_claim_has_sentinel_span(self):
        # Backward-compatible default keeps existing constructors working.
        claim = LabeledClaim(
            label="Confirmed",
            sentence="x",
            section="s",
            cite_numbers=(),
            source_urls=(),
        )
        assert claim.label_span == (-1, -1)


class TestPlanDowngrades:
    def _calibration(self, report):
        claims = extract_labeled_claims(report, max_per_label=50)
        return report, calibrate_claims(claims, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m)

    def test_untraceable_traceable_label_is_planned(self):
        report, calibration = self._calibration(INLINE_REPORT)
        downgrades = plan_label_downgrades(report, calibration)
        assert len(downgrades) == 1
        only = downgrades[0]
        assert only.original_label == "Reported"  # the market-leader claim
        assert only.new_label == HONEST_DOWNGRADE_LABEL
        assert only.section == "Strategic Overview"
        assert report[only.span[0] : only.span[1]] == "(Reported)"

    def test_traceable_label_is_not_planned(self):
        report, calibration = self._calibration(INLINE_REPORT)
        downgrades = plan_label_downgrades(report, calibration)
        # The supported (Confirmed) revenue claim must be left alone.
        assert all(d.original_label != "Confirmed" for d in downgrades)

    def test_inference_labels_never_planned(self):
        report, calibration = self._calibration(INLINE_REPORT)
        downgrades = plan_label_downgrades(report, calibration)
        assert all(d.original_label in ("Confirmed", "Reported") for d in downgrades)

    def test_no_source_label_fails_open(self):
        # A Confirmed claim with no resolvable citation -> verdict no_source.
        # That is not positive evidence of an overclaim, so the pass leaves it.
        report = (
            "## Overview\n\nA confident but uncited statement. (Confirmed)\n\n"
            "## Sources\n\n[cite: 1] https://acme.example/x\n"
        )
        claims = extract_labeled_claims(report, max_per_label=50)
        calibration = calibrate_claims(claims, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m)
        assert plan_label_downgrades(report, calibration) == []

    def test_unfetchable_label_fails_open(self):
        report = INLINE_REPORT
        claims = extract_labeled_claims(report, max_per_label=50)
        # Every fetch returns empty -> verdict unfetchable -> no downgrade.
        calibration = calibrate_claims(
            claims, fetch_fn=lambda u: "", judge_fn=_judge_supports_if_50m
        )
        assert plan_label_downgrades(report, calibration) == []

    def test_drifted_span_is_refused(self):
        # A claim whose span no longer points at its own label is not rewritten.
        bad = LabeledClaim(
            label="Confirmed",
            sentence="x",
            section="s",
            cite_numbers=(1,),
            source_urls=("https://acme.example/x",),
            label_span=(0, 5),
        )
        from primr.qa.label_calibration import CalibrationReport, ClaimCalibration

        calibration = CalibrationReport(
            results=[ClaimCalibration(claim=bad, verdict="untraceable")]
        )
        assert plan_label_downgrades("nothing here matches", calibration) == []


class TestApplyDowngrades:
    def test_apply_rewrites_only_the_flagged_token(self):
        report, calibration = (
            INLINE_REPORT,
            calibrate_claims(
                extract_labeled_claims(INLINE_REPORT, max_per_label=50),
                fetch_fn=_fetch,
                judge_fn=_judge_supports_if_50m,
            ),
        )
        downgrades = plan_label_downgrades(report, calibration)
        rewritten = apply_label_downgrades(report, downgrades)
        # The unsupported market-leader claim is now (Estimated).
        assert "market leader in route optimization. [cite: 2] (Estimated)" in rewritten
        assert "(Reported)" not in rewritten
        # The supported revenue claim keeps (Confirmed); inference labels intact.
        assert "revenue to $50M in 2025. [cite: 1] (Confirmed)" in rewritten
        assert "(Hypothesis)" in rewritten

    def test_apply_drops_an_explanatory_suffix(self):
        report = (
            "## Overview\n\nGrowth is strong. [cite: 1] (Confirmed - per the 10-K)\n\n"
            "## Sources\n\n[cite: 1] https://acme.example/unrelated\n"
        )
        claims = extract_labeled_claims(report, max_per_label=50)
        calibration = calibrate_claims(
            claims, fetch_fn=lambda u: "Page about something else.", judge_fn=lambda c, t: False
        )
        downgrades = plan_label_downgrades(report, calibration)
        rewritten = apply_label_downgrades(report, downgrades)
        assert "(Estimated)" in rewritten
        assert "Confirmed" not in rewritten.split("## Sources")[0]

    def test_apply_with_no_downgrades_is_identity(self):
        assert apply_label_downgrades(INLINE_REPORT, []) == INLINE_REPORT


class TestApplyLabelHonesty:
    def test_end_to_end_downgrades_only_untraceable(self):
        result = apply_label_honesty(
            INLINE_REPORT, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m
        )
        assert isinstance(result, LabelHonestyResult)
        assert result.changed is True
        assert len(result.downgrades) == 1
        assert "(Reported)" not in result.report_content
        assert "revenue to $50M in 2025. [cite: 1] (Confirmed)" in result.report_content

    def test_standalone_label_is_downgraded(self):
        result = apply_label_honesty(
            STANDALONE_REPORT, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m
        )
        assert result.changed is True
        # The standalone (Confirmed) trailing the margins block becomes (Estimated).
        assert "\n(Estimated)\n" in result.report_content
        assert "\n(Confirmed)\n" not in result.report_content

    def test_all_supported_is_a_noop(self):
        result = apply_label_honesty(INLINE_REPORT, fetch_fn=_fetch, judge_fn=lambda c, t: True)
        assert result.changed is False
        assert result.report_content == INLINE_REPORT
        assert result.downgrades == ()

    def test_is_idempotent(self):
        first = apply_label_honesty(INLINE_REPORT, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m)
        second = apply_label_honesty(
            first.report_content, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m
        )
        # The downgraded label is now inference-class (exempt): nothing left to do.
        assert second.changed is False
        assert second.report_content == first.report_content

    def test_to_dict_is_json_shaped(self):
        result = apply_label_honesty(
            INLINE_REPORT, fetch_fn=_fetch, judge_fn=_judge_supports_if_50m
        )
        payload = result.to_dict()
        assert payload["downgraded_count"] == 1
        assert payload["downgrades"][0]["original_label"] == "Reported"
        assert payload["downgrades"][0]["new_label"] == HONEST_DOWNGRADE_LABEL
        assert "section" in payload["downgrades"][0]

    def test_audits_all_claims_no_cap_inconsistency(self):
        # The pass mutates, so it must audit EVERY claim: more than 50 of one
        # label must never ship with some downgraded and some not (which would
        # put two different labels on the same ungrounded claim).
        body = "\n\n".join(f"Acme dominates segment {i}. [cite: 1] (Confirmed)" for i in range(55))
        report = (
            f"## Overview\n\n{body}\n\n## Sources\n\n[cite: 1] https://acme.example/unrelated\n"
        )
        result = apply_label_honesty(
            report, fetch_fn=lambda u: "An unrelated page.", judge_fn=lambda c, t: False
        )
        assert result.report_content.count("(Confirmed)") == 0
        assert result.report_content.count("(Estimated)") == 55
        assert len(result.downgrades) == 55


class TestExtractCoverage:
    def test_none_extracts_all(self):
        body = "\n\n".join(f"Claim {i}. (Confirmed)" for i in range(12))
        report = f"## S\n\n{body}\n"
        assert len(extract_labeled_claims(report, max_per_label=None)) == 12

    def test_int_cap_still_bounds(self):
        body = "\n\n".join(f"Claim {i}. (Confirmed)" for i in range(12))
        report = f"## S\n\n{body}\n"
        assert len(extract_labeled_claims(report, max_per_label=3)) == 3
