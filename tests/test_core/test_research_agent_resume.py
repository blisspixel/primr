"""Tests for research_agent local run-state resume helpers."""

from __future__ import annotations

import json
from datetime import datetime as real_datetime

import pytest

from primr.core import research_agent


def test_create_working_folder_reuses_incomplete_run(tmp_path, monkeypatch):
    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))

    company_root = tmp_path / "ExampleCo"
    reusable = company_root / "2026-02-25_1200"
    reusable.mkdir(parents=True)
    (reusable / "_run_state.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )

    result = research_agent.create_working_folder(
        "ExampleCo", "https://example.co", reuse_incomplete=True
    )
    assert result == str(reusable)


def test_create_working_folder_skips_completed_run(tmp_path, monkeypatch):
    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))

    company_root = tmp_path / "ExampleCo"
    completed = company_root / "2026-02-25_1200"
    completed.mkdir(parents=True)
    (completed / "_run_state.json").write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )

    result = research_agent.create_working_folder(
        "ExampleCo", "https://example.co", reuse_incomplete=True
    )
    assert result != str(completed)
    assert result.startswith(str(company_root))


@pytest.mark.parametrize("status", ["canceled", "cancelled"])
def test_create_working_folder_reuses_canceled_run(tmp_path, monkeypatch, status):
    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))

    company_root = tmp_path / "ExampleCo"
    canceled = company_root / "2026-02-25_1200"
    canceled.mkdir(parents=True)
    (canceled / "_run_state.json").write_text(
        json.dumps({"status": status}),
        encoding="utf-8",
    )

    result = research_agent.create_working_folder(
        "ExampleCo", "https://example.co", reuse_incomplete=True
    )
    assert result == str(canceled)


def test_completed_current_timestamp_allocates_collision_suffix(tmp_path, monkeypatch):
    from primr.core import workspace

    class FixedDateTime:
        @classmethod
        def now(cls):
            return real_datetime(2026, 7, 18, 12, 0)

    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(workspace, "datetime", FixedDateTime)
    company_root = tmp_path / "ExampleCo"
    completed = company_root / "2026-07-18_1200"
    completed.mkdir(parents=True)
    (completed / "_run_state.json").write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )

    result = research_agent.create_working_folder(
        "ExampleCo", "https://example.co", reuse_incomplete=True
    )

    assert result == str(company_root / "2026-07-18_1200_001")


def test_resume_selects_suffixed_incomplete_run(tmp_path, monkeypatch):
    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))
    company_root = tmp_path / "ExampleCo"
    completed = company_root / "2026-07-18_1234"
    incomplete = company_root / "2026-07-18_1234_001"
    completed.mkdir(parents=True)
    incomplete.mkdir()
    (completed / "_run_state.json").write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )
    (incomplete / "_run_state.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )

    result = research_agent.create_working_folder(
        "ExampleCo",
        "https://example.co",
        reuse_incomplete=True,
    )

    assert result == str(incomplete)


def test_second_resume_process_is_refused(tmp_path, monkeypatch):
    from primr.core.workspace import ResumeLeaseError, release_resume_lease

    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))
    reusable = tmp_path / "ExampleCo" / "2026-02-25_1200"
    reusable.mkdir(parents=True)
    (reusable / "_run_state.json").write_text(
        json.dumps({"status": "running"}),
        encoding="utf-8",
    )

    first = research_agent.create_working_folder(
        "ExampleCo", "https://example.co", reuse_incomplete=True
    )
    with pytest.raises(ResumeLeaseError, match="already being resumed"):
        research_agent.create_working_folder(
            "ExampleCo", "https://example.co", reuse_incomplete=True
        )
    release_resume_lease(first)


def test_perform_research_releases_lease_after_unexpected_setup_error(tmp_path, monkeypatch):
    from primr.core.workspace import release_resume_lease

    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path / "working"))
    monkeypatch.setattr(research_agent, "OUTPUT_DIR", str(tmp_path / "output"))
    reusable = tmp_path / "working" / "ExampleCo" / "2026-02-25_1200"
    reusable.mkdir(parents=True)
    (reusable / "_run_state.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )

    def fail_framing(**_kwargs):
        raise RuntimeError("injected setup failure")

    monkeypatch.setattr("primr.core.research_framing.resolve_run_framing", fail_framing)

    with pytest.raises(RuntimeError, match="injected setup failure"):
        research_agent.perform_research(
            "ExampleCo",
            "https://example.co",
            resume_local=True,
            platforms=("agnostic",),
            skip_confirm=True,
        )

    reclaimed = research_agent.create_working_folder(
        "ExampleCo", "https://example.co", reuse_incomplete=True
    )
    assert reclaimed == str(reusable)
    release_resume_lease(reclaimed)


def test_refused_fresh_run_does_not_leave_timestamped_orphan(tmp_path, monkeypatch):
    from primr.core.workspace import (
        ResumeLeaseError,
        acquire_company_run_lease_for_target,
        release_resume_lease,
    )

    working_root = tmp_path / "working"
    monkeypatch.setattr(research_agent, "WORKING_DIR", str(working_root))
    company_root = acquire_company_run_lease_for_target(
        "ExampleCo", "https://example.co", base_dir=working_root
    )

    with pytest.raises(ResumeLeaseError, match="active research process"):
        research_agent.perform_research(
            "ExampleCo",
            "https://example.co",
            skip_confirm=True,
            platforms=("agnostic",),
        )

    assert not [path for path in company_root.iterdir() if path.is_dir()]
    release_resume_lease(company_root)


def test_update_run_state_sets_updated_timestamp(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()

    research_agent._update_run_state(str(folder), status="running", current_phase="scrape")
    state = research_agent._load_run_state(str(folder))

    assert state["status"] == "running"
    assert state["current_phase"] == "scrape"
    assert "updated_at" in state


def test_save_run_state_keeps_last_good_file_when_atomic_replace_is_denied(tmp_path, monkeypatch):
    import pytest

    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "_run_state.json").write_text('{"status": "scrape"}', encoding="utf-8")

    def fail_replace(_src, _dst):
        raise PermissionError("Access is denied")

    monkeypatch.setattr("primr.utils.atomic_io.os.replace", fail_replace)
    monkeypatch.setattr(research_agent.os, "replace", fail_replace)

    with pytest.raises(PermissionError):
        research_agent._save_run_state(str(folder), {"status": "running"})

    state = research_agent._load_run_state(str(folder))
    assert state["status"] == "scrape"
    assert not list(folder.glob("*.tmp"))


def test_append_run_event_keeps_recent_200(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()

    for idx in range(205):
        research_agent._append_run_event(str(folder), "phase", "running", f"event-{idx}")

    state = research_agent._load_run_state(str(folder))
    events = state["events"]
    assert len(events) == 200
    assert events[0]["message"] == "event-5"
    assert events[-1]["message"] == "event-204"


def test_validate_scrape_quality_thresholds():
    ok, reason = research_agent._validate_scrape_quality(
        {"https://example.com": "x" * 1000},
        min_pages=1,
        min_chars=500,
    )
    assert ok is True
    assert "Scrape quality too low" in reason


def test_strategy_money_to_millions_conversions():
    assert research_agent._strategy_money_to_millions(2, "B") == 2000.0
    assert research_agent._strategy_money_to_millions(500, "K") == 0.5
    assert research_agent._strategy_money_to_millions(12, "M") == 12
