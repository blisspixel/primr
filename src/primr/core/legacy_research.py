"""Canonical legacy section pipeline, independent of the public research facade.

The facade injects its compatibility callbacks; the orchestrator uses the same
implementation with leaf-owned defaults. Scrape and shipping policy is retained.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from primr.ai.grading_agent import grade_report
from primr.ai.llm import llm
from primr.ai.summarize import summarize_scraped_content
from primr.config.config import (
    GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT,
    MAX_EXTERNAL_SEARCH_QUERIES,
    MAX_EXTERNAL_SOURCES,
    MIN_SCRAPED_CHARS,
    MIN_SCRAPED_PAGES,
)
from primr.config.prompts import get_prompt_template, get_registry
from primr.config.sections_config import SECTION_KEY_MAP
from primr.core.workspace import create_working_folder, save_section_output
from primr.data.scrape import fetch_web_content
from primr.data.search_utils import (
    generate_external_search_queries,
    generate_search_queries,
    search_web,
)
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.url_helpers import web_url_is_external

logger = get_logger(__name__)


def _prompt_templates() -> dict[str, str]:
    return {name: get_prompt_template(name).template for name in get_registry().list_prompts()}


def generate_prompt(template_name: str, **kwargs: Any) -> str:
    templates = _prompt_templates()
    if template_name not in templates:
        raise ValueError(f"Prompt '{template_name}' not found")
    return templates[template_name].format(**kwargs)


class Prompt(Protocol):
    def __call__(self, template_name: str, **kwargs: Any) -> str:
        """Render the named legacy template with its supplied variables."""


class ModelCall(Protocol):
    def __call__(self, prompt: str, model_type: str = "fast") -> str:
        """Generate text with the explicitly selected model role."""


class Fetch(Protocol):
    def __call__(
        self,
        website: str,
        company_name: str | None,
        max_pages: int | None = None,
        use_vision: bool = False,
        working_folder: str | None = None,
    ) -> dict[str, str]:
        """Collect website text through the existing guarded scraper."""


class ExternalQueries(Protocol):
    def __call__(self, company_name: str, website: str, max_queries: int) -> list[str]:
        """Build the bounded company-specific external search plan."""


class SaveSection(Protocol):
    def __call__(self, folder_path: str, section_key: str, content: str) -> object:
        """Persist one section in its explicitly owned working folder."""


class ScrapeQuality(Protocol):
    def __call__(self, corpus: dict[str, str]) -> tuple[bool, str]:
        """Return the existing scrape-quality decision and explanation."""


def _validate_scrape_quality(
    corpus: dict[str, str],
    *,
    min_pages: int = MIN_SCRAPED_PAGES,
    min_chars: int = MIN_SCRAPED_CHARS,
) -> tuple[bool, str]:
    """Check whether scraped website content is sufficient for reliable analysis."""
    pages = len(corpus)
    chars = sum(len(c or "") for c in corpus.values())
    ok = pages >= min_pages and chars >= min_chars
    reason = (
        f"Scrape quality too low ({pages} pages, {chars:,} chars; "
        f"requires >= {min_pages} pages and >= {min_chars:,} chars)"
    )
    return ok, reason


@dataclass(frozen=True)
class LegacyServices:
    prompt: Prompt = generate_prompt
    model: ModelCall = llm
    fetch: Fetch = fetch_web_content
    summarize: Callable[[str, str, dict[str, str], str], str] = summarize_scraped_content
    external_queries: ExternalQueries = generate_external_search_queries
    queries: Callable[[str, str | None, str, str], list[str]] = generate_search_queries
    search: Callable[[str, str, str | None], list[dict[str, str]]] = search_web
    grade: Callable[[str, str, str, str | None, str, str], tuple[float | None, bool, str]] = (
        grade_report
    )
    save: SaveSection = save_section_output
    folder: Callable[[str, str], str] = create_working_folder
    validate: ScrapeQuality = _validate_scrape_quality
    prompts: Mapping[str, str] = field(default_factory=_prompt_templates)


Overview = Callable[[str, str | None, str, str], str]
Section = Callable[[str, str, str | None, str, str, str, str], str | None]


def generate_initial_overview(
    company_name: str,
    website: str | None,
    industry: str,
    folder_path: str,
    *,
    services: LegacyServices | None = None,
) -> str:
    services = services or LegacyServices()
    overview_prompt = services.prompt(
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
    overview = services.model(overview_prompt, model_type="report")

    overview_file = os.path.join(folder_path, f"{company_name}_Draft_Overview.txt")
    with open(overview_file, "w", encoding="utf-8") as f:
        f.write(overview)

    return overview


def research_section(
    section_name: str,
    company_name: str,
    website: str | None,
    industry: str,
    folder_path: str,
    overview: str,
    summarized_insights: str,
    *,
    services: LegacyServices | None = None,
) -> str | None:
    services = services or LegacyServices()
    section_key = SECTION_KEY_MAP.get(section_name)

    if not section_key or section_key not in services.prompts:
        return ""

    if section_name in ["Company Name", "Website", "Industry"]:
        value = (
            company_name
            if section_name == "Company Name"
            else website
            if section_name == "Website"
            else industry
        )
        services.save(folder_path, section_key, value or "N/A")
        return value

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
        "value_theory": overview,
    }

    try:
        ai_prompt = services.prompt(section_key, **prompt_data)
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

    ai_response = services.model(ai_input, model_type="report")

    if section_name not in ["Company Name", "Website", "Industry"]:
        try:
            score, needs_research, feedback = services.grade(
                ai_response, section_name, company_name, website, overview, summarized_insights
            )

            if (
                needs_research
                and score is not None
                and score < GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT
            ):
                queries = services.queries(company_name, website, section_name, ai_response)
                for query in queries[:2]:
                    results = services.search(query, company_name, website)
                    if results:
                        formatted = "\n".join(
                            f"- [{r.get('title', 'Source')}]({r.get('url', '')}): {r.get('snippet', '')}"
                            for r in results[:5]
                        )
                        ai_input += f"\n\n## Additional Research\n{formatted}"
                        ai_response = services.model(ai_input, model_type="report")
                        break
        except Exception as e:
            logger.warning(f"Grading/refinement failed for section '{section_name}': {e}")

    if not ai_response or len(ai_response.strip()) < 50:
        ai_response = f"No detailed {section_name} information available for {company_name}."

    services.save(folder_path, section_key, ai_response)
    return ai_response


def run_research(
    company_name: str,
    website: str,
    on_progress: Callable[[str], None] | None = None,
    fail_on_low_scrape: bool = True,
    folder_path: str | None = None,
    *,
    services: LegacyServices | None = None,
    overview_fn: Overview | None = None,
    section_fn: Section | None = None,
) -> dict[str, str] | None:
    """
    Run structured research and return section results.

    This is the entry point used by ResearchOrchestrator for structured mode.

    Args:
        company_name: Name of the company
        website: Company website URL
        on_progress: Optional callback for progress updates (message: str)

    Returns:
        Dict mapping section_key to content, or None if scraping/quality
        gates fail before any sections are produced.
    """
    services = services or LegacyServices()
    import time as time_module

    def progress(msg: str) -> None:
        """Send progress update via callback or console."""
        if on_progress:
            on_progress(msg)
        else:
            console.info(msg)

    def format_time(seconds: float) -> str:
        """Format seconds into readable time string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"

    folder_path = folder_path or services.folder(company_name, website)
    progress(f"> Working folder: {folder_path}")

    # Scrape website - saves raw scrapes incrementally to _raw_scrapes folder
    # fetch_web_content already shows completion message, no need to duplicate
    scraped_data = (
        services.fetch(website, company_name, max_pages=50, working_folder=folder_path)
        if website
        else {}
    )

    # Abort if website was provided but nothing could be scraped
    if website and not scraped_data:
        console.fail("Could not scrape any pages from the website - site may be blocking")
        console.muted("  The site may be rate-limiting after a recent scrape.")
        console.muted('  Try: primr "Company" url --mode deep  (skips site scraping)')
        return None

    if website and fail_on_low_scrape:
        quality_ok, quality_reason = services.validate(scraped_data)
        if not quality_ok:
            console.fail(quality_reason)
            console.muted("  Re-run with --skip-scrape-validation to continue anyway")
            return None

    # External research - with LLM validation to ensure correct company
    # This prevents including content from similarly-named but unrelated companies
    # (e.g., a SaaS vendor and an unrelated services firm that share the same trade name)
    progress("Searching for external sources...")

    external_data: dict[str, str] = {}
    total_search_results = 0
    if website:
        from primr.data.scrape import scrape_external_sources_validated
        from primr.data.search_utils import search_web

        # Generate targeted search queries using LLM
        progress("Generating search strategy...")
        external_queries = services.external_queries(
            company_name,
            website,
            max_queries=MAX_EXTERNAL_SEARCH_QUERIES,
        )

        # Keep hardcoded queries as reliable fallbacks at the end
        fallback_queries = [
            "news OR press release OR announcement",
            "funding OR acquisition OR partnership",
        ]
        all_queries = list(external_queries)
        for fallback in fallback_queries:
            if len(all_queries) >= MAX_EXTERNAL_SEARCH_QUERIES:
                break
            if fallback not in all_queries:
                all_queries.append(fallback)

        max_external_sources = MAX_EXTERNAL_SOURCES

        for query in all_queries:
            if len(external_data) >= max_external_sources:
                break

            results = search_web(query, company_name, website)
            if results:
                total_search_results += len(results)
                progress(f"  Found {len(results)} results for '{query[:40]}...'")
                filtered = [
                    r for r in results[:5] if web_url_is_external(r.get("url", ""), website)
                ]
                remaining_slots = max_external_sources - len(external_data)
                progress(f"  Validating {len(filtered)} external articles...")
                scraped = scrape_external_sources_validated(
                    filtered,
                    company_name=company_name,
                    website=website,
                    max_sources=min(2, remaining_slots),
                    working_folder=folder_path,
                )
                external_data.update(scraped)

    progress(
        f"+ {len(external_data)} external sources validated (from {total_search_results} search results)"
    )

    all_scraped = {**scraped_data, **external_data}
    from primr.output.working_brief import emit_after_structured_scrape as _emit_wb

    _emit_wb(company_name, website, folder_path, scraped_data, external_data, progress)

    try:
        from primr.core.collection_coverage import record_run_collection

        record_run_collection(folder_path, website, all_scraped)
    except (OSError, ValueError) as exc:
        logger.warning("Collection inventory could not be recorded: %s", exc)

    # Save raw scraped URLs to working folder for debugging
    urls_file = os.path.join(folder_path, "_scraped_urls.txt")
    with open(urls_file, "w", encoding="utf-8") as f:
        f.write(f"# Scraped URLs for {company_name}\n")
        f.write(f"# Website: {website}\n")
        f.write(f"# Total: {len(all_scraped)} pages\n\n")
        f.write("## Website Pages:\n")
        for url in scraped_data:
            f.write(f"  {url}\n")
        f.write(f"\n## External Sources ({len(external_data)}):\n")
        for url in external_data:
            f.write(f"  {url}\n")

    # Summarize content
    progress("Summarizing content...")
    summarized = services.summarize(company_name, website, all_scraped, folder_path)
    if not summarized.strip():
        summarized = "No insights extracted."
    progress("+ Content summarized")

    # Industry identification
    progress("Identifying industry...")
    industry_prompt = services.prompt(
        "industry",
        company_name=company_name,
        company_website=website or "N/A",
        scraped_insights=summarized,
    )
    industry = services.model(industry_prompt, model_type="research").strip() or "Unknown"
    progress(f"+ Industry: {industry}")

    # Overview
    progress("Generating overview...")
    overview = (
        overview_fn or (lambda c, w, i, f: generate_initial_overview(c, w, i, f, services=services))
    )(company_name, website, industry, folder_path)
    progress("+ Overview complete")

    # Research all sections
    sections = [
        "Company Name",
        "Website",
        "Industry",
        "Detailed Products/Services",
        "Unique Selling Proposition (USP)",
        "Mission & Vision",
        "Company History",
        "Key Achievements",
        "Target Audience",
        "Financial Overview",
        "Potential Business Drivers & KPIs",
        "Industry Insights",
        "Potential Business Drivers",
        "Primary Apps or Sources of Data",
        "Main Types of Users",
        "Board of Directors Concerns",
        "Potential Business Value",
        "Strategic Recommendations",
    ]

    # Count non-trivial sections for progress
    analysis_sections = [s for s in sections if s not in ["Company Name", "Website", "Industry"]]
    total_analysis = len(analysis_sections)

    sections_start = time_module.time()
    progress(f"Analyzing {total_analysis} report sections...")
    section_results = {}
    analysis_idx = 0

    for section in sections:
        section_key = SECTION_KEY_MAP.get(section)
        if section_key:
            # Show progress for non-trivial sections (clean format, no timing per step)
            if section not in ["Company Name", "Website", "Industry"]:
                analysis_idx += 1
                progress(f"  [{analysis_idx}/{total_analysis}] {section}")

            content = (
                section_fn
                or (
                    lambda n, c, w, i, f, o, summary: research_section(
                        n, c, w, i, f, o, summary, services=services
                    )
                )
            )(section, company_name, website, industry, folder_path, overview, summarized)
            if content:
                section_results[section_key] = content

    # Final timing for sections
    progress(
        f"+ {total_analysis} sections complete ({format_time(time_module.time() - sections_start)})"
    )

    console.progress_done()
    return section_results
