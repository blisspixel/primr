"""
Tests for upgraded QASubagent and QAGateHook deterministic checks.

Covers: new dimension weights, hypothesis/confidence/truncation scoring,
and QAGateHook ReportAnalyzer-backed analysis.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.primr.agentic.hooks import HookContext, HookResult, HookType, QAGateHook
from src.primr.agentic.subagents.base import SubagentContext
from src.primr.agentic.subagents.qa import QASubagent


def _write_report(content: str) -> Path:
    """Write content to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def _make_qa_context(report_path: Path) -> SubagentContext:
    """Build a minimal SubagentContext pointing at a report file."""
    return SubagentContext(
        company_name="TestCo",
        company_url="https://testco.com",
        working_dir=report_path.parent,
        parent_results={"report_path": report_path},
    )


# Good report with hypothesis framing, confidence labels, and citations
GOOD_REPORT = (
    "# Strategic Overview: TestCo\n"
    "## Executive Summary\n"
    + "word "
    * 100
    + "\n(Confirmed) Revenue grew 20%. (Reported) CEO stated expansion plans.\n"
    "(Estimated) Market share around 15%. (Hypothesis) May target enterprise.\n"
    "We hypothesize that TestCo will expand. To validate, check filings.\n"
    "Worth validating the partnership claims. Appears to be growing.\n"
    "[cite: 1] [cite: 2] [cite: 3] [Source: Annual Report]\n"
    "## Key Insights\n" + "word " * 100 + "\n(Hypothesis) Could enter new markets.\n"
    "[cite: 4] [cite: 5]\n"
    "## Sources\n" + "word " * 60 + "\nhttps://testco.com [cite: 6]\n"
)

# Thin report with no hypothesis framing or confidence labels
THIN_REPORT = "# Report\n## Section One\nShort text.\n## Section Two\nAlso short.\n"


# =============================================================================
# QASubagent Tests
# =============================================================================


class TestQASubagentDimensions:
    def test_dimensions_include_new_keys(self):
        assert "hypothesis_framing" in QASubagent.DIMENSIONS
        assert "confidence_labels" in QASubagent.DIMENSIONS

    def test_weights_sum_to_one(self):
        total = sum(QASubagent.DIMENSIONS.values())
        assert abs(total - 1.0) < 1e-9

    def test_good_report_scores_high(self):
        report_path = _write_report(GOOD_REPORT)
        ctx = _make_qa_context(report_path)
        agent = QASubagent(ctx)
        result = asyncio.run(agent.execute())
        assert result.status.value == "completed"
        assert result.data is not None
        assert result.data.score >= 70
        assert "hypothesis_framing" in result.data.dimension_scores
        assert "confidence_labels" in result.data.dimension_scores

    def test_thin_report_penalizes_hypothesis_framing(self):
        report_path = _write_report(THIN_REPORT)
        ctx = _make_qa_context(report_path)
        agent = QASubagent(ctx)
        result = asyncio.run(agent.execute())
        assert result.data is not None
        assert result.data.dimension_scores["hypothesis_framing"] <= 60
        assert any("hypothesis" in f.lower() for f in result.data.feedback)

    def test_thin_report_penalizes_confidence_labels(self):
        report_path = _write_report(THIN_REPORT)
        ctx = _make_qa_context(report_path)
        agent = QASubagent(ctx)
        result = asyncio.run(agent.execute())
        assert result.data is not None
        assert result.data.dimension_scores["confidence_labels"] <= 70
        assert any("confidence" in f.lower() for f in result.data.feedback)

    def test_truncated_sections_feedback(self):
        content = "# Report\n## Full Section\n" + "word " * 100 + "\n## Stub Section\nTiny.\n"
        report_path = _write_report(content)
        ctx = _make_qa_context(report_path)
        agent = QASubagent(ctx)
        result = asyncio.run(agent.execute())
        assert result.data is not None
        assert "Stub Section" in result.data.sections_to_improve


# =============================================================================
# QAGateHook Tests
# =============================================================================


class TestQAGateHookDeterministic:
    def _run_hook(self, report_content: str) -> tuple[int | None, list[str]]:
        """Run the QAGateHook on report content and return (score, feedback)."""
        report_path = _write_report(report_content)

        # Build a mock result object with report_path attribute
        mock_result = MagicMock()
        mock_result.report_path = str(report_path)
        mock_result.data = None

        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=mock_result,
        )

        hook = QAGateHook(min_score=70)
        asyncio.run(hook.execute(context))
        return hook.last_score, hook.last_feedback

    def test_penalizes_missing_hypothesis_framing(self):
        content = (
            "# Report\n"
            "## Executive Summary\n" + "word " * 200 + "\n"
            "## Key Insights\n" + "word " * 200 + "\n"
            "## Sources\n" + "word " * 200 + "\n"
        )
        score, feedback = self._run_hook(content)
        assert score is not None
        assert any("hypothesis" in f.lower() for f in feedback)

    def test_penalizes_truncated_sections(self):
        content = (
            "# Report\n"
            "## Executive Summary\n" + "word " * 200 + "\n"
            "## Key Insights\n" + "word " * 200 + "\n"
            "## Stub\nTiny.\n"
            "## Sources\n" + "word " * 200 + "\n"
        )
        score, feedback = self._run_hook(content)
        assert score is not None
        assert any("truncated" in f.lower() for f in feedback)

    def test_rewards_complete_report(self):
        score, feedback = self._run_hook(GOOD_REPORT)
        assert score is not None
        assert score >= 70

    def test_score_stays_in_range(self):
        # Minimal report should still produce 0-100 score
        score, _ = self._run_hook("tiny")
        assert score is not None
        assert 0 <= score <= 100

        # Good report too
        score2, _ = self._run_hook(GOOD_REPORT)
        assert score2 is not None
        assert 0 <= score2 <= 100

    def test_skips_non_write_stage(self):
        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="scrape",
        )
        hook = QAGateHook(min_score=70)
        response = asyncio.run(hook.execute(context))
        assert response.result == HookResult.ALLOW
