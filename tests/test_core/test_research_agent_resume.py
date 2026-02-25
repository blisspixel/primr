"""Tests for research_agent local run-state resume helpers."""

from __future__ import annotations

import json

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

    result = research_agent.create_working_folder("ExampleCo", "https://example.co", reuse_incomplete=True)
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

    result = research_agent.create_working_folder("ExampleCo", "https://example.co", reuse_incomplete=True)
    assert result != str(completed)
    assert result.startswith(str(company_root))


def test_create_working_folder_reuses_canceled_run(tmp_path, monkeypatch):
    monkeypatch.setattr(research_agent, "WORKING_DIR", str(tmp_path))

    company_root = tmp_path / "ExampleCo"
    canceled = company_root / "2026-02-25_1200"
    canceled.mkdir(parents=True)
    (canceled / "_run_state.json").write_text(
        json.dumps({"status": "canceled"}),
        encoding="utf-8",
    )

    result = research_agent.create_working_folder("ExampleCo", "https://example.co", reuse_incomplete=True)
    assert result == str(canceled)


def test_update_run_state_sets_updated_timestamp(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()

    research_agent._update_run_state(str(folder), status="running", current_phase="scrape")
    state = research_agent._load_run_state(str(folder))

    assert state["status"] == "running"
    assert state["current_phase"] == "scrape"
    assert "updated_at" in state


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
