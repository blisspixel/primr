"""
Structured research pipeline for website-based company research.

This module implements the scrape-based research pipeline that:
1. Scrapes company website and external sources
2. Summarizes and analyzes content
3. Generates report sections using AI

Usage:
    from primr.core.structured_research import run_research, research_section

    # Run full structured research
    results = run_research("Acme Corp", "https://acme.example")

    # Research a single section
    content = research_section("Industry", context)
"""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from primr.ai.grading_agent import grade_report
from primr.ai.llm import llm
from primr.ai.summarize import summarize_scraped_content
from primr.config.config import (
    GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT,
    MAX_EXTERNAL_SEARCH_QUERIES,
    MAX_EXTERNAL_SOURCES,
)
from primr.config.prompts import generate_prompt
from primr.config.sections_config import SECTION_KEY_MAP
from primr.core.workspace import create_working_folder, save_section_output
from primr.data.scrape import fetch_web_content, scrape_external_sources_validated
from primr.data.search_utils import (
    generate_external_search_queries,
    generate_search_queries,
    search_web,
)
from primr.utils.logging_config import get_logger

logger = get_logger("structured_research")


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class ScrapedData:
    """Container for scraped content with metadata."""
    website_pages: dict[str, str] = field(default_factory=dict)
    external_sources: dict[str, str] = field(default_factory=dict)

    @property
    def all_content(self) -> dict[str, str]:
        return {**self.website_pages, **self.external_sources}

    @property
    def page_count(self) -> int:
        return len(self.website_pages)

    @property
    def source_count(self) -> int:
        return len(self.external_sources)


@dataclass
class AnalysisResult:
    """Result of content analysis phase."""
    summarized_content: str
    industry: str
    overview: str


@dataclass
class ResearchContext:
    """Immutable context passed through the pipeline."""
    company_name: str
    website: str | None
    folder_path: str
    industry: str
    overview: str
    summarized_insights: str


# =============================================================================
# PROTOCOLS
# =============================================================================

class ProgressReporter(Protocol):
    """Protocol for progress reporting, enabling custom UX."""

    def report(self, message: str) -> None:
        """Report a progress message."""
        ...

    def phase_start(self, phase: int, total: int, name: str) -> None:
        """Report start of a phase."""
        ...

    def phase_complete(self, name: str, stats: dict[str, str] | None = None) -> None:
        """Report completion of a phase."""
        ...


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================

