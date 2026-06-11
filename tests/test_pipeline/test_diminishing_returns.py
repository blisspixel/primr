"""Tests for diminishing-returns detection in the cross-validation loop."""

from primr.pipeline.diminishing_returns import (
    DEFAULT_CONSECUTIVE_LIMIT,
    DEFAULT_IMPROVEMENT_THRESHOLD,
    DiminishingReturnsDetector,
    SectionImprovement,
    assess_improvement,
)


def _improvement(score: float, title: str = "Section") -> SectionImprovement:
    return SectionImprovement(
        section_title=title, word_delta_ratio=score, new_citations=0, score=score
    )


class TestAssessImprovement:
    def test_word_growth_scores_positive(self):
        original = "word " * 100
        regenerated = "word " * 120
        imp = assess_improvement("S", original, regenerated)
        assert imp.word_delta_ratio == 0.2
        assert imp.score == 0.2

    def test_shrinking_rewrite_scores_zero_not_negative(self):
        original = "word " * 100
        regenerated = "word " * 80
        imp = assess_improvement("S", original, regenerated)
        assert imp.word_delta_ratio == -0.2
        assert imp.score == 0.0

    def test_new_citations_count_as_improvement(self):
        original = "Claim without source. " * 10
        regenerated = original + " Backed [cite: 3] and confirmed [cite: 7]."
        imp = assess_improvement("S", original, regenerated)
        assert imp.new_citations == 2
        assert imp.score >= 0.10  # 2 citations x 5%

    def test_citation_loss_does_not_go_negative(self):
        original = "Backed [cite: 1] and [cite: 2]. " * 5
        regenerated = "Backed once [cite: 1]. " * 5
        imp = assess_improvement("S", original, regenerated)
        assert imp.new_citations == 0

    def test_empty_original_with_content_is_full_improvement(self):
        imp = assess_improvement("S", "", "brand new content here")
        assert imp.score == 1.0

    def test_empty_both_is_zero(self):
        imp = assess_improvement("S", "", "")
        assert imp.score == 0.0


class TestDetector:
    def test_defaults_match_roadmap(self):
        assert DEFAULT_IMPROVEMENT_THRESHOLD == 0.05
        assert DEFAULT_CONSECUTIVE_LIMIT == 3

    def test_no_stop_before_limit(self):
        detector = DiminishingReturnsDetector()
        detector.record(_improvement(0.01))
        detector.record(_improvement(0.02))
        assert not detector.should_stop()

    def test_stops_after_three_consecutive_low(self):
        detector = DiminishingReturnsDetector()
        for _ in range(3):
            detector.record(_improvement(0.01))
        assert detector.should_stop()

    def test_good_regeneration_resets_streak(self):
        detector = DiminishingReturnsDetector()
        detector.record(_improvement(0.01))
        detector.record(_improvement(0.02))
        detector.record(_improvement(0.30))  # real improvement resets
        detector.record(_improvement(0.01))
        detector.record(_improvement(0.01))
        assert not detector.should_stop()
        detector.record(_improvement(0.01))
        assert detector.should_stop()

    def test_threshold_boundary_exactly_at_threshold_is_not_low(self):
        detector = DiminishingReturnsDetector()
        for _ in range(5):
            detector.record(_improvement(0.05))  # == threshold, not below
        assert not detector.should_stop()

    def test_stop_reason_mentions_iterations(self):
        detector = DiminishingReturnsDetector()
        for _ in range(3):
            detector.record(_improvement(0.0))
        reason = detector.stop_reason()
        assert "diminishing returns" in reason
        assert "3 iteration(s)" in reason

    def test_summary_is_json_shaped(self):
        import json

        detector = DiminishingReturnsDetector()
        detector.record(
            SectionImprovement(
                section_title="Market", word_delta_ratio=0.1, new_citations=2, score=0.1
            )
        )
        summary = detector.summary()
        # Round-trips through JSON and carries the per-section detail
        encoded = json.loads(json.dumps(summary))
        assert encoded["iterations"] == 1
        assert encoded["stopped_early"] is False
        assert encoded["per_section"][0]["section"] == "Market"

    def test_custom_thresholds(self):
        detector = DiminishingReturnsDetector(improvement_threshold=0.5, consecutive_limit=2)
        detector.record(_improvement(0.4))
        detector.record(_improvement(0.4))
        assert detector.should_stop()
