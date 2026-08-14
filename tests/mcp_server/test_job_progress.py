"""Progress-message stage inference for MCP job honesty."""

from __future__ import annotations

from types import SimpleNamespace

from primr.mcp_server.job_progress import apply_progress_stage, infer_research_stage
from primr.mcp_server.types import ResearchStage


def test_infer_scraping_and_deep_and_writing():
    assert infer_research_stage("Starting website scraping...") is ResearchStage.SCRAPING
    assert infer_research_stage("Starting Deep Research (single comprehensive call)...") is (
        ResearchStage.DEEP_RESEARCH
    )
    assert infer_research_stage("Writing: Executive Summary (1/23)...") is ResearchStage.WRITING
    assert infer_research_stage("Phase 3: Assembling final report...") is ResearchStage.WRITING
    assert infer_research_stage("Extracting insights") is ResearchStage.EXTRACTING
    assert infer_research_stage("Running claim verification...") is ResearchStage.QA
    assert infer_research_stage("heartbeat") is None
    assert infer_research_stage("") is None


def test_apply_progress_advances_monotonic_job():
    calls: list[ResearchStage] = []

    class Job:
        def advance_stage(self, stage):
            calls.append(stage)
            return True

    job = Job()
    assert apply_progress_stage(job, "Starting website scraping...") is True
    assert apply_progress_stage(job, "Starting Deep Research...") is True
    assert apply_progress_stage(job, "") is False
    assert calls == [ResearchStage.SCRAPING, ResearchStage.DEEP_RESEARCH]


def test_apply_progress_ignores_jobs_without_advance():
    assert apply_progress_stage(SimpleNamespace(), "Starting Deep Research...") is False
