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
        return OrchestratorResult(
            company_name=company_name,
            website=website,
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={},
            success=False,
            error=f"Deep research routing failed: {type(route_err).__name__}",
            duration_seconds=time.time() - start_time,
        )

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
        context_files=[str(path) for path in context_files] if context_files else None,
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
        raw_partial_content = getattr(deep_result, "content", "")
        partial_content = raw_partial_content if isinstance(raw_partial_content, str) else ""
        partial_sections = (
            {"strategic_overview_partial": partial_content} if partial_content else {}
        )
        return OrchestratorResult(
            company_name=company_name,
            website=website,
            mode=ResearchMode.DEEP_RESEARCH,
            section_results=partial_sections,
            raw_content=partial_content,
            citations=getattr(deep_result, "citations", []),
            success=False,
            error=deep_result.error,
            duration_seconds=total_duration,
            sections_written=getattr(deep_result, "sections_written", 0),
            search_queries_count=getattr(deep_result, "search_queries_count", 0),
            pending_interaction_id=getattr(deep_result, "interaction_id", ""),
            target_pages=getattr(deep_result, "target_pages", 0),
            actual_pages=getattr(deep_result, "actual_pages", 0),
            target_attained=getattr(deep_result, "target_attained", False),
        )

    target_pages = getattr(deep_result, "target_pages", 0)
    actual_pages = getattr(deep_result, "actual_pages", 0)
    target_attained = getattr(deep_result, "target_attained", False)
    if target_pages and not target_attained:
        message = (
            f"Accordion report produced approximately {actual_pages}/{target_pages} target pages; "
            "preserving the evidence-limited report"
        )
        logger.warning(message)
        if on_progress:
            on_progress(message)

    try:
        formatted = ReportFormatter().format_report(
            raw_content=deep_result.content, company_name=company_name, citation_style="numbered"
        )
        formatted_markdown = formatted.markdown
        formatted_word_count = formatted.word_count
        formatted_citations = formatted.citations
    except Exception as format_err:
        logger.warning("Deep research formatting failed; preserving raw report: %s", format_err)
        formatted_markdown = deep_result.content
        formatted_word_count = len(deep_result.content.split())
        formatted_citations = deep_result.citations
    section_results = {
        "strategic_overview": formatted_markdown,
    }

    logger.info(
        f"Deep research (Accordion) completed: ~{formatted_word_count} words, "
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
        raw_content=formatted_markdown,
        citations=formatted_citations,
        success=True,
        duration_seconds=total_duration,
        sections_written=deep_result.sections_written,
        search_queries_count=deep_result.search_queries_count,
        pending_interaction_id=deep_result.interaction_id,
        target_pages=target_pages,
        actual_pages=actual_pages,
        target_attained=target_attained,
    )
