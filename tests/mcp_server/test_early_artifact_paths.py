"""Body-free early_artifact_paths on MCP job status."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
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
    assert early[0]["name"] == brief.name
    assert "report" not in response.get("artifacts", {})
