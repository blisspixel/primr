"""Tests for CLI resume/recovery helpers and output finalization."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import Mock, patch

from primr.core import cli


def test_build_recovered_basename_ai_strategy_includes_company_vendor_and_date():
    job_info = {
        "type": "deep_research",
        "metadata": {
            "company_name": "ExampleCo",
            "cloud_vendor": "aws",
            "report_kind": "ai_strategy",
        },
    }
    date_str = datetime.now().strftime("%m-%d-%Y")
    name = cli._build_recovered_basename("interaction-123", job_info)
    assert name == f"ExampleCo_AI_Strategy_AWS_{date_str}"


def test_build_recovered_basename_strategic_overview():
    job_info = {
        "type": "deep_research",
        "metadata": {"company_name": "ExampleCo", "report_kind": "strategic_overview"},
    }
    date_str = datetime.now().strftime("%m-%d-%Y")
    name = cli._build_recovered_basename("interaction-123", job_info)
    assert name == f"ExampleCo_Strategic_Overview_{date_str}"


def test_save_recovered_outputs_writes_md_txt_and_docx(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "OUTPUT_DIR", str(tmp_path))
    job_info = {
        "type": "deep_research",
        "metadata": {
            "company_name": "ExampleCo",
            "cloud_vendor": "aws",
            "report_kind": "ai_strategy",
        },
    }
    content = "# Title\n\nRecovered content."

    with patch("primr.output.markdown_converter.markdown_to_docx") as mock_to_docx:
        outputs = cli._save_recovered_outputs("interaction-123", job_info, content)

    assert outputs["md"].endswith(".md")
    assert outputs["txt"].endswith(".txt")
    assert outputs["docx"].endswith(".docx")
    with open(outputs["md"], encoding="utf-8") as f:
        assert "Recovered content." in f.read()
    with open(outputs["txt"], encoding="utf-8") as f:
        assert "Recovered content." in f.read()
    mock_to_docx.assert_called_once()


def test_find_latest_run_state_returns_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "WORKING_DIR", str(tmp_path))
    older = tmp_path / "ExampleCo" / "2026-02-24_1700"
    newer = tmp_path / "ExampleCo" / "2026-02-25_0200"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    older_state = older / "_run_state.json"
    newer_state = newer / "_run_state.json"
    older_state.write_text(
        json.dumps({"company_name": "Old", "status": "failed"}), encoding="utf-8"
    )
    newer_state.write_text(
        json.dumps({"company_name": "New", "status": "running"}), encoding="utf-8"
    )
    os.utime(older_state, (100, 100))
    os.utime(newer_state, (200, 200))

    found = cli._find_latest_run_state()
    assert found is not None
    path, state = found
    assert path.endswith(str(newer_state))
    assert state["company_name"] == "New"


def test_resume_pending_jobs_returns_error_when_check_error(monkeypatch):
    import importlib

    deep_research_module = importlib.import_module("primr.ai.deep_research")
    jobs = {"job-1": {"description": "ExampleCo AI strategy", "type": "deep_research"}}
    client = Mock()
    client.check_job.return_value = {"status": "check_error", "error": "Server disconnected"}

    monkeypatch.setattr(deep_research_module, "get_pending_jobs", lambda: jobs)
    monkeypatch.setattr(deep_research_module, "get_deep_research_client", lambda: client)

    exit_code = cli.resume_pending_jobs()
    assert exit_code == 1


def test_resume_pending_jobs_finalizes_completed(monkeypatch):
    import importlib

    deep_research_module = importlib.import_module("primr.ai.deep_research")
    jobs = {"job-1": {"description": "ExampleCo AI strategy", "type": "deep_research"}}
    client = Mock()
    client.check_job.return_value = {"status": "completed", "content": "Final content"}

    monkeypatch.setattr(deep_research_module, "get_pending_jobs", lambda: jobs)
    monkeypatch.setattr(deep_research_module, "get_deep_research_client", lambda: client)
    monkeypatch.setattr(
        cli,
        "_save_recovered_outputs",
        lambda interaction_id, job_info, content: {"md": "a.md", "docx": "a.docx", "txt": "a.txt"},
    )

    exit_code = cli.resume_pending_jobs()
    assert exit_code == 0


def test_resume_pending_jobs_falls_back_to_txt_when_finalize_fails(tmp_path, monkeypatch):
    import importlib

    deep_research_module = importlib.import_module("primr.ai.deep_research")
    jobs = {"job-1": {"description": "ExampleCo AI strategy", "type": "deep_research"}}
    client = Mock()
    client.check_job.return_value = {"status": "completed", "content": "Recovered body"}

    monkeypatch.setattr(cli, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(deep_research_module, "get_pending_jobs", lambda: jobs)
    monkeypatch.setattr(deep_research_module, "get_deep_research_client", lambda: client)
    monkeypatch.setattr(
        cli,
        "_save_recovered_outputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("docx fail")),
    )

    exit_code = cli.resume_pending_jobs()

    fallback = tmp_path / "recovered_deep_research_job-1.txt"
    assert fallback.exists()
    assert fallback.read_text(encoding="utf-8") == "Recovered body"
    assert exit_code == 1


def test_find_latest_run_state_returns_none_for_malformed_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "WORKING_DIR", str(tmp_path))
    bad = tmp_path / "ExampleCo" / "2026-02-25_0200"
    bad.mkdir(parents=True)
    (bad / "_run_state.json").write_text("{not-json", encoding="utf-8")

    found = cli._find_latest_run_state()
    assert found is None


def test_find_latest_run_state_skips_bad_newest_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "WORKING_DIR", str(tmp_path))
    older = tmp_path / "ExampleCo" / "2026-02-24_1700"
    newer_bad = tmp_path / "ExampleCo" / "2026-02-25_0200"
    older.mkdir(parents=True)
    newer_bad.mkdir(parents=True)
    older_state = older / "_run_state.json"
    newer_state = newer_bad / "_run_state.json"
    older_state.write_text(
        json.dumps({"company_name": "ExampleCo", "status": "running"}), encoding="utf-8"
    )
    newer_state.write_text("{bad-json", encoding="utf-8")
    os.utime(older_state, (100, 100))
    os.utime(newer_state, (200, 200))

    found = cli._find_latest_run_state()
    assert found is not None
    path, state = found
    assert path.endswith(str(older_state))
    assert state["company_name"] == "ExampleCo"
