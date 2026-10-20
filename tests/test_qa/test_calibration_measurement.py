"""Tests for offline calibration measurement."""

from pathlib import Path

import pytest

from primr.qa.calibration_measurement import (
    claim_text_for_judge,
    load_captured_sources,
    lookup_captured_source,
    parse_judge_verdict,
    relevant_passage,
    report_clustered_wilson_lower,
    sample_labeled_claims,
    wilson_lower_bound,
)
from primr.qa.label_calibration import (
    LabeledClaim,
    build_evidence_review_prompt,
    build_judge_prompt,
    calibrate_claims,
)


def test_judge_label_pattern_matches_the_extractor() -> None:
    from primr.qa import calibration_measurement, label_calibration

    assert calibration_measurement._LABEL_RE.pattern == label_calibration._LABEL_RE.pattern


def test_claim_text_for_judge_removes_confidence_labels() -> None:
    text = claim_text_for_judge("Revenue reached $50M. (Confirmed - filings) [cite: 1]\n(Reported)")
    assert "(Confirmed" not in text
    assert "(Reported)" not in text
    assert "Revenue reached $50M." in text
    assert "[cite: 1]" in text


def test_judge_prompt_hides_the_confidence_label_and_picks_the_relevant_passage() -> None:
    filler = "Unrelated market commentary. " * 400
    source = filler + "\n\nRevenue reached $50M in the annual filing.\n\n" + filler
    prompt = build_judge_prompt(
        "Revenue reached $50M. (Confirmed) [cite: 1]",
        source,
    )
    assert "(Confirmed)" not in prompt
    assert "Revenue reached $50M." in prompt
    assert "annual filing" in prompt
    assert "Abstain when the source text is not enough to decide." in prompt
    assert len(prompt) < len(source)


def test_evidence_review_prompt_can_abstain_without_seeing_the_label() -> None:
    prompt = build_evidence_review_prompt(
        "Revenue reached $50M. (Confirmed) [cite: 1]",
        "Revenue reached $50M in the annual filing.",
    )
    assert "(Confirmed)" not in prompt
    assert "true | false | abstain" in prompt
    assert "Set supported to abstain" in prompt


def test_relevant_passage_keeps_short_sources_whole() -> None:
    source = "Revenue reached $50M."
    assert relevant_passage("Revenue reached $50M.", source) == source


def test_parse_judge_verdict_keeps_abstain_distinct() -> None:
    assert parse_judge_verdict("yes") == "yes"
    assert parse_judge_verdict("<think>maybe</think>\nabstain") == "abstain"
    assert parse_judge_verdict("the source is merely related") == "unparseable"
    assert parse_judge_verdict("yes, with a caveat") == "yes"


def test_abstain_is_recorded_and_excluded_from_precision() -> None:
    claim = LabeledClaim(
        "Confirmed",
        "Revenue reached $50M. (Confirmed) [cite: 1]",
        "Executive Summary",
        (1,),
        ("https://news.example/revenue",),
    )
    seen: list[str] = []

    def judge(claim_text: str, source_text: str) -> str:
        seen.append(claim_text)
        assert "$50M" in source_text
        return "abstain"

    report = calibrate_claims(
        [claim],
        fetch_fn=lambda _url: "Revenue reached $50M in the filing.",
        judge_fn=judge,
    )
    assert "(Confirmed)" not in seen[0]
    assert report.results[0].verdict == "abstain"
    assert report.results[0].judge_verdicts == ("abstain",)
    assert report.precision("Confirmed") is None
    payload = report.to_dict()
    assert payload["per_label"]["Confirmed"]["abstain"] == 1
    assert payload["claims"][0]["judge_verdicts"] == ["abstain"]
    assert payload["validation_rubric"]["support"]["abstained"] == 1
    assert payload["validation_rubric"]["support"]["unsupported"] == 0


def test_unparseable_judge_stays_untraceable() -> None:
    claim = LabeledClaim(
        "Confirmed",
        "Revenue reached $50M. (Confirmed) [cite: 1]",
        "Executive Summary",
        (1,),
        ("https://news.example/revenue",),
    )
    report = calibrate_claims(
        [claim],
        fetch_fn=lambda _url: "Revenue reached $50M.",
        judge_fn=lambda _claim, _source: "not a verdict",
    )
    assert report.results[0].verdict == "untraceable"
    assert report.results[0].judge_verdicts == ("unparseable",)
    assert report.precision("Confirmed") == 0.0


