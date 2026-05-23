"""
Coverage tests for pipeline_runner.py.

Exercises artifact collection/copy helpers, run_strategy_generation,
run_qa_analysis, and the run_research orchestration with all external
dependencies mocked (no real LLM/network/scrape calls).
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.mcp_server.pipeline_runner import (
    PipelineRunner,
    _collect_run_artifacts,
    _copy_artifacts_to_destination,
    run_qa_analysis,
    run_strategy_generation,
)
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
        s.rate_limiter.reset()
        yield s


@pytest.fixture
def runner(server):
    return PipelineRunner(server)


# ---------------------------------------------------------------------------
# _collect_run_artifacts
# ---------------------------------------------------------------------------
class TestCollectRunArtifacts:
    def test_missing_output_dir_returns_primary(self, tmp_path):
        primary = str(tmp_path / "nonexistent" / "report.md")
        result = _collect_run_artifacts(primary, "Acme Corp")
        assert result == [primary]

    def test_collects_sibling_artifacts(self, tmp_path):
        from datetime import datetime

        today = datetime.now().strftime("%m-%d-%Y")
        primary = tmp_path / "Acme_Corp_Strategic_Overview.md"
        primary.write_text("report", encoding="utf-8")
        sibling = tmp_path / f"Acme_Corp_AI_Strategy_{today}.md"
        sibling.write_text("strategy", encoding="utf-8")
        # A non-matching file that should be skipped
        other = tmp_path / "Unrelated_Company.md"
        other.write_text("nope", encoding="utf-8")

        result = _collect_run_artifacts(str(primary), "Acme Corp")
        assert str(primary) in result
        assert str(sibling) in result
        assert str(other) not in result
        # primary is always first
        assert result[0] == str(primary)


# ---------------------------------------------------------------------------
# _copy_artifacts_to_destination
# ---------------------------------------------------------------------------
class TestCopyArtifactsToDestination:
    def test_copies_existing_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        f1 = src / "report.md"
        f1.write_text("content", encoding="utf-8")
        dest = tmp_path / "dest"

        result = _copy_artifacts_to_destination([str(f1)], str(dest))
        assert len(result) == 1
        assert (dest / "report.md").exists()
        assert result[0] == str(dest / "report.md")

    def test_skips_nonexistent_returns_original(self, tmp_path):
        missing = str(tmp_path / "ghost.md")
        dest = tmp_path / "dest"
        result = _copy_artifacts_to_destination([missing], str(dest))
        # No file copied -> returns original list
        assert result == [missing]


# ---------------------------------------------------------------------------
# run_strategy_generation
# ---------------------------------------------------------------------------
class TestRunStrategyGeneration:
    @pytest.mark.asyncio
    async def test_success_extracts_company_from_filename(self, tmp_path):
        report = tmp_path / "Acme_Corp_Strategic_Overview_05-22-2026.md"
        report.write_text("# report", encoding="utf-8")

        fake_result = SimpleNamespace(
            error=None,
            md_path=str(tmp_path / "out.md"),
            docx_path=None,
            txt_path=None,
        )
        with patch(
            "primr.core.ai_strategy.generate_ai_strategy",
            new=AsyncMock(return_value=fake_result),
        ) as mock_gen:
            result = await run_strategy_generation(
                report_path=str(report),
                strategy_type="ai_strategy",
                platform="azure",
            )
        assert result["output_path"] == str(tmp_path / "out.md")
        assert result["strategy_type"] == "ai_strategy"
        # company name should have been parsed from the filename prefix
        _, kwargs = mock_gen.call_args
        assert kwargs["company_name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_error_raises_runtime(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# report", encoding="utf-8")
        fake_result = SimpleNamespace(
            error="strategy failed", md_path=None, docx_path=None, txt_path=None
        )
        with (
            patch(
                "primr.core.ai_strategy.generate_ai_strategy",
                new=AsyncMock(return_value=fake_result),
            ),
            pytest.raises(RuntimeError, match="strategy failed"),
        ):
            await run_strategy_generation(
                report_path=str(report),
                strategy_type="customer_experience",
            )


# ---------------------------------------------------------------------------
# run_qa_analysis
# ---------------------------------------------------------------------------
class TestRunQAAnalysis:
    @pytest.mark.asyncio
    async def test_returns_scores(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# report", encoding="utf-8")

        analysis = SimpleNamespace(
            overall_score=88.0,
            completeness_score=90.0,
            accuracy_score=85.0,
            clarity_score=80.0,
            actionability_score=75.0,
            issues=[SimpleNamespace(description="fix this")],
        )
        with (
            patch("primr.qa.report_loader.ReportLoader") as MockLoader,
            patch("primr.qa.analyzer.QAAnalyzer") as MockAnalyzer,
        ):
            MockLoader.return_value.load.return_value = MagicMock()
            MockAnalyzer.return_value.analyze_report.return_value = analysis
            result = await run_qa_analysis(str(report))

        assert result["overall_score"] == 88.0
        assert result["category_scores"]["completeness"] == 90.0
        assert result["improvement_suggestions"] == ["fix this"]

    @pytest.mark.asyncio
    async def test_load_failure_raises(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# report", encoding="utf-8")
        with patch("primr.qa.report_loader.ReportLoader") as MockLoader:
            MockLoader.return_value.load.return_value = None
            with pytest.raises(RuntimeError, match="Could not load report"):
                await run_qa_analysis(str(report))


# ---------------------------------------------------------------------------
# run_research orchestration
# ---------------------------------------------------------------------------
class TestRunResearchFastMode:
    @pytest.mark.asyncio
    async def test_fast_mode_success(self, server, runner, monkeypatch, tmp_path):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        report = tmp_path / "report.md"
        report.write_text("done", encoding="utf-8")

        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            lambda *a, **k: str(report),
        )
        await runner.run_research(
            job=job, company_url="https://example.com", mode="full"
        )
        updated = server.job_store.get(job.job_id)
        assert updated.get_status().value == "completed"
        assert str(report) in updated.output_paths

    @pytest.mark.asyncio
    async def test_fast_mode_failure(self, server, runner, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            lambda *a, **k: None,
        )
        await runner.run_research(
            job=job, company_url="https://example.com", mode="full"
        )
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "research_failed"

    @pytest.mark.asyncio
    async def test_fast_mode_with_destination(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        report = tmp_path / "report.md"
        report.write_text("done", encoding="utf-8")
        dest = tmp_path / "dest"

        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            lambda *a, **k: str(report),
        )
        await runner.run_research(
            job=job,
            company_url="https://example.com",
            mode="full",
            destination=str(dest),
        )
        updated = server.job_store.get(job.job_id)
        assert updated.get_status().value == "completed"
        assert (dest / "report.md").exists()


class TestRunResearchOrchestrator:
    @pytest.mark.asyncio
    async def test_premium_mode_success(self, server, runner, monkeypatch, tmp_path):
        # Premium never uses fast path even with XAI key
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        job = server.job_store.create("Acme Corp", "premium", owner_client_id="stdio")

        result = SimpleNamespace(
            success=True,
            error=None,
            raw_content="# Report Body",
            section_results={},
        )
        mock_orch = MagicMock()
        mock_orch.research = AsyncMock(return_value=result)

        with patch(
            "primr.core.research_orchestrator.ResearchOrchestrator",
            return_value=mock_orch,
        ):
            # Avoid filesystem write churn: patch _save_report + qa + manifest
            runner._save_report = AsyncMock(return_value=str(tmp_path / "report.md"))
            runner._run_qa = AsyncMock(return_value={"overall_score": 91})
            runner._generate_run_manifest = AsyncMock()
            await runner.run_research(
                job=job, company_url="https://example.com", mode="premium"
            )

        updated = server.job_store.get(job.job_id)
        assert updated.get_status().value == "completed"
        assert updated.qa_score == 91

    @pytest.mark.asyncio
    async def test_orchestrator_failure(self, server, runner, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        job = server.job_store.create("Acme Corp", "premium", owner_client_id="stdio")

        result = SimpleNamespace(
            success=False, error="orchestrator boom", raw_content=None, section_results={}
        )
        mock_orch = MagicMock()
        mock_orch.research = AsyncMock(return_value=result)
        with patch(
            "primr.core.research_orchestrator.ResearchOrchestrator",
            return_value=mock_orch,
        ):
            await runner.run_research(
                job=job, company_url="https://example.com", mode="premium"
            )
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "research_failed"

    @pytest.mark.asyncio
    async def test_pipeline_exception_records_failed(self, server, runner, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        job = server.job_store.create("Acme Corp", "premium", owner_client_id="stdio")

        with patch(
            "primr.core.research_orchestrator.ResearchOrchestrator",
            side_effect=RuntimeError("init failed"),
        ):
            await runner.run_research(
                job=job, company_url="https://example.com", mode="premium"
            )
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "pipeline_error"
        assert "init failed" in updated.error_message


class TestSaveReportAndManifest:
    @pytest.mark.asyncio
    async def test_save_report_writes_file(self, runner, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        result = SimpleNamespace(raw_content="# Hello", section_results={})
        path = await runner._save_report("Acme Corp", result)
        assert Path(path).exists()
        assert Path(path).read_text(encoding="utf-8") == "# Hello"

    @pytest.mark.asyncio
    async def test_save_report_uses_section_results(self, runner, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        result = SimpleNamespace(
            raw_content=None, section_results={"Overview": "body text"}
        )
        path = await runner._save_report("Acme Corp", result)
        content = Path(path).read_text(encoding="utf-8")
        assert "## Overview" in content
        assert "body text" in content

    @pytest.mark.asyncio
    async def test_generate_run_manifest(self, server, runner, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        report = tmp_path / "report.md"
        report.write_text("x", encoding="utf-8")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        await runner._generate_run_manifest(job, "https://example.com", "full")
        manifest = tmp_path / "run_manifest.json"
        assert manifest.exists()

    @pytest.mark.asyncio
    async def test_run_qa_method_handles_failure(self, runner):
        # _run_qa swallows exceptions and returns None
        with patch("primr.qa.report_loader.ReportLoader", side_effect=RuntimeError("x")):
            result = await runner._run_qa("/nonexistent/report.md")
        assert result is None
