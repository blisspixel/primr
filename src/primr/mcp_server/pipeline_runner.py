"""
Pipeline runner for MCP server.

This module provides background task execution for research jobs,
wiring MCP tools to actual Primr core modules.

Requirements: 15.2, 19.1-19.4
"""

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any, Protocol, cast

from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.strategy_operations import run_strategy_generation
from primr.mcp_server.types import ResearchStage


class PipelineServerContext(Protocol):
    """Minimal controller surface required by ``PipelineRunner``."""

    job_store: Any


logger = logging.getLogger(__name__)

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30
PUBLIC_RESEARCH_FAILURE_MESSAGE = "Research pipeline failed. See server logs for details."


class PipelineRunner:
    """
    Runs research pipelines in the background.

    Wires MCP job state to actual Primr core modules:
    - research_orchestrator for research execution
    - ai_strategy for strategy generation
    - qa.analyzer for quality assessment

    Provides heartbeat updates during long-running operations.
    """

    def __init__(self, mcp_server: PipelineServerContext):
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
        platform: str | None = None,
        skip_qa: bool = False,
        verify: bool = False,
        destination: str | None = None,
        budget_usd: float | None = None,
    ) -> None:
        """
        Run the research pipeline for a job.

        This is the main entry point for background research execution.
        Updates job state as the pipeline progresses.

        Args:
            job: The job state to update
            company_url: Company website URL
            mode: Research mode (scrape, deep, full)
            platform: Optional platform for strategy
            skip_qa: Whether to skip QA
            verify: Whether to run claim verification
            destination: Optional destination directory for output files
            budget_usd: Operator-approved per-run cost ceiling (the MCP cost
                cap). When set, it activates the same optional-stage budget
                checkpoints the CLI ``--budget`` flag uses. Without it the run
                is governed by its pre-flight estimate only.
        """
        self._cancel_requested = False
        current_task = asyncio.current_task()
        self._running_task = current_task

        # Bound optional spend to the operator-approved cap, mirroring the CLI
        # --budget path. The budget is process-global and the MCP server runs
        # one job at a time, so it is cleared in a finally below to never leak
        # into the next job.
        from primr.utils.run_budget import clear_run_budget, set_run_budget

        budget_active = False
        clear_run_budget()
        if budget_usd is not None and budget_usd > 0:
            set_run_budget(budget_usd)
            budget_active = True

        try:
            # Defensive per-job accounting reset: the fast path resets in its
            # own setup, but the non-fast/orchestrator paths do not - without
            # this a long-lived server bleeds prior jobs' spend into this
            # job's checkpoints and usage records. Inside the try so a broken
            # reset marks THIS job failed instead of wedging the single-job
            # store with a forever-running job.
            from primr.ai.client import reset_run_usage_accounting

            reset_run_usage_accounting()

            import os

            from primr.config.config import OUTPUT_DIR

            job_output_dir = Path(OUTPUT_DIR) / job.job_id

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
                    # Raise CancelledError (a BaseException) so it bypasses the
                    # orchestrator's broad `except Exception` and reaches the
                    # CANCELLED-recording handler below. A RuntimeError here is
                    # caught as a generic failure and mis-records the job as
                    # FAILED/research_failed instead of CANCELLED/user_cancelled.
                    raise asyncio.CancelledError("Job cancelled by user")
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
                        ai_strategy=platform is not None,
                        platforms=(platform,) if platform else ("agnostic",),
                        output_dir=job_output_dir,
                        diagnostics_dir=job_output_dir / "_diagnostics",
                        write_txt=True,
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

                # Fast mode produces final output directly — collect all artifacts
                # (report + strategy files) from the output directory
                all_artifacts = _collect_run_artifacts(result_path, job.company_name)
                _require_ai_strategy_artifact(
                    all_artifacts,
                    required=platform is not None,
                )

                if verify:
                    on_progress("Running claim verification...")
                    try:
                        from primr.core.research_agent import _run_verification

                        await asyncio.to_thread(
                            _run_verification,
                            company_name=job.company_name,
                            company_url=company_url,
                            report_path=result_path,
                        )
                        all_artifacts = _with_verification_artifacts(all_artifacts)
                    except Exception as e:
                        logger.warning(f"Verification failed (non-blocking): {e}")

                # If a destination was specified, copy artifacts there
                if destination:
                    all_artifacts = _copy_artifacts_to_destination(
                        all_artifacts, str(Path(destination) / job.job_id)
                    )

                all_artifacts = _with_trace_artifacts(all_artifacts, job)
                job.output_paths = all_artifacts
                await self._complete_with_manifest(
                    job,
                    company_url,
                    mode,
                    budget_usd=budget_usd,
                    fast_mode=True,
                    premium_mode=False,
                )
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
                logger.error(
                    "Research job %s failed: %s",
                    job.job_id,
                    result.error or "Research failed without an error detail",
                )
                job.advance_stage(ResearchStage.FAILED)
                job.error_type = "research_failed"
                job.error_message = PUBLIC_RESEARCH_FAILURE_MESSAGE
                self.mcp_server.job_store.update(job)
                return

            # Stage: Writing
            job.advance_stage(ResearchStage.WRITING)
            self.mcp_server.job_store.update(job)
            on_progress("Writing report...")

            # Save the report
            output_path = await self._save_report(
                job.company_name, result, output_dir=job_output_dir
            )
            job.output_paths = [output_path]
            pending_interaction_id = getattr(result, "pending_interaction_id", "")
            if isinstance(pending_interaction_id, str) and pending_interaction_id:
                from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

                if not acknowledge_pending_job_after_outputs(pending_interaction_id, [output_path]):
                    logger.warning(
                        "Report was saved but pending interaction %s remains listed",
                        pending_interaction_id,
                    )

            # The estimate and public contract include one agnostic AI
            # strategy by default for full and premium runs. Fast mode creates
            # it inside perform_fast_research; the standard orchestrator path
            # must add the same artifact explicitly.
            if platform is not None:
                on_progress("Generating AI strategy...")
                strategy_result = await run_strategy_generation(
                    output_path,
                    "ai_strategy",
                    platform=platform,
                    on_progress=on_progress,
                )
                strategy_path = strategy_result.get("output_path")
                if not isinstance(strategy_path, str) or not strategy_path:
                    raise RuntimeError("AI strategy generation produced no output artifact")
                job.output_paths.append(strategy_path)
                self.mcp_server.job_store.update(job)

            # Stage: QA (unless skipped)
            if not skip_qa:
                job.advance_stage(ResearchStage.QA)
                self.mcp_server.job_store.update(job)
                on_progress("Running quality assessment...")

                qa_result = await self._run_qa(output_path)
                if qa_result:
                    job.qa_score = qa_result.get("overall_score")

            # Stage: Verification (optional, non-blocking)
            verification_completed = False
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
                    verification_completed = True
                except Exception as e:
                    logger.warning(f"Verification failed (non-blocking): {e}")

            if verification_completed:
                job.output_paths = _with_verification_artifacts(job.output_paths)

            # If a destination was specified, copy artifacts there
            if destination and job.output_paths:
                job.output_paths = _copy_artifacts_to_destination(
                    job.output_paths, str(Path(destination) / job.job_id)
                )

            job.output_paths = _with_trace_artifacts(job.output_paths, job)
            await self._complete_with_manifest(
                job,
                company_url,
                mode,
                budget_usd=budget_usd,
                fast_mode=use_fast,
                premium_mode=mode == "premium",
            )

            logger.info(f"Research job {job.job_id} completed successfully")

        except asyncio.CancelledError:
            job.advance_stage(ResearchStage.CANCELLED)
            job.error_type = "user_cancelled"
            job.error_message = "Job was cancelled"
            self.mcp_server.job_store.update(job)
            logger.info(f"Research job {job.job_id} was cancelled")

        except Exception:
            logger.exception("Research job %s failed", job.job_id)
            job.advance_stage(ResearchStage.FAILED)
            job.error_type = "pipeline_error"
            job.error_message = PUBLIC_RESEARCH_FAILURE_MESSAGE
            self.mcp_server.job_store.update(job)
        finally:
            if budget_active:
                clear_run_budget()
            if self._running_task is current_task:
                self._running_task = None

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

    def _attach_generated_manifest(self, job: ResearchJobState, path: object) -> None:
        """Attach one generated manifest without duplicating job artifacts."""
        if isinstance(path, str) and path and path not in job.output_paths:
            job.output_paths.append(path)
            self.mcp_server.job_store.update(job)

    async def _complete_with_manifest(
        self,
        job: ResearchJobState,
        company_url: str,
        mode: str,
        *,
        budget_usd: float | None,
        fast_mode: bool,
        premium_mode: bool,
    ) -> None:
        """Write the success manifest before committing terminal completion."""
        manifest_job = ResearchJobState.from_journal_dict(job.to_journal_dict())
        if not manifest_job.advance_stage(ResearchStage.COMPLETED):
            raise RuntimeError("Could not prepare completed run manifest state")
        manifest_path = await self._generate_run_manifest(
            manifest_job,
            company_url,
            mode,
            budget_usd=budget_usd,
            fast_mode=fast_mode,
            premium_mode=premium_mode,
        )
        if (
            isinstance(manifest_path, str)
            and manifest_path
            and manifest_path not in job.output_paths
        ):
            job.output_paths.append(manifest_path)
        if not job.advance_stage(ResearchStage.COMPLETED):
            raise RuntimeError("Could not commit completed research job state")
        self.mcp_server.job_store.update(job)

    async def _save_report(
        self,
        company_name: str,
        result,
        *,
        output_dir: str | Path | None = None,
    ) -> str:
        """
        Save the research result to a file.

        Returns the output path.
        """
        import os
        from datetime import datetime

        from primr.config.config import OUTPUT_DIR

        destination = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
        os.makedirs(destination, exist_ok=True)

        # Generate filename
        safe_name = company_name.replace(" ", "_").replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.md"
        output_path = os.path.join(destination, filename)

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
        *,
        budget_usd: float | None = None,
        fast_mode: bool | None = None,
        premium_mode: bool | None = None,
    ) -> str:
        """
        Generate run_manifest.json for audit trail.

        Requirements: FR-7.1, FR-7.2
        """
        import json
        import os
        from pathlib import Path

        from primr.config.config import OUTPUT_DIR
        from primr.core.budget_policy import describe_budget_enforcement
        from primr.utils.atomic_io import atomic_write_text

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

        resolved_fast_mode = (
            mode == "full" and bool(os.environ.get("XAI_API_KEY"))
            if fast_mode is None
            else fast_mode
        )
        resolved_premium_mode = mode == "premium" if premium_mode is None else premium_mode
        budget_policy_mode = {
            "scrape": "scrape-only",
            "deep": "deep-research",
            "full": "complete",
            "premium": "complete",
        }.get(mode, "complete")
        budget_enforcement = describe_budget_enforcement(
            mode=budget_policy_mode,
            fast_mode=resolved_fast_mode,
            premium_mode=resolved_premium_mode,
        ).as_dict()

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
            "budget": {
                "approved_ceiling_usd": budget_usd,
                "runtime_budget_active": budget_usd is not None and budget_usd > 0,
                "enforcement": budget_enforcement,
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

        # Write the manifest atomically before the caller commits terminal
        # completion. This prevents a partial JSON file from being published as
        # the audit record for a successful run.
        manifest_path = output_dir / "run_manifest.json"
        atomic_write_text(manifest_path, json.dumps(manifest, indent=2))

        logger.info(f"Run manifest saved to {manifest_path}")
        return str(manifest_path)

    def request_cancel(self) -> None:
        """Request cancellation of the running job."""
        self._cancel_requested = True
        if self._running_task:
            self._running_task.cancel()


def _collect_run_artifacts(primary_path: str, _company_name: str) -> list[str]:
    """
    Collect all output artifacts (report + strategy files) for a completed run.

    The MCP runner gives each job an isolated directory, so every recognized
    direct child belongs to that job. The primary report remains first.

    Args:
        primary_path: The primary output path returned by the pipeline.
        _company_name: Retained for compatibility with older internal callers.

    Returns:
        List of artifact paths, primary report first.
    """
    from pathlib import Path

    from primr.output.artifact_inventory import inventory_explicit, scan_artifact_roots

    primary = Path(primary_path)
    output_dir = primary.parent

    if not output_dir.exists():
        return [primary_path]

    explicit = inventory_explicit([primary], expand_adjacent=True)
    artifacts = [str(record.path) for record in explicit if record.exists]
    seen = {Path(path).resolve(strict=False) for path in artifacts}
    scan = scan_artifact_roots([output_dir], max_depth=0)
    if scan["errors"] or scan["truncated"]:
        logger.warning(
            "Artifact inventory for %s was partial: errors=%s truncated=%s",
            output_dir,
            scan["errors"],
            scan["truncated"],
        )
    for record in cast("list", scan["artifacts"]):
        candidate = record.path
        normalized_path = candidate.resolve(strict=False)
        if normalized_path in seen:
            continue
        if record.artifact_type in {
            "calibration_sidecar",
            "qa_summary",
            "verification_summary",
            "run_manifest",
        } or candidate.suffix.lower() in {".md", ".txt", ".docx", ".pdf"}:
            artifacts.append(str(candidate))
            seen.add(normalized_path)
    return artifacts or [primary_path]


def _require_ai_strategy_artifact(artifact_paths: list[str], *, required: bool) -> None:
    """Reject a successful fast run that omitted its approved strategy."""
    if required and not any("_ai_strategy" in Path(path).stem.lower() for path in artifact_paths):
        raise RuntimeError("Fast research completed without the approved AI strategy artifact")


def _with_trace_artifacts(
    artifact_paths: list[str],
    job: ResearchJobState,
) -> list[str]:
    """Append same-run scrape trace artifacts when tracing produced them."""
    paths = list(artifact_paths)
    seen = {Path(path).resolve(strict=False) for path in paths}
    for trace_path in _collect_trace_artifacts(job):
        normalized = Path(trace_path).resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(trace_path)
    return paths


def _with_verification_artifacts(artifact_paths: list[str]) -> list[str]:
    """Append adjacent verification artifacts produced for the current run."""
    paths = list(artifact_paths)
    seen = {Path(path).resolve(strict=False) for path in paths}
    for artifact_path in artifact_paths:
        for candidate in _verification_artifact_candidates(Path(artifact_path)):
            if not candidate.is_file():
                continue
            normalized = candidate.resolve(strict=False)
            if normalized in seen:
                continue
            seen.add(normalized)
            paths.append(str(candidate))
    return paths


def _verification_artifact_candidates(path: Path) -> list[Path]:
    return [
        path.parent / "verification.json",
        path.with_name(f"{path.stem}_verification.json"),
        path.with_name(f"{path.stem}_verify.json"),
    ]


def _collect_trace_artifacts(job: ResearchJobState) -> list[str]:
    from datetime import datetime, timezone

    trace_dir = Path("logs") / "scrape_traces"
    if not trace_dir.is_dir():
        return []

    start_ts = job.start_time.timestamp() - 5
    end = job.completion_time or job.last_heartbeat_time or datetime.now(timezone.utc)
    end_ts = end.timestamp() + 60
    safe_name = _trace_company_slug(job.company_name)

    traces: list[Path] = []
    for candidate in trace_dir.glob(f"{safe_name}_*.jsonl"):
        modified = candidate.stat().st_mtime
        if start_ts <= modified <= end_ts:
            traces.append(candidate)
    return [str(path) for path in sorted(traces, key=lambda path: path.stat().st_mtime)]


def _trace_company_slug(company_name: str) -> str:
    sanitized = company_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return "".join(char for char in sanitized if char.isalnum() or char in "_-")[:50]


def _copy_artifacts_to_destination(artifact_paths: list[str], destination: str) -> list[str]:
    """
    Copy artifact files to a user-specified destination directory.

    Args:
        artifact_paths: List of source artifact file paths.
        destination: Target directory path.

    Returns:
        List of new artifact paths in the destination directory.
    """
    import shutil
    from pathlib import Path

    dest_dir = Path(destination)
    dest_dir.mkdir(parents=True, exist_ok=True)

    new_paths: list[str] = []
    for src_path in artifact_paths:
        src = Path(src_path)
        if not src.exists():
            continue
        dest_file = dest_dir / src.name
        shutil.copy2(str(src), str(dest_file))
        new_paths.append(str(dest_file))
        logger.info(f"Copied artifact to destination: {dest_file}")

    return new_paths if new_paths else artifact_paths
