"""Regression tests for bug-hunt round 2 correctness fixes.

Each class pins a defect so it cannot silently return.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from primr.core.cli import CLIConfig, Command
from primr.core.cli_orchestrate import handle_orchestrate
from primr.mcp_server.job_responses import build_job_response, build_output_artifact_rows
from primr.output.working_brief import (
    WorkingBriefInput,
    assemble_working_brief,
    early_artifact_path_records,
    emit_collection_working_brief,
)
from primr.utils.cost_estimator import CostEstimate


def _estimate(total: float = 0.5) -> CostEstimate:
    return CostEstimate(
        mode="complete",
        estimated_input_tokens=1,
        estimated_output_tokens=1,
        estimated_search_queries=0,
        input_cost=0.0,
        output_cost=0.0,
        search_cost=0.0,
        total_cost=total,
        duration_minutes="30-45 min",
        notes=[],
    )


class TestOrchestrateUrlValidation:
    def test_whitespace_only_website_refused(self, monkeypatch):
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(),
        )
        code = handle_orchestrate(
            CLIConfig(
                command=Command.ORCHESTRATE,
                company_name="Acme",
                website="   ",
                dry_run_requested=True,
            )
        )
        assert code == 1

    def test_invalid_url_refused(self, monkeypatch):
        monkeypatch.setattr(
            "primr.utils.cost_display.print_cost_estimate",
            lambda *a, **k: _estimate(),
        )
        code = handle_orchestrate(
            CLIConfig(
                command=Command.ORCHESTRATE,
                company_name="Acme",
                website="javascript:alert(1)",
                dry_run_requested=True,
            )
        )
        assert code == 1


class TestWorkingBriefZeroCounts:
    def test_explicit_zero_pages_not_replaced_by_url_list(self) -> None:
        md = assemble_working_brief(
            WorkingBriefInput(
                company_name="ExampleCo",
                scraped_urls=("https://example.co/orphan",),
                pages_scraped=0,
                external_urls=("https://news.example/a",),
                external_source_count=0,
            )
        )
        assert "Pages scraped:** 0" in md or "Pages scraped: 0" in md
        assert "Validated sources:** 0" in md or "Validated sources: 0" in md


class TestWorkingBriefExistence:
    def test_missing_paths_omitted_from_early_records(self, tmp_path: Path) -> None:
        from primr.core.run_state_io import _update_run_state

        gone = tmp_path / "missing_brief.md"
        present = tmp_path / "working_brief.md"
        present.write_text("# brief", encoding="utf-8")
        _update_run_state(
            str(tmp_path),
            working_brief_paths=[str(gone), str(present)],
        )
        records = early_artifact_path_records(tmp_path)
        assert len(records) == 1
        assert records[0]["name"] == "working_brief.md"


class TestHiringRefreshPreservesUrls:
    def test_refresh_keeps_sample_urls_from_run_state(self, tmp_path: Path) -> None:
        from primr.core.fast_run_hiring import _refresh_working_brief_hiring

        emit_collection_working_brief(
            company_name="ExampleCo",
            website="https://example.co",
            folder_path=str(tmp_path),
            scraped_urls=("https://example.co/", "https://example.co/about"),
            pages_scraped=2,
            external_urls=("https://news.example/story",),
            external_source_count=1,
            public_output_dir=tmp_path / "out",
        )
        first = (tmp_path / "working_brief.md").read_text(encoding="utf-8")
        assert "https://example.co/about" in first

        _refresh_working_brief_hiring(
            folder_path=str(tmp_path),
            company_label="ExampleCo",
            website="https://example.co",
            postings_found=3,
            postings_extracted=2,
            source="ats",
        )
        refreshed = (tmp_path / "working_brief.md").read_text(encoding="utf-8")
        assert "https://example.co/about" in refreshed
        assert "Postings found:** 3" in refreshed or "Postings found: 3" in refreshed


class TestMcpBinaryArtifacts:
    def test_docx_bytes_still_produce_metadata_row(self, tmp_path: Path) -> None:
        docx = tmp_path / "ExampleCo_Strategic_Overview_08-05-2026.docx"
        # Non-UTF-8 bytes (would previously skip the whole row via read_text).
        docx.write_bytes(b"PK\x03\x04\xff\xfe\x00binary-docx-payload")
        rows = build_output_artifact_rows(
            [str(docx)],
            include_content=True,
            artifact_filter="all",
        )
        assert len(rows) == 1
        assert rows[0]["filename"] == docx.name
        assert rows[0]["content_hash"].startswith("sha256:")
        assert rows[0]["content_included"] is False
        assert rows[0].get("content_note") == "binary_or_non_utf8"

    def test_artifacts_available_requires_on_disk_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.md"
        job = SimpleNamespace(
            job_id="job-1",
            company_name="ExampleCo",
            mode="full",
            current_stage=SimpleNamespace(value="complete"),
            stage_progress_percent=100,
            start_time=None,
            last_heartbeat_time=None,
            completion_time=None,
            output_paths=[str(missing)],
            error_message=None,
            error_type=None,
            get_status=lambda: SimpleNamespace(value="completed"),
            is_possibly_stuck=lambda: False,
            is_terminal=lambda: True,
        )
        response = build_job_response(
            job,
            include_artifacts=False,
            include_report_content=False,
        )
        assert response["artifacts_available"] is False
