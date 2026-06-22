"""Tests for _repair_strategy_artifact_issues and _prepare_strategy_for_output."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import (
    _prepare_strategy_for_output,
    _repair_strategy_artifact_issues,
)


class TestRepairStrategyArtifactIssues:
    def test_empty_content_returns_unchanged(self):
        result = _repair_strategy_artifact_issues(
            "", "Acme", "azure", "Microsoft", [], ["budget_inconsistent"]
        )
        assert result == ""

    def test_whitespace_content_returns_unchanged(self):
        result = _repair_strategy_artifact_issues(
            "   \n  ", "Acme", "azure", "Microsoft", [], ["budget_inconsistent"]
        )
        assert result == "   \n  "

    def test_no_issues_returns_unchanged(self):
        original = "## Section\n\nbody content here"
        result = _repair_strategy_artifact_issues(original, "Acme", "azure", "Microsoft", [], [])
        assert result == original

    def test_llm_exception_returns_original(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(side_effect=RuntimeError("grok down")),
        )
        original = "## Section\n\nbody"
        result = _repair_strategy_artifact_issues(
            original,
            "Acme",
            "azure",
            "Microsoft",
            ["https://s.example"],
            ["missing_citations"],
        )
        assert result == original

    def test_empty_llm_response_returns_original(self, monkeypatch):
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value=""))
        original = "## Section\n\nbody"
        result = _repair_strategy_artifact_issues(
            original,
            "Acme",
            "azure",
            "Microsoft",
            [],
            ["budget_inconsistent"],
        )
        assert result == original

    def test_repaired_content_returned(self, monkeypatch):
        repaired = "## Section\n\nrepaired body"
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value=repaired))
        result = _repair_strategy_artifact_issues(
            "## Section\n\noriginal body",
            "Acme",
            "azure",
            "Microsoft",
            ["https://s.example"],
            ["missing_citations"],
        )
        assert result == repaired

    def test_agnostic_vendor_uses_strategy_label(self, monkeypatch):
        mock = MagicMock(return_value="## ok\n\nrepaired")
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _repair_strategy_artifact_issues(
            "## ok\n\norig",
            "Acme",
            "agnostic",
            "Customer Experience",
            [],
            ["missing_citations"],
        )
        prompt = mock.call_args.args[0]
        # When vendor=agnostic, vendor_label should fall through to strategy_label
        assert "Customer Experience" in prompt

    def test_explicit_model_used(self, monkeypatch):
        # Routed through the failover seam: a real registered model passed
        # explicitly is honored as the preferred (first-tried) model. Unknown
        # model strings fall through to the chain default by design.
        from primr.pipeline.llm_failover import set_breaker_for_test
        from primr.pipeline.model_breaker import ModelCircuitBreaker

        set_breaker_for_test(ModelCircuitBreaker())
        monkeypatch.setenv("XAI_API_KEY", "fake")
        mock = MagicMock(return_value="## ok\n\nrepaired")
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", mock)
        _repair_strategy_artifact_issues(
            "## ok\n\norig",
            "Acme",
            "azure",
            "Microsoft",
            [],
            ["missing_citations"],
            model="grok-4.3",
        )
        set_breaker_for_test(None)
        assert mock.call_args.kwargs["model"] == "grok-4.3"


class TestPrepareStrategyForOutput:
    def test_clean_strategy_no_issues_returns_qa_metrics(self, monkeypatch):
        # Stub the dependencies to avoid network calls
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value="## Section\n\nbody"),
        )
        strategy = "## Section\n\nbody content [cite: 1]\n\n## Sources\n[cite: 1] https://a.example"
        result, qa, rejected = _prepare_strategy_for_output(
            strategy, "Acme", "azure", "Microsoft", ["https://a.example"]
        )
        # Returns a 3-tuple
        assert isinstance(result, str)
        assert isinstance(qa, dict)
        assert isinstance(rejected, list)

    def test_returns_tuple_of_three(self, monkeypatch):
        monkeypatch.setattr("primr.ai.grok_client.grok_llm", MagicMock(return_value="ok"))
        result = _prepare_strategy_for_output("", "Acme", "azure", "Microsoft", [])
        assert len(result) == 3


def test_repair_strategy_sends_full_document_not_truncated(monkeypatch):
    """Bug-hunt round 3: the repair LLM must see the FULL document. The old
    [:50_000] cap dropped everything past 50K from the rewrite (silent loss)."""
    captured: dict = {}

    def fake_failover(role, prompt, **kwargs):
        captured["prompt"] = prompt
        return "## Fixed\n\nrepaired document"

    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", fake_failover)
    tail_marker = "UNIQUE_TAIL_MARKER_XYZ"
    big = "## Section\n\n" + ("filler word " * 8000) + "\n\n" + tail_marker + "\n"
    assert len(big) > 80_000  # well past the old 50K cap
    _repair_strategy_artifact_issues(
        big, "Acme", "azure", "Microsoft", ["https://x.example"], ["budget_inconsistent"]
    )
    assert tail_marker in captured["prompt"]
