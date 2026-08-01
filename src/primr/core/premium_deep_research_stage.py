"""Premium deep-research Accordion stage with capability-router gating.

Extracted from ``ResearchOrchestrator._run_deep_research_with_context`` so the
orchestrator stays under the architecture file-size ceiling while the stage
owns routing, fail-closed agent/local behavior, and body-free route records.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from primr.ai import stage_routing
from primr.ai.deep_research import ReportFormatter, get_deep_research_orchestrator
from primr.core.research_types import OrchestratorResult, ResearchConfig, ResearchMode
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured

logger = get_logger("core.premium_deep_research_stage")


async def run_deep_research_with_context(
    *,
    company_name: str,
    website: str | None,
    config: ResearchConfig,
    on_progress: Callable[[str], None] | None,
    context_files: list | None = None,
    folder_path: str | None = None,
) -> OrchestratorResult:
    """Run Deep Research Accordion with capability-router gating.

    Model selection is resolved through the capability router for
    ``premium.deep_research``. Agent/local profiles without a deep-research
    backend fail closed without launching the Gemini agent.
    """
    del context_files  # reserved for future File Search Store handoff

    start_time = time.time()
    route = None
    try:
        route = stage_routing.resolve_stage_model(
            "premium.deep_research",
            legacy_model_type="reasoning",
        )
        log_structured("info", "Premium deep research route selected", **route.log_metadata())
        if getattr(route, "execution_mode", "llm") == "unavailable":
            failure = stage_routing.stage_route_failure_class(route)
            stage_routing.record_stage_route_usage(
                folder_path,
                route,
                outcome="fallback",
                input_items=1,
                output_items=0,
                duration_seconds=time.time() - start_time,
                failure_class=failure,
            )
            error = f"Deep research unavailable: {failure}"
            logger.warning(error)
            return OrchestratorResult(
                company_name=company_name,
                website=website,
                mode=ResearchMode.DEEP_RESEARCH,
                section_results={},
                success=False,
                error=error,
                duration_seconds=time.time() - start_time,
            )
    except Exception as route_err:
        logger.warning("Premium deep research route resolution failed: %s", route_err)

    if on_progress:
        on_progress("Using Accordion Method for comprehensive report...")
        on_progress("  Phase 1: Deep Research gathers facts")
        on_progress("  Phase 2: Section-by-section writing with Gemini Flash")
        if route is not None and route.backend_id:
            on_progress(f"  Backend: {route.backend_id}")

    orchestrator = get_deep_research_orchestrator()

    def progress_wrapper(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    deep_result = await orchestrator.generate_comprehensive_report(
        company_name=company_name,
        website_url=website,
        stage1_context=config.supplemental_context or None,
        on_progress=progress_wrapper,
        target_pages=30,
    )

    total_duration = time.time() - start_time

    if not deep_result.success:
        logger.warning(f"Deep research failed: {deep_result.error}")
        if route is not None:
            stage_routing.record_stage_route_usage(
                folder_path,
                route,
                outcome="fallback",
                input_items=1,
                output_items=0,
                duration_seconds=total_duration,
                failure_class="deep_research_failed",
            )
        return OrchestratorResult(
            company_name=company_name,
            website=website,
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={},
            success=False,
            error=deep_result.error,
            duration_seconds=total_duration,
        )

    formatter = ReportFormatter()
    formatted = formatter.format_report(
        raw_content=deep_result.content, company_name=company_name, citation_style="numbered"
    )
    section_results = {
        "strategic_overview": formatted.markdown,
    }

    logger.info(
        f"Deep research (Accordion) completed: ~{formatted.word_count} words, "
        f"{deep_result.api_calls} API calls, {total_duration:.0f}s"
    )
    if route is not None:
        stage_routing.record_stage_route_usage(
            folder_path,
            route,
            outcome="selected",
            input_items=1,
            output_items=deep_result.sections_written or 1,
            duration_seconds=total_duration,
        )

    return OrchestratorResult(
        company_name=company_name,
        website=website,
        mode=ResearchMode.DEEP_RESEARCH,
        section_results=section_results,
        raw_content=formatted.markdown,
        citations=formatted.citations,
        success=True,
        duration_seconds=total_duration,
        sections_written=deep_result.sections_written,
        search_queries_count=deep_result.search_queries_count,
        pending_interaction_id=deep_result.interaction_id,
    )
