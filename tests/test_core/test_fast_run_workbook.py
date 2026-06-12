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
