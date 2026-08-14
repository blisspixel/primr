"""Unified orchestration for structured and Deep Research engines."""

import asyncio
import os
from collections.abc import Callable

from primr.ai.deep_research import (
    DeepResearchClient,
    ReportFormatter,
    ResearchProgress,
    get_deep_research_orchestrator,
)
from primr.ai.deep_research import ResearchResult as DeepResearchResult
from primr.core.research_types import OrchestratorResult, ResearchConfig, ResearchMode
from primr.utils.errors import ResearchError
from primr.utils.logging_config import get_logger
from primr.utils.observability import Metrics, emit_metrics, operation_context

logger = get_logger("core.orchestrator")

__all__ = [
    "OrchestratorResult",
    "ResearchConfig",
    "ResearchMode",
    "ResearchOrchestrator",
]


class ResearchOrchestrator:
    """
    Orchestrates research using multiple engines.

    The orchestrator provides a unified interface for running company
    research, abstracting away the differences between engines.

    Engines:
    - Structured: Traditional pipeline with scraping + AI extraction
    - Deep Research: Gemini Deep Research Agent for autonomous research
    - Hybrid: Combine both for comprehensive coverage (future)

    Example:
        orchestrator = ResearchOrchestrator()

        # Quick research with Deep Research
        result = await orchestrator.research(
            "Acme Corp",
            mode=ResearchMode.DEEP_RESEARCH
        )

        # Detailed research with structured pipeline
        result = await orchestrator.research(
            "Acme Corp",
            "https://acme.example",
            mode=ResearchMode.STRUCTURED
        )
    """

    def __init__(self):
        """Initialize the orchestrator."""
        self._deep_research_client: DeepResearchClient | None = None
        logger.debug("Research orchestrator initialized")

    @property
    def deep_research_client(self) -> DeepResearchClient:
        """Lazy-load the Deep Research client."""
        if self._deep_research_client is None:
            self._deep_research_client = DeepResearchClient()
        return self._deep_research_client

    async def research(
        self,
        company_name: str,
        website: str | None = None,
        mode: ResearchMode = ResearchMode.STRUCTURED,
        config: ResearchConfig | None = None,
        on_progress: Callable[[str], None] | None = None,
        context_files: list | None = None,
        folder_path: str | None = None,
    ) -> OrchestratorResult:
        """
        Execute company research using the specified mode.

        Args:
            company_name: Name of the company to research
            website: Optional company website URL
            mode: Research mode (structured, deep-research, hybrid)
            config: Optional configuration overrides
            on_progress: Optional callback for progress updates
            context_files: Optional list of files to upload as context for Deep Research
            folder_path: Optional run working folder for body-free stage_routes

        Returns:
            OrchestratorResult with section_results dict

        Raises:
            ResearchError: If research fails
        """
        config = config or ResearchConfig(mode=mode)
        # Prefer explicit kwarg; config.folder_path keeps research_agent under the line ceiling.
        route_folder = folder_path or config.folder_path
        start_time = asyncio.get_running_loop().time()

        with operation_context(
            "research", company=company_name, mode=mode.value, website=website or "none"
        ):
            logger.info(f"Starting {mode.value} research for {company_name}")

            try:
                if mode == ResearchMode.DEEP_RESEARCH:
                    result = await self._run_deep_research_with_context(
                        company_name,
                        website,
                        config,
                        on_progress,
                        context_files,
                        folder_path=route_folder,
                    )
                elif mode == ResearchMode.STRUCTURED:
                    result = await self._run_structured_research(
                        company_name, website, config, on_progress
                    )
                elif mode == ResearchMode.COMPLETE:
                    result = await self._run_complete_research(
                        company_name, website, config, on_progress, context_files
                    )
                elif mode == ResearchMode.HYBRID:
                    result = await self._run_hybrid_research(
                        company_name, website, config, on_progress
                    )
                else:
                    raise ResearchError(f"Unknown research mode: {mode}")

                result.duration_seconds = asyncio.get_running_loop().time() - start_time
                logger.info(f"Research completed in {result.duration_seconds:.0f}s")

                self._emit_research_metrics(
                    operation="research",
                    company_name=company_name,
                    mode=mode.value,
                    duration=result.duration_seconds,
                    success=True,
                    section_count=len(result.section_results),
                    citation_count=len(result.citations),
                )

                return result

            except Exception as e:
                duration = asyncio.get_running_loop().time() - start_time
                logger.error(f"Research failed: {e}", exc_info=True)

                self._emit_research_metrics(
                    operation="research",
                    company_name=company_name,
                    mode=mode.value,
                    duration=duration,
                    success=False,
                    error_type=type(e).__name__,
                )

                return OrchestratorResult(
                    company_name=company_name,
                    website=website,
                    mode=mode,
                    section_results={},
                    success=False,
                    error=str(e),
                    duration_seconds=duration,
                )

    def _emit_research_metrics(
        self,
        operation: str,
        company_name: str,
        mode: str,
        duration: float,
        success: bool,
        section_count: int = 0,
        citation_count: int = 0,
        error_type: str | None = None,
    ) -> None:
        """
        Emit structured metrics for research operations.

        Args:
            operation: Name of the operation
            company_name: Company being researched
            mode: Research mode used
            duration: Duration in seconds
            success: Whether operation succeeded
            section_count: Number of sections generated
            citation_count: Number of citations found
            error_type: Type of error if failed
        """
        metrics = Metrics(
            operation=operation,
            duration_seconds=duration,
            success=success,
            error_type=error_type,
            metadata={
                "company": company_name,
                "mode": mode,
                "sections": section_count,
                "citations": citation_count,
            },
        )
        emit_metrics(metrics)

    async def _run_deep_research(
        self,
        company_name: str,
        website: str | None,
        config: ResearchConfig,
        on_progress: Callable[[str], None] | None,
    ) -> OrchestratorResult:
        """Run research using Deep Research Agent."""

        def progress_callback(progress: ResearchProgress) -> None:
            if on_progress:
                msg = progress.message or progress.thought or "Processing..."
                on_progress(msg)

        priority_urls = [website] if website else None

        result = await self.deep_research_client.research(
            query=f"Research {company_name}" + (f" ({website})" if website else ""),
            output_format="company_profile",
            poll_interval=config.poll_interval,
            timeout=config.timeout,
            on_progress=progress_callback,
            priority_urls=priority_urls,
            job_metadata={
                "report_kind": "strategic_overview",
                "company_name": company_name,
            },
        )

        if not result.success:
            raise ResearchError(f"Deep research failed: {result.error}")

        section_results = self._normalize_deep_research_result(result)

        return OrchestratorResult(
            company_name=company_name,
            website=website,
            mode=ResearchMode.DEEP_RESEARCH,
            section_results=section_results,
            raw_content=result.content,
            citations=result.citations,
            success=True,
            search_queries_count=result.search_queries_count,
            pending_interaction_id=result.interaction_id,
        )

    async def _run_structured_research(
        self,
        company_name: str,
        website: str | None,
        config: ResearchConfig,
        on_progress: Callable[[str], None] | None,
    ) -> OrchestratorResult:
        """
        Run research using the structured pipeline.

        This delegates to the existing research_agent.py workflow.
        """
        # Import here to avoid circular imports
        from primr.core.research_agent import run_research

        # Note: run_research is synchronous, so we run it in executor
        # Pass the progress callback so updates display during execution
        loop = asyncio.get_running_loop()

        section_results = await loop.run_in_executor(
            None,
            lambda: run_research(
                company_name,
                website or "",
                on_progress=on_progress,
                fail_on_low_scrape=config.fail_on_low_scrape,
                folder_path=config.folder_path,
            ),
        )

        return OrchestratorResult(
            company_name=company_name,
            website=website,
            mode=ResearchMode.STRUCTURED,
            section_results=section_results or {},
            success=bool(section_results),
        )

    async def _run_complete_research(
        self,
        company_name: str,
        website: str | None,
        config: ResearchConfig,
        on_progress: Callable[[str], None] | None,
        context_files: list | None = None,
    ) -> OrchestratorResult:
        """
        Run complete research using the sequential Accordion architecture.

        This is the recommended mode for comprehensive reports:

        Phase 1: Structured Pipeline (Data Collection)
            - Full website scraping + web search
            - Creates baseline context (Stage 1)
            - ~15-25 minutes

        Phase 2: Dossier and Sequential Report Writing
            - One Deep Research dossier followed by continuity-aware sections
            - Uses Stage 1 context via File Search Store
            - Generates and assembles one cohesive report
            - ~15-30 minutes

        Sequential writing preserves cross-section context and avoids the quota
        pressure of the previous parallel-chapter approach.

        Args:
            company_name: Name of the company to research
            website: Optional company website URL
            config: Research configuration
            on_progress: Optional callback for progress updates
            context_files: Optional list of user-provided files (PDFs, docs)

        Returns:
            OrchestratorResult with comprehensive report
        """
        import time as time_module

        from primr.utils.console import console

        total_start = time_module.time()
        step1_context_file: str | None = None

        try:
            # ================================================================
            # PHASE 1: Data Collection (Structured Pipeline) - UNCHANGED
            # ================================================================
            phase1_start = time_module.time()
            console.phase_banner(
                step_num=1,
                total_steps=2,
                title="Data Collection",
                description="Website scraping + web search + AI analysis",
                expected_duration="15-25 minutes",
            )

            structured_result = await self._run_structured_research(
                company_name, website, config, on_progress
            )

            if not structured_result.success:
                if config.fail_on_low_scrape:
                    logger.error(
                        "Structured Pipeline failed and strict scrape validation is enabled"
                    )
                    console.error("Data collection failed scrape validation; aborting run.")
                    console.muted("  Override with --skip-scrape-validation to continue anyway")
                    return OrchestratorResult(
                        company_name=company_name,
                        website=website,
                        mode=ResearchMode.COMPLETE,
                        section_results={},
                        success=False,
                        error="Data collection failed scrape validation",
                        duration_seconds=time_module.time() - total_start,
                    )
                logger.warning("Structured Pipeline failed, continuing with limited context")
                console.warn("Data collection had issues, continuing with limited context...")
            else:
                phase1_duration = time_module.time() - phase1_start
                console.phase_complete(
                    "Data Collection",
                    stats=[
                        ("Sections generated", str(len(structured_result.section_results))),
                        ("Duration", f"{int(phase1_duration // 60)}m {int(phase1_duration % 60)}s"),
                    ],
                )

            # Prepare Stage 1 context for Deep Research
            stage1_context: str | None = None
            if structured_result.success and structured_result.section_results:
                try:
                    step1_context_file = self._prepare_step1_context(
                        company_name, structured_result.section_results
                    )
                    with open(step1_context_file, encoding="utf-8") as f:
                        stage1_context = f.read()
                    logger.info(f"Stage 1 context prepared: {len(stage1_context)} chars")
                except Exception as e:
                    logger.warning(f"Failed to prepare Stage 1 context: {e}", exc_info=True)
                    if on_progress:
                        on_progress("Warning: Could not prepare context, proceeding without it")

            # Supplemental evidence (e.g. hiring signals) rides into the same
            # stage-1 context - even when the structured phase failed, so the
            # Deep Research call still sees it.
            if config.supplemental_context:
                stage1_context = (
                    f"{stage1_context}\n\n{config.supplemental_context}"
                    if stage1_context
                    else config.supplemental_context
                )

            # ================================================================
            # PHASE 2: Comprehensive Deep Research (Sequential Elaboration)
            # ================================================================
            phase2_start = time_module.time()
            console.phase_banner(
                step_num=2,
                total_steps=2,
                title="Deep Research",
                description="Comprehensive report with sequential elaboration (~50-page target)",
                expected_duration="15-30 minutes",
            )

            orchestrator = get_deep_research_orchestrator()

            def progress_wrapper(msg: str) -> None:
                # Only call on_progress - avoid duplicate console output
                # The parent callback handles console display
                if on_progress:
                    on_progress(msg)

            deep_result = await orchestrator.generate_comprehensive_report(
                company_name=company_name,
                website_url=website,
                stage1_context=stage1_context,
                context_files=[str(path) for path in context_files] if context_files else None,
                on_progress=progress_wrapper,
                target_pages=50,
            )

            phase2_duration = time_module.time() - phase2_start

            if not deep_result.success:
                logger.error(f"Deep Research failed: {deep_result.error}")
                console.error(f"Deep Research failed: {deep_result.error}")

                # Suggest scrape mode if quota exhausted
                if deep_result.error and "quota" in deep_result.error.lower():
                    console.warn(
                        "Tip: Try --mode scrape to generate report without Deep Research API"
                    )

                return OrchestratorResult(
                    company_name=company_name,
                    website=website,
                    mode=ResearchMode.COMPLETE,
                    section_results=structured_result.section_results
                    if structured_result.success
                    else {},
                    success=False,
                    error=deep_result.error,
                    duration_seconds=time_module.time() - total_start,
                    raw_content=getattr(deep_result, "content", ""),
                    citations=getattr(deep_result, "citations", []),
                    pending_interaction_id=getattr(deep_result, "interaction_id", ""),
                    sections_written=getattr(deep_result, "sections_written", 0),
                    search_queries_count=getattr(deep_result, "search_queries_count", 0),
                    target_pages=getattr(deep_result, "target_pages", 0),
                    actual_pages=getattr(deep_result, "actual_pages", 0),
                    target_attained=getattr(deep_result, "target_attained", False),
                )

            formatter = ReportFormatter()
            formatted = formatter.format_report(
                raw_content=deep_result.content,
                company_name=company_name,
                citation_style="numbered",
            )

            console.phase_complete(
                "Deep Research",
                stats=[
                    ("Word count", f"~{formatted.word_count:,}"),
                    ("Chapters", str(len(formatted.chapters))),
                    ("API calls", str(deep_result.api_calls)),
                    ("Duration", f"{int(phase2_duration // 60)}m {int(phase2_duration % 60)}s"),
                ],
            )

            # ================================================================
            # CLEANUP & RETURN
            # ================================================================
            total_duration = time_module.time() - total_start

            section_results = {
                "strategic_overview": formatted.markdown,
                "table_of_contents": formatted.table_of_contents,
            }

            # Include structured pipeline results for backward compatibility
            if structured_result.success:
                for key, value in structured_result.section_results.items():
                    if key not in section_results:
                        section_results[key] = value

            logger.info(
                f"Complete research finished: {len(formatted.chapters)} chapters, "
                f"~{formatted.word_count} words, {total_duration:.0f}s total, "
                f"{deep_result.api_calls} API call(s)"
            )

            return OrchestratorResult(
                company_name=company_name,
                website=website,
                mode=ResearchMode.COMPLETE,
                section_results=section_results,
                raw_content=formatted.markdown,
                citations=deep_result.citations,
                success=True,
                duration_seconds=total_duration,
                search_queries_count=deep_result.search_queries_count,
                pending_interaction_id=deep_result.interaction_id,
                target_pages=getattr(deep_result, "target_pages", 0),
                actual_pages=getattr(deep_result, "actual_pages", 0),
                target_attained=getattr(deep_result, "target_attained", False),
            )

        except Exception as e:
            logger.error(f"Complete research failed: {e}", exc_info=True)

            # Preserve partial results from structured phase if available
            partial_results = {}
            try:
                if structured_result and structured_result.success:
                    partial_results = structured_result.section_results
            except NameError:
                pass  # structured_result not yet assigned

            return OrchestratorResult(
                company_name=company_name,
                website=website,
                mode=ResearchMode.COMPLETE,
                section_results=partial_results,
                success=False,
                error=str(e),
                duration_seconds=time_module.time() - total_start,
            )
        finally:
            if step1_context_file:
                try:
                    os.remove(step1_context_file)
                except Exception:
                    logger.debug(
                        "Failed to clean up temp file %s", step1_context_file, exc_info=True
                    )

    def _summarize_context(self, section_results: dict[str, str]) -> str:
        """
        Create a summary of the structured pipeline results for the architect.

        Args:
            section_results: Results from structured pipeline

        Returns:
            Summary string for chapter planning
        """
        if not section_results:
            return "No initial context available."

        summary_parts = []

        priority_sections = [
            "company_overview",
            "detailed_products_services",
            "target_audience",
            "competitive_position",
            "financial_overview",
            "industry_insights",
        ]

        for section in priority_sections:
            if section in section_results:
                content = section_results[section]
                if len(content) > 500:
                    content = content[:500] + "..."
                title = section.replace("_", " ").title()
                summary_parts.append(f"**{title}:**\n{content}")

        return "\n\n".join(summary_parts) if summary_parts else "Limited context available."

    # NOTE: _upload_to_file_search_store and _delete_file_search_store were removed
    # as dead code. File Search Store management is now handled by:
    # - DeepResearchClient._upload_context_files() for uploads
    # - DeepResearchClient._cleanup_file_store() for cleanup
    # - FileSearchStoreManager for the orchestrator patterns
    # All cleanup is done via try/finally blocks to prevent billing leaks.

    def _prepare_step1_context(self, company_name: str, section_results: dict[str, str]) -> str:
        """
        Convert Step 1 results to a markdown file for File Search upload.

        Args:
            company_name: Name of the company
            section_results: Dict of section key -> content

        Returns:
            Path to the temporary markdown file
        """
        import tempfile
        from datetime import datetime

        # Build markdown document
        lines = [
            f"# Initial Research Findings: {company_name}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "This document contains initial research findings from website scraping and web search.",
            "Use this as context for deeper strategic analysis.",
            "",
            "---",
            "",
        ]

        # Add each section
        for section_key, content in section_results.items():
            # Convert section key to readable title
            title = section_key.replace("_", " ").title()
            lines.extend([f"## {title}", "", content, "", "---", ""])

        # Write to temp file
        content = "\n".join(lines)

        # Create temp file with .txt extension (universally recognized MIME type)
        # NOTE: We must close the fd from mkstemp before opening the file by path
        fd, filepath = tempfile.mkstemp(
            suffix=".txt", prefix=f"{company_name.replace(' ', '_')}_step1_"
        )
        os.close(fd)  # Close the fd - we'll open by path

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.debug(f"Created Step 1 context file: {filepath}")
        return filepath

    async def _run_deep_research_with_context(
        self,
        company_name: str,
        website: str | None,
        config: ResearchConfig,
        on_progress: Callable[[str], None] | None,
        context_files: list | None = None,
        folder_path: str | None = None,
    ) -> OrchestratorResult:
        """Run Deep Research Accordion; implementation lives in the stage module."""
        from primr.core.premium_deep_research_stage import run_deep_research_with_context

        return await run_deep_research_with_context(
            company_name=company_name,
            website=website,
            config=config,
            on_progress=on_progress,
            context_files=context_files,
            folder_path=folder_path,
        )

    def _merge_research_results(
        self, step1_sections: dict[str, str], step2_sections: dict[str, str]
    ) -> dict[str, str]:
        """
        Merge Step 1 (ground truth) with Step 2 (strategic layer).

        Strategy:
        - Step 1 sections are preferred for factual company data
        - Step 2 sections are preferred for strategic analysis
        - Both are included where they don't overlap

        Args:
            step1_sections: Results from structured pipeline
            step2_sections: Results from deep research

        Returns:
            Merged section dictionary
        """
        merged = {}

        # Sections where Step 1 (ground truth) takes precedence
        step1_priority = {
            "company_overview",
            "company_website",
            "scraped_website_summary",
            "detailed_products_services",
            "primary_apps_sources_of_data",
            "company_history",
            "mission_vision",
            "unique_selling_proposition",
            "main_types_of_users",
            "target_audience",
        }

        # Sections where Step 2 (strategic layer) takes precedence
        step2_priority = {
            "competitive_position",
            "industry_insights",
            "strategic_recommendations",
            "financial_overview",
            "board_of_directors_concerns",
            "gap_analysis",
            "strategic_implications",
            "second_order_insights",
        }

        # Add all Step 1 sections
        for key, content in step1_sections.items():
            merged[key] = content

        # Add/override with Step 2 sections based on priority
        for key, content in step2_sections.items():
            if key in step2_priority:
                # Step 2 takes precedence for strategic sections
                merged[key] = content
            elif key not in merged:
                # Add new sections from Step 2
                merged[key] = content
            elif key not in step1_priority:
                # For non-priority sections, prefer Step 2 if longer/richer
                if len(content) > len(merged.get(key, "")):
                    merged[key] = content

        return merged

    async def _run_hybrid_research(
        self,
        company_name: str,
        website: str | None,
        config: ResearchConfig,
        on_progress: Callable[[str], None] | None,
    ) -> OrchestratorResult:
        """
        Run hybrid research combining both engines (parallel execution).

        Note: This is the legacy parallel mode. For sequential two-step
        research, use COMPLETE mode instead.

        Strategy:
        1. Run Deep Research for broad market/competitive analysis
        2. Run targeted scraping for specific website data
        3. Merge results, preferring website data for company-specific info
        """
        if on_progress:
            on_progress("Running hybrid research (Deep Research + Scraping)...")

        # Run both in parallel
        deep_task = self._run_deep_research(company_name, website, config, on_progress)
        structured_task = self._run_structured_research(company_name, website, config, on_progress)

        deep_result, structured_result = await asyncio.gather(
            deep_task, structured_task, return_exceptions=True
        )

        # Log exceptions from parallel tasks (they'd otherwise be silently swallowed)
        if isinstance(deep_result, Exception):
            logger.error("Deep research failed in hybrid mode: %s", deep_result)
        if isinstance(structured_result, Exception):
            logger.error("Structured research failed in hybrid mode: %s", structured_result)

        # Merge results
        section_results = {}

        # Start with deep research results
        if isinstance(deep_result, OrchestratorResult) and deep_result.success:
            section_results.update(deep_result.section_results)

        # Override with structured results for website-specific sections
        if isinstance(structured_result, OrchestratorResult) and structured_result.success:
            website_sections = [
                "company_website",
                "scraped_website_summary",
                "detailed_products_services",
                "primary_apps_sources_of_data",
            ]
            for section in website_sections:
                if section in structured_result.section_results:
                    section_results[section] = structured_result.section_results[section]

        pending_interaction_id = (
            deep_result.pending_interaction_id
            if isinstance(deep_result, OrchestratorResult) and deep_result.success
            else ""
        )
        return OrchestratorResult(
            company_name=company_name,
            website=website,
            mode=ResearchMode.HYBRID,
            section_results=section_results,
            success=bool(section_results),
            pending_interaction_id=pending_interaction_id,
        )

    def _normalize_deep_research_result(self, result: DeepResearchResult) -> dict[str, str]:
        """
        Normalize Deep Research output to section format.

        Maps the structured output from Deep Research to the
        section keys expected by the report generator.
        """
        content = result.content
        sections: dict[str, str] = {}

        # Parse the markdown sections
        current_section: str | None = None
        current_content: list[str] = []

        for line in content.split("\n"):
            # Check for section headers
            if line.startswith("## "):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                header = line[3:].strip().lower()
                current_section = self._map_header_to_section(header)
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        # Store raw content as overview if no sections parsed
        if not sections:
            sections["company_overview"] = content

        return sections

    def _map_header_to_section(self, header: str) -> str:
        """Map a markdown header to a section key."""
        header_lower = header.lower()

        mappings = {
            "executive summary": "company_overview",
            "company overview": "company_overview",
            "products & services": "detailed_products_services",
            "products and services": "detailed_products_services",
            "financial analysis": "financial_overview",
            "financial overview": "financial_overview",
            "competitive landscape": "competitive_position",
            "competition": "competitive_position",
            "industry analysis": "industry_insights",
            "industry": "industry_insights",
            "strategic assessment": "strategic_recommendations",
            "strategy": "strategic_recommendations",
            "recommendations": "strategic_recommendations",
            "history": "company_history",
            "company history": "company_history",
            "mission": "mission_vision",
            "mission and vision": "mission_vision",
            "leadership": "board_of_directors_concerns",
            "management": "board_of_directors_concerns",
            "target market": "target_audience",
            "customers": "main_types_of_users",
            "value proposition": "unique_selling_proposition",
        }

        for key, section in mappings.items():
            if key in header_lower:
                return section

        # Default to a generic key based on header
        return header_lower.replace(" ", "_").replace("&", "and")


# =============================================================================
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

import threading

_orchestrator: ResearchOrchestrator | None = None
_orchestrator_lock = threading.Lock()


def get_orchestrator() -> ResearchOrchestrator:
    """
    Get the global orchestrator instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety
    while minimizing lock contention.
    """
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            # Double-check after acquiring lock
            if _orchestrator is None:
                _orchestrator = ResearchOrchestrator()
    return _orchestrator


def reset_orchestrator() -> None:
    """Reset the global orchestrator (useful for testing)."""
    global _orchestrator
    with _orchestrator_lock:
        _orchestrator = None