def run_research(
    company_name: str,
    website: str,
    on_progress: Callable[[str], None] | None = None,
    reporter: ProgressReporter | None = None
) -> dict[str, str]:
    """
    Run structured research pipeline.

    Executes three phases:
    1. Data Collection: Scrape website and external sources
    2. Analysis: Summarize content and identify industry
    3. Section Generation: Build all report sections

    Args:
        company_name: Name of the company
        website: Company website URL
        on_progress: Optional callback for progress updates
        reporter: Optional progress reporter for detailed updates

    Returns:
        Dict mapping section_key to content
    """
    import time as time_module

    def progress(msg: str) -> None:
        """Send progress update via callback or reporter."""
        if on_progress:
            on_progress(msg)
        if reporter:
            reporter.report(msg)

    def format_time(seconds: float) -> str:
        """Format seconds into readable time string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        return f"{int(seconds//60)}m {int(seconds%60)}s"

    folder_path = create_working_folder(company_name, website)

    # Phase 1: Data Collection
    scraped = _collect_data(company_name, website, progress)
    progress(f"+ {scraped.page_count} pages, {scraped.source_count} external sources")

    # Phase 2: Analysis
    analysis = _analyze_content(company_name, website, scraped, folder_path, progress)
    progress(f"+ Industry: {analysis.industry}")

    # Phase 3: Section Generation
    context = ResearchContext(
        company_name=company_name,
        website=website,
        folder_path=folder_path,
        industry=analysis.industry,
        overview=analysis.overview,
        summarized_insights=analysis.summarized_content
    )

    sections_start = time_module.time()
    section_results = _generate_sections(context, progress)
    progress(f"+ Sections complete ({format_time(time_module.time() - sections_start)})")

    return section_results


def research_section(
    section_name: str,
    company_name: str,
    website: str | None,
    industry: str,
    folder_path: str,
    overview: str,
    summarized_insights: str
) -> str:
    """
    Research a single report section.

    Uses AI to generate section content based on context.
    Applies quality grading and refinement if needed.

    Args:
        section_name: Name of the section to research
        company_name: Name of the company
        website: Company website URL
        industry: Identified industry
        folder_path: Path to working folder
        overview: Company overview text
        summarized_insights: Summarized scraped content

    Returns:
        Generated section content
    """
    section_key = SECTION_KEY_MAP.get(section_name)

    if not section_key:
        return ""

    # Handle simple metadata sections
    if section_name in ["Company Name", "Website", "Industry"]:
        value = _get_metadata_value(section_name, company_name, website, industry)
        save_section_output(folder_path, section_key, value or "N/A")
        return value or "N/A"

    # Generate AI content for complex sections
    ai_response = _generate_section_content(
        section_name, section_key, company_name, website,
        industry, overview, summarized_insights
    )

    # Apply grading and refinement
    ai_response = _refine_section_if_needed(
        ai_response, section_name, company_name, website,
        overview, summarized_insights
    )

    # Ensure minimum content
    if not ai_response or len(ai_response.strip()) < 50:
        ai_response = f"No detailed {section_name} information available for {company_name}."

    save_section_output(folder_path, section_key, ai_response)
    return ai_response


@contextmanager
def research_pipeline(company_name: str, website: str) -> Iterator[ResearchContext]:
    """
    Context manager for research pipeline.

    Handles setup, cleanup, and error recovery.
    Yields ResearchContext for use in pipeline stages.

    Args:
        company_name: Name of the company
        website: Company website URL

    Yields:
        ResearchContext for pipeline operations
    """
    folder_path = create_working_folder(company_name, website)

    try:
        # Run initial phases to build context
        scraped = _collect_data(company_name, website, None)
        analysis = _analyze_content(company_name, website, scraped, folder_path, None)

        context = ResearchContext(
            company_name=company_name,
            website=website,
            folder_path=folder_path,
            industry=analysis.industry,
            overview=analysis.overview,
            summarized_insights=analysis.summarized_content
        )

        yield context

    except Exception as e:
        logger.exception(f"Research pipeline failed: {e}")
        raise


def generate_initial_overview(
    company_name: str,
    website: str | None,
    industry: str,
    folder_path: str
) -> str:
    """
    Generate initial company overview.

    Args:
        company_name: Name of the company
        website: Company website URL
        industry: Identified industry
        folder_path: Path to working folder

    Returns:
        Generated overview text
    """
    overview_prompt = generate_prompt(
        "initial_company_overview",
        company_name=company_name,
        company_website=website or "N/A",
        industry=industry,
        detailed_products_services="N/A",
        unique_selling_proposition="N/A",
        mission_vision="N/A",
        company_history="N/A",
        key_achievements="N/A",
        target_audience="N/A",
        financial_overview="N/A",
        business_drivers_and_kpis="N/A",
        business_outcomes="N/A",
        scraped_website_summary="N/A",
    )
    overview = llm(overview_prompt, model_type="report")

    import os
    overview_file = os.path.join(folder_path, f"{company_name}_Draft_Overview.txt")
    with open(overview_file, "w", encoding="utf-8") as f:
        f.write(overview)

    return overview


# =============================================================================
# INTERNAL PHASE FUNCTIONS
# =============================================================================

def _collect_data(
    company_name: str,
    website: str | None,
    progress: Callable[[str], None] | None = None
) -> ScrapedData:
    """
    Phase 1: Data Collection.

    Scrapes company website (up to 15 pages) and external sources.

    Args:
        company_name: Name of the company
        website: Company website URL
        progress: Optional progress callback

    Returns:
        ScrapedData container with all scraped content
    """
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    website_pages = {}
    if website:
        website_pages = fetch_web_content(website, company_name, max_pages=50)
        if len(website_pages) <= 2:
            report("! Limited website access - site may have bot protection")

    report("Generating search strategy...")
    external_queries = generate_external_search_queries(
        company_name,
        website,
        max_queries=MAX_EXTERNAL_SEARCH_QUERIES,
    )

    fallback_queries = [
        "news OR press release OR announcement",
        "funding OR acquisition OR partnership",
        "revenue OR earnings OR financial results OR investor relations",
    ]
    all_queries = list(external_queries)
    for fallback in fallback_queries:
        if len(all_queries) >= MAX_EXTERNAL_SEARCH_QUERIES:
            break
        if fallback not in all_queries:
            all_queries.append(fallback)

    external_data: dict[str, str] = {}
    max_external_sources = MAX_EXTERNAL_SOURCES

    for query in all_queries:
        if len(external_data) >= max_external_sources:
            break

        report(f"Searching: {company_name} {query[:40]}...")
        results = search_web(query, company_name, website)
        if results:
            filtered = [
                r for r in results[:5]
                if not website or website.lower() not in r.get("url", "").lower()
            ]
            remaining_slots = max_external_sources - len(external_data)
            scraped = scrape_external_sources_validated(
                filtered,
                company_name=company_name,
                website=website,
                max_sources=min(2, remaining_slots)
            )
            external_data.update(scraped)

    report(f"Found {len(external_data)} validated external sources")
    return ScrapedData(website_pages=website_pages, external_sources=external_data)


def _analyze_content(
    company_name: str,
    website: str | None,
    scraped: ScrapedData,
    folder_path: str,
    progress: Callable[[str], None] | None = None
) -> AnalysisResult:
    """
    Phase 2: Content Analysis.

    Summarizes scraped content, identifies industry,
    and generates initial company overview.

    Args:
        company_name: Name of the company
        website: Company website URL
        scraped: Scraped data from Phase 1
        folder_path: Path to working folder
        progress: Optional progress callback

    Returns:
        AnalysisResult with summarized content, industry, and overview
    """
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    # Summarize content
    report("Summarizing content...")
    summarized = summarize_scraped_content(
        company_name, website, scraped.all_content, folder_path
    )
    if not summarized.strip():
        summarized = "No insights extracted."
    report("+ Content summarized")

    # Industry identification
    report("Identifying industry...")
    industry_prompt = generate_prompt(
        "industry",
        company_name=company_name,
        company_website=website or "N/A",
        scraped_insights=summarized
    )
    industry = llm(industry_prompt, model_type="research").strip() or "Unknown"

    # Generate overview
    report("Generating overview...")
    overview = generate_initial_overview(company_name, website, industry, folder_path)
    report("+ Overview complete")

    return AnalysisResult(
        summarized_content=summarized,
        industry=industry,
        overview=overview
    )


def _generate_sections(
    context: ResearchContext,
    progress: Callable[[str], None] | None = None
) -> dict[str, str]:
    """
    Phase 3: Section Generation.

    Generates all report sections using AI.
    Applies quality grading and refinement.

    Args:
        context: Research context from previous phases
        progress: Optional progress callback

    Returns:
        Dict mapping section_key to content
    """
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    sections = [
        "Company Name", "Website", "Industry", "Detailed Products/Services",
        "Unique Selling Proposition (USP)", "Mission & Vision", "Company History",
        "Key Achievements", "Target Audience", "Financial Overview",
        "Potential Business Drivers & KPIs", "Industry Insights",
        "Potential Business Drivers", "Primary Apps or Sources of Data",
        "Main Types of Users", "Board of Directors Concerns",
        "Potential Business Value", "Strategic Recommendations"
    ]

    # Count non-trivial sections for progress
    analysis_sections = [s for s in sections if s not in ["Company Name", "Website", "Industry"]]
    total_analysis = len(analysis_sections)

    report(f"Analyzing {total_analysis} report sections...")
    section_results = {}
    analysis_idx = 0

    for section in sections:
        section_key = SECTION_KEY_MAP.get(section)
        if section_key:
            if section not in ["Company Name", "Website", "Industry"]:
                analysis_idx += 1
                report(f"  [{analysis_idx}/{total_analysis}] {section}")

            content = research_section(
                section, context.company_name, context.website,
                context.industry, context.folder_path,
                context.overview, context.summarized_insights
            )
            if content:
                section_results[section_key] = content

    return section_results


# =============================================================================
# INTERNAL HELPER FUNCTIONS
# =============================================================================

def _get_metadata_value(
    section_name: str,
    company_name: str,
    website: str | None,
    industry: str
) -> str:
    """Get value for simple metadata sections."""
    if section_name == "Company Name":
        return company_name
    elif section_name == "Website":
        return website or "N/A"
    elif section_name == "Industry":
        return industry
    return "N/A"


def _generate_section_content(
    section_name: str,
    section_key: str,
    company_name: str,
    website: str | None,
    industry: str,
    overview: str,
    summarized_insights: str
) -> str:
    """Generate AI content for a section."""
    prompt_data = {
        "company_name": company_name,
        "company_website": website or "N/A",
        "industry": industry or "N/A",
        "detailed_products_services": summarized_insights or "N/A",
        "unique_selling_proposition": "N/A",
        "mission_vision": "N/A",
        "company_history": "N/A",
        "key_achievements": "N/A",
        "target_audience": "N/A",
        "financial_overview": "N/A",
        "business_drivers_and_kpis": "N/A",
        "potential_business_outcomes": "N/A",
        "industry_insights": "N/A",
        "potential_business_drivers": "N/A",
        "primary_apps_sources_of_data": "N/A",
        "main_types_of_users": "N/A",
        "board_of_directors_concerns": "N/A",
        "potential_business_value": "N/A",
        "strategic_recommendations": "N/A",
        "scraped_website_summary": summarized_insights or "N/A",
        "value_theory": overview
    }

    try:
        ai_prompt = generate_prompt(section_key, **prompt_data)
    except KeyError:
        return ""

    ai_input = f"""
