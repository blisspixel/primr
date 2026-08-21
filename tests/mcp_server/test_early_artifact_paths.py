"""Body-free early_artifact_paths on MCP job status."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from primr.mcp_server.job_responses import build_job_response


def test_running_job_lists_working_brief_under_job_output(tmp_path, monkeypatch):
    from primr.mcp_server import job_responses as jr

    job_id = "job-example"
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    brief = job_dir / "ExampleCo_Working_Brief_08-05-2026.md"
    brief.write_text("# WORKING BRIEF — incomplete\n", encoding="utf-8")

    monkeypatch.setattr(jr, "OUTPUT_DIR", str(tmp_path), raising=False)
    # Patch via config used inside helper
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))

    job = SimpleNamespace(
        job_id=job_id,
        company_name="ExampleCo",
        mode="full",
        current_stage=SimpleNamespace(value="scraping"),
        stage_progress_percent=20,
        start_time=datetime.now(timezone.utc),
        last_heartbeat_time=datetime.now(timezone.utc),
        completion_time=None,
        output_paths=[],
        error_message=None,
        error_type=None,
        get_status=lambda: SimpleNamespace(value="running"),
        is_possibly_stuck=lambda: False,
        is_terminal=lambda: False,
    )

    response = build_job_response(
        job,
        include_artifacts=False,
        include_report_content=False,
    )
    assert response["status"] == "running"
    early = response.get("early_artifact_paths") or []
    assert len(early) == 1
    assert early[0]["artifact_role"] == "working_brief"


def test_mcp_classifier_does_not_treat_working_brief_as_report():
    from pathlib import Path

    from primr.mcp_server.job_responses import (
        artifact_matches_filter,
        classify_output_artifact,
    )

    brief = Path("ExampleCo_Working_Brief_08-14-2026.md")
    assert classify_output_artifact(brief) == "working_brief"
    assert artifact_matches_filter("working_brief", "report") is False
    assert artifact_matches_filter("working_brief", "all") is True
    overview = Path("ExampleCo_Strategic_Overview_08-14-2026.md")
    assert classify_output_artifact(overview) == "strategic_overview"
    qa = Path("ExampleCo_QA_Report_08-14-2026.txt")
    assert classify_output_artifact(qa) == "qa_summary"
    from primr.mcp_server.job_responses import select_primary_report_path

    chosen = select_primary_report_path(
        [
            str(qa),
            str(overview),
        ]
    )
    assert chosen is not None
    assert chosen.endswith("ExampleCo_Strategic_Overview_08-14-2026.md")


def test_on_disk_artifacts_available_requires_existing_file(tmp_path):
    from primr.mcp_server.job_responses import on_disk_artifacts_available

    missing = tmp_path / "gone.md"
    present = tmp_path / "report.md"
    present.write_text("# x\n", encoding="utf-8")
    assert on_disk_artifacts_available([str(missing)]) is False
    assert on_disk_artifacts_available([str(present)]) is True
    assert on_disk_artifacts_available([]) is False
