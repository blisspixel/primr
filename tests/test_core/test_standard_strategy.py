from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

from primr.core.standard_strategy import run_standard_ai_strategy


def _run(tmp_path, **overrides):
    generate = overrides.pop("generate_strategy", MagicMock(return_value="/out/strategy.docx"))
    consolidate = overrides.pop("consolidate_context", MagicMock(return_value="context.md"))
    defaults = {
        "enabled": True,
        "company_name": "ExampleCo",
        "platform": "azure",
        "folder_path": str(tmp_path),
        "total_phases": 5,
        "refresh_vendor_research": False,
        "discovery_notes_content": None,
        "lite_strategy": False,
        "output_dir": None,
        "diagnostics_dir": None,
        "write_txt": True,
        "consolidate_context": consolidate,
        "generate_strategy": generate,
    }
    defaults.update(overrides)
    return run_standard_ai_strategy(**defaults), generate, consolidate


def test_disabled_stage_persists_not_requested_without_generation(tmp_path):
    result, generate, consolidate = _run(tmp_path, enabled=False)

    assert result.output_path is None
    assert result.outcome.status == "not_requested"
    generate.assert_not_called()
    consolidate.assert_not_called()
    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    assert state["strategy_status"] == "not_requested"


def test_success_persists_completed_target_and_exact_local_task_count(tmp_path):
    def generated(*_args, **kwargs):
        kwargs["strategy_task_observer"]("started")
        kwargs["strategy_task_observer"]("completed")
        observer = kwargs["vendor_refresh_observer"]
        observer("started")
        observer("completed")
        return "/out/strategy.docx"

    result, generate, consolidate = _run(
        tmp_path,
        refresh_vendor_research=True,
        generate_strategy=MagicMock(side_effect=generated),
    )

    assert result.outcome.status == "completed"
    assert result.outcome.completed_targets == ("ai:azure",)
    assert result.deep_research_tasks_started == 1
    assert result.vendor_refresh_tasks_started == 1
    consolidate.assert_called_once_with(str(tmp_path))
    assert generate.call_args.args == ("ExampleCo", "azure")
    assert generate.call_args.kwargs["force_refresh_vendor"] is True


def test_failed_generation_keeps_base_route_observable(tmp_path):
    result, _, _ = _run(tmp_path, generate_strategy=MagicMock(return_value=None))

    assert result.outcome.status == "failed"
    assert result.outcome.failed_targets == ("ai:azure",)
    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    assert state["strategy_status"] == "failed"
    assert any(
        event["phase"] == "ai_strategy" and event["status"] == "failed" for event in state["events"]
    )


def test_context_consolidation_failure_preserves_base_route_and_failed_outcome(tmp_path):
    result, generate, _ = _run(
        tmp_path,
        consolidate_context=MagicMock(side_effect=OSError("context unavailable")),
    )

    assert result.output_path is None
    assert result.outcome.status == "failed"
    assert result.deep_research_tasks_started == 0
    generate.assert_not_called()
    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    assert state["strategy_status"] == "failed"
    assert any(
        event["phase"] == "ai_strategy"
        and event["status"] == "failed"
        and event["extra"]["failure_type"] == "OSError"
        for event in state["events"]
    )


def test_concurrent_runs_keep_strategy_task_counts_local(tmp_path):
    barrier = threading.Barrier(2)

    def run_one(folder_name: str):
        folder = tmp_path / folder_name
        folder.mkdir()

        def generated(*_args, **kwargs):
            kwargs["strategy_task_observer"]("started")
            barrier.wait(timeout=5)
            kwargs["strategy_task_observer"]("completed")
            return f"/out/{folder_name}.docx"

        return _run(folder, generate_strategy=MagicMock(side_effect=generated))[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_one, ("one", "two")))

    assert [result.deep_research_tasks_started for result in results] == [1, 1]
