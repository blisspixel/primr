from primr.core.research_agent import (
    _compute_fast_report_qa_metrics,
    _enforce_fast_section_quality_guards,
    _polish_fast_report_for_trust,
)


def test_polish_fast_report_returns_original_on_error(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("primr.ai.grok_client.grok_llm", _boom)
    original = "## Executive Summary\n\nTest content."
    result = _polish_fast_report_for_trust(
        "ExampleCo", "https://example.com", original, ["https://example.com/src"]
    )
    assert result == original


def test_polish_fast_report_uses_polished_output(monkeypatch):
    polished = "## Executive Summary\n\nImproved content [cite: 1].\n\n## Sources\n\n[cite: 1] https://example.com/src"

    def _ok(*args, **kwargs):
        return polished

    monkeypatch.setattr("primr.ai.grok_client.grok_llm", _ok)
    original = "## Executive Summary\n\nTest content."
    result = _polish_fast_report_for_trust(
        "ExampleCo", "https://example.com", original, ["https://example.com/src"]
    )
    assert result == polished


def test_polish_fast_report_includes_feedback_guidance(monkeypatch):
    captured = {"prompt": ""}

    def _ok(prompt, *args, **kwargs):
        captured["prompt"] = prompt
        return "## Executive Summary\n\nEdited."

    monkeypatch.setattr(
        "primr.core.research_agent._load_fast_feedback_guidance", lambda: "Rule A\nRule B"
    )
    monkeypatch.setattr("primr.ai.grok_client.grok_llm", _ok)

    _polish_fast_report_for_trust(
        "ExampleCo",
        "https://example.com",
        "## Executive Summary\n\nOriginal.",
        ["https://example.com/src"],
    )
    assert "Rule A" in captured["prompt"]
    assert "Rule B" in captured["prompt"]


def test_polish_fast_report_rejects_destructive_compression(monkeypatch):
    original = (
        "## Executive Summary\n\n" + ("Long content " * 800) + "\n\n"
        "## SWOT Analysis\n\n" + ("More long content " * 400)
    )

    def _compressed(*args, **kwargs):
        return "## Executive Summary\n\nShort."

    monkeypatch.setattr("primr.ai.grok_client.grok_llm", _compressed)
    result = _polish_fast_report_for_trust(
        "ExampleCo", "https://example.com", original, ["https://example.com/src"]
    )
    assert result == original


def test_enforce_fast_section_quality_guards_adds_labels_and_validation():
    report = (
        "# Report\n\n"
        "## Executive Summary\n\n"
        "This section has no explicit confidence markers.\n\n"
        "## Sources\n\n"
        "[cite: 1] https://example.com"
    )
    guarded = _enforce_fast_section_quality_guards(report)
    assert "(Reported)" in guarded
    assert "What to validate:" in guarded
    # Sources section should remain as a references section.
    assert "## Sources" in guarded


def test_compute_fast_report_qa_metrics_passes_on_guarded_report():
    report = (
        "# Report\n\n"
        "## Executive Summary\n\n"
        "Core claim with evidence (Reported).\n\n"
        "What to validate: Confirm adoption metrics in customer interviews.\n\n"
        "## Products and Services\n\n"
        "Offering detail (Estimated).\n\n"
        "What to validate: Validate product mix by segment.\n\n"
        "## Sources\n\n"
        "[cite: 1] https://example.com\n"
    )
    metrics = _compute_fast_report_qa_metrics(report)
    assert metrics["confidence_labels"] >= 2
    assert metrics["missing_citations"] == 0
    assert metrics["sections_with_validate"] == metrics["section_count"]
