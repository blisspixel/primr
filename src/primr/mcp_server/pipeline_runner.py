"""
Pipeline runner for MCP server.

This module provides background task execution for research jobs,
wiring MCP tools to actual Primr core modules.

Requirements: 15.2, 19.1-19.4
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.types import ResearchStage

if TYPE_CHECKING:
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30


class PipelineRunner:
    """
    Runs research pipelines in the background.

    Wires MCP job state to actual Primr core modules:
    - research_orchestrator for research execution
    - ai_strategy for strategy generation
    - qa.analyzer for quality assessment

    Provides heartbeat updates during long-running operations.
    """

    def __init__(self, mcp_server: "PrimrMCPServer"):
        """
        Initialize the pipeline runner.

        Args:
            mcp_server: The MCP server instance for job store access
        """
        self.mcp_server = mcp_server
        self._running_task: asyncio.Task | None = None
        self._cancel_requested = False

    async def run_research(
        self,
        job: ResearchJobState,
        company_url: str,
        mode: str,
        cloud_vendor: str | None = None,
        skip_qa: bool = False,
        verify: bool = False,
    ) -> None:
        """
        Run the research pipeline for a job.

        This is the main entry point for background research execution.
        Updates job state as the pipeline progresses.

        Args:
            job: The job state to update
            company_url: Company website URL
            mode: Research mode (scrape, deep, full)
            cloud_vendor: Optional cloud vendor for strategy
            skip_qa: Whether to skip QA
        """
        self._cancel_requested = False

        try:
            import os

            # Map MCP mode to orchestrator mode
            from primr.core.research_orchestrator import ResearchMode, ResearchOrchestrator

            mode_map = {
                "scrape": ResearchMode.STRUCTURED,
                "deep": ResearchMode.DEEP_RESEARCH,
                "full": ResearchMode.COMPLETE,
                "premium": ResearchMode.COMPLETE,
            }
            research_mode = mode_map.get(mode, ResearchMode.COMPLETE)

            # Determine if fast mode should be used:
            # "full" + XAI_API_KEY → fast pipeline; "premium" → always Gemini+DR
            use_fast = mode == "full" and os.environ.get("XAI_API_KEY")

            # Create progress callback that updates job state
            def on_progress(message: str) -> None:
                if self._cancel_requested:
                    raise RuntimeError("Job cancelled by user")
                job.heartbeat()
                self.mcp_server.job_store.update(job)
                logger.debug(f"Progress: {message}")

            # Stage 1: Scraping (for scrape, full, and premium modes)
            if mode in ("scrape", "full", "premium"):
                job.advance_stage(ResearchStage.SCRAPING)
                self.mcp_server.job_store.update(job)
                on_progress("Starting website scraping...")

            if use_fast:
                # Fast pipeline: Grok 4.1
                import time

                from primr.core.research_agent import perform_fast_research

                # Start heartbeat task
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(job, HEARTBEAT_INTERVAL))
                try:
                    result_path = await asyncio.to_thread(
                        perform_fast_research,
                        job.company_name,
                        company_url,
                        time.time(),
                        ai_strategy=cloud_vendor is not None,
                        cloud_vendors=(cloud_vendor,) if cloud_vendor else ("agnostic",),
                    )
                finally:
                    heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat_task

                if not result_path:
                    job.advance_stage(ResearchStage.FAILED)
                    job.error_type = "research_failed"
                    job.error_message = "Fast mode pipeline failed"
                    self.mcp_server.job_store.update(job)
                    return

                # Fast mode produces final output directly
                job.advance_stage(ResearchStage.COMPLETED)
                job.output_paths = [result_path]
                self.mcp_server.job_store.update(job)
                return

            # Standard orchestrator pipeline (premium or non-fast full)
            orchestrator = ResearchOrchestrator()

            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(job, HEARTBEAT_INTERVAL))

            try:
                result = await orchestrator.research(
                    company_name=job.company_name,
                    website=company_url,
                    mode=research_mode,
                    on_progress=on_progress,
                )
            finally:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

            if not result.success:
                job.advance_stage(ResearchStage.FAILED)
                job.error_type = "research_failed"
                job.error_message = result.error or "Research failed"
                self.mcp_server.job_store.update(job)
                return

            # Stage: Writing
            job.advance_stage(ResearchStage.WRITING)
            self.mcp_server.job_store.update(job)
            on_progress("Writing report...")

            # Save the report
            output_path = await self._save_report(job.company_name, result)
            job.output_paths = [output_path]

            # Stage: QA (unless skipped)
            if not skip_qa:
                job.advance_stage(ResearchStage.QA)
                self.mcp_server.job_store.update(job)
                on_progress("Running quality assessment...")

                qa_result = await self._run_qa(output_path)
                if qa_result:
                    job.qa_score = qa_result.get("overall_score")

            # Stage: Verification (optional, non-blocking)
            if verify and output_path:
                on_progress("Running claim verification...")
                try:
                    from primr.core.research_agent import _run_verification

                    await asyncio.to_thread(
                        _run_verification,
                        company_name=job.company_name,
                        company_url=company_url,
                        report_path=output_path,
                    )
                except Exception as e:
                    logger.warning(f"Verification failed (non-blocking): {e}")

            # Complete
            job.advance_stage(ResearchStage.COMPLETED)
            self.mcp_server.job_store.update(job)

            # Generate run manifest for audit trail (FR-7.1)
            await self._generate_run_manifest(job, company_url, mode)

            logger.info(f"Research job {job.job_id} completed successfully")

        except asyncio.CancelledError:
            job.advance_stage(ResearchStage.CANCELLED)
            job.error_type = "user_cancelled"
            job.error_message = "Job was cancelled"
            self.mcp_server.job_store.update(job)
            logger.info(f"Research job {job.job_id} was cancelled")

        except Exception as e:
            logger.error(f"Research job {job.job_id} failed: {e}")
            job.advance_stage(ResearchStage.FAILED)
            job.error_type = "pipeline_error"
            job.error_message = str(e)
            self.mcp_server.job_store.update(job)

    async def _heartbeat_loop(
        self,
        job: ResearchJobState,
        interval: float,
    ) -> None:
        """
        Send periodic heartbeats during long operations.

        Requirements: 2.12, 19.1-19.3
        """
        while True:
            await asyncio.sleep(interval)
            job.heartbeat()
            self.mcp_server.job_store.update(job)
            logger.debug(f"Heartbeat for job {job.job_id}")

    async def _save_report(
        self,
        company_name: str,
        result,
    ) -> str:
        """
        Save the research result to a file.

        Returns the output path.
        """
        import os
        from datetime import datetime

        from primr.config.config import OUTPUT_DIR

        # Create output directory if needed
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Generate filename
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.md"
        output_path = os.path.join(OUTPUT_DIR, filename)

        # Write content
        content = result.raw_content or "\n\n".join(
            f"## {k}\n\n{v}" for k, v in result.section_results.items()
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Report saved to {output_path}")
        return output_path

    async def _run_qa(self, report_path: str) -> dict | None:
        """
        Run QA analysis on a report.

        Returns QA results dict or None on failure.
        """
        try:
            from primr.qa.analyzer import QAAnalyzer
            from primr.qa.report_loader import ReportLoader

            # Load report
            loader = ReportLoader()
            report = loader.load(report_path)

            if not report:
                logger.warning(f"Could not load report for QA: {report_path}")
                return None

            # Run analysis
            analyzer = QAAnalyzer()
            analysis = analyzer.analyze_report(report)

            return {
                "overall_score": analysis.overall_score,
                "category_scores": {
                    "completeness": analysis.completeness_score,
                    "accuracy": analysis.accuracy_score,
                    "clarity": analysis.clarity_score,
                    "actionability": analysis.actionability_score,
                },
                "issues_count": len(analysis.issues),
            }

        except Exception as e:
            logger.warning(f"QA analysis failed: {e}")
            return None

    async def _generate_run_manifest(
        self,
        job: ResearchJobState,
        company_url: str,
        mode: str,
    ) -> None:
        """
        Generate run_manifest.json for audit trail.

        Requirements: FR-7.1, FR-7.2
        """
        import json
        from pathlib import Path

        from primr.config.config import OUTPUT_DIR

        # Determine output directory for this job
        if job.output_paths:
            output_dir = Path(job.output_paths[0]).parent
        else:
            safe_name = job.company_name.replace(" ", "_").replace("/", "_").lower()
            output_dir = Path(OUTPUT_DIR) / safe_name

        output_dir.mkdir(parents=True, exist_ok=True)

        # Calculate actual execution time
        actual_time_minutes = None
        if job.start_time and job.completion_time:
            delta = job.completion_time - job.start_time
            actual_time_minutes = int(delta.total_seconds() / 60)

        # Build manifest per FR-7.2 schema
        manifest = {
            "schema_version": "1.0",
            "job_id": job.job_id,
            "company_name": job.company_name,
            "company_url": company_url,
            "mode": mode,
            "estimate": {
                "cost_usd": None,  # Would need to track from estimate_run
                "time_minutes": None,
                "estimated_at": None,
            },
            "approval": {
                "token": None,  # Would need to track from workflow
                "approved_at": None,
                "approved_by": job.owner_client_id or "stdio",
                "bound_to_estimate": False,
            },
            "execution": {
                "started_at": job.start_time.isoformat() if job.start_time else None,
                "completed_at": job.completion_time.isoformat() if job.completion_time else None,
                "status": job.get_status().value,
                "actual_cost_usd": None,  # Would need usage tracking
                "actual_time_minutes": actual_time_minutes,
            },
            "artifacts": job.output_paths or [],
        }

        # Write manifest
        manifest_path = output_dir / "run_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Run manifest saved to {manifest_path}")

    def request_cancel(self) -> None:
        """Request cancellation of the running job."""
        self._cancel_requested = True
        if self._running_task:
            self._running_task.cancel()


async def run_strategy_generation(
    report_path: str,
    strategy_type: str,
    cloud_vendor: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> dict:
    """
    Run strategy generation on an existing report.

    Args:
        report_path: Path to the research report
        strategy_type: Type of strategy to generate
        cloud_vendor: Optional cloud vendor preference
        on_progress: Optional progress callback

    Returns:
        Dict with output_path, strategy_type, and qa_score
    """
    # Extract company name from report filename
    import os
    import re

    from primr.core.ai_strategy import CloudVendor, generate_ai_strategy

    # Filename pattern: "Company_Name_Strategic_Overview_MM-DD-YYYY.ext"
    filename = os.path.splitext(os.path.basename(report_path))[0]
    match = re.match(
        r"^(.+?)_(?:Strategic_Overview|AI_Strategy|Customer_Experience|Security|Data_Fabric)",
        filename,
    )
    if match:
        company_name = match.group(1).replace("_", " ")
    else:
        company_name = filename.replace("_", " ")

    # Map strategy type
    vendor = CloudVendor.from_string(cloud_vendor) if cloud_vendor else CloudVendor.AGNOSTIC

    result = await generate_ai_strategy(
        company_name=company_name,
        cloud_vendor=vendor,
        company_research_path=report_path,
        on_progress=on_progress,
    )

    if result.error:
        raise RuntimeError(result.error)

    return {
        "output_path": result.md_path or result.docx_path or result.txt_path,
        "strategy_type": strategy_type,
        "qa_score": None,  # Strategy doesn't have QA yet
    }


async def run_qa_analysis(report_path: str) -> dict:
    """
    Run QA analysis on a report.

    Args:
        report_path: Path to the report file

    Returns:
        Dict with QA results
    """
    from primr.qa.analyzer import QAAnalyzer
    from primr.qa.report_loader import ReportLoader

    # Load report
    loader = ReportLoader()
    report = loader.load(report_path)

    if not report:
        raise RuntimeError(f"Could not load report: {report_path}")

    # Run analysis
    analyzer = QAAnalyzer()
    analysis = analyzer.analyze_report(report)

    return {
        "overall_score": analysis.overall_score,
        "category_scores": {
            "completeness": analysis.completeness_score,
            "accuracy": analysis.accuracy_score,
            "clarity": analysis.clarity_score,
            "actionability": analysis.actionability_score,
        },
        "improvement_suggestions": [issue.description for issue in analysis.issues[:5]]
        if analysis.issues
        else [],
    }


def get_doctor_status() -> dict:
    """
    Get system health status.

    Returns:
        Dict with health status information
    """
    import os

    from primr.config.config import OUTPUT_DIR

    warnings = []

    # Check API keys
    api_keys_configured = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    if not api_keys_configured:
        warnings.append("No API key configured (GOOGLE_API_KEY or GEMINI_API_KEY)")

    # Check output directory
    if not os.path.exists(OUTPUT_DIR):
        warnings.append(f"Output directory does not exist: {OUTPUT_DIR}")

    # Check for orphaned stores (placeholder - would check Gemini file stores)
    orphaned_stores_count = 0

    # Check config validity
    config_valid = True
    try:
        from primr.config.config import validate_config

        result = validate_config()
        config_valid = result.valid
        if not config_valid:
            for err in result.errors:
                warnings.append(f"Config: {err}")
    except Exception as e:
        config_valid = False
        warnings.append(f"Configuration error: {e}")

    return {
        "orphaned_stores_count": orphaned_stores_count,
        "config_valid": config_valid,
        "api_keys_configured": api_keys_configured,
        "warnings": warnings,
    }