def test_captured_source_is_used_without_a_live_fetch(tmp_path: Path) -> None:
    capture = tmp_path / "scraped_content.txt"
    capture.write_text(
        "\n".join(
            [
                "# ExampleCo - Scraped Content",
                "=" * 60,
                "URL: https://news.example/revenue",
                "=" * 60,
                "Revenue reached $50M in the annual filing.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    captured = load_captured_sources(capture)
    claim = LabeledClaim(
        "Confirmed",
        "Revenue reached $50M. (Confirmed) [cite: 1]",
        "Executive Summary",
        (1,),
        ("https://news.example/revenue",),
    )

    def explode(_url: str) -> str:
        raise AssertionError("live fetch should not run")

    report = calibrate_claims(
        [claim],
        fetch_fn=explode,
        judge_fn=lambda _claim, source: "yes" if "$50M" in source else "no",
        captured_sources=captured,
    )
    assert report.results[0].verdict == "traceable"


@pytest.mark.parametrize(
    ("requested", "captured"),
    [
        ("https://news.example/report", "https://news.example/Report"),
        ("https://news.example/report?id=abc", "https://news.example/report?id=ABC"),
        ("https://news.example/report/", "https://news.example/report"),
        ("https://news.example/report", "https://news.example/report/"),
    ],
)
def test_frozen_capture_does_not_substitute_a_similar_url(requested: str, captured: str) -> None:
    assert lookup_captured_source(requested, {captured: "Wrong resource"}) is None
    fetched: list[str] = []
    judged: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return "Requested resource, fetched explicitly."

    claim = LabeledClaim("Confirmed", "A claim. (Confirmed)", "S", (1,), (requested,))
    calibrate_claims(
        [claim],
        fetch_fn=fetch,
        judge_fn=lambda _claim, source: judged.append(source) or "yes",
        captured_sources={captured: "Wrong resource"},
    )
    assert fetched == [requested]
    assert judged == ["Requested resource, fetched explicitly."]


@pytest.mark.parametrize("text", ["", "Exact frozen evidence."])
def test_exact_frozen_capture_wins_even_when_empty(text: str) -> None:
    url = "https://news.example/report"
    captures = {url.upper(): "Wrong case", url + "/": "Wrong slash", url: text}
    assert lookup_captured_source(url, captures) == text

    def fetch(_url: str) -> str:
        pytest.fail("Exact captures, including empty ones, must never be fetched")

    judged: list[str] = []
    claim = LabeledClaim("Confirmed", "A claim. (Confirmed)", "S", (1,), (url,))
    result = calibrate_claims(
        [claim],
        fetch_fn=fetch,
        judge_fn=lambda _claim, source: judged.append(source) or "yes",
        captured_sources=captures,
    )
    assert judged == ([text] if text else [])
    assert result.results[0].verdict == ("traceable" if text else "unfetchable")


def test_seeded_sample_is_stable_and_not_only_the_document_prefix() -> None:
    claims = [
        LabeledClaim("Confirmed", f"Claim {index}. (Confirmed)", "S", (), ()) for index in range(6)
    ]
    first = sample_labeled_claims(claims, max_per_label=2, seed=1)
    again = sample_labeled_claims(claims, max_per_label=2, seed=1)
    assert [claim.sentence for claim in first] == [claim.sentence for claim in again]
    assert len(first) == 2
    prefix = [claim.sentence for claim in claims[:2]]
    assert any(
        [claim.sentence for claim in sample_labeled_claims(claims, max_per_label=2, seed=seed)]
        != prefix
        for seed in range(10)
    )


def test_clustered_wilson_lower_bound_is_below_a_perfect_point_rate() -> None:
    assert round(wilson_lower_bound(3, 10), 3) == 0.108
    assert round(wilson_lower_bound(5, 5), 3) == 0.566
    assert round(wilson_lower_bound(4, 4), 3) == 0.51
    assert round(report_clustered_wilson_lower([(1, 1)] * 5), 3) == 0.566
    assert round(report_clustered_wilson_lower([(1, 1)] * 4), 3) == 0.51
    pooled = wilson_lower_bound(4, 5)
    clustered = report_clustered_wilson_lower([(1, 1), (1, 1), (1, 1), (1, 1), (0, 1)])
    assert clustered is not None
    assert clustered < pooled
