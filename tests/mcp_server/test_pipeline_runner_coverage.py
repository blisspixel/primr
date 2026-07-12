"""
Coverage tests for pipeline_runner.py.

Exercises artifact collection/copy helpers, strategy and QA operations, and the
run_research orchestration with all external dependencies mocked.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.mcp_server.pipeline_runner import (
    PUBLIC_RESEARCH_FAILURE_MESSAGE,
    PipelineRunner,
    _collect_run_artifacts,
    _copy_artifacts_to_destination,
    run_strategy_generation,
)
from primr.mcp_server.qa_operations import run_qa_analysis
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
        job_dir = tmp_path / "job-1"
        job_dir.mkdir()
        primary = job_dir / "Acme_Corp_Strategic_Overview.md"
        primary.write_text("report", encoding="utf-8")
        sibling = job_dir / f"Acme_Corp_AI_Strategy_{today}.md"
        sibling.write_text("strategy", encoding="utf-8")
        other_dir = tmp_path / "job-2"
        other_dir.mkdir()
        other = other_dir / "Acme_Corp_AI_Strategy_other.md"
        other.write_text("nope", encoding="utf-8")

        result = _collect_run_artifacts(str(primary), "Acme Corp")
        assert str(primary) in result
        assert str(sibling) in result
        assert str(other) not in result
        # primary is always first
        assert result[0] == str(primary)

    def test_logs_partial_inventory(self, tmp_path, caplog):
        primary = tmp_path / "report.md"
        primary.write_text("body", encoding="utf-8")
        with patch(
            "primr.output.artifact_inventory.scan_artifact_roots",
            return_value={
                "artifacts": [],
                "errors": ["scan failed"],
                "truncated": True,
            },
        ):
            result = _collect_run_artifacts(str(primary), "Acme")

        assert result == [str(primary)]
        assert "Artifact inventory" in caplog.text


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
            MockLoader.return_value.load_report_from_path.return_value = MagicMock()
            MockAnalyzer.return_value.analyze_report.return_value = analysis
            result = await run_qa_analysis(str(report))

        MockLoader.return_value.load_report_from_path.assert_called_once_with(report)
        assert result["overall_score"] == 88.0
        assert result["category_scores"]["completeness"] == 90.0
        assert result["improvement_suggestions"] == ["fix this"]

    @pytest.mark.asyncio
    async def test_load_failure_raises(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# report", encoding="utf-8")
        with patch("primr.qa.report_loader.ReportLoader") as MockLoader:
            MockLoader.return_value.load_report_from_path.return_value = None
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
        await runner.run_research(job=job, company_url="https://example.com", mode="full")
        updated = server.job_store.get(job.job_id)
        assert updated.get_status().value == "completed"
        assert str(report) in updated.output_paths

    @pytest.mark.asyncio
    async def test_fast_mode_delivers_the_single_approved_strategy(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        output_dir = tmp_path / "job-output"
        output_dir.mkdir()
        report = output_dir / "Acme_Corp_Strategic_Overview_07-12-2026.md"
        strategy = output_dir / "Acme_Corp_AI_Strategy_Azure_07-12-2026.md"
        report.write_text("report", encoding="utf-8")
        strategy.write_text("strategy", encoding="utf-8")
        seen = {}

        def fake_fast_research(*_args, **kwargs):
            seen.update(kwargs)
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fake_fast_research)

        await runner.run_research(
            job=job,
            company_url="https://example.com",
            mode="full",
            platform="azure",
        )

        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.COMPLETED
        assert str(report) in updated.output_paths
        assert str(strategy) in updated.output_paths
        assert seen["ai_strategy"] is True
        assert seen["platforms"] == ("azure",)

    @pytest.mark.asyncio
    async def test_fast_mode_fails_if_approved_strategy_artifact_is_missing(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        report = tmp_path / "Acme_Corp_Strategic_Overview_07-12-2026.md"
        report.write_text("report", encoding="utf-8")
        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            lambda *_args, **_kwargs: str(report),
        )

        await runner.run_research(
            job=job,
            company_url="https://example.com",
            mode="full",
            platform="azure",
        )

        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "pipeline_error"
        assert updated.output_paths == []

    @pytest.mark.asyncio
    async def test_fast_mode_failure(self, server, runner, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            lambda *a, **k: None,
        )
        await runner.run_research(job=job, company_url="https://example.com", mode="full")
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "research_failed"

    @pytest.mark.asyncio
    async def test_fast_mode_with_destination(self, server, runner, monkeypatch, tmp_path):
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
        assert (dest / job.job_id / "report.md").exists()

    @pytest.mark.asyncio
    async def test_fast_mode_verify_copies_verification_artifact(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        report = tmp_path / "report.md"
        report.write_text("done", encoding="utf-8")
        dest = tmp_path / "dest"

        def fake_verify(*, report_path, **_kwargs):
            verification = Path(report_path).parent / "verification.json"
            verification.write_text('{"trust_score": 1.0}', encoding="utf-8")

        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            lambda *a, **k: str(report),
        )
        monkeypatch.setattr("primr.core.research_agent._run_verification", fake_verify)

        await runner.run_research(
            job=job,
            company_url="https://example.com",
            mode="full",
            verify=True,
            destination=str(dest),
        )

        updated = server.job_store.get(job.job_id)
        assert updated.get_status().value == "completed"
        job_dest = dest / job.job_id
        assert updated.output_paths == [
            str(job_dest / "report.md"),
            str(job_dest / "verification.json"),
            str(job_dest / "run_manifest.json"),
        ]
        assert (job_dest / "verification.json").exists()

    @pytest.mark.asyncio
    async def test_shared_destination_keeps_jobs_isolated(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        destination = tmp_path / "shared"
        manifest_paths = []
        for index in range(2):
            report = tmp_path / f"report-{index}.md"
            report.write_text(f"run {index}", encoding="utf-8")
            monkeypatch.setattr(
                "primr.core.research_agent.perform_fast_research",
                lambda *args, report=report, **kwargs: str(report),
            )
            job = server.job_store.create(f"Acme {index}", "full", owner_client_id="stdio")
            await runner.run_research(
                job=job,
                company_url="https://example.com",
                mode="full",
                destination=str(destination),
            )
            manifest_paths.append(Path(job.output_paths[-1]))

        assert manifest_paths[0] != manifest_paths[1]
        assert all(path.is_file() for path in manifest_paths)

    @pytest.mark.asyncio
    async def test_fast_mode_activates_and_clears_run_budget(
        self, server, runner, monkeypatch, tmp_path
    ):
        from primr.utils.run_budget import clear_run_budget, get_run_budget

        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        clear_run_budget()
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        report = tmp_path / "report.md"
        report.write_text("done", encoding="utf-8")
        seen = {}

        def fake_fast_research(*_args, **_kwargs):
            budget = get_run_budget()
            seen["budget"] = budget
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fake_fast_research)

        await runner.run_research(
            job=job,
            company_url="https://example.com",
            mode="full",
            budget_usd=2.5,
        )

        assert seen["budget"] is not None
        assert seen["budget"].max_cost == 2.5
        assert get_run_budget() is None

    @pytest.mark.asyncio
    async def test_fast_mode_without_cap_clears_stale_run_budget(
        self, server, runner, monkeypatch, tmp_path
    ):
        from primr.utils.run_budget import get_run_budget, set_run_budget

        monkeypatch.setenv("XAI_API_KEY", "fake-key")
        set_run_budget(1.0)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        report = tmp_path / "report.md"
        report.write_text("done", encoding="utf-8")
        seen = {}

        def fake_fast_research(*_args, **_kwargs):
            seen["budget"] = get_run_budget()
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fake_fast_research)

        await runner.run_research(job=job, company_url="https://example.com", mode="full")

        assert seen["budget"] is None
        assert get_run_budget() is None


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
            pending_interaction_id="interaction-123",
        )
        mock_orch = MagicMock()
        mock_orch.research = AsyncMock(return_value=result)

        with (
            patch(
                "primr.core.research_orchestrator.ResearchOrchestrator",
                return_value=mock_orch,
            ),
            patch(
                "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
                return_value=True,
            ) as acknowledge_mock,
        ):
            # Avoid filesystem write churn: patch _save_report + qa + manifest
            runner._save_report = AsyncMock(return_value=str(tmp_path / "report.md"))
            runner._run_qa = AsyncMock(return_value={"overall_score": 91})
            runner._generate_run_manifest = AsyncMock()
            await runner.run_research(job=job, company_url="https://example.com", mode="premium")

        updated = server.job_store.get(job.job_id)
        assert updated.get_status().value == "completed"
        assert updated.qa_score == 91
        acknowledge_mock.assert_called_once_with("interaction-123", [str(tmp_path / "report.md")])

    @pytest.mark.asyncio
    async def test_standard_path_generates_promised_strategy_before_completion(
        self, server, runner, monkeypatch, tmp_path
    ):
        """A platform-bearing premium run delivers the strategy priced by its estimate."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        job = server.job_store.create("Acme Corp", "premium", owner_client_id="stdio")
        result = SimpleNamespace(
            success=True,
            error=None,
            raw_content="# Report Body",
            section_results={},
            pending_interaction_id="",
        )
        orchestrator = MagicMock(research=AsyncMock(return_value=result))
        report_path = str(tmp_path / "report.md")
        strategy_path = str(tmp_path / "strategy.md")
        runner._save_report = AsyncMock(return_value=report_path)
        runner._generate_run_manifest = AsyncMock(return_value=str(tmp_path / "run_manifest.json"))

        with (
            patch(
                "primr.core.research_orchestrator.ResearchOrchestrator",
                return_value=orchestrator,
            ),
            patch(
                "primr.mcp_server.pipeline_runner.run_strategy_generation",
                new=AsyncMock(
                    return_value={
                        "output_path": strategy_path,
                        "strategy_type": "ai_strategy",
                        "qa_score": None,
                    }
                ),
            ) as strategy_mock,
        ):
            await runner.run_research(
                job,
                "https://example.com",
                "premium",
                platform="agnostic",
                skip_qa=True,
            )

        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.COMPLETED
        assert strategy_path in updated.output_paths
        strategy_mock.assert_awaited_once()
        assert strategy_mock.await_args.kwargs["platform"] == "agnostic"

    @pytest.mark.asyncio
    async def test_standard_path_report_only_shape_emits_no_strategy(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        job = server.job_store.create("Acme Corp", "premium", owner_client_id="stdio")
        result = SimpleNamespace(
            success=True,
            error=None,
            raw_content="# Report Body",
            section_results={},
            pending_interaction_id="",
        )
        report_path = str(tmp_path / "report.md")
        manifest_path = str(tmp_path / "run_manifest.json")
        runner._save_report = AsyncMock(return_value=report_path)
        runner._generate_run_manifest = AsyncMock(return_value=manifest_path)

        with (
            patch(
                "primr.core.research_orchestrator.ResearchOrchestrator",
                return_value=MagicMock(research=AsyncMock(return_value=result)),
            ),
            patch(
                "primr.mcp_server.pipeline_runner.run_strategy_generation",
                new=AsyncMock(),
            ) as strategy_mock,
        ):
            await runner.run_research(
                job,
                "https://example.com",
                "premium",
                platform=None,
                skip_qa=True,
            )

        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.COMPLETED
        assert updated.output_paths == [report_path, manifest_path]
        strategy_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_report_write_failure_retains_pending_interaction(
        self, server, runner, monkeypatch
    ):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        job = server.job_store.create("Acme", "premium", owner_client_id="stdio")
        result = SimpleNamespace(
            success=True,
            error=None,
            raw_content="# Report",
            section_results={},
            pending_interaction_id="interaction-123",
        )
        orchestrator = MagicMock(research=AsyncMock(return_value=result))
        runner._save_report = AsyncMock(side_effect=OSError("disk full"))
        with (
            patch(
                "primr.core.research_orchestrator.ResearchOrchestrator",
                return_value=orchestrator,
            ),
            patch(
                "primr.ai.job_persistence.acknowledge_pending_job_after_outputs"
            ) as acknowledge_mock,
        ):
            await runner.run_research(job, "https://example.com", "premium")

        assert job.get_status().value == "failed"
        acknowledge_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestrator_failure_is_sanitized(self, server, runner, monkeypatch, caplog):
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
            await runner.run_research(job=job, company_url="https://example.com", mode="premium")
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "research_failed"
        assert updated.error_message == PUBLIC_RESEARCH_FAILURE_MESSAGE
        assert "orchestrator boom" in caplog.text

    @pytest.mark.asyncio
    async def test_pipeline_exception_records_sanitized_failure(
        self, server, runner, monkeypatch, caplog
    ):
        from primr.utils.run_budget import clear_run_budget, get_run_budget

        monkeypatch.delenv("XAI_API_KEY", raising=False)
        clear_run_budget()
        job = server.job_store.create("Acme Corp", "premium", owner_client_id="stdio")

        with patch(
            "primr.core.research_orchestrator.ResearchOrchestrator",
            side_effect=RuntimeError("init failed"),
        ):
            await runner.run_research(
                job=job,
                company_url="https://example.com",
                mode="premium",
                budget_usd=2.0,
            )
        updated = server.job_store.get(job.job_id)
        assert updated.current_stage == ResearchStage.FAILED
        assert updated.error_type == "pipeline_error"
        assert updated.error_message == PUBLIC_RESEARCH_FAILURE_MESSAGE
        assert "init failed" in caplog.text
        assert get_run_budget() is None


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
        result = SimpleNamespace(raw_content=None, section_results={"Overview": "body text"})
        path = await runner._save_report("Acme Corp", result)
        content = Path(path).read_text(encoding="utf-8")
        assert "## Overview" in content
        assert "body text" in content

    def test_attach_generated_manifest_is_idempotent(self, server, runner, tmp_path):
        job = server.job_store.create("Acme", "full", owner_client_id="stdio")
        manifest = str(tmp_path / "run_manifest.json")
        runner._attach_generated_manifest(job, manifest)
        runner._attach_generated_manifest(job, manifest)
        assert job.output_paths == [manifest]

    @pytest.mark.asyncio
    async def test_generate_run_manifest(self, server, runner, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        report = tmp_path / "report.md"
        report.write_text("x", encoding="utf-8")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        manifest_path = await runner._generate_run_manifest(
            job,
            "https://example.com",
            "premium",
            budget_usd=2.0,
            fast_mode=False,
            premium_mode=True,
        )
        manifest = tmp_path / "run_manifest.json"
        assert manifest_path == str(manifest)
        assert manifest.exists()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload["budget"]["approved_ceiling_usd"] == 2.0
        assert payload["budget"]["runtime_budget_active"] is True
        assert payload["budget"]["enforcement"]["checkpointed_stages"] == [
            "optional strategy generation"
        ]
        assert payload["budget"]["enforcement"]["non_interruptible_required_tasks"] == [
            "required Deep Research task"
        ]

    @pytest.mark.asyncio
    async def test_generate_run_manifest_uses_atomic_write(
        self, server, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        atomic_write = MagicMock()
        monkeypatch.setattr("primr.utils.atomic_io.atomic_write_text", atomic_write)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        report = tmp_path / "report.md"
        report.write_text("body", encoding="utf-8")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)

        manifest_path = await runner._generate_run_manifest(
            job,
            "https://example.com",
            "full",
        )

        assert manifest_path == str(tmp_path / "run_manifest.json")
        atomic_write.assert_called_once()
        target, content = atomic_write.call_args.args
        assert target == tmp_path / "run_manifest.json"
        assert json.loads(content)["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_manifests_are_isolated_by_job_output_directory(self, server, runner, tmp_path):
        paths = []
        for index in range(2):
            job = server.job_store.create(f"Acme {index}", "full", owner_client_id="stdio")
            job_dir = tmp_path / job.job_id
            job_dir.mkdir()
            report = job_dir / "report.md"
            report.write_text("body", encoding="utf-8")
            job.output_paths = [str(report)]
            job.advance_stage(ResearchStage.COMPLETED)
            paths.append(await runner._generate_run_manifest(job, "https://example.com", "full"))

        assert paths[0] != paths[1]
        assert all(Path(path).name == "run_manifest.json" for path in paths)

    @pytest.mark.asyncio
    async def test_run_qa_method_handles_failure(self, runner):
        # _run_qa swallows exceptions and returns None
        with patch("primr.qa.report_loader.ReportLoader", side_effect=RuntimeError("x")):
            result = await runner._run_qa("/nonexistent/report.md")
        assert result is None
