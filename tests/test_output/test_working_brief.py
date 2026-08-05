"""Hermetic tests for Layer-1 progressive working brief assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from primr.output.artifact_inventory import classify_artifact, infer_artifact_role
from primr.output.working_brief import (
    WORKING_BRIEF_BANNER,
    WorkingBriefInput,
    assemble_working_brief,
    read_recon_excerpt,
    working_brief_filename,
    write_working_brief,
)


def test_assemble_includes_banner_and_pending_stages() -> None:
    md = assemble_working_brief(
        WorkingBriefInput(
            company_name="ExampleCo",
            website="https://example.co",
            run_id="working/exampleco/run-1",
            scraped_urls=("https://example.co/", "https://example.co/about"),
            pages_scraped=2,
            external_urls=("https://news.example/a",),
            external_source_count=1,
            recon_excerpt="Tenant: ExampleCo\nServices: Microsoft 365",
            hiring_postings_found=3,
            hiring_postings_extracted=2,
            hiring_source="ats",
            generated_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        )
    )
    assert WORKING_BRIEF_BANNER in md
    assert "ExampleCo" in md
    assert "https://example.co" in md
    assert "Pages scraped:** 2" in md or "Pages scraped: 2" in md
    assert "Microsoft 365" in md
    assert "Postings found:** 3" in md or "Postings found: 3" in md
    assert "Research deepening" in md
    assert "Strategic Overview" in md  # incomplete disclaimer


def test_working_brief_never_classified_as_primary_report(tmp_path: Path) -> None:
    public = tmp_path / "ExampleCo_Working_Brief_08-04-2026.md"
    local = tmp_path / "working_brief.md"
    for path in (public, local):
        path.write_text("# brief", encoding="utf-8")
        assert classify_artifact(path) == "working_brief"
        assert infer_artifact_role(path) == "working_brief"
        assert infer_artifact_role(path) != "primary_report"


def test_strategic_overview_still_primary(tmp_path: Path) -> None:
    path = tmp_path / "ExampleCo_Strategic_Overview_08-04-2026.md"
    path.write_text("# final", encoding="utf-8")
    assert infer_artifact_role(path) == "primary_report"


def test_write_working_brief_atomic_and_fail_open(tmp_path: Path) -> None:
    working = tmp_path / "run"
    public = tmp_path / "output"
    working.mkdir()
    paths = write_working_brief(
        WorkingBriefInput(company_name="ExampleCo", website="https://example.co"),
        working_folder=working,
        public_output_dir=public,
    )
    assert len(paths) == 2
    assert (working / "working_brief.md").is_file()
    assert WORKING_BRIEF_BANNER in (working / "working_brief.md").read_text(encoding="utf-8")
    assert any(path.parent == public for path in paths)
    assert working_brief_filename("ExampleCo").startswith("ExampleCo_Working_Brief_")


def test_read_recon_excerpt_truncates(tmp_path: Path) -> None:
    (tmp_path / "_recon_context.txt").write_text("a" * 50, encoding="utf-8")
    assert read_recon_excerpt(tmp_path, max_chars=10) == "a" * 10
    assert read_recon_excerpt(tmp_path / "missing") is None


def test_emit_after_structured_scrape_writes_brief(tmp_path: Path) -> None:
    from primr.output.working_brief import emit_after_structured_scrape

    messages: list[str] = []
    paths = emit_after_structured_scrape(
        "ExampleCo",
        "https://example.co",
        str(tmp_path),
        {"https://example.co/": "body"},
        {"https://news.example/a": "ext"},
        on_progress=messages.append,
    )
    assert paths
    assert (tmp_path / "working_brief.md").is_file()
    assert any("Working brief" in msg for msg in messages)


def test_public_brief_uses_run_state_output_dir(tmp_path: Path, monkeypatch) -> None:
    """Public brief must follow run-state output_dir (CLI --output-dir / MCP job)."""
    from primr.core.fast_run_collection import _emit_working_brief_after_collection
    from primr.core.run_state_io import _save_run_state
    from primr.output.working_brief import resolve_public_output_dir

    working = tmp_path / "working" / "run"
    job_out = tmp_path / "jobs" / "job-1"
    working.mkdir(parents=True)
    job_out.mkdir(parents=True)
    _save_run_state(str(working), {"output_dir": str(job_out)})

    assert resolve_public_output_dir(str(working)) == str(job_out)

    monkeypatch.setattr(
        "primr.config.config.OUTPUT_DIR",
        str(tmp_path / "global-output"),
    )
    _emit_working_brief_after_collection(
        company_name="ExampleCo",
        website="https://example.co",
        folder_path=str(working),
        scraped_data={"https://example.co/": "body"},
        pages_scraped=1,
        external_data={},
    )
    assert (working / "working_brief.md").is_file()
    public = list(job_out.glob("*_Working_Brief_*.md"))
    assert len(public) == 1
    assert not (tmp_path / "global-output").exists() or not list(
        (tmp_path / "global-output").glob("*_Working_Brief_*.md")
    )