## Company: {company_name}
## Website: {website or "N/A"}
## Industry: {industry or "N/A"}
## Section: {section_name}

{ai_prompt}

## Context
{overview}

## Scraped Insights
{summarized_insights}
"""

    return llm(ai_input, model_type="report")


def _refine_section_if_needed(
    ai_response: str,
    section_name: str,
    company_name: str,
    website: str | None,
    overview: str,
    summarized_insights: str
) -> str:
    """Apply grading and refinement to section content."""
    try:
        score, needs_research, feedback = grade_report(
            ai_response, section_name, company_name, website,
            overview, summarized_insights
        )

        if needs_research and score < GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT:
            queries = generate_search_queries(
                company_name, website, section_name, ai_response
            )
            for query in queries[:2]:
                results = search_web(query, company_name, website)
                if results:
                    # Rebuild input with additional research
                    ai_input = f"""
## Company: {company_name}
## Website: {website or "N/A"}
## Section: {section_name}

{ai_response}

## Additional Research
{chr(10).join(f"- [{r.get('title', 'Source')}]({r.get('url', '')}): {r.get('snippet', '')}" for r in results[:5])}
"""
                    ai_response = llm(ai_input, model_type="report")
                    break
    except Exception as e:
        logger.warning(f"Grading/refinement failed for section '{section_name}': {e}")

    return ai_response
