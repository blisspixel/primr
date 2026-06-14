"""Tests for the extracted analysis-workbook stage (roadmap #23, Batch C).

Pins the session tangle (refactor map #5): continuous mode constructs the
shared ContinuousReasoningSession here and returns it for Phase 5 reuse.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_workbook import ANALYSIS_SYSTEM_PROMPT, generate_analysis_workbook


@pytest.fixture
def seams(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_recovery(executor, fn, folder_path):
        captured["recovery_args"] = (executor, folder_path)
        return SimpleNamespace(success=True, output=fn(), skip_reason=None)

    monkeypatch.setattr("primr.pipeline.integration.analysis_with_recovery", fake_recovery)

    failover = MagicMock(return_value="workbook via failover")
    monkeypatch.setattr("primr.core.fast_run_workbook.call_with_failover", failover)

    session_cls = MagicMock()
    session_cls.return_value.send.return_value = "workbook via session"
    monkeypatch.setattr("primr.ai.grok_client.ContinuousReasoningSession", session_cls)

    captured["failover"] = failover
    captured["session_cls"] = session_cls
    captured["tmp"] = tmp_path
    return captured


def _call(seams, **overrides):
    defaults = {
        "company_label": "AcmeCo",
        "website": "https://acme.example",
        "raw_corpus": "corpus text",
        "external_sources_raw": "external text",
        "combined_insights": "fallback insights",
        "grok_reasoning": "reasoner-model",
        "grok_reasoning_effort": None,
        "continuous_reasoning": False,
        "reasoning_session": None,
        "recovery_executor": object(),
        "folder_path": str(seams["tmp"]),
        "total_phases": 5,
    }
    defaults.update(overrides)
    return generate_analysis_workbook(**defaults)


class TestFreshCallTopology:
    def test_failover_path_used_when_not_continuous(self, seams):
        workbook, session = _call(seams)
        assert workbook == "workbook via failover"
        assert session is None
        seams["session_cls"].assert_not_called()
        kwargs = seams["failover"].call_args.kwargs
        assert kwargs["preferred_model"] == "reasoner-model"
        assert kwargs["system_prompt"] == ANALYSIS_SYSTEM_PROMPT

    def test_workbook_persisted_to_working_folder(self, seams):
        _call(seams)
        path = seams["tmp"] / "analysis_workbook.md"
        assert path.read_text(encoding="utf-8") == "workbook via failover"


class TestContinuousSessionTangle:
    def test_session_constructed_and_returned(self, seams):
        workbook, session = _call(seams, continuous_reasoning=True)
        assert workbook == "workbook via session"
        assert session is seams["session_cls"].return_value
        ctor = seams["session_cls"].call_args.kwargs
        assert ctor["model"] == "reasoner-model"
        assert ctor["system_prompt"] == ANALYSIS_SYSTEM_PROMPT
        seams["failover"].assert_not_called()

    def test_existing_session_reused_not_reconstructed(self, seams):
        existing = MagicMock()
        existing.send.return_value = "workbook via existing session"
        workbook, session = _call(seams, continuous_reasoning=True, reasoning_session=existing)
        assert workbook == "workbook via existing session"
        assert session is existing
        seams["session_cls"].assert_not_called()

    def test_reasoning_effort_threaded_to_session(self, seams):
        _call(seams, continuous_reasoning=True, grok_reasoning_effort="low")
        assert seams["session_cls"].call_args.kwargs["reasoning_effort"] == "low"


class TestFallbacks:
    def test_recovery_failure_falls_back_to_insights(self, seams, monkeypatch):
        monkeypatch.setattr(
            "primr.pipeline.integration.analysis_with_recovery",
            lambda *a: SimpleNamespace(success=False, output=None, skip_reason="exhausted"),
        )
        workbook, _ = _call(seams)
        assert workbook == "fallback insights"

    def test_empty_output_falls_back_to_insights(self, seams):
        seams["failover"].return_value = "   "
        workbook, _ = _call(seams)
        assert workbook == "fallback insights"

    def test_fallback_workbook_still_persisted(self, seams):
        seams["failover"].return_value = ""
        _call(seams)
        path = seams["tmp"] / "analysis_workbook.md"
        assert path.read_text(encoding="utf-8") == "fallback insights"


class TestDay1HypothesisTree:
    """Tradecraft Step 2b: a framed run forms + saves the Day-1 tree and prepends
    it to the workbook prompt; an unframed run is unchanged."""

    _TREE_JSON = (
        '{"branches": [{"issue": "Posture", "hypotheses": '
        '[{"claim": "TREE_CLAIM_TOKEN", "test_question": "azure or on-prem?"}]}]}'
    )

    def _role_aware(self, seams):
        """Make call_with_failover return tree JSON for the WRITING (tree) call
        and workbook text for the REASONING (workbook) call."""
        from primr.pipeline.llm_failover import LLMRole

        def side_effect(role, prompt, **kwargs):
            if role == LLMRole.WRITING:
                return self._TREE_JSON
            return "workbook via failover"

        seams["failover"].side_effect = side_effect
        return seams

    def test_tree_formed_saved_and_prepended_when_framed(self, seams):
        from primr.core.research_framing import ResearchFraming

        self._role_aware(seams)
        framing = ResearchFraming(core_question="near-term cloud budget?")
        _call(seams, framing=framing)

        # Artifact written
        md = (seams["tmp"] / "hypothesis_tree.md").read_text(encoding="utf-8")
        assert "TREE_CLAIM_TOKEN" in md
        assert (seams["tmp"] / "hypothesis_tree.json").exists()

        # Tree prepended to the workbook (REASONING) prompt
        from primr.pipeline.llm_failover import LLMRole

        reasoning_prompts = [
            c.args[1]
            for c in seams["failover"].call_args_list
            if len(c.args) >= 2 and c.args[0] == LLMRole.REASONING
        ]
        assert reasoning_prompts
        assert "DAY-1 HYPOTHESIS TREE" in reasoning_prompts[0]
        assert "TREE_CLAIM_TOKEN" in reasoning_prompts[0]

    def test_no_tree_when_unframed(self, seams):
        _call(seams)  # no framing
        assert not (seams["tmp"] / "hypothesis_tree.md").exists()

    def test_no_tree_when_framing_unspecified(self, seams):
        from primr.core.research_framing import ResearchFraming

        self._role_aware(seams)
        _call(seams, framing=ResearchFraming())  # neutral -> not is_specified
        assert not (seams["tmp"] / "hypothesis_tree.md").exists()

    def test_failsoft_when_tree_llm_returns_garbage(self, seams):
        from primr.core.research_framing import ResearchFraming
        from primr.pipeline.llm_failover import LLMRole

        def side_effect(role, prompt, **kwargs):
            if role == LLMRole.WRITING:
                return "sorry, no JSON here"
            return "workbook via failover"

        seams["failover"].side_effect = side_effect
        # Must not raise; empty tree saved, nothing prepended.
        workbook, _ = _call(seams, framing=ResearchFraming(core_question="x"))
        assert workbook == "workbook via failover"
        md = (seams["tmp"] / "hypothesis_tree.md").read_text(encoding="utf-8")
        assert "No hypotheses formed" in md


class TestPrebuiltTreeReuse:
    """Tradecraft Step 4: the orchestrator builds the tree once before deepening
    and passes the block here for reuse, so the workbook does NOT rebuild it."""

    def test_prebuilt_block_used_without_rebuild(self, seams):
        from primr.pipeline.llm_failover import LLMRole

        _call(seams, prebuilt_day1_block="=== DAY-1 HYPOTHESIS TREE ===\nPREBUILT_TOKEN")

        # No WRITING (tree-build) call happened — the block was reused.
        writing_calls = [
            c for c in seams["failover"].call_args_list if c.args and c.args[0] == LLMRole.WRITING
        ]
        assert not writing_calls
        # Not re-saved at this stage (the orchestrator already saved it).
        assert not (seams["tmp"] / "hypothesis_tree.md").exists()
        # Prepended to the reasoning prompt.
        reasoning_prompts = [
            c.args[1]
            for c in seams["failover"].call_args_list
            if len(c.args) >= 2 and c.args[0] == LLMRole.REASONING
        ]
        assert any("PREBUILT_TOKEN" in p for p in reasoning_prompts)

    def test_empty_prebuilt_block_prepends_nothing(self, seams):
        from primr.pipeline.llm_failover import LLMRole

        _call(seams, prebuilt_day1_block="")
        reasoning_prompts = [
            c.args[1]
            for c in seams["failover"].call_args_list
            if len(c.args) >= 2 and c.args[0] == LLMRole.REASONING
        ]
        assert reasoning_prompts
        assert "DAY-1 HYPOTHESIS TREE" not in reasoning_prompts[0]


class TestBuildDay1HypothesisTree:
    """The hoisted builder: returns (block, tree), fails soft, no-op when unframed."""

    _TREE_JSON = (
        '{"branches": [{"issue": "Posture", "hypotheses": '
        '[{"claim": "BUILD_TOKEN", "test_question": "azure or on-prem?"}]}]}'
    )

    def test_unframed_returns_empty(self, seams):
        from primr.core.fast_run_workbook import build_day1_hypothesis_tree

        block, tree = build_day1_hypothesis_tree("Acme", None, "corpus", "ext", str(seams["tmp"]))
        assert block == ""
        assert tree is None

    def test_framed_returns_block_and_tree(self, seams):
        from primr.core.fast_run_workbook import build_day1_hypothesis_tree
        from primr.core.research_framing import ResearchFraming

        seams["failover"].return_value = self._TREE_JSON
        block, tree = build_day1_hypothesis_tree(
            "Acme", ResearchFraming(core_question="q?"), "c", "e", str(seams["tmp"])
        )
        assert "DAY-1 HYPOTHESIS TREE" in block
        assert "BUILD_TOKEN" in block
        assert tree is not None
        assert not tree.is_empty
        assert (seams["tmp"] / "hypothesis_tree.md").exists()

    def test_failsoft_on_exception(self, seams):
        from primr.core.fast_run_workbook import build_day1_hypothesis_tree
        from primr.core.research_framing import ResearchFraming

        seams["failover"].side_effect = RuntimeError("boom")
        block, tree = build_day1_hypothesis_tree(
            "Acme", ResearchFraming(core_question="q?"), "c", "e", str(seams["tmp"])
        )
        assert block == ""
        assert tree is None
