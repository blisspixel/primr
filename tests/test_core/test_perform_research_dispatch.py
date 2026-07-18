"""Dispatcher-contract tests for perform_research (roadmap #23 endgame).

perform_research is the top-level mode dispatcher: input validation, run-state
init/resume, discovery-notes loading, the recon pre-flight (platform
auto-detection), the cost-confirmation gate, and routing to the fast /
scrape-only / deep pipelines. These tests patch the pipeline seams but use the
REAL run-state IO against tmp folders, so the persisted lifecycle
(initializing -> mode -> completed/failed/cancelled) is pinned as written to
disk, not as mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core import research_agent


def _read_state(folder: Path) -> dict:
    return json.loads((folder / "_run_state.json").read_text(encoding="utf-8"))


@pytest.fixture
def seams(monkeypatch, tmp_path):
    run_folder = tmp_path / "working" / "acme"
    run_folder.mkdir(parents=True)
    out_dir = tmp_path / "output"

    monkeypatch.setenv("XAI_API_KEY", "fake-xai-key-for-tests")
    monkeypatch.setattr(research_agent, "create_working_folder", lambda c, w, **k: str(run_folder))
    monkeypatch.setattr(research_agent, "OUTPUT_DIR", str(out_dir))

    fast = MagicMock(return_value=str(out_dir / "report.docx"))
    scrape_only = MagicMock(return_value=str(out_dir / "insights.md"))
    deep = MagicMock(return_value=str(out_dir / "deep.docx"))
    monkeypatch.setattr(research_agent, "perform_fast_research", fast)
    monkeypatch.setattr(research_agent, "perform_scrape_only", scrape_only)
    monkeypatch.setattr(research_agent, "perform_deep_research", deep)

    confirm = MagicMock(return_value=True)
    monkeypatch.setattr("primr.utils.cost_estimator.display_cost_estimate", confirm)

    # Seal the legacy structured-pipeline boundary: when a test routes past
    # the fast/deep dispatchers, the inline pipeline must not touch the
    # network. Empty scrape + failing quality gate stops it at phase 1.
    monkeypatch.setattr(research_agent, "fetch_web_content", lambda *a, **k: {})
    monkeypatch.setattr(
        research_agent,
        "_validate_scrape_quality",
        lambda data: (False, "no scraped content (test boundary)"),
    )

    return {
        "folder": run_folder,
        "out_dir": out_dir,
        "fast": fast,
        "scrape_only": scrape_only,
        "deep": deep,
        "confirm": confirm,
    }


def _run(**overrides):
    defaults = {
        "company_name": "AcmeCo",
        "website": "https://acme.example",
        "mode": "structured",
        "skip_confirm": True,
        "skip_recon": True,
    }
    defaults.update(overrides)
    return research_agent.perform_research(**defaults)


class TestInputValidation:
    def test_no_company_and_no_website_returns_none(self, seams):
        assert _run(company_name=None, website=None) is None
        seams["fast"].assert_not_called()


class TestRunStateLifecycle:
    def test_fresh_run_initializes_state_with_resilience_keys(self, seams):
        _run()
        state = _read_state(seams["folder"])
        assert state["company_name"] == "AcmeCo"
        assert state["mode"] == "structured"
        assert "background_aborts" in state  # resilience keys present
        assert any(e["status"] == "started" for e in state["events"])

    def test_fast_success_marks_completed(self, seams):
        result = _run()
        assert result == str(seams["out_dir"] / "report.docx")
        state = _read_state(seams["folder"])
        assert state["status"] == "completed"
        assert state["current_phase"] == "complete"
        assert "completed_at" in state

    def test_fast_failure_marks_failed(self, seams):
        seams["fast"].return_value = None
        assert _run() is None
        state = _read_state(seams["folder"])
        assert state["status"] == "failed"
        assert state["current_phase"] == "fast_mode"

    def test_resume_appends_resumed_event_and_keeps_keys(self, seams):
        (seams["folder"] / "_run_state.json").write_text(
            json.dumps({"status": "interrupted", "events": []}), encoding="utf-8"
        )
        _run(resume_local=True)
        state = _read_state(seams["folder"])
        assert "background_aborts" in state  # backfilled on resume
        assert any(e.get("status") == "resumed" for e in state["events"])

    def test_fresh_run_does_not_restore_platforms_from_existing_state(self, seams):
        (seams["folder"] / "_run_state.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "cloud_vendors": ["aws"],
                    "strategy_platform_source": "recon_single",
                    "events": [],
                }
            ),
            encoding="utf-8",
        )

        _run(resume_local=False)

        kwargs = seams["fast"].call_args.kwargs
        assert kwargs["platforms"] == ("agnostic",)
        state = _read_state(seams["folder"])
        assert state["cloud_vendors"] == ["agnostic"]
        assert state["strategy_platform_source"] == "default_agnostic"


class TestDiscoveryNotes:
    def test_missing_notes_file_fails_run(self, seams, tmp_path):
        result = _run(discovery_notes_path=str(tmp_path / "nope.md"))
        assert result is None
        state = _read_state(seams["folder"])
        assert state["status"] == "failed"
        seams["fast"].assert_not_called()

    def test_notes_content_threads_to_fast_pipeline(self, seams, tmp_path):
        notes = tmp_path / "notes.md"
        notes.write_text("met the CTO; cares about churn", encoding="utf-8")
        _run(discovery_notes_path=str(notes))
        kwargs = seams["fast"].call_args.kwargs
        assert kwargs["discovery_notes_content"] == "met the CTO; cares about churn"

    def test_empty_notes_treated_as_absent(self, seams, tmp_path):
        notes = tmp_path / "notes.md"
        notes.write_text("   ", encoding="utf-8")
        _run(discovery_notes_path=str(notes))
        assert seams["fast"].call_args.kwargs["discovery_notes_content"] is None


class TestCostConfirmationGate:
    def test_user_decline_cancels_run(self, seams):
        seams["confirm"].return_value = False
        assert _run(skip_confirm=False) is None
        state = _read_state(seams["folder"])
        assert state["status"] == "cancelled"
        seams["fast"].assert_not_called()

    def test_skip_confirm_bypasses_estimate(self, seams):
        _run(skip_confirm=True)
        seams["confirm"].assert_not_called()

    def test_confirm_gate_receives_full_shaping_flags(self, seams):
        """The interactive confirm number must reflect the same premium/verify/
        grok-tier/strategy shaping the run and the --budget gate price with, or
        the approved number diverges from actual spend (roadmap follow-up)."""
        _run(
            skip_confirm=False,
            mode="complete",
            premium_mode=True,
            verify=True,
            grok_tier="max",
            strategies=["customer_experience"],
        )
        kwargs = seams["confirm"].call_args.kwargs
        assert kwargs["premium_mode"] is True
        assert kwargs["verify"] is True
        assert kwargs["grok_tier"] == "max"
        assert kwargs["strategy_types"] == ["customer_experience"]


class TestReconPreflight:
    def _recon(self, monkeypatch, slugs=("aws",), detected=("aws",)):
        info = SimpleNamespace(slugs=list(slugs), services=["s1", "s2"], insights=["i1"])

        async def fake_resolve(domain):
            return info, []

        monkeypatch.setattr("recon_tool.resolver.resolve_tenant", fake_resolve)
        monkeypatch.setattr("primr.core.platform_mapper.map_platforms", lambda s: list(detected))
        monkeypatch.setattr(
            "primr.core.recon_context.format_recon_context", lambda i: "RECON CONTEXT"
        )
        return info

    def test_autodetect_sets_platforms_when_unspecified(self, seams, monkeypatch):
        self._recon(monkeypatch, detected=("azure",))
        _run(skip_recon=False, platforms=None)
        assert seams["fast"].call_args.kwargs["platforms"] == ("azure",)
        state = _read_state(seams["folder"])
        assert state["recon_detected_platforms"] == ["azure"]
        assert state["strategy_platform_source"] == "recon_single"
        assert state["recon_service_count"] == 2

    def test_no_strong_signal_keeps_one_agnostic_strategy(self, seams, monkeypatch):
        self._recon(monkeypatch, slugs=("microsoft365",), detected=("agnostic",))
        _run(skip_recon=False, platforms=None)
        assert seams["fast"].call_args.kwargs["platforms"] == ("agnostic",)
        state = _read_state(seams["folder"])
        assert state["cloud_vendors"] == ["agnostic"]
        assert state["recon_detected_platforms"] == []
        assert state["strategy_platform_source"] == "default_agnostic"

    def test_multiple_signals_produce_one_integrated_strategy(self, seams, monkeypatch):
        self._recon(monkeypatch, detected=("azure", "aws"))
        _run(skip_recon=False, platforms=None)
        assert seams["fast"].call_args.kwargs["platforms"] == ("agnostic",)
        state = _read_state(seams["folder"])
        assert state["cloud_vendors"] == ["agnostic"]
        assert state["recon_detected_platforms"] == ["azure", "aws"]
        assert state["strategy_platform_source"] == "recon_multiple_integrated"

    def test_explicit_platforms_win_over_detection(self, seams, monkeypatch):
        self._recon(monkeypatch, detected=("azure",))
        _run(skip_recon=False, platforms=("aws",))
        assert seams["fast"].call_args.kwargs["platforms"] == ("aws",)
        state = _read_state(seams["folder"])
        assert state["strategy_platform_source"] == "explicit"

    def test_recon_context_written_to_working_folder(self, seams, monkeypatch):
        self._recon(monkeypatch)
        _run(skip_recon=False)
        recon_file = seams["folder"] / "_recon_context.txt"
        assert recon_file.read_text(encoding="utf-8") == "RECON CONTEXT"

    def test_recon_failure_never_blocks_research(self, seams, monkeypatch):
        async def boom(domain):
            raise RuntimeError("DNS exploded")

        monkeypatch.setattr("recon_tool.resolver.resolve_tenant", boom)
        result = _run(skip_recon=False)
        assert result == str(seams["out_dir"] / "report.docx")
        state = _read_state(seams["folder"])
        assert any(
            e.get("status") == "failed" and e.get("phase") == "recon" for e in state["events"]
        )

    def test_resume_keeps_stored_platform_when_recon_fails(self, seams, monkeypatch):
        (seams["folder"] / "_run_state.json").write_text(
            json.dumps(
                {
                    "status": "interrupted",
                    "cloud_vendors": ["aws"],
                    "strategy_platform_source": "recon_single",
                    "events": [],
                }
            ),
            encoding="utf-8",
        )

        async def boom(domain):
            raise RuntimeError("DNS unavailable")

        monkeypatch.setattr("recon_tool.resolver.resolve_tenant", boom)
        _run(resume_local=True, skip_recon=False)

        assert seams["fast"].call_args.kwargs["platforms"] == ("aws",)
        state = _read_state(seams["folder"])
        assert state["cloud_vendors"] == ["aws"]
        assert state["strategy_platform_source"] == "recon_single"


class TestModeDispatch:
    def test_fast_mode_receives_output_routing(self, seams, tmp_path):
        custom_out = tmp_path / "custom"
        _run(output_dir=str(custom_out))
        kwargs = seams["fast"].call_args.kwargs
        assert kwargs["output_dir"] == custom_out
        assert kwargs["write_txt"] is False  # custom destination suppresses public txt
        assert kwargs["diagnostics_dir"] == seams["folder"] / "_diagnostics"

    def test_default_output_writes_public_txt(self, seams):
        _run()
        kwargs = seams["fast"].call_args.kwargs
        assert kwargs["write_txt"] is True
        assert kwargs["diagnostics_dir"] is None

    def test_scrape_only_dispatch(self, seams):
        result = _run(mode="scrape-only")
        assert result == str(seams["out_dir"] / "insights.md")
        seams["scrape_only"].assert_called_once()
        seams["fast"].assert_not_called()

    def test_deep_modes_dispatch_when_fast_unavailable(self, seams, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = _run(mode="complete", fast_mode=False)
        assert result == str(seams["out_dir"] / "deep.docx")
        seams["deep"].assert_called_once()
        seams["fast"].assert_not_called()

    def test_premium_mode_bypasses_fast_autodetect(self, seams):
        _run(mode="complete", premium_mode=True)
        seams["deep"].assert_called_once()
        seams["fast"].assert_not_called()

    def test_fast_autodetect_requires_xai_key(self, seams, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        _run(mode="structured")
        seams["fast"].assert_not_called()
