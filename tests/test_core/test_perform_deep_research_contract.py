"""Contract tests for perform_deep_research (roadmap #23 endgame).

The premium-mode orchestrator: pre-flight validation before expensive API
calls, orphaned-resource cleanup, the async DeepResearch orchestrator call,
partial-result salvage on failure, artifact generation routing, the strategy
loop, and usage/cost recording. Seams are patched; run-state IO is real
against tmp folders so the persisted lifecycle is pinned as written to disk.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.config.models import DEEP_RESEARCH_COST
from primr.core import research_agent
from primr.utils.run_budget import clear_run_budget


def _read_state(folder: Path) -> dict:
    return json.loads((folder / "_run_state.json").read_text(encoding="utf-8"))


def _result(**overrides):
    defaults = {
        "success": True,
        "error": None,
        "section_results": {"overview": "## Overview\nbody"},
        "sections_written": 8,
        "raw_content": "## Report\nfull markdown [cite: 1] and [cite: 2]",
        "search_queries_count": 12,
        "pending_interaction_id": "interaction-123",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def seams(monkeypatch, tmp_path):
    run_folder = tmp_path / "working" / "acme"
    run_folder.mkdir(parents=True)
    out_dir = tmp_path / "output"

    monkeypatch.setattr(
        "primr.config.settings.get_settings",
        lambda: SimpleNamespace(api=SimpleNamespace(gemini_key="fake-gemini-key")),
    )
    cleanup = MagicMock(return_value={"caches_deleted": 0, "stores_deleted": 0})
    monkeypatch.setattr("primr.ai.deep_research.cleanup_orphaned_resources", cleanup)

    research_result = _result()

    async def fake_research(**kwargs):
        captured["research_kwargs"] = kwargs
        return research_result

    orchestrator = SimpleNamespace(research=fake_research)
    monkeypatch.setattr(research_agent, "get_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(research_agent, "collect_fenced_hiring_block", lambda **_: "")

    save_section = MagicMock()
    monkeypatch.setattr(research_agent, "save_section_output", save_section)

    def write_report_outputs(*_args, written_paths, **_kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = [out_dir / "deep.md", out_dir / "deep.txt", out_dir / "deep.docx"]
        for path in paths:
            path.write_text("content", encoding="utf-8")
        written_paths.extend(paths)
        return str(paths[-1])

    docx = MagicMock(side_effect=write_report_outputs)
    monkeypatch.setattr(research_agent, "_convert_deep_research_to_docx", docx)
    verify = MagicMock()
    monkeypatch.setattr(research_agent, "_run_claim_verification_non_blocking", verify)
    acknowledge = MagicMock(return_value=True)
    monkeypatch.setattr(
        "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
        acknowledge,
    )
    final_report = MagicMock(return_value=str(out_dir / "assembled.docx"))
    monkeypatch.setattr(research_agent, "generate_final_report", final_report)

    def generate_strategy(**kwargs):
        observer = kwargs.get("strategy_task_observer")
        if observer:
            observer("started")
            observer("completed")
        return str(out_dir / f"{kwargs['platform']}.docx")

    strategy_gen = MagicMock(side_effect=generate_strategy)
    monkeypatch.setattr(research_agent, "_generate_strategy_section", strategy_gen)

    fake_client = MagicMock()
    fake_client.get_usage_summary.return_value = {
        "total_cost": 1.25,
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
    }
    monkeypatch.setattr("primr.ai.client.get_client", lambda: fake_client)
    monkeypatch.setattr(
        "primr.utils.cost_estimator.estimate_cost",
        lambda *a, **k: SimpleNamespace(total_cost=2.50),
    )
    tracker = MagicMock()
    monkeypatch.setattr("primr.utils.usage_tracker.get_usage_tracker", lambda: tracker)
    job_log = MagicMock()
    # The finalization tail (cost/summary/usage/job-summary) now lives in the
    # extracted deep_run_summary seam, so patch log_job_summary where it is
    # called from, not research_agent's (no-longer-invoked) namespace binding.
    monkeypatch.setattr("primr.core.deep_run_summary.log_job_summary", job_log)

    captured = {
        "folder": run_folder,
        "out_dir": out_dir,
        "result": research_result,
        "cleanup": cleanup,
        "save_section": save_section,
        "docx": docx,
        "verify": verify,
        "acknowledge": acknowledge,
        "final_report": final_report,
        "strategy_gen": strategy_gen,
        "tracker": tracker,
        "job_log": job_log,
    }
    return captured


@pytest.fixture(autouse=True)
def _clear_budget():
    clear_run_budget()
    yield
    clear_run_budget()


def _run(seams, **overrides):
    defaults = {
        "company_name": "AcmeCo",
        "website": "https://acme.example",
        "mode": "deep-research",
        "start_time": time.time() - 90,
        "folder_path": str(seams["folder"]),
    }
    defaults.update(overrides)
    return research_agent.perform_deep_research(**defaults)


class TestPreflight:
    def test_no_company_or_website_fails_before_api_calls(self, seams):
        assert _run(seams, company_name=None, website=None) is None
        state = _read_state(seams["folder"])
        assert state["status"] == "failed"
        assert state["current_phase"] == "preflight"
        assert "research_kwargs" not in seams  # orchestrator never invoked

    def test_missing_context_file_fails_with_recorded_errors(self, seams, tmp_path):
        assert _run(seams, context_files=[str(tmp_path / "ghost.pdf")]) is None
        state = _read_state(seams["folder"])
        failed = [e for e in state["events"] if e.get("status") == "failed"]
        assert any("ghost.pdf" in str(e) for e in failed)

    def test_empty_context_file_rejected(self, seams, tmp_path):
        empty = tmp_path / "empty.pdf"
        empty.touch()
        assert _run(seams, context_files=[str(empty)]) is None

    def test_missing_gemini_key_fails_preflight(self, seams, monkeypatch):
        monkeypatch.setattr(
            "primr.config.settings.get_settings",
            lambda: SimpleNamespace(api=SimpleNamespace(gemini_key=None)),
        )
        assert _run(seams) is None
        assert "research_kwargs" not in seams

    def test_orphan_cleanup_failure_is_nonfatal(self, seams):
        seams["cleanup"].side_effect = RuntimeError("cleanup exploded")
        result = _run(seams)
        assert result == str(seams["out_dir"] / "deep.docx")


class TestFailurePath:
    def test_failure_marks_state_and_surfaces_paid_partial(self, seams):
        seams["result"].success = False
        seams["result"].error = "quota exhausted"
        seams["result"].section_results = {}
        result = _run(seams)
        assert result is not None
        assert Path(result).is_file()
        state = _read_state(seams["folder"])
        assert state["status"] == "failed"
        assert state["current_phase"] == "deep_research"
        seams["acknowledge"].assert_called_once_with("interaction-123", [result])

    def test_partial_sections_salvaged_on_failure(self, seams):
        seams["result"].success = False
        seams["result"].error = "died mid-run"
        seams["result"].section_results = {"overview": "partial", "market": "partial"}
        result = _run(seams)
        assert result is not None
        assert Path(result).is_file()
        assert seams["save_section"].call_count == 2

    def test_orchestrator_exception_degrades_to_none(self, seams, monkeypatch):
        async def boom(**kwargs):
            raise RuntimeError("orchestrator exploded")

        monkeypatch.setattr(
            research_agent, "get_orchestrator", lambda: SimpleNamespace(research=boom)
        )
        assert _run(seams) is None
        state = _read_state(seams["folder"])
        assert state["status"] == "failed"
        assert state["current_phase"] == "error"


class TestSuccessPath:
    def test_artifacts_and_completed_state(self, seams):
        result = _run(seams)
        assert result == str(seams["out_dir"] / "deep.docx")
        # Sections persisted + raw markdown saved for reference
        seams["save_section"].assert_called_once()
        raw_md = seams["folder"] / "deep_research_output.md"
        assert raw_md.read_text(encoding="utf-8").startswith("## Report")
        state = _read_state(seams["folder"])
        assert state["status"] == "completed"
        assert state["duration_seconds"] >= 90
        seams["acknowledge"].assert_called_once_with(
            "interaction-123",
            [
                seams["out_dir"] / "deep.md",
                seams["out_dir"] / "deep.txt",
                seams["out_dir"] / "deep.docx",
            ],
        )

    def test_docx_conversion_receives_output_routing(self, seams, tmp_path):
        custom = tmp_path / "custom-out"
        _run(seams, output_dir=str(custom), write_txt=False)
        kwargs = seams["docx"].call_args.kwargs
        assert kwargs["output_dir"] == custom
        assert kwargs["write_txt"] is False

    def test_docx_conversion_failure_retains_pending_interaction(self, seams):
        seams["docx"].side_effect = None
        seams["docx"].return_value = None
        assert _run(seams) is None
        seams["acknowledge"].assert_not_called()
        assert _read_state(seams["folder"])["status"] == "failed"

    def test_docx_gate_failure_returns_durable_markdown(self, seams):
        markdown_path = seams["out_dir"] / "deep.md"
        text_path = seams["out_dir"] / "deep.txt"

        def write_markdown_fallback(*_args, written_paths, **_kwargs):
            seams["out_dir"].mkdir(parents=True, exist_ok=True)
            markdown_path.write_text("# Durable report", encoding="utf-8")
            text_path.write_text("Durable report", encoding="utf-8")
            written_paths.extend([markdown_path, text_path])
            return None

        seams["docx"].side_effect = write_markdown_fallback

        assert _run(seams) == str(markdown_path)
        seams["acknowledge"].assert_called_once_with("interaction-123", [markdown_path, text_path])
        assert _read_state(seams["folder"])["status"] == "completed"

    def test_no_raw_content_uses_structured_assembly(self, seams):
        seams["result"].raw_content = ""
        result = _run(seams)
        assert result == str(seams["out_dir"] / "assembled.docx")
        seams["docx"].assert_not_called()
        seams["final_report"].assert_called_once()

    def test_sections_written_fallback_to_results_len(self, seams):
        seams["result"].sections_written = 0
        seams["result"].section_results = {"a": "1", "b": "2", "c": "3"}
        _run(seams)
        job = seams["job_log"].call_args.args[0]
        assert job.sections_generated == 3

    def test_usage_recorded_with_search_queries(self, seams):
        _run(seams)
        kwargs = seams["tracker"].record_usage.call_args.kwargs
        assert kwargs["search_queries"] == 12
        assert kwargs["pipeline_cost"] == 1.25
        assert kwargs["deep_research_cost"] > 0  # one DR task for deep-research mode
        seams["tracker"].save.assert_called_once()

    def test_verify_runs_after_deep_report_is_produced(self, seams):
        result = _run(seams, verify=True)

        seams["verify"].assert_called_once_with(
            "AcmeCo",
            "https://acme.example",
            str(seams["out_dir"] / "deep.txt"),
        )
        assert result == str(seams["out_dir"] / "deep.docx")

    def test_verify_uses_diagnostics_text_for_custom_output(self, seams, tmp_path):
        custom_output = tmp_path / "deliverables"
        diagnostics = seams["folder"] / "_diagnostics"
        markdown_path = custom_output / "deep.md"
        text_path = diagnostics / "deep.txt"
        docx_path = custom_output / "deep.docx"

        def write_routed_outputs(*_args, written_paths, **_kwargs):
            custom_output.mkdir(parents=True, exist_ok=True)
            diagnostics.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text("# Durable report", encoding="utf-8")
            text_path.write_text("Durable report", encoding="utf-8")
            docx_path.write_text("docx", encoding="utf-8")
            written_paths.extend([markdown_path, text_path, docx_path])
            return str(docx_path)

        seams["docx"].side_effect = write_routed_outputs

        assert _run(seams, verify=True, output_dir=str(custom_output)) == str(docx_path)
        seams["verify"].assert_called_once_with("AcmeCo", "https://acme.example", str(text_path))

    def test_verify_is_not_run_without_report(self, seams):
        seams["docx"].side_effect = None
        seams["docx"].return_value = None

        assert _run(seams, verify=True) is None
        seams["verify"].assert_not_called()


class TestStrategyLoop:
    def test_multi_vendor_ai_strategy_compound_keys(self, seams):
        result = _run(seams, strategies=["ai"], platforms=("aws", "azure"))
        assert result == str(seams["out_dir"] / "deep.docx")
        assert seams["strategy_gen"].call_count == 2
        vendors = [c.kwargs["platform"] for c in seams["strategy_gen"].call_args_list]
        assert vendors == ["aws", "azure"]
        state = _read_state(seams["folder"])
        assert state["strategy_status"] == "completed"
        assert state["strategy_completed_targets"] == ["ai:aws", "ai:azure"]

    def test_partial_strategy_failure_keeps_report_and_records_nonzero_signal(self, seams):
        seams["strategy_gen"].side_effect = [
            str(seams["out_dir"] / "aws.docx"),
            None,
        ]

        result = _run(seams, strategies=["ai"], platforms=("aws", "azure"))

        assert result == str(seams["out_dir"] / "deep.docx")
        state = _read_state(seams["folder"])
        assert state["status"] == "completed"
        assert state["strategy_status"] == "partial"
        assert state["strategy_completed_targets"] == ["ai:aws"]
        assert state["strategy_failed_targets"] == ["ai:azure"]

    def test_explicit_ai_strategies_count_deep_research_task_cost(self, seams):
        _run(seams, strategies=["ai"], platforms=("aws", "azure"))

        kwargs = seams["tracker"].record_usage.call_args.kwargs
        expected_tasks = 3  # main report + one explicit AI strategy per vendor
        assert kwargs["deep_research_cost"] == pytest.approx(
            expected_tasks * DEEP_RESEARCH_COST.standard_task_cost
        )

    def test_strategy_preflight_failure_is_not_counted_as_provider_spend(self, seams):
        seams["strategy_gen"].side_effect = lambda **_kwargs: None

        _run(seams, strategies=["ai"], platforms=("azure",))

        kwargs = seams["tracker"].record_usage.call_args.kwargs
        assert kwargs["deep_research_cost"] == pytest.approx(DEEP_RESEARCH_COST.standard_task_cost)

    def test_explicit_refresh_is_prepared_once_before_strategy_generation(self, seams, monkeypatch):
        from primr.core.deep_vendor_refresh import DeepVendorRefreshResult

        refresh = MagicMock(
            return_value=DeepVendorRefreshResult(
                planned_count=2,
                started_count=2,
            )
        )
        monkeypatch.setattr(
            "primr.core.deep_vendor_refresh.refresh_deep_strategy_vendors",
            refresh,
        )

        _run(
            seams,
            strategies=["ai"],
            platforms=("aws", "azure"),
            refresh_vendor_research=True,
        )

        refresh.assert_called_once_with(
            mode="deep-research",
            vendors=["aws", "azure"],
            folder_path=str(seams["folder"]),
        )
        assert all(
            call.kwargs["force_refresh_vendor"] is False
            for call in seams["strategy_gen"].call_args_list
        )

    def test_legacy_ai_strategy_flag_maps_to_ai(self, seams):
        _run(seams, ai_strategy=True, platforms=("azure",))
        assert seams["strategy_gen"].call_count == 1
        assert seams["strategy_gen"].call_args.kwargs["strategy_name"] == "ai"

    def test_budget_over_main_deep_research_spend_skips_optional_strategy(self, seams):
        from primr.utils.run_budget import set_run_budget

        set_run_budget(1.0)

        result = _run(seams, strategies=["ai"], platforms=("azure",))

        assert result == str(seams["out_dir"] / "deep.docx")
        seams["strategy_gen"].assert_not_called()
        state = _read_state(seams["folder"])
        assert state["strategy_status"] == "failed"
        assert state["strategy_skipped_targets"] == ["ai:azure"]
        assert any(
            event.get("phase") == "strategy_generation"
            and event.get("status") == "skipped"
            and event.get("extra", {}).get("strategy") == "ai"
            and event.get("extra", {}).get("platform") == "azure"
            for event in state["events"]
        )

    def test_no_strategy_skips_loop(self, seams):
        _run(seams)
        seams["strategy_gen"].assert_not_called()
        assert _read_state(seams["folder"])["strategy_status"] == "not_requested"
