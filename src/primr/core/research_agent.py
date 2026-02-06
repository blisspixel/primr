"""
Automated Company Research Agent - Orchestration Hub

This module serves as the main entry point and orchestration hub for company research.
It delegates to specialized modules for specific functionality:

- workspace: Working folder management, file consolidation
- structured_research: Website scraping and section generation
- vendor_research: Cloud vendor AI capabilities research
- ai_strategy: AI strategy generation
- deep_research_runner: Deep Research execution
- cli: Command-line interface

For backward compatibility, this module re-exports key functions from the specialized modules.

Usage:
    from primr.core.research_agent import perform_research, main

    # Run research programmatically
    result = perform_research("Tesla", "https://tesla.com")

    # Run CLI
    main()
"""
# Suppress RuntimeWarning FIRST - before any other imports
import warnings

warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)

# =============================================================================
# BACKWARD COMPATIBLE RE-EXPORTS
# =============================================================================
# These imports ensure existing code that imports from research_agent.py continues to work.
# New code should import directly from the specialized modules.

# From workspace module

# From structured_research module

# From cli module
# From ai_strategy module
from primr.core.ai_strategy import (
    CloudVendor,
)
from primr.core.cli import (
    main as _main_new,
)

# From deep_research_runner module
from primr.core.deep_research_runner import (
    DeepResearchConfig,
    DeepResearchMode,
)

# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # Re-exported types
    "CloudVendor",
    "DeepResearchConfig",
    "DeepResearchMode",
    "consolidate_working_folder",
    # Workspace management
    "create_working_folder",
    "ensure_valid_url",
    "generate_initial_overview",
    "get_user_input",
    "main",
    # Main entry points
    "perform_research",
    # Utility
    "process_csv",
    "research_section",
    "run_doctor",
    # Structured research
    "run_research",
    "save_section_output",
    "validate_context_files",
]

import asyncio
import atexit
import gc
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from primr.ai.grading_agent import grade_report
from primr.ai.llm import llm
from primr.ai.summarize import summarize_scraped_content
from primr.config.config import (
    GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT,
    LOGS_DIR,
    OUTPUT_DIR,
    PROJECT_ROOT,
    WORKING_DIR,
)
from primr.config.models import PrimrModels
from primr.config.sections_config import SECTION_KEY_MAP
from primr.core.research_orchestrator import (
    ResearchMode,
    get_orchestrator,
)
from primr.data.scrape import fetch_web_content, scrape_external_sources_validated
from primr.data.search_utils import generate_search_queries, search_google
from primr.output.output_utils import generate_final_report
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import (
    JobSummary,
    correlation_scope,
    log_job_summary,
    log_structured,
)

load_dotenv()

logger = get_logger("research_agent")

# Setup directories
for directory in [OUTPUT_DIR, WORKING_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Load prompts from package config directory
PROMPTS_FILE = Path(__file__).parent.parent / "config" / "prompts.json"
with open(PROMPTS_FILE, encoding="utf-8") as f:
    PROMPTS = json.load(f)


def generate_prompt(template_name, **kwargs):
    if template_name not in PROMPTS:
        raise ValueError(f"Prompt '{template_name}' not found")
    return PROMPTS[template_name].format(**kwargs)


# User-friendly tier names for display
TIER_DISPLAY_NAMES = {
    "requests": "HTTP",
    "httpx": "HTTP/2",
    "curl_cffi": "stealth HTTP",
    "playwright": "browser",
    "playwright_aggressive": "browser+",
    "drissionpage": "headless",
    "drissionpage_stealth": "stealth browser",
    "vision": "AI vision",
    "cache": "cache",
}


def format_tier_stats(tier_stats: dict) -> str:
    """Format tier stats for user-friendly display."""
    # Sort by count descending
    sorted_tiers = sorted(tier_stats.items(), key=lambda x: -x[1])
    parts = []
    for tier, count in sorted_tiers:
        display_name = TIER_DISPLAY_NAMES.get(tier, tier)
        parts.append(f"{count} {display_name}")
    return ", ".join(parts)


def select_links_with_llm(
    links: list,
    company_name: str,
    website: str,
    max_links: int = 50,
) -> list[str]:
    """
    Use LLM to intelligently select the most valuable links for research.

    The LLM acts like a business analyst deciding which pages to read to understand
    a company - prioritizing pages about leadership, strategy, products,
    financials, and recent news.

    Args:
        links: List of DiscoveredLink objects (pre-scored heuristically)
        company_name: Company name for context
        website: Company website URL
        max_links: Maximum links to return (passed to LLM so it knows the constraint)

    Returns:
        List of URLs selected by the LLM
    """
    if not links:
        return []

    # If we have fewer links than max, just return all of them
    if len(links) <= max_links:
        return [link.url for link in links]

    # Format links for the prompt - include URL and anchor text if available
    link_list = []
    for link in links[:200]:  # Cap at 200 to avoid token limits
        if hasattr(link, 'anchor_text') and link.anchor_text:
            link_list.append(f"{link.url} ({link.anchor_text})")
        else:
            link_list.append(link.url)

    links_text = "\n".join(link_list)

    try:
        prompt = generate_prompt(
            "filter_links_for_research",
            company_name=company_name,
            website=website,
            links=links_text,
            max_links=max_links,  # Pass limit to prompt so LLM knows the constraint
        )

        # Use link_selection model type (Flash - cheap and fast)
        response = llm(prompt, model_type="link_selection")

        # Parse response - expect one URL per line
        selected_urls = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if line and line.startswith("http"):
                selected_urls.append(line)

        # If LLM returned valid URLs, use them (LLM already knows the limit)
        if selected_urls:
            logger.info(f"LLM selected {len(selected_urls)} links from {len(links)}")
            return selected_urls

    except Exception as e:
        logger.warning(f"LLM link selection failed: {e}, falling back to heuristic scoring")

    # Fallback to heuristic scoring if LLM fails
    return [link.url for link in links[:max_links]]


def create_working_folder(company_name, website):
    """
    Create working folder for research artifacts with timestamped run ID.

    Each run gets its own subfolder like: working/Company_Name/2026-01-09_0915/
    This prevents mixing old and new data from different runs.
    """
    from datetime import datetime

    if not company_name and website:
        parsed_url = urlparse(website)
        company_name = parsed_url.netloc.replace("www.", "").replace(".", "_")

    folder_name = company_name.replace(" ", "_") if company_name else "Unknown_Company"

    # Create timestamped run folder: Company_Name/2026-01-09_0915
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M")
    folder_path = os.path.join(WORKING_DIR, folder_name, run_id)

    os.makedirs(folder_path, exist_ok=True)
    logger.info(f"Created working folder: {folder_path}")
    return folder_path


def ensure_valid_url(website):
    if not website:
        return None
    website = website.strip()
    if website.startswith(("http://", "https://")):
        return website
    if website.startswith("www."):
        return f"https://{website}"
    return f"https://{website}"


def get_user_input():
    console.banner("Company Research")
    console.blank()

    company_name = input("  Company name: ").strip()
    website = input("  Website URL:  ").strip()

    if not company_name and not website:
        console.error("Need either company name or website")
        sys.exit(1)

    return company_name, ensure_valid_url(website) if website else None


def save_section_output(folder_path, section_key, content):
    """Save section content to file."""
    filepath = os.path.join(folder_path, f"{section_key}.txt")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        logger.error(f"Failed to save section {section_key}: {e}")


def consolidate_working_folder(folder_path: str) -> str:
    """
    Consolidate all .txt files from a working folder into a single context file.

    Args:
        folder_path: Path to working folder (e.g., working/Parts_Town)

    Returns:
        Path to the consolidated temporary file
    """
    import glob
    import tempfile

    if not os.path.isdir(folder_path):
        raise ValueError(f"Working folder not found: {folder_path}")

    # Find all .txt files
    txt_files = glob.glob(os.path.join(folder_path, "*.txt"))
    if not txt_files:
        raise ValueError(f"No .txt files found in {folder_path}")

    # Extract company name from folder
    company_name = os.path.basename(folder_path).replace("_", " ")

    # Build consolidated document
    lines = [
        f"# Research Context: {company_name}",
        f"Source: {folder_path}",
        "",
        "This document contains research findings from the Structured Pipeline.",
        "",
        "---",
        ""
    ]

    # Read each file and add to document
    for txt_file in sorted(txt_files):
        filename = os.path.basename(txt_file)
        section_name = filename.replace(".txt", "").replace("_", " ").title()

        try:
            with open(txt_file, encoding="utf-8") as f:
                content = f.read().strip()

            if content:
                lines.extend([
                    f"## {section_name}",
                    "",
                    content,
                    "",
                    "---",
                    ""
                ])
        except Exception as e:
            logger.warning(f"Failed to read {txt_file}: {e}")

    # Write to temp file
    # NOTE: We must close the fd from mkstemp before opening the file by path
    content = '\n'.join(lines)
    fd, filepath = tempfile.mkstemp(
        suffix='.txt',
        prefix=f'{company_name.replace(" ", "_")}_context_'
    )
    os.close(fd)  # Close the fd - we'll open by path

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Consolidated {len(txt_files)} files into {filepath}")
    return filepath


# Supported file types for Deep Research File Search
SUPPORTED_CONTEXT_EXTENSIONS = {'.txt', '.pdf', '.md', '.json', '.csv'}


def validate_context_files(file_paths: list) -> tuple:
    """
    Validate context files for Deep Research upload.

    Args:
        file_paths: List of file paths to validate

    Returns:
        Tuple of (valid_files, invalid_files, warnings)
    """
    valid_files = []
    invalid_files = []
    warnings = []

    for file_path in file_paths:
        if not os.path.exists(file_path):
            invalid_files.append((file_path, "File not found"))
            continue

        ext = os.path.splitext(file_path)[1].lower()

        if ext in SUPPORTED_CONTEXT_EXTENSIONS:
            valid_files.append(file_path)
        elif ext in {'.docx', '.doc'}:
            # Word docs - suggest converting to PDF
            invalid_files.append((file_path, "Word docs not directly supported. Convert to PDF or use the .txt output"))
            warnings.append("Tip: Use the _Company_Overview.txt file from output/ instead of .docx")
        elif ext in {'.xlsx', '.xls'}:
            invalid_files.append((file_path, "Excel files not supported. Export to CSV"))
        else:
            invalid_files.append((file_path, f"Unsupported file type: {ext}"))

    return valid_files, invalid_files, warnings


def generate_initial_overview(company_name, website, industry, folder_path):
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

    overview_file = os.path.join(folder_path, f"{company_name}_Draft_Overview.txt")
    with open(overview_file, "w", encoding="utf-8") as f:
        f.write(overview)

    return overview


def research_section(section_name, company_name, website, industry, folder_path, overview, summarized_insights):
    section_key = SECTION_KEY_MAP.get(section_name)

    if not section_key or section_key not in PROMPTS:
        return ""

    if section_name in ["Company Name", "Website", "Industry"]:
        value = company_name if section_name == "Company Name" else website if section_name == "Website" else industry
        save_section_output(folder_path, section_key, value or "N/A")
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

    ai_response = llm(ai_input, model_type="report")

    if section_name not in ["Company Name", "Website", "Industry"]:
        try:
            score, needs_research, feedback = grade_report(
                ai_response, section_name, company_name, website, overview, summarized_insights
            )

            if needs_research and score < GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT:
                queries = generate_search_queries(company_name, website, section_name, ai_response)
                for query in queries[:2]:
                    results = search_google(query, company_name, website)
                    if results:
                        ai_input += f"\n\n## Additional Research\n{results}"
                        ai_response = llm(ai_input, model_type="report")
                        break
        except Exception as e:
            logger.warning(f"Grading/refinement failed for section '{section_name}': {e}")

    if not ai_response or len(ai_response.strip()) < 50:
        ai_response = f"No detailed {section_name} information available for {company_name}."

    save_section_output(folder_path, section_key, ai_response)
    return ai_response


def run_research(company_name: str, website: str, on_progress: Callable[[str], None] | None = None) -> dict:
    """
    Run structured research and return section results.

    This is the entry point used by ResearchOrchestrator for structured mode.

    Args:
        company_name: Name of the company
        website: Company website URL
        on_progress: Optional callback for progress updates (message: str)

    Returns:
        Dict mapping section_key to content
    """
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
        return f"{int(seconds//60)}m {int(seconds%60)}s"

    folder_path = create_working_folder(company_name, website)
    progress(f"> Working folder: {folder_path}")

    # Scrape website - saves raw scrapes incrementally to _raw_scrapes folder
    # fetch_web_content already shows completion message, no need to duplicate
    scraped_data = fetch_web_content(website, company_name, max_pages=50, working_folder=folder_path) if website else {}

    # External research - with LLM validation to ensure correct company
    # This prevents including content from similarly-named but unrelated companies
    # (e.g., "EverTrue" fundraising software vs "EverTrue" senior living)
    progress("Searching Google for external sources...")

    external_data = {}
    total_search_results = 0
    if website:
        from primr.data.scrape import scrape_external_sources_validated
        from primr.data.search_utils import search_google

        urlparse(website).netloc.replace("www.", "")

        # Search for business news and press releases about the company
        external_queries = [
            "news OR press release OR announcement",
            "funding OR acquisition OR partnership",
        ]

        for query in external_queries:
            results = search_google(query, company_name, website)
            if results:
                total_search_results += len(results)
                progress(f"  Found {len(results)} results for '{query[:30]}...'")
                filtered = [r for r in results[:5] if website.lower() not in r.get("url", "").lower()]
                progress(f"  Validating {len(filtered)} external articles...")
                scraped = scrape_external_sources_validated(
                    filtered,
                    company_name=company_name,
                    website=website,
                    max_sources=2,
                    working_folder=folder_path
                )
                external_data.update(scraped)

                if len(external_data) >= 3:
                    break

    progress(f"+ {len(external_data)} external sources validated (from {total_search_results} search results)")

    all_scraped = {**scraped_data, **external_data}

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
    summarized = summarize_scraped_content(company_name, website, all_scraped, folder_path)
    if not summarized.strip():
        summarized = "No insights extracted."
    progress("+ Content summarized")

    # Clean up raw scrapes folder now that we have the summary
    raw_folder = os.path.join(folder_path, "_raw_scrapes")
    if os.path.exists(raw_folder):
        import shutil
        try:
            shutil.rmtree(raw_folder)
            logger.debug("Cleaned up raw scrapes folder")
        except Exception as e:
            logger.debug(f"Failed to clean up raw scrapes: {e}")

    # Industry identification
    progress("Identifying industry...")
    industry_prompt = generate_prompt(
        "industry",
        company_name=company_name,
        company_website=website or "N/A",
        scraped_insights=summarized
    )
    industry = llm(industry_prompt, model_type="research").strip() or "Unknown"
    progress(f"+ Industry: {industry}")

    # Overview
    progress("Generating overview...")
    overview = generate_initial_overview(company_name, website, industry, folder_path)
    progress("+ Overview complete")

    # Research all sections
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

            content = research_section(
                section, company_name, website, industry,
                folder_path, overview, summarized
            )
            if content:
                section_results[section_key] = content

    # Final timing for sections
    progress(f"+ {total_analysis} sections complete ({format_time(time_module.time() - sections_start)})")

    console.progress_done()
    return section_results


def perform_scrape_only(
    company_name: str | None,
    website: str | None,
    start_time: float,
    max_scrape_time: int | None = None,
) -> str | None:
    """
    Scrape mode: Build site corpus + extract insights.

    Delegates to fetch_web_content() for all scraping work.

    Cost: ~$0.01-0.05 (LLM for summarization only)
    """
    display_name = company_name or (urlparse(website or "").netloc if website else "")

    # Create working folder (silent)
    folder_path = create_working_folder(company_name, website)

    # Build Site Corpus (shows its own progress)
    corpus = fetch_web_content(
        website=website,
        company_name=company_name,
        max_pages=50,
        working_folder=folder_path,
    )

    pages_scraped = len(corpus)
    total_chars = sum(len(c) for c in corpus.values())

    if pages_scraped == 0:
        console.fail("Could not scrape any pages - site may be blocking")
        console.muted("Try: primr \"Company\" url --mode deep")
        return None

    # Save combined corpus
    scraped_file = os.path.join(folder_path, "scraped_content.txt")
    with open(scraped_file, "w", encoding="utf-8") as f:
        f.write(f"# {display_name} - Scraped Content\n")
        f.write(f"# URL: {website}\n")
        f.write(f"# Pages: {pages_scraped}\n\n")
        for url, content in corpus.items():
            f.write(f"\n{'='*60}\n")
            f.write(f"URL: {url}\n")
            f.write(f"{'='*60}\n")
            f.write(content[:5000] + "\n")

    # Extract Insights (LLM)
    console.status("Extracting insights...")
    time.time()

    summarized = summarize_scraped_content(
        company_name, website, corpus, folder_path
    )
    console.clear_line()
    console.done("Insights extracted")

    # Save insights
    insights_file = os.path.join(folder_path, "insights.txt")
    with open(insights_file, "w", encoding="utf-8") as f:
        f.write(f"# {display_name} - Key Insights\n\n")
        f.write(summarized)

    # Final summary - one clean line
    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

    console.blank()
    console.done(f"Complete: {pages_scraped} pages, {total_chars:,} chars ({time_str})")
    console.muted(f"Output: {folder_path}")

    return folder_path


def perform_research(
    company_name: str | None = None,
    website: str | None = None,
    mode: str = "structured",
    citation_style: str = "numbered",
    ai_strategy: bool = False,
    cloud_vendor: str = "agnostic",
    skip_confirm: bool = False,
    context_files: list[Any] | None = None,
    refresh_vendor_research: bool = False,
    strategies: list[str] | None = None,
    strategy_only: bool = False,
    no_qa: bool = False,
    max_scrape_time: int | None = None,
    discovery_notes_path: str | None = None,
) -> str | None:
    if not company_name and not website:
        console.error("No company name or website provided")
        return None

    display_name: str = company_name or (urlparse(website or "").netloc if website else "")

    # Load discovery notes if provided
    discovery_notes_content: str | None = None
    if discovery_notes_path:
        try:
            with open(discovery_notes_path, encoding='utf-8') as f:
                discovery_notes_content = f.read().strip()
            if discovery_notes_content:
                logger.info(f"Loaded discovery notes from {discovery_notes_path}")
            else:
                logger.warning(f"Discovery notes file is empty: {discovery_notes_path}")
                discovery_notes_content = None
        except FileNotFoundError:
            logger.error(f"Discovery notes file not found: {discovery_notes_path}")
            console.error(f"Discovery notes file not found: {discovery_notes_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to load discovery notes: {e}")
            console.error(f"Failed to load discovery notes: {e}")
            return None

    # Show cost estimate and ask for confirmation
    if not skip_confirm:
        from primr.utils.cost_estimator import display_cost_estimate
        if not display_cost_estimate(mode, display_name, ai_strategy):
            console.info("Research cancelled by user")
            return None

    start_time = time.time()

    # Wrap entire research flow in correlation context for tracing
    with correlation_scope("research", company=display_name, mode=mode):
        log_structured("info", "Starting research job", company=display_name, mode=mode, ai_strategy=ai_strategy)

        # Handle scrape-only mode - scrape and extract insights
        if mode == "scrape-only":
            return perform_scrape_only(company_name, website, start_time, max_scrape_time)

        # Check if using Deep Research, Complete, or Hybrid mode
        if mode in ("deep-research", "complete", "hybrid"):
            return perform_deep_research(
                company_name, website, mode, start_time, citation_style,
                ai_strategy, cloud_vendor, context_files, refresh_vendor_research,
                strategies=strategies, strategy_only=strategy_only,
                discovery_notes_path=discovery_notes_path,
                discovery_notes_content=discovery_notes_content
            )

        folder_path = create_working_folder(company_name, website)

        try:
            # Phase 1: Data Collection
            console.phase_banner(1, 4, "Data Collection", "Scraping website and external sources", "5-10 min")

            # Scrape website
            with console.timed_operation("Scanning website"):
                scraped_data = fetch_web_content(website, company_name, max_pages=50) if website else {}
                pages_scraped = len(scraped_data)
            log_structured("info", "Website scraping complete", pages=pages_scraped)

            # Warn if scraping was very limited
            if pages_scraped <= 2 and website:
                console.warn("Limited website access - report will rely more on web research")

            # External research - with LLM validation to ensure correct company
            # This prevents including content from similarly-named but unrelated companies
            with console.timed_operation("Searching external sources (with validation)"):
                # Include website domain in search to get more targeted results
                if website:
                    urlparse(website).netloc.replace("www.", "")

                # Search for business news and press releases about the company
                # These queries target high-value sources for company intelligence
                external_queries = [
                    "news OR press release OR announcement",  # Recent news coverage
                    "funding OR acquisition OR partnership",   # Business developments
                ]
                external_data = {}

                for query in external_queries:
                    results = search_google(query, company_name, website)
                    if results:
                        filtered = [r for r in results[:5] if website and website.lower() not in r.get("url", "").lower()]
                        scraped = scrape_external_sources_validated(
                            filtered,
                            company_name=company_name,
                            website=website,
                            max_sources=2
                        )
                        external_data.update(scraped)

                        # Stop if we have enough validated sources
                        if len(external_data) >= 3:
                            break
            log_structured("info", "External sources complete (validated)", sources=len(external_data))

            all_scraped = {**scraped_data, **external_data}
            console.phase_complete("Data Collection", [("Pages scraped", str(pages_scraped)), ("External sources", str(len(external_data)))])

            # Phase 2: Analysis
            console.phase_banner(2, 4, "Analysis", "Processing and summarizing content", "3-5 min")

            with console.timed_operation("Summarizing content"):
                summarized = summarize_scraped_content(company_name, website, all_scraped, folder_path)
                if not summarized.strip():
                    summarized = "No insights extracted."

            # Industry identification
            with console.timed_operation("Identifying industry"):
                industry_prompt = generate_prompt(
                    "industry",
                    company_name=company_name,
                    company_website=website or "N/A",
                    scraped_insights=summarized
                )
                industry = llm(industry_prompt, model_type="research").strip() or "Unknown"
            console.info(f"Industry: {industry}")
            console.phase_complete("Analysis")

            # Phase 3: Report Generation
            console.phase_banner(3, 4, "Report Generation", "Building comprehensive report sections", "10-15 min")

            # Overview
            with console.timed_operation("Building overview"):
                overview = generate_initial_overview(company_name, website, industry, folder_path)

            # Value theory
            with console.timed_operation("Value analysis"):
                value_prompt = generate_prompt(
                    "value_theory",
                    company_name=company_name,
                    company_website=website or "N/A"
                )
                value_theory = llm(value_prompt, model_type="research").strip()

                value_file = os.path.join(folder_path, "value_theory.txt")
                with open(value_file, "w", encoding="utf-8") as f:
                    f.write(value_theory or "N/A")

            # Sections
            sections = [
                "Company Name", "Website", "Industry", "Detailed Products/Services",
                "Unique Selling Proposition (USP)", "Mission & Vision", "Company History",
                "Key Achievements", "Target Audience", "Financial Overview",
                "Potential Business Drivers & KPIs", "Industry Insights",
                "Potential Business Drivers", "Primary Apps or Sources of Data",
                "Main Types of Users", "Board of Directors Concerns",
                "Potential Business Value", "Strategic Recommendations"
            ]

            section_start = time.time()
            for i, section in enumerate(sections):
                console.progress_with_time(i + 1, len(sections), section, section_start)
                research_section(section, company_name, website, industry, folder_path, overview, summarized)

            console.progress_done()
            console.phase_complete("Report Generation", [("Sections", str(len(sections)))])

            # Phase 4: Output
            console.phase_banner(4, 4, "Finalizing", "Generating output documents", "1-2 min")
            with console.timed_operation("Generating documents"):
                docx_path = generate_final_report(company_name or display_name, citation_style=citation_style)

            # Generate AI strategy if requested (uses Deep Research with company context)
            ai_strategy_path = None
            if ai_strategy:
                console.phase_banner(5, 5, "AI Strategy Analysis", "Generating AI recommendations", "5-10 min")
                # Consolidate working folder into single context file for AI strategy
                context_file = consolidate_working_folder(folder_path)
                # No heartbeat - the progress callback provides phase-aware status updates
                ai_strategy_path = _generate_ai_strategy_section(
                    company_name or display_name,
                    cloud_vendor,
                    company_research_path=context_file,
                    force_refresh_vendor=refresh_vendor_research,
                    discovery_notes_content=discovery_notes_content
                )
                if ai_strategy_path:
                    console.phase_complete("AI Strategy Analysis")

            # Run QA analysis if enabled (default: enabled, --no-qa disables)
            qa_result = None
            ai_strategy_qa_result = None
            if not no_qa:
                try:
                    from primr.qa.integration import QAIntegration
                    from primr.qa.models import QAOptions

                    verbose_mode = hasattr(console, 'verbose') and console.verbose

                    qa_options = QAOptions(
                        enabled=True,
                        save_detailed=True,
                        verbose_cli=verbose_mode
                    )
                    qa_integration = QAIntegration(qa_options)

                    # QA for main Strategic Overview report
                    if docx_path:
                        txt_report_path = Path(docx_path).with_suffix('.txt')
                        if txt_report_path.exists():
                            qa_result = qa_integration.run_post_generation_qa(txt_report_path, company_name or display_name)

                    # QA for AI Strategy report
                    if ai_strategy_path:
                        ai_strategy_txt = Path(ai_strategy_path).with_suffix('.txt')
                        if ai_strategy_txt.exists():
                            ai_strategy_qa_result = qa_integration.run_post_generation_qa(
                                ai_strategy_txt,
                                f"{company_name or display_name} (AI Strategy)"
                            )

                except Exception as e:
                    logger.warning(f"QA analysis failed: {e}")

            elapsed = time.time() - start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

            console.phase_complete("Finalizing", [("Duration", time_str)])

            # Final output
            if docx_path:
                report_path = Path(docx_path).resolve()
                # Use file:// URI for clickable links in terminal
                file_uri = report_path.as_uri()
                console.success_box("Report ready", file_uri)

            if ai_strategy_path:
                console.success_box("AI Strategy", ai_strategy_path)

            # Display QA grades inline
            qa_grades = []
            if qa_result and qa_result.grade > 0:
                qa_grades.append(("Overview", qa_result.grade))
            if ai_strategy_qa_result and ai_strategy_qa_result.grade > 0:
                qa_grades.append(("AI Strategy", ai_strategy_qa_result.grade))
            if qa_grades:
                console.grades(qa_grades)

            # Get actual usage from AI client
            from primr.ai.client import get_client
            client = get_client()
            usage = client.get_usage_summary()
            actual_cost = usage.get("total_cost", 0)

            # Get estimated cost for comparison
            from primr.utils.cost_estimator import estimate_cost
            estimate_cost(mode, ai_strategy, use_historical=False)

            # Summary stats
            summary_items = [
                ("Duration", time_str),
                ("Cost", f"${actual_cost:.2f}"),
            ]
            console.summary(summary_items)

            # Save usage to history
            from primr.utils.usage_tracker import get_usage_tracker
            tracker = get_usage_tracker()
            tracker.record_usage(
                mode=mode,
                company=display_name,
                input_tokens=usage.get("total_input_tokens", 0),
                output_tokens=usage.get("total_output_tokens", 0),
                duration_seconds=elapsed,
            )
            tracker.save()

            # Log job summary for observability
            job_summary = JobSummary.create(
                company=display_name,
                mode=mode,
                duration_seconds=elapsed,
                api_calls=usage.get("api_calls", 0),
                total_tokens=usage.get("total_input_tokens", 0) + usage.get("total_output_tokens", 0),
                sections_generated=len(sections),
                output_path=docx_path,
            )
            log_job_summary(job_summary)

            return docx_path

        except Exception as e:
            console.error(f"Research failed: {e}")
            log_structured("error", "Research failed", error=str(e), error_type=type(e).__name__)
            logger.exception("Research failed")
            return None


def perform_deep_research(
    company_name: str | None,
    website: str | None,
    mode: str,
    start_time: float,
    citation_style: str = "numbered",
    ai_strategy: bool = False,
    cloud_vendor: str = "agnostic",
    context_files: list[Any] | None = None,
    refresh_vendor_research: bool = False,
    strategies: list[str] | None = None,
    strategy_only: bool = False,
    discovery_notes_path: str | None = None,
    discovery_notes_content: str | None = None,
) -> str | None:
    """
    Perform research using Deep Research Agent, Complete, or Hybrid mode.

    Args:
        company_name: Name of the company
        website: Company website URL
        mode: Research mode ('deep-research', 'complete', or 'hybrid')
        start_time: Start timestamp for duration tracking
        citation_style: Citation formatting style
        ai_strategy: If True, generate AI opportunity recommendations (legacy, use strategies instead)
        cloud_vendor: Cloud vendor for AI recommendations
        context_files: Optional list of files (PDFs, docs) to upload as context for Deep Research
        refresh_vendor_research: If True, force regenerate vendor research
        strategies: List of strategy module names to generate (e.g., ['ai', 'cloud'])
        strategy_only: If True, skip company overview and only run strategies
        discovery_notes_path: Path to discovery notes file (for logging/tracking)
        discovery_notes_content: Loaded content of discovery notes (freeform meeting insights)
    """
    display_name: str = company_name or (urlparse(website or "").netloc if website else "")

    # =================================================================
    # PRE-FLIGHT VALIDATION - Verify everything BEFORE expensive API calls
    # =================================================================
    preflight_errors = []

    # 1. Must have company name or website
    if not company_name and not website:
        preflight_errors.append("Must provide company name or website")

    # 2. Validate context files exist and are readable
    if context_files:
        for f in context_files:
            if not os.path.exists(f):
                preflight_errors.append(f"Context file not found: {f}")
            elif not os.path.isfile(f):
                preflight_errors.append(f"Context path is not a file: {f}")
            elif os.path.getsize(f) == 0:
                preflight_errors.append(f"Context file is empty: {f}")

    # 3. Validate API key is configured
    from primr.config.settings import get_settings
    settings = get_settings()
    if not settings.api.gemini_key:
        preflight_errors.append("GEMINI_API_KEY not configured")

    # ABORT if any pre-flight errors
    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        console.error("Fix these issues before running expensive Deep Research")
        return None

    # =================================================================

    # Map mode string to enum
    mode_map = {
        "deep-research": (ResearchMode.DEEP_RESEARCH, "Deep Research"),
        "complete": (ResearchMode.COMPLETE, "Complete (Two-Step)"),
        "hybrid": (ResearchMode.HYBRID, "Hybrid"),
    }
    research_mode, mode_label = mode_map.get(mode, (ResearchMode.DEEP_RESEARCH, "Deep Research"))

    # Wrap deep research in correlation context
    with correlation_scope("deep_research", company=display_name, mode=mode):
        log_structured("info", "Starting deep research", company=display_name, mode=mode)

        # For COMPLETE mode, the orchestrator handles all phase banners
        # For simple DEEP_RESEARCH mode, we show our own phase banners
        is_simple_deep_research = mode == "deep-research"

        if is_simple_deep_research:
            context_info = ""
            if context_files:
                context_info = f" with {len(context_files)} context file(s)"
            console.phase_banner(1, 3, f"{mode_label}{context_info}", "Autonomous AI research", "10-15 min")

        # Track last phase to only print on phase changes
        last_phase = [None]  # Use list to allow mutation in closure

        def progress_callback(msg: str) -> None:
            # Extract phase from message (e.g., "Searching sources (2m 30s)")
            phase = msg.split(" (")[0].strip() if " (" in msg else msg.strip()

            # Only print on actual phase changes, not time updates
            if phase and phase != last_phase[0] and not phase.startswith("  "):
                last_phase[0] = phase
                console.info(phase)

            log_structured("debug", f"Deep research progress: {msg}")

        try:
            # Run async orchestrator with heartbeat for long operations
            orchestrator = get_orchestrator()

            # Create event loop if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            with console.heartbeat("Deep Research in progress", interval=90.0):
                result = loop.run_until_complete(
                    orchestrator.research(
                        company_name=company_name or display_name,
                        website=website,
                        mode=research_mode,
                        on_progress=progress_callback,
                        context_files=context_files
                    )
                )

            if not result.success:
                console.error(f"Research failed: {result.error}")
                log_structured("error", "Deep research failed", error=result.error)
                return None

            # Use sections_written for accurate count (accordion method tracks this)
            section_count = result.sections_written if result.sections_written > 0 else len(result.section_results)
            log_structured("info", "Deep research complete", sections=section_count)

            # Get accurate citation count for display
            len(result.citations)  # Default fallback

            # Calculate word and page count from raw content
            word_count = len(result.raw_content.split()) if result.raw_content else 0
            page_count = word_count // 500  # ~500 words per page

            if is_simple_deep_research:
                console.phase_complete("Deep Research", [
                    ("Pages", f"~{page_count}"),
                    ("Words", f"{word_count:,}"),
                    ("Sections", str(section_count)),
                ])
                console.phase_banner(2, 3, "Processing Results", "Saving and converting output", "1-2 min")

            # Save section results to working folder
            folder_path = create_working_folder(company_name, website)

            with console.timed_operation("Saving results"):
                for section_key, content in result.section_results.items():
                    save_section_output(folder_path, section_key, content)

            # Save raw markdown for reference
            raw_md_path = None
            if result.raw_content:
                raw_md_path = os.path.join(folder_path, "deep_research_output.md")
                with open(raw_md_path, "w", encoding="utf-8") as f:
                    f.write(result.raw_content)

            # Generate final report - use direct markdown conversion for Deep Research
            with console.timed_operation("Generating documents"):
                if result.raw_content and mode in ("deep-research", "complete", "hybrid"):
                    # Deep Research: convert markdown directly to DOCX (preserves structure)
                    docx_path = _convert_deep_research_to_docx(
                        result.raw_content,
                        company_name or display_name,
                        website
                    )
                else:
                    # Structured pipeline: use DocumentBuilder to assemble sections
                    docx_path = generate_final_report(company_name or display_name, citation_style=citation_style)

            if is_simple_deep_research:
                console.phase_complete("Processing Results")

            # Determine which strategies to run
            strategies_to_run: list[str] = []
            if strategies:
                # Explicit --strategy flag takes precedence
                strategies_to_run = strategies
            elif ai_strategy:
                # Legacy --ai-strategy flag (default behavior)
                strategies_to_run = ["ai"]

            # Generate strategies (uses Deep Research with company context)
            strategy_paths: dict[str, str] = {}
            if strategies_to_run:
                base_phase = 3 if is_simple_deep_research else 5
                total_strategies = len(strategies_to_run)

                for idx, strategy_name in enumerate(strategies_to_run):
                    phase_num = base_phase + idx
                    total_phases = base_phase + total_strategies - 1

                    # Get display name from registry
                    from primr.prompts.registry import get_registry
                    registry = get_registry()
                    strategy_module = registry.get(strategy_name)
                    display_strategy_name = strategy_module.display_name if strategy_module else strategy_name.replace("_", " ").title()

                    console.phase_banner(
                        phase_num, total_phases,
                        f"{display_strategy_name} Analysis",
                        f"Generating {display_strategy_name.lower()} recommendations",
                        "5-10 min"
                    )

                    # Generate the strategy
                    strategy_path = _generate_strategy_section(
                        strategy_name=strategy_name,
                        company_name=company_name or display_name,
                        cloud_vendor=cloud_vendor,
                        company_research_path=raw_md_path,
                        force_refresh_vendor=refresh_vendor_research
                    )

                    if strategy_path:
                        strategy_paths[strategy_name] = strategy_path
                        console.phase_complete(f"{display_strategy_name} Analysis")

            # For backward compatibility
            strategy_paths.get("ai")

            elapsed = time.time() - start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

            console.ok(f"Complete in {time_str}")

            # Final output - use plain paths (consistent format)
            if docx_path:
                console.success_box("Report ready", str(Path(docx_path).resolve()))

            # Show all generated strategy outputs
            for strategy_name, strategy_path in strategy_paths.items():
                from primr.prompts.registry import get_registry
                registry = get_registry()
                strategy_module = registry.get(strategy_name)
                display_name = strategy_module.display_name if strategy_module else strategy_name.replace("_", " ").title()
                console.success_box(display_name, str(Path(strategy_path).resolve()))

            # Get actual usage from AI client (for structured pipeline calls)
            from primr.ai.client import get_client
            client = get_client()
            usage = client.get_usage_summary()

            # Deep Research uses Interactions API which doesn't expose token counts
            # Estimate based on output length: ~4 chars per token, $12/1M output tokens
            # Also estimate input based on prompt + context (~50k tokens typical)
            total_output_chars = sum(len(content) for content in result.section_results.values())
            estimated_output_tokens = total_output_chars // 4
            estimated_input_tokens = 50_000  # Typical for Deep Research prompt + context

            # Add AI client usage (from structured pipeline in complete mode)
            total_input = usage.get("total_input_tokens", 0) + estimated_input_tokens
            total_output = usage.get("total_output_tokens", 0) + estimated_output_tokens

            # Calculate actual cost: $2/1M input, $12/1M output
            actual_cost = (total_input / 1_000_000) * 2.0 + (total_output / 1_000_000) * 12.0

            # Get pre-run estimate for comparison
            from primr.utils.cost_estimator import estimate_cost
            pre_estimate = estimate_cost(mode, ai_strategy, use_historical=False)

            # Use sections_written for accurate count
            section_count = result.sections_written if result.sections_written > 0 else len(result.section_results)

            # Get accurate citation count using report analyzer
            citation_count = 0
            if docx_path:
                try:
                    # Convert DOCX path to MD path for analysis
                    md_path = str(docx_path).replace('.docx', '.md')
                    if os.path.exists(md_path):
                        from report_analyzer import ReportAnalyzer
                        analyzer = ReportAnalyzer(md_path)
                        citation_analysis = analyzer.analyze_citations()
                        citation_count = citation_analysis['unique_citations']
                except Exception as e:
                    logger.debug(f"Could not analyze citations: {e}")
                    citation_count = len(result.citations)  # Fallback to original
            else:
                citation_count = len(result.citations)

            # Summary stats with estimated vs actual comparison
            summary_items = [
                ("Mode", mode_label),
                ("Sections", str(section_count)),
                ("Citations", str(citation_count)),
                ("Duration", time_str),
                ("Est. Cost", f"${pre_estimate.total_cost:.2f}"),
                ("Actual Cost", f"~${actual_cost:.2f}"),
            ]
            if ai_strategy:
                summary_items.append(("AI Strategy", "Yes"))
            console.summary(summary_items)

            # Save usage to history
            from primr.utils.usage_tracker import get_usage_tracker
            tracker = get_usage_tracker()
            tracker.record_usage(
                mode=mode,
                company=display_name,
                input_tokens=total_input,
                output_tokens=total_output,
                search_queries=result.search_queries_count,  # Actual count from API
                duration_seconds=elapsed,
            )
            tracker.save()

            # Log job summary for observability
            job_summary = JobSummary.create(
                company=display_name,
                mode=mode,
                duration_seconds=elapsed,
                api_calls=0,  # Deep Research doesn't expose API call count
                total_tokens=total_input + total_output,
                sections_generated=section_count,
                output_path=docx_path,
            )
            log_job_summary(job_summary)

            return docx_path

        except Exception as e:
            console.error(f"Deep research failed: {e}")
            log_structured("error", "Deep research failed", error=str(e), error_type=type(e).__name__)
            logger.exception("Deep research failed")
            return None


def _convert_deep_research_to_docx(
    markdown_content: str,
    company_name: str,
    website: str | None
) -> str | None:
    """
    Convert Deep Research markdown output to all output formats.

    This bypasses the DocumentBuilder and preserves the exact structure
    that Deep Research produces. The AI follows the prompt's section
    structure, so we just convert it cleanly to Word format.

    Outputs:
    - {company}_Strategic_Overview_{date}.md  - Raw markdown
    - {company}_Strategic_Overview_{date}.txt - Plain text
    - {company}_Strategic_Overview_{date}.docx - Word document

    Args:
        markdown_content: Raw markdown from Deep Research
        company_name: Name of the company
        website: Company website URL

    Returns:
        Path to generated DOCX file, or None on failure
    """
    from primr.output.markdown_converter import markdown_to_docx
    from primr.output.output_utils import OUTPUT_DIR

    date_str = datetime.now().strftime("%m-%d-%Y")
    base_name = f"{company_name}_Strategic_Overview_{date_str}"

    try:
        # Save markdown (.md)
        md_path = Path(OUTPUT_DIR) / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        console.ok(f"MD saved: {base_name}.md", show_time=False)

        # Save plain text (.txt)
        txt_path = Path(OUTPUT_DIR) / f"{base_name}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        console.ok(f"TXT saved: {base_name}.txt", show_time=False)

        # Build subtitle with date and website
        subtitle_parts = [datetime.now().strftime("%B %d, %Y")]
        if website:
            subtitle_parts.append(website)
        subtitle = " | ".join(subtitle_parts)

        # Convert to DOCX
        docx_path = Path(OUTPUT_DIR) / f"{base_name}.docx"
        try:
            markdown_to_docx(
                markdown_text=markdown_content,
                output_path=docx_path,
                title=f"Strategic Company Overview: {company_name}",
                subtitle=subtitle
            )
        except PermissionError:
            # File is probably open in Word - try with timestamp suffix
            timestamp = datetime.now().strftime("%H%M%S")
            file_name = f"{base_name}_{timestamp}.docx"
            docx_path = Path(OUTPUT_DIR) / file_name
            console.warn(f"Original file locked, saving as: {file_name}")
            markdown_to_docx(
                markdown_text=markdown_content,
                output_path=docx_path,
                title=f"Strategic Company Overview: {company_name}",
                subtitle=subtitle
            )

        console.ok(f"DOCX saved: {docx_path.name}", show_time=False)
        return str(docx_path)

    except Exception as e:
        console.error(f"Failed to convert markdown to DOCX: {e}")
        logger.exception("Markdown to DOCX conversion failed")
        return None


def _get_vendor_research_path(cloud_vendor: str) -> str:
    """Get the path for vendor research file based on current month."""
    from datetime import datetime

    current_month = datetime.now().strftime("%Y-%m")
    filename = f"vendor-research-{cloud_vendor.lower()}-{current_month}.txt"
    return os.path.join(PROJECT_ROOT, "vendor-research", filename)


def _is_vendor_research_current(cloud_vendor: str) -> bool:
    """Check if we have current month's vendor research."""
    # Azure has a manually curated file that's always preferred
    if cloud_vendor.lower() == "azure":
        from primr.config.config import PROJECT_ROOT
        manual_path = os.path.join(PROJECT_ROOT, "docs/research latest microsoft ignite analysis.txt")
        if os.path.exists(manual_path):
            return True

    research_path = _get_vendor_research_path(cloud_vendor)
    return os.path.exists(research_path)


def _generate_vendor_research(cloud_vendor: str) -> str | None:
    """
    Generate fresh vendor AI research using Deep Research.

    This creates a comprehensive overview of the latest AI services and capabilities
    from the specified cloud vendor, suitable for use as context in AI strategy generation.

    Args:
        cloud_vendor: Cloud vendor (azure, aws, gcp, agnostic)

    Returns:
        Path to generated research file, or None if generation failed
    """
    from datetime import datetime

    from primr.ai.deep_research import ResearchStatus, get_deep_research_client
    from primr.config.settings import get_settings

    # =================================================================
    # PRE-FLIGHT VALIDATION - Check everything BEFORE expensive API call
    # =================================================================
    preflight_errors = []

    # 1. Validate cloud vendor
    valid_vendors = ["azure", "aws", "gcp", "agnostic"]
    if cloud_vendor.lower() not in valid_vendors:
        preflight_errors.append(f"Invalid cloud vendor: {cloud_vendor}. Must be one of: {', '.join(valid_vendors)}")

    # 2. Validate API key is configured
    settings = get_settings()
    if not settings.api.gemini_key:
        preflight_errors.append("GEMINI_API_KEY not configured in .env")

    # 3. Check docs directory is writable
    docs_dir = os.path.join(PROJECT_ROOT, "docs")
    try:
        os.makedirs(docs_dir, exist_ok=True)
        test_file = os.path.join(docs_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        preflight_errors.append(f"Docs directory not writable: {docs_dir} ({e})")

    # ABORT if any pre-flight errors
    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        console.error("Fix these issues before running expensive Deep Research")
        return None
    # =================================================================

    current_date = datetime.now().strftime("%B %Y")

    vendor_names = {
        "azure": "Microsoft Azure",
        "aws": "Amazon Web Services (AWS)",
        "gcp": "Google Cloud Platform (GCP)",
        "agnostic": "the AI Industry (cross-vendor)"
    }
    vendor_name = vendor_names.get(cloud_vendor.lower(), cloud_vendor)

    # Conference names for each vendor
    conferences = {
        "azure": "Microsoft Ignite, Microsoft Build",
        "aws": "AWS re:Invent, AWS Summit",
        "gcp": "Google Cloud Next, Google I/O",
        "agnostic": "NeurIPS, major vendor conferences (Ignite, re:Invent, Cloud Next), and recent announcements from OpenAI, Anthropic, NVIDIA, Meta, Mistral, and Cohere"
    }
    conference = conferences.get(cloud_vendor.lower(), "recent conferences")

    # Vendor-specific model platform names
    model_platforms = {
        "azure": "Azure OpenAI Service and Azure AI Foundry",
        "aws": "Amazon Bedrock",
        "gcp": "Vertex AI",
        "agnostic": "major model providers (OpenAI, Anthropic, Google, Meta, Mistral, Cohere) and cloud platforms (Azure, AWS, GCP)"
    }
    model_platform = model_platforms.get(cloud_vendor.lower(), "the AI platform")

    # Vendor-specific official sources (detailed)
    official_sources_detail = {
        "azure": "Microsoft Learn docs, Azure Blog, official 'What's New' pages, Microsoft Tech Community, Ignite/Build session pages, and Azure pricing pages",
        "aws": "AWS Documentation, AWS News Blog, official 'What's New' announcements, re:Invent session pages, and AWS pricing pages",
        "gcp": "Google Cloud Documentation, Google Cloud Blog, official release notes, Cloud Next session pages, and GCP pricing pages",
        "agnostic": "official documentation and blogs from OpenAI, Anthropic, NVIDIA, Meta AI, Mistral, Cohere, and the major cloud vendors (Azure, AWS, GCP)"
    }
    official_source = official_sources_detail.get(cloud_vendor.lower(), "official documentation and pricing pages")

    # Vendor-specific service map categories
    service_maps = {
        "azure": """
AI Platform: Azure OpenAI Service, Azure AI Foundry, Cognitive Services
Agent/Copilot: Copilot Studio, Semantic Kernel, AI Builder
Data Plane: Azure Storage, Synapse, Fabric, Azure AI Search, Cosmos DB
App Plane: Azure Functions, Logic Apps, Event Grid, API Management
Security Plane: Entra ID, Key Vault, Purview, Defender for Cloud""",
        "aws": """
AI Platform: Amazon Bedrock, SageMaker, Comprehend, Rekognition
Agent/Copilot: Bedrock Agents, Amazon Q, Step Functions
Data Plane: S3, Lake Formation, Glue, OpenSearch, Redshift, DynamoDB
App Plane: Lambda, Step Functions, EventBridge, API Gateway
Security Plane: IAM, KMS, CloudTrail, GuardDuty, Macie""",
        "gcp": """
AI Platform: Vertex AI, Gemini API, Document AI, Vision AI
Agent/Copilot: Vertex AI Agent Builder, Dialogflow CX
Data Plane: Cloud Storage, BigQuery, Dataflow, Vertex AI Search, Firestore
App Plane: Cloud Functions, Cloud Run, Workflows, Eventarc, API Gateway
Security Plane: IAM, Cloud KMS, Security Command Center, DLP API""",
        "agnostic": """
Model Providers: OpenAI (GPT-4, o1), Anthropic (Claude), Google (Gemini), Meta (Llama), Mistral, Cohere
Infrastructure: NVIDIA (GPUs, NIM, NeMo), cloud platforms (Azure, AWS, GCP)
Cloud AI Platforms: Azure OpenAI/AI Foundry, Amazon Bedrock, Vertex AI
Agent Frameworks: LangChain, LlamaIndex, Semantic Kernel, AutoGen, CrewAI
Vector Databases: Pinecone, Weaviate, Qdrant, Chroma, pgvector
Evaluation/Observability: LangSmith, Weights & Biases, Arize, Helicone"""
    }
    service_map = service_maps.get(cloud_vendor.lower(), "")

    prompt = f"""You are an AI technology analyst. Research the latest AI services and capabilities.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# {vendor_name} AI Services and Capabilities

**Prepared by:** Primr Research System
**Date:** {current_date}

---

Then continue with the sections below.

=============================================================================
RESEARCH INSTRUCTIONS
=============================================================================

CRITICAL: This research must reflect the AI landscape as of {current_date}.
You MUST use live web search to find the latest information.
Do NOT rely on potentially outdated training data.

=============================================================================
RESEARCH AND VALIDATION PROTOCOL
=============================================================================

For every service or feature listed in this document:

1. **Verify current name**: Confirm the service still exists and has not been renamed or deprecated
2. **Status**: Note if GA (Generally Available) or Preview/Beta
3. **Region availability**: Flag if limited to specific regions
4. **Citation**: Link to official {vendor_name} documentation or blog post, include publish date or "last updated" date
5. **Pricing**: If pricing is mentioned, cite the pricing page and state assumptions (region, token units, provisioned throughput, etc.)
6. **Unconfirmed flag**: If a claim cannot be verified through official sources, mark as "UNCONFIRMED"

SOURCE HYGIENE (critical for defensibility):
- Primary sources ONLY: {official_source}
- If a product page is used, it must include a dated release note or "What's New" reference
- DO NOT use third-party blogs (SiliconAngle, InfoWorld, Medium, etc.) as primary evidence
- Third-party sources may be used ONLY to triangulate when official sources are unavailable
- If you must cite a third-party source, explicitly note it is not first-party

DEPRECATION AND END-OF-LIFE:
Flag any service, feature, or model that was deprecated, merged, or renamed in the past 12 months.
State the replacement or migration path.

PRICING GUIDANCE:
- Provide pricing at the level needed for directional architecture decisions, not a full cost model
- Label all pricing as "indicative, as of {current_date}" since pricing changes frequently
- Prefer linking to pricing pages rather than restating exact numbers
- If specific numbers are included, state assumptions (region, usage volume, token units)

CASE STUDY EVIDENCE STANDARD:
- Only include customer stories backed by official {vendor_name} sources (case study page, official blog, conference session)
- If a case study cannot be verified through first-party sources, DO NOT include it
- Downgrade unverified claims to "reported" language or omit entirely
- This section is high-risk for credibility. When in doubt, leave it out.

=============================================================================
FORMATTING RULES
=============================================================================

- Write in full paragraphs with clear section headers
- Use bullets for lists of services
- No em-dashes, use commas or periods
- Avoid hype language. Prefer operational language over visionary claims.
- Include specific service names, features, and availability status

=============================================================================
RESEARCH GOAL
=============================================================================

Many companies are interested in adopting AI in {current_date}. For {vendor_name}, I need a comprehensive
overview of the latest AI services, capabilities, and best practices that we should keep in mind when
advising enterprise customers on AI strategy.

Search for the latest updates from {conference} and recent {vendor_name} announcements.

=============================================================================
SECTION STRUCTURE
=============================================================================

## Executive Summary
Key themes and strategic direction for {vendor_name} AI in {current_date}.

## Service Map

A simple mapping of where services live in the {vendor_name} stack:
{service_map}

Update this map if any services have been renamed, merged, or deprecated.

## Foundation Models and AI Services

For {model_platform}, provide:
- Which models are available (provider, model family, version)
- What is new in the past 6 months
- GA vs Preview status for each model
- Customization options (fine-tuning, continued pretraining, adapters, prompt caching, guardrails)
- Pricing model overview (cite pricing page with assumptions)

## Productivity AI and Copilots
- Enterprise productivity tools with AI
- Integration with existing workflows
- Licensing and deployment models

## Agentic AI and Automation
- Agent building platforms and tools
- Orchestration capabilities
- Multi-agent scenarios
- When agents are appropriate versus workflow automation

## Data and Analytics AI
- AI-powered analytics and BI
- Data platform integration
- Vector search and RAG capabilities
- Default enterprise pattern for RAG on {vendor_name}

## AI Development Platform
- Model hosting options and when to use each
- Developer tools and SDKs
- MLOps and deployment
- Evaluation and monitoring capabilities

## Security and Governance
- AI governance tools
- Data protection and compliance
- Identity and access for AI
- Guardrails and content filtering

## Recommendation Guidance

When to use which service:
- Model hosting: When to use {model_platform} vs other options
- RAG: Default pattern for enterprise RAG and vector search
- Agents: When agents are appropriate versus simpler automation
- Anti-patterns to avoid (pilot purgatory, tool sprawl, no evaluation, skipping governance)

## Notable Customer Case Studies

IMPORTANT: Only include customer stories that have a primary {vendor_name} source (official case study page, official blog, conference session). If not from a primary source, do not include it.

- Real-world implementations with source links
- ROI examples where documented
- Industry-specific use cases

## New in the Past 6 Months

Bulleted list of recent changes. For each item include:
- What changed
- GA or Preview status
- Date and source URL

## Deprecations and Migrations (Past 12 Months)

List any services, features, or models that were:
- Deprecated or end-of-lifed
- Renamed or rebranded
- Merged into another service

For each, state the replacement or migration path.

## Sources

List all sources with URLs and dates. Group by section for easy reference.
"""

    console.info(f"Generating fresh {cloud_vendor.upper()} AI research...")
    console.info("Estimated: 5-10 min, ~$0.50")  # Deep Research for vendor docs

    client = get_deep_research_client()

    def progress_callback(progress):
        if progress.message:
            console.info(f"Vendor Research: {progress.message}")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            client.research(
                query=prompt,
                output_format=None,
                on_progress=progress_callback,
                timeout=1800  # 30 min timeout
            )
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error("Vendor research generation failed")
            return None

        # Save to docs folder
        research_path = _get_vendor_research_path(cloud_vendor)
        os.makedirs(os.path.dirname(research_path), exist_ok=True)

        with open(research_path, "w", encoding="utf-8") as f:
            f.write(result.content)

        # Calculate actual cost from result
        output_tokens = len(result.content) // 4  # Rough estimate
        input_tokens = 5000  # Prompt size
        actual_cost = (input_tokens / 1_000_000) * 2.0 + (output_tokens / 1_000_000) * 12.0
        duration_str = f"{result.duration_seconds / 60:.1f}m"

        console.ok(f"Vendor research saved: {os.path.basename(research_path)} ({duration_str}, ~${actual_cost:.2f})")
        return research_path

    except Exception as e:
        console.error(f"Vendor research failed: {e}")
        logger.exception("Vendor research error")
        return None


def _get_or_generate_vendor_research(cloud_vendor: str) -> list[str]:
    """
    Get vendor research file, generating if needed.

    For Azure, prefers the manually curated Ignite analysis.
    For AWS/GCP, auto-generates if current month's research doesn't exist.

    Args:
        cloud_vendor: Cloud vendor (azure, aws, gcp)

    Returns:
        List of paths to vendor research files, or empty list if unavailable
    """

    result_paths = []

    # Azure: always include manually curated Ignite analysis (it's excellent)
    if cloud_vendor.lower() == "azure":
        manual_path = os.path.join(PROJECT_ROOT, "docs/research latest microsoft ignite analysis.txt")
        if os.path.exists(manual_path):
            result_paths.append(manual_path)

    # Check for current month's auto-generated research
    research_path = _get_vendor_research_path(cloud_vendor)
    if os.path.exists(research_path):
        result_paths.append(research_path)
    elif not result_paths:  # Only auto-generate if we have nothing
        generated = _generate_vendor_research(cloud_vendor)
        if generated:
            result_paths.append(generated)

    return result_paths


def _generate_strategy_section(
    strategy_name: str,
    company_name: str,
    cloud_vendor: str,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    discovery_notes_content: str | None = None
) -> str | None:
    """
    Generate a strategy document using Deep Research.

    This is a generic function that can generate any strategy module
    defined in the strategies/ directory.

    Args:
        strategy_name: Name of the strategy module (e.g., 'ai', 'customer_experience', 'modern_security_compliance', 'data_fabric_strategy')
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference (azure, aws, gcp, agnostic)
        company_research_path: Path to company research markdown (used as context)
        force_refresh_vendor: If True, regenerate vendor research even if current
        discovery_notes_content: Optional freeform meeting insights from discovery

    Returns:
        Path to the generated DOCX file, or None if generation failed
    """
    # Map strategy names to their YAML files and generation functions
    strategy_map = {
        "ai": "ai_first_transformation",
        "customer_experience": "customer_experience",
        "modern_security_compliance": "modern_security_compliance",
        "data_fabric_strategy": "data_fabric_strategy",
    }

    # Handle AI strategy separately (has vendor research)
    if strategy_name == "ai":
        return _generate_ai_strategy_section(
            company_name=company_name,
            cloud_vendor=cloud_vendor,
            company_research_path=company_research_path,
            force_refresh_vendor=force_refresh_vendor,
            discovery_notes_content=discovery_notes_content
        )

    # Handle other fully-defined strategies
    if strategy_name in strategy_map:
        return _generate_generic_strategy(
            strategy_name=strategy_name,
            strategy_yaml=strategy_map[strategy_name],
            company_name=company_name,
            company_research_path=company_research_path,
            discovery_notes_content=discovery_notes_content
        )

    # For placeholder strategies, show a message
    from primr.prompts.registry import get_registry
    registry = get_registry()
    strategy_module = registry.get(strategy_name)

    if not strategy_module:
        console.error(f"Strategy module not found: {strategy_name}")
        return None

    # Check if it's a placeholder
    import yaml
    if strategy_module.config_path.exists():
        with open(strategy_module.config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            meta = data.get("meta", {})
            if meta.get("status") == "placeholder":
                console.warn(f"Strategy '{strategy_name}' is a placeholder - not yet implemented")
                console.info(f"To implement, update: {strategy_module.config_path}")
                return None

    # For fully implemented strategies (future), use PromptComposer
    console.warn(f"Strategy '{strategy_name}' generation not yet implemented")
    return None


def _generate_generic_strategy(
    strategy_name: str,
    strategy_yaml: str,
    company_name: str,
    company_research_path: str | None = None,
    discovery_notes_content: str | None = None
) -> str | None:
    """
    Generate a strategy document using Deep Research and the strategy YAML definition.

    This is the generic implementation for CX, Security, Data Fabric, and future strategies.

    Args:
        strategy_name: Internal strategy name (e.g., 'customer_experience')
        strategy_yaml: YAML filename (e.g., 'customer_experience')
        company_name: Name of the company
        company_research_path: Path to company research markdown (used as context)
        discovery_notes_content: Optional freeform meeting insights from discovery

    Returns:
        Path to the generated DOCX file, or None if generation failed
    """
    from datetime import datetime
    from pathlib import Path

    import yaml

    from primr.ai.deep_research import ResearchStatus, get_deep_research_client
    from primr.config.settings import get_settings
    from primr.output.markdown_converter import markdown_to_docx
    from primr.output.output_utils import OUTPUT_DIR

    # Load strategy YAML to get metadata
    strategy_yaml_path = Path(__file__).parent.parent / "prompts" / "strategies" / f"{strategy_yaml}.yaml"
    if not strategy_yaml_path.exists():
        console.error(f"Strategy YAML not found: {strategy_yaml_path}")
        return None

    with open(strategy_yaml_path, encoding="utf-8") as f:
        strategy_config = yaml.safe_load(f)

    meta = strategy_config.get("meta", {})
    strategy_display_name = meta.get("name", strategy_name)

    # =================================================================
    # PRE-FLIGHT VALIDATION
    # =================================================================
    preflight_errors = []

    if not company_name or not company_name.strip():
        preflight_errors.append("Company name is required for strategy generation")

    settings = get_settings()
    if not settings.api.gemini_key:
        preflight_errors.append("GEMINI_API_KEY not configured in .env")

    if company_research_path:
        if not os.path.exists(company_research_path):
            preflight_errors.append(f"Company research file not found: {company_research_path}")
        elif os.path.getsize(company_research_path) == 0:
            preflight_errors.append(f"Company research file is empty: {company_research_path}")

    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_file = os.path.join(OUTPUT_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        preflight_errors.append(f"Output directory not writable: {OUTPUT_DIR} ({e})")

    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        return None

    console.info("Pre-flight checks passed")
    # =================================================================

    try:
        # Build the strategy prompt from YAML
        prompt = _build_strategy_prompt_from_yaml(
            strategy_config=strategy_config,
            company_name=company_name,
            discovery_notes_content=discovery_notes_content
        )

        # Prepare context files
        context_files = []
        if company_research_path and os.path.exists(company_research_path):
            context_files.append(company_research_path)
            console.info("Using Strategic Overview as context")

        # Run Deep Research
        client = get_deep_research_client()

        def progress_callback(progress):
            if progress.message:
                console.info(f"{strategy_display_name}: {progress.message}")

        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            client.research(
                query=prompt,
                output_format=None,
                on_progress=progress_callback,
                context_files=context_files if context_files else None,
                timeout=1800  # 30 min timeout
            )
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error(f"{strategy_display_name} research failed")
            return None

        # Track usage
        output_tokens = len(result.content) // 4
        input_tokens = 50_000  # Estimated

        from primr.utils.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        tracker.record_usage(
            mode=f"strategy-{strategy_name}",
            company=company_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=result.duration_seconds,
        )

        # Generate output files
        date_str = datetime.now().strftime("%m-%d-%Y")
        output_filename = meta.get("output_filename", f"{{company_name}}_{strategy_name}")
        base_name = output_filename.format(company_name=company_name) + f"_{date_str}"

        # Save markdown
        md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(result.content)
        console.ok(f"{strategy_display_name} MD: {base_name}.md", show_time=False)

        # Save plain text
        txt_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result.content)
        console.ok(f"{strategy_display_name} TXT: {base_name}.txt", show_time=False)

        # Convert to DOCX
        docx_path = os.path.join(OUTPUT_DIR, f"{base_name}.docx")
        try:
            subtitle = datetime.now().strftime("%B %d, %Y")
            markdown_to_docx(
                markdown_text=result.content,
                output_path=Path(docx_path),
                title=f"{strategy_display_name}: {company_name}",
                subtitle=subtitle
            )
            console.ok(f"{strategy_display_name} DOCX: {base_name}.docx", show_time=False)
        except PermissionError:
            timestamp = datetime.now().strftime("%H%M%S")
            docx_path = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.docx")
            console.warn(f"Original file locked, saving as: {base_name}_{timestamp}.docx")
            markdown_to_docx(
                markdown_text=result.content,
                output_path=Path(docx_path),
                title=f"{strategy_display_name}: {company_name}",
                subtitle=subtitle
            )
        except Exception as e:
            console.warn(f"DOCX conversion failed: {e}")
            docx_path = md_path

        return docx_path

    except Exception as e:
        console.error(f"{strategy_display_name} generation failed: {e}")
        logger.exception(f"{strategy_display_name} error")
        return None


def _build_strategy_prompt_from_yaml(
    strategy_config: dict,
    company_name: str,
    discovery_notes_content: str | None = None
) -> str:
    """
    Build a Deep Research prompt from a strategy YAML configuration.

    This reads the YAML structure and generates a comprehensive prompt that
    instructs Deep Research to produce the strategy document.

    Args:
        strategy_config: Parsed YAML configuration
        company_name: Name of the company
        discovery_notes_content: Optional freeform meeting insights

    Returns:
        Formatted prompt string for Deep Research
    """
    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")

    meta = strategy_config.get("meta", {})
    strategy_name = meta.get("name", "Strategy Document")

    # Build the prompt
    prompt_parts = []

    # Header
    prompt_parts.append(f"# {strategy_name} for {company_name}")
    prompt_parts.append(f"Date: {current_date}\n")

    # Document purpose
    if "document_purpose" in strategy_config:
        prompt_parts.append("## YOUR ROLE AND TASK")
        prompt_parts.append(strategy_config["document_purpose"])
        prompt_parts.append("")

    # Context instructions
    if "context_instructions" in strategy_config:
        prompt_parts.append("## HOW TO USE CONTEXT")
        prompt_parts.append(strategy_config["context_instructions"])
        prompt_parts.append("")

    # Writing standards
    if "writing_standards" in strategy_config:
        prompt_parts.append("## WRITING QUALITY STANDARDS")
        prompt_parts.append(strategy_config["writing_standards"])
        prompt_parts.append("")

    # Epistemic rules
    if "epistemic_rules" in strategy_config:
        prompt_parts.append("## EPISTEMIC RULES (CRITICAL)")
        epistemic = strategy_config["epistemic_rules"]
        for rule_name, rule_text in epistemic.items():
            prompt_parts.append(f"### {rule_name.replace('_', ' ').title()}")
            prompt_parts.append(rule_text)
            prompt_parts.append("")

    # Discovery notes if provided
    if discovery_notes_content:
        prompt_parts.append("## DISCOVERY NOTES (INTERNAL INSIGHTS)")
        prompt_parts.append("You have access to internal discovery notes from conversations with the company.")
        prompt_parts.append("Use these to ground your recommendations in their actual situation:")
        prompt_parts.append("")
        prompt_parts.append(discovery_notes_content)
        prompt_parts.append("")

    # Sections structure
    if "sections" in strategy_config:
        prompt_parts.append("## DOCUMENT STRUCTURE")
        prompt_parts.append("Generate a comprehensive strategy document with the following sections:\n")

        for section in strategy_config["sections"]:
            section_name = section.get("name", "Untitled Section")
            section_purpose = section.get("purpose", "")
            section_depth = section.get("depth", "")

            prompt_parts.append(f"### {section_name}")
            if section_purpose:
                prompt_parts.append(f"**Purpose**: {section_purpose}")

            if "covers" in section:
                prompt_parts.append("**Covers**:")
                for item in section["covers"]:
                    prompt_parts.append(f"- {item}")

            if "subsections" in section:
                for subsection in section["subsections"]:
                    subsection_name = subsection.get("name", "")
                    prompt_parts.append(f"\n#### {subsection_name}")
                    if "covers" in subsection:
                        for item in subsection["covers"]:
                            prompt_parts.append(f"- {item}")

            if section_depth:
                prompt_parts.append(f"\n**Depth Guidance**: {section_depth}")

            prompt_parts.append("")

    # Final instructions
    prompt_parts.append("## FINAL INSTRUCTIONS")
    prompt_parts.append(f"Generate a comprehensive {strategy_name} for {company_name}.")
    prompt_parts.append("Follow ALL the rules above, especially:")
    prompt_parts.append("- Use the Strategic Overview from File Search Store as PRIMARY source")
    prompt_parts.append("- Frame assessments as hypotheses to validate, not facts")
    prompt_parts.append("- Connect every recommendation to THIS company's specific situation")
    prompt_parts.append("- Include the Facilitation Toolkit sections (board presentation, stakeholder inception, workshop design)")
    prompt_parts.append("- Be specific, honest, and actionable")
    prompt_parts.append("")
    prompt_parts.append("Begin the document now.")

    return "\n".join(prompt_parts)


def _generate_ai_strategy_section(
    company_name: str,
    cloud_vendor: str,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    discovery_notes_content: str | None = None
) -> str | None:
    """
    Generate AI strategy using Deep Research for board-level analysis.

    This uses a second Deep Research call to produce a comprehensive AI roadmap
    that's grounded in the company's actual business model, pain points, and
    the latest vendor capabilities.

    Outputs:
    - {company}_AI_Strategy_{date}.md  - Raw markdown
    - {company}_AI_Strategy_{date}.txt - Plain text
    - {company}_AI_Strategy_{date}.docx - Word document

    Args:
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference (azure, aws, gcp)
        company_research_path: Path to company research markdown (used as context)
        force_refresh_vendor: If True, regenerate vendor research even if current
        discovery_notes_content: Optional freeform meeting insights from discovery

    Returns:
        Path to the generated DOCX file, or None if generation failed
    """
    from datetime import datetime

    from primr.ai.deep_research import ResearchStatus, get_deep_research_client
    from primr.config.settings import get_settings
    from primr.output.markdown_converter import markdown_to_docx
    from primr.output.output_utils import OUTPUT_DIR

    # =================================================================
    # PRE-FLIGHT VALIDATION - Check everything BEFORE expensive API call
    # =================================================================
    preflight_errors = []

    # 1. Validate company name
    if not company_name or not company_name.strip():
        preflight_errors.append("Company name is required for AI strategy generation")

    # 2. Validate cloud vendor
    valid_vendors = ["azure", "aws", "gcp", "agnostic"]
    if cloud_vendor.lower() not in valid_vendors:
        preflight_errors.append(f"Invalid cloud vendor: {cloud_vendor}. Must be one of: {', '.join(valid_vendors)}")

    # 3. Validate API key is configured
    settings = get_settings()
    if not settings.api.gemini_key:
        preflight_errors.append("GEMINI_API_KEY not configured in .env")

    # 4. Validate company research path if provided
    if company_research_path:
        if not os.path.exists(company_research_path):
            preflight_errors.append(f"Company research file not found: {company_research_path}")
        elif os.path.getsize(company_research_path) == 0:
            preflight_errors.append(f"Company research file is empty: {company_research_path}")

    # 5. Check output directory is writable
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_file = os.path.join(OUTPUT_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        preflight_errors.append(f"Output directory not writable: {OUTPUT_DIR} ({e})")

    # ABORT if any pre-flight errors
    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        console.error("Fix these issues before running expensive Deep Research")
        return None

    console.info("Pre-flight checks passed")
    # =================================================================

    try:
        # Build the AI Strategy prompt
        prompt = _build_ai_strategy_prompt(company_name, cloud_vendor, discovery_notes_content)

        # Prepare context files if we have company research
        context_files = []
        if company_research_path and os.path.exists(company_research_path):
            context_files.append(company_research_path)

        # Get vendor-specific research (auto-generates if needed)
        vendor_doc_paths = []
        if cloud_vendor.lower() != "agnostic":
            # Force refresh if requested
            if force_refresh_vendor:
                console.info(f"Force refreshing {cloud_vendor.upper()} vendor research...")
                generated = _generate_vendor_research(cloud_vendor)
                vendor_doc_paths = [generated] if generated else []
            else:
                vendor_doc_paths = _get_or_generate_vendor_research(cloud_vendor)

            # Add vendor-specific research files as context
            for vendor_doc_path in vendor_doc_paths:
                if vendor_doc_path and os.path.exists(vendor_doc_path):
                    context_files.append(vendor_doc_path)

            if vendor_doc_paths:
                console.info(f"Using {len(vendor_doc_paths)} {cloud_vendor.upper()} research doc(s) as context")

        # Always include agnostic/cross-industry AI research as additional context
        # This covers OpenAI, Anthropic, NVIDIA, Meta, etc. which is relevant for all vendors
        agnostic_path = _get_vendor_research_path("agnostic")
        if os.path.exists(agnostic_path):
            context_files.append(agnostic_path)
            console.info("Using cross-industry AI research as additional context")

        # Run Deep Research for AI Strategy
        client = get_deep_research_client()

        def progress_callback(progress):
            if progress.message:
                console.info(f"AI Strategy: {progress.message}")

        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            client.research(
                query=prompt,
                output_format=None,  # Use the prompt directly
                on_progress=progress_callback,
                context_files=context_files if context_files else None,
                timeout=1800  # 30 min timeout for AI strategy
            )
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error("AI Strategy research failed")
            return None

        # Track AI Strategy usage (separate from main research)
        # Deep Research API doesn't expose tokens, so estimate from output
        ai_strategy_output_tokens = len(result.content) // 4  # ~4 chars per token
        ai_strategy_input_tokens = 50_000  # Estimated prompt + context

        from primr.utils.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        tracker.record_usage(
            mode="ai-strategy",
            company=company_name,
            input_tokens=ai_strategy_input_tokens,
            output_tokens=ai_strategy_output_tokens,
            duration_seconds=result.duration_seconds,
        )
        # Note: Don't save here - let the main research flow save all at once

        date_str = datetime.now().strftime("%m-%d-%Y")
        base_name = f"{company_name}_AI_Strategy_{date_str}"

        # Save markdown (.md)
        md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(result.content)
        console.ok(f"AI Strategy MD: {base_name}.md", show_time=False)

        # Save plain text (.txt)
        txt_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result.content)
        console.ok(f"AI Strategy TXT: {base_name}.txt", show_time=False)

        # Convert to DOCX
        docx_path = os.path.join(OUTPUT_DIR, f"{base_name}.docx")
        try:
            subtitle_parts = [datetime.now().strftime("%B %d, %Y")]
            # Clean subtitle: "December 18, 2024 | Azure" (no "Cloud Vendor:" prefix)
            subtitle_parts.append(cloud_vendor.title())
            subtitle = " | ".join(subtitle_parts)

            markdown_to_docx(
                markdown_text=result.content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle
            )
            console.ok(f"AI Strategy DOCX: {base_name}.docx", show_time=False)
        except PermissionError:
            # File locked - try with timestamp
            timestamp = datetime.now().strftime("%H%M%S")
            docx_path = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.docx")
            console.warn(f"Original file locked, saving as: {base_name}_{timestamp}.docx")
            markdown_to_docx(
                markdown_text=result.content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle
            )
        except Exception as e:
            console.warn(f"DOCX conversion failed: {e}")
            docx_path = md_path  # Fall back to MD path

        return docx_path

    except Exception as e:
        console.error(f"AI Strategy generation failed: {e}")
        logger.exception("AI Strategy error")
        return None


def _build_ai_strategy_prompt(
    company_name: str,
    cloud_vendor: str,
    discovery_notes_content: str | None = None
) -> str:
    """
    Build a Deep Research prompt for board-level AI strategy.

    This prompt produces a comprehensive AI roadmap covering all major AI domains:
    - Strategic thesis and prioritization
    - Productivity AI by persona
    - Automation and workflow
    - Conversational AI (internal/external)
    - Agentic AI connected to data/apps
    - Generative BI and analytics
    - Traditional AI/ML
    - Security and governance
    - Organizational structure (AI Practice Group)
    - Explicit deprioritization (what NOT to do)
    - Failure and experimentation model

    Args:
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference (azure, aws, gcp, agnostic)
        discovery_notes_content: Optional freeform meeting insights from discovery
    """
    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")

    vendor_names = {
        "azure": "Microsoft Azure",
        "aws": "Amazon Web Services (AWS)",
        "gcp": "Google Cloud Platform (GCP)",
        "agnostic": "all major cloud vendors (Azure, AWS, GCP)"
    }
    vendor_name = vendor_names.get(cloud_vendor.lower(), vendor_names["agnostic"])

    # Vendor-specific context with key services to research
    vendor_specific_guidance = {
        "azure": """
KEY AZURE AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):

Productivity & Copilots:
- Microsoft 365 Copilot (Word, Excel, PowerPoint, Outlook, Teams)
- Copilot Studio (build custom copilots and agents)
- Work IQ (personalized AI based on work patterns)

Agentic AI & Automation:
- Agent 365 (AI agent control plane, governance, monitoring)
- Foundry (unified AI platform for building and deploying agents)
- Power Automate with AI Builder
- Semantic Kernel for agent orchestration

Data & Analytics:
- Microsoft Fabric (unified analytics platform)
- Fabric IQ (semantic layer for AI-ready data)
- Azure AI Search (vector search, RAG)
- Power BI with Copilot

AI Development:
- Azure OpenAI Service (GPT-4, GPT-4o, o1 models)
- Azure AI Foundry (model catalog, fine-tuning)
- GitHub Copilot for developers

Security & Governance:
- Entra Agent ID (identity for AI agents)
- Microsoft Purview (data governance, compliance)
- Microsoft Defender for Cloud (AI security)
- Responsible AI dashboard

Search for the latest announcements from Microsoft Ignite 2025 and recent Azure updates.
""",
        "aws": """
KEY AWS AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):

Productivity & Assistants:
- Amazon Q (AI assistant for business and developers)
- Amazon Q in Connect (customer service AI)
- Amazon Q Business (enterprise knowledge assistant)

Agentic AI & Automation:
- Amazon Bedrock Agents (autonomous AI agents)
- AWS Step Functions for AI orchestration
- Amazon Bedrock Flows (visual agent builder)

Data & Analytics:
- Amazon SageMaker (ML platform)
- Amazon Bedrock Knowledge Bases (RAG)
- Amazon QuickSight Q (natural language BI)
- AWS Glue for data integration

AI Development:
- Amazon Bedrock (Claude, Llama, Titan, Mistral models)
- Amazon SageMaker JumpStart (model hub)
- Amazon CodeWhisperer for developers
- PartyRock (no-code AI app builder)

Security & Governance:
- Amazon Bedrock Guardrails (content filtering, PII protection)
- AWS IAM for AI access control
- Amazon Macie (data security)
- AWS CloudTrail for AI audit logging

Search for the latest announcements from AWS re:Invent 2024 and recent AWS updates.
""",
        "gcp": """
KEY GOOGLE CLOUD AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):

Productivity & Assistants:
- Gemini for Google Workspace (Docs, Sheets, Slides, Gmail, Meet)
- Gemini for Google Cloud (cloud console assistant)
- NotebookLM (AI research assistant)

Agentic AI & Automation:
- Vertex AI Agent Builder (build and deploy agents)
- Vertex AI Extensions (connect agents to APIs)
- Google Cloud Workflows for orchestration

Data & Analytics:
- BigQuery with Gemini (natural language SQL)
- Vertex AI Search (enterprise search)
- Looker with Gemini (conversational BI)
- Dataplex for data governance

AI Development:
- Vertex AI (Gemini Pro, Gemini Ultra, PaLM models)
- Vertex AI Model Garden (model catalog)
- Gemini Code Assist for developers
- Vertex AI Studio (prompt design, tuning)

Security & Governance:
- Vertex AI Model Monitoring
- Google Cloud IAM for AI
- Data Loss Prevention API
- Cloud Audit Logs

Search for the latest announcements from Google Cloud Next 2024 and recent GCP updates.
""",
        "agnostic": """
MULTI-CLOUD AI STRATEGY (search for latest as of {current_date}):

Compare and recommend the best services across Azure, AWS, and GCP for each use case.
Consider:
- Which vendor has the strongest offering for each domain?
- Interoperability and avoiding vendor lock-in
- Cost comparison across platforms
- Enterprise readiness and support

Key areas to compare:
- Foundation models: Azure OpenAI vs Amazon Bedrock vs Vertex AI
- Productivity AI: M365 Copilot vs Amazon Q vs Gemini for Workspace
- Agent platforms: Copilot Studio vs Bedrock Agents vs Agent Builder
- Data platforms: Fabric vs SageMaker/Bedrock vs BigQuery/Vertex
- Governance: Purview vs Bedrock Guardrails vs Vertex AI governance

Search for the latest announcements from all three vendors' recent conferences.
"""
    }

    vendor_guidance = vendor_specific_guidance.get(cloud_vendor.lower(), vendor_specific_guidance["agnostic"])
    vendor_guidance = vendor_guidance.format(current_date=current_date)

    vendor_context = f"""
CLOUD VENDOR FOCUS: {vendor_name}

CRITICAL RESEARCH REQUIREMENT:
You MUST actively search for and cite the LATEST AI services and capabilities from {vendor_name}
as of {current_date}. Do NOT rely on training data. AI technology changes monthly.

You have access to context files with the latest vendor announcements and capabilities.
USE THESE CONTEXT FILES as your primary source for current technology recommendations.

{vendor_guidance}

IMPORTANT: Search for additional information to verify current availability and pricing.
Cite specific announcement dates and sources for all technology recommendations.
"""

    return f"""You are a senior AI strategy consultant. Generate a comprehensive AI roadmap for board-level decision making.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# AI Strategy: {company_name}

**Prepared by:** Primr Research System
**Date:** {current_date}

---

Then continue with the sections below.

=============================================================================
RESEARCH INSTRUCTIONS
=============================================================================

CRITICAL: This strategy must reflect the AI landscape as of {current_date}.
AI technology evolves rapidly. You MUST actively search for the latest announcements,
services, and capabilities. Do NOT rely on potentially outdated training data.
Every technology recommendation must be verified and cited per the Research Protocol below.

You have access to research about {company_name} in the context files. Use that foundation
to develop a comprehensive AI strategy that their CIO and board would actually use.

AUDIENCE CLARIFICATION:
This strategy is an internal planning artifact. Recommendations represent proposed directions to evaluate, not commitments or final decisions.

THE GOAL: Produce an AI roadmap that answers "What should we actually do with AI, and why?"
This is not a generic list of AI buzzwords. It's a strategic document that connects AI
capabilities to THIS company's specific business model, pain points, competitive pressures,
and organizational reality. The intent is to help leadership make confident, well-sequenced decisions, not to prescribe a single correct path.

=============================================================================
RESEARCH AND VALIDATION PROTOCOL
=============================================================================

For every vendor service, tool, or capability named in this document:

1. **Verify current name**: Confirm the service still exists and has not been renamed or deprecated
2. **Status**: Note if GA (Generally Available) or Preview/Beta
3. **Region availability**: Flag if limited to specific regions
4. **Compliance certifications**: Note relevant certifications (SOC2, HIPAA, FedRAMP) if applicable
5. **Citation**: Link to official product page or release note with date (e.g., "Announced Nov 2024")
6. **Pricing**: If pricing varies, cite pricing page and state assumptions (users, tokens, volume)
7. **Unconfirmed flag**: If anything cannot be verified through search, mark as "UNCONFIRMED" and offer an alternative

This protocol reduces confident but incorrect vendor claims.

=============================================================================
STRATEGIC CONTEXT
=============================================================================

THE AGENTIC TRANSFORMATION
We are in the "Agentic Era" where AI evolves from passive assistants to proactive agents
capable of planning, reasoning, and executing multi-step workflows autonomously. The key
distinction is between "AI-enabled" (AI bolted onto legacy processes) vs "AI-native"
(intelligence as the foundational operating substrate). The competitive advantage lies
not in "using AI" but in "becoming agentic." Not every function needs to become agentic
immediately. The strategy must distinguish where autonomy creates real economic leverage
versus where it adds unnecessary risk.

HEURISTICS AND RULES OF THUMB (internal planning guidance, not cited facts):
- The "10-20-70 Rule": Allocate roughly 10% effort to algorithms, 20% to technology
  infrastructure, and 70% to people, processes, and cultural transformation.
  In plain language: most AI projects fail due to change management, not technology.
- The "J-Curve": Expect productivity to dip during the learning phase before surging.
  Leadership must be prepared for a 2-4 month adjustment period.
- Default to RAG over fine-tuning for 90% of enterprise use cases. Fine-tune only when
  you need to change the model's style, format, or domain-specific reasoning.

The output should give them:
1. A clear strategic thesis: AI-enabled vs AI-native, and the path between
2. A framework for thinking about AI across ALL domains
3. 5 specific Quick Wins they can start in 90 days (with ROI models)
4. 5 specific Bigger Bets for transformational impact
5. 3 things they should explicitly NOT pursue (deprioritization)
6. ROI frameworks using the appropriate model (productivity, revenue, or risk)
7. An organizational model with governance "traffic light" system
8. A target AI architecture posture to prevent tool sprawl

CONFIDENCE LABELING RULE:
All recommendations must be labeled as one of:
- "Low-regret / proven pattern" - widely adopted, strong evidence base
- "Context-dependent bet" - success depends on company-specific factors
- "Exploratory / frontier" - emerging capability, higher uncertainty
Never present a recommendation without one of these labels. Confidence labels reflect uncertainty in outcomes, not confidence in the team's ability to execute.

{vendor_context}

FORMATTING RULES:
- Write in full paragraphs for strategic sections
- Use bullets only for specific recommendations or lists
- No em-dashes, use commas or periods
- Tone: Strategic and direct, like a CIO presenting to the board
- Avoid hype language. Prefer operational language over visionary claims.
- Cite sources per the Research and Validation Protocol above
- For each recommendation, include: Business Case, Technology, ROI Model, Timeline
- The final Board Summary must fit on ONE PAGE (approximately 500-600 words)

=============================================================================
DOCUMENT STRUCTURE
=============================================================================

## AI Strategic Thesis (Recommended Direction)

Based on our research into {company_name}'s business model, industry, and competitive landscape, we recommend the following strategic thesis. This is a PROPOSED direction to discuss with leadership, not an assessment of their current plans.

**Recommended Transformation Path**: Based on their industry and business model, should {company_name} pursue:
- "AI-enabled" (AI bolted onto existing processes for efficiency) - lower risk, faster wins
- "AI-native" (intelligence as the operating substrate) - higher investment, transformational potential

**Proposed Primary Value Lever**: Based on their competitive position and industry dynamics, where should AI investment focus?
- Cost reduction and operational efficiency?
- Revenue growth and customer experience?
- Risk reduction and compliance?
- Competitive differentiation?

**Recommended Priorities**: Based on their business, what should they focus on first?

**Suggested Deprioritizations**: What should they explicitly NOT pursue in the near term, and why?
- Include the condition under which they should revisit
- Include the signal that would indicate the condition has changed

**Change Management Reality**: Most AI projects fail due to change management, not technology. Recommend allocating 70% of AI budget to people, processes, and cultural transformation.

Be specific to {company_name}'s situation. Avoid generic statements like "AI will transform the business." Instead: "Based on {company_name}'s position in [industry], we recommend focusing AI investment on [specific area] because [specific reason]. This could target [estimated impact]. We suggest deferring [specific thing] until [specific condition]."

## Executive Summary

The "so what" for the board. 2-3 paragraphs covering:
- Why AI matters for THIS company specifically (competitive pressure, efficiency opportunity)
- The recommended investment level and expected ROI
- The 3 most important things to do in the next 12 months

## Likely Current State (Hypotheses to Validate)

IMPORTANT: We do NOT have visibility into {company_name}'s internal systems, data platforms, or organizational readiness. The following are HYPOTHESES based on:
- Their industry and company size
- Public signals (job postings, press releases, tech stack mentions)
- Typical patterns for companies in their sector

Frame each assessment as "Based on [evidence], we hypothesize..." and note what we'd want to validate in conversation.

### Data Platform Maturity (Hypothesis)
Based on their industry and size, hypothesize their likely data situation:
- **Likely data sources**: What systems probably generate their core business data?
- **Probable challenges**: Based on industry patterns, what data debt might they face?
- **Signals we observed**: Any public mentions of data initiatives, cloud migrations, or analytics investments?

Frame as: "Companies of this size in this industry typically face [X]. We'd want to understand their specific situation."

### Technology Signals (What We Can Observe)
Based on public information (job postings, press releases, tech blog posts, conference talks):
- **Cloud posture**: Any signals about their cloud provider or migration status?
- **Tech stack hints**: What technologies appear in their job postings?
- **Digital maturity signals**: E-commerce sophistication, mobile apps, API mentions?

Note: This is inference from public signals, not confirmed knowledge.

### Organizational Readiness (Industry Baseline)
Based on typical patterns for their industry and size:
- **AI adoption curve**: Where do companies like this typically sit on AI maturity?
- **Change management capacity**: What's typical for organizations of this scale?
- **Likely constraints**: Budget cycles, regulatory requirements, talent availability?

Frame as hypotheses to explore, not assertions about their actual state.

### Common Anti-Patterns to Discuss
These are common failure modes we'd want to explore with leadership (not accusations):
- **Pilot proliferation**: Many companies have dozens of disconnected AI PoCs. Worth asking about their current AI initiatives.
- **Tool sprawl**: Without governance, teams often adopt conflicting AI tools. Worth understanding their current landscape.
- **Data foundation gaps**: AI projects often stall on data quality. Worth exploring their data readiness.

## Competitive AI Landscape

Be specific about the competitive context:
- **One competitor ahead on AI**: Who is doing AI better? What specifically are they doing? What is the gap?
- **One peer making common AI mistakes**: What mistakes should {company_name} avoid? (e.g., pilot proliferation, tool sprawl, no governance)
- **Value at stake over 24 months**: What value could be protected or created by acting on AI?

Framing Guidance: When discussing the cost of inaction, emphasize the value that could be protected or created by acting, not a presumption of failure if action is delayed. Express as a range of potential impacts, not a single deterministic outcome. Present best-case, likely-case, and worst-case scenarios rather than asserting a single inevitable future.

## Recommended AI Architecture Posture

Based on the target cloud vendor and industry best practices, here's what {company_name} SHOULD build toward. These are recommendations, not assessments of their current state.

### Knowledge Grounding Pattern (RAG as Default)
For most enterprise AI use cases, recommend:
- Retrieval-Augmented Generation (RAG) as the default pattern for knowledge grounding
- Specific vector database and embedding strategy for the target cloud vendor
- Fine-tuning reserved only for style/format changes or domain-specific reasoning
- Data sources to prioritize: internal documents, wikis, customer data, operational databases

### Identity, Access, and Audit (Recommended Framework)
What they should implement:
- User authentication to AI systems (SSO integration)
- Service principal / managed identity for AI agents calling backend systems
- Audit logging for all AI interactions (prompts, responses, actions taken)
- PII handling policies for prompts and responses

### Agent Boundaries and Kill Switches (Governance Model)
Recommended guardrails:
- Define where agents can act autonomously vs. require human approval
- Set dollar/impact thresholds for human-in-the-loop
- Implement runaway agent detection and automatic stopping
- Establish escalation paths for agent failures

### Reusable Platform Components (Build Once, Use Many)
To prevent tool sprawl, recommend building shared infrastructure:
- Common prompt templates and guardrails library
- Shared vector stores and knowledge bases
- Centralized model endpoints and API gateway
- Evaluation and monitoring infrastructure
- Cost allocation and chargeback mechanisms

=============================================================================
AI OPPORTUNITY DOMAINS
=============================================================================

For EACH domain below, provide specific recommendations tailored to {company_name}.
Do not give generic advice. Connect every recommendation to their actual business.

### Productivity AI by Persona

Different user groups need different AI tools. For {company_name}, identify 3-4 key personas
and recommend specific productivity AI for each:

Example personas to consider (adapt to their business):
- Executives: Strategic insights, board prep, competitive intelligence
- Sales/Account teams: Customer research, proposal generation, CRM enrichment
- Operations: Process documentation, troubleshooting guides, knowledge capture
- Customer service: Response drafting, knowledge lookup, case summarization
- Finance: Report generation, variance analysis, forecasting assistance
- Engineering/Technical: Code assistance, documentation, design review

For each persona:
- What are their daily pain points?
- What AI tools would help? (Be specific: Copilot for M365, custom GPTs, etc.)
- What is the productivity gain? (hours saved per week, quality improvement)
- What is the adoption approach?

### Process Automation

Identify 3-5 high-value automation opportunities specific to {company_name}'s operations:

Consider:
- Document processing (invoices, orders, contracts, compliance docs)
- Workflow automation (approvals, routing, notifications)
- Data entry and validation
- Report generation and distribution
- Integration between systems

For each opportunity:
- What is the current manual process?
- What is the volume? (transactions/day, hours spent)
- What technology would automate it? (Power Automate, custom agents, RPA)
- What is the ROI? (FTE equivalent, error reduction, speed improvement)

### Conversational AI

**Internal Conversational AI (Employee-Facing)**
- Knowledge base chatbots for HR, IT, policies
- Technical support assistants
- Training and onboarding assistants
- Internal search and discovery

**External Conversational AI (Customer-Facing)**
- Customer service chatbots
- Sales assistants and product finders
- Order status and self-service
- Technical support for customers

For each recommendation:
- What is the use case specific to {company_name}?
- What is the expected deflection rate or efficiency gain?
- What technology? (Copilot Studio, custom agents, third-party)
- What is the customer/employee experience improvement?

### Agentic AI (Connected to Data, Apps, Services)

This is the frontier: AI agents that can take actions, not just answer questions.
Identify 2-3 agentic AI opportunities for {company_name}:

Consider:
- Multi-step workflows that span multiple systems
- Decision-making processes that could be augmented or automated
- Complex research and analysis tasks
- Orchestration across CRM, ERP, and operational systems

For each:
- What is the end-to-end process?
- What systems need to be connected?
- What decisions can the agent make vs. escalate to humans?
- What governance is needed?

Reference the latest agentic AI capabilities from {vendor_name} (search for current announcements).

### Generative BI and Analytics

Modern analytics is moving from dashboards to natural language queries and AI-generated insights.
Recommend how {company_name} should evolve their analytics:

Consider:
- Natural language querying of business data
- Automated insight generation and anomaly detection
- AI-powered forecasting and scenario modeling
- Self-service analytics for business users
- Integration with data platforms (Fabric, Databricks, Snowflake)

For {company_name}:
- What are their key business questions?
- What data would power AI analytics?
- What is the path from current BI to AI-powered analytics?
- What is the business impact of faster, better insights?

### Traditional AI/ML

Not everything is generative AI. Identify opportunities for traditional ML:

Consider:
- Demand forecasting and inventory optimization
- Pricing optimization
- Customer churn prediction
- Fraud detection
- Predictive maintenance
- Recommendation engines

For {company_name}:
- What predictions would be valuable?
- What data do they have to train models?
- Build vs. buy vs. use pre-built models?
- What is the ROI of better predictions?

### Security, Governance, and Responsible AI

All AI must be secure and governed. Recommend a framework for {company_name}:

Cover:
- Data governance: What data can AI access? Classification, permissions
- Model governance: How are models approved, monitored, updated?
- Security: Prompt injection protection, data leakage prevention, access controls
- Responsible AI: Bias detection, transparency, human oversight
- Compliance: Industry-specific requirements (HIPAA, PCI, SOX, etc.)

Reference the latest governance tools from {vendor_name} as listed in the vendor guidance above.

=============================================================================
PRIORITIZATION FILTERS
=============================================================================

Before presenting recommendations, evaluate all candidate initiatives using these 5 filters.
For each of the top 10 recommendations (5 Quick Wins + 5 Bigger Bets), include a brief
sentence explaining why it scored well on these criteria:

- **Expected Business Impact**: Revenue, cost savings, risk reduction, or strategic value
- **Data Readiness**: Is the required data available, clean, and accessible?
- **Integration Complexity**: How many systems must connect? Are APIs available?
- **Adoption and Change Load**: How much workflow change and training is required?
- **Risk and Compliance Exposure**: Data sensitivity, regulatory requirements, autonomy level

This ensures recommendations are explainable and defensible, not just technically interesting.

=============================================================================
STRATEGIC RECOMMENDATIONS
=============================================================================

## ROI Model Selection

Use the appropriate ROI model for each recommendation type:

**Productivity ROI** (for labor savings and throughput)
```
ROI = ((Hours Saved/Week x 52 x Hourly Cost x Adoption Rate) - Annual Cost) / Annual Cost
```
- Hours saved per week per user (be conservative: 1-3 hours typical)
- Number of target users
- Assumed adoption rate (use 40-60% for credibility, not 100%)
- Hourly fully-loaded cost
- Annual license/infrastructure cost

**Revenue ROI** (for conversion, retention, pricing initiatives)
```
Revenue Impact = (Baseline Metric x Improvement % x Revenue per Unit) - Implementation Cost
```
- Baseline metric (conversion rate, churn rate, average deal size)
- Expected improvement percentage (cite benchmarks where available)
- Revenue per unit affected
- Implementation and ongoing costs

**Risk ROI** (for compliance, security, error reduction)
```
Risk ROI = (Expected Loss Reduction + Compliance Cost Avoidance) - Implementation Cost
```
- Current exposure (fines, breach costs, error remediation)
- Expected reduction percentage
- Compliance cost avoidance (audit prep, manual controls)
- Implementation cost

For each recommendation, select the most appropriate model and show the calculation.

## Five Quick Wins (Start in 90 Days)

Quick Wins build organizational confidence, prove ROI, and fund future investments. They typically leverage off-the-shelf Copilot capabilities or established RAG patterns without custom model training.

For each Quick Win, provide:
- **The Opportunity**: What is it? (1-2 sentences)
- **Why It Matters for {company_name}**: Connect to their specific business pain point
- **Why It Won** (Prioritization): Must reference at least two prioritization filters and one constraint (data, change, risk, or cost)
- **Technology**: Specific tools/services (with citations per Research Protocol). Default to RAG over fine-tuning.
- **Implementation**: What does it take? (weeks, resources, dependencies)
- **ROI Calculation**: Use the appropriate model above with specific numbers
- **Success Metrics**: How do you verify "realized" vs "projected" savings?

Quick Win Categories (adapt to {company_name}):
- Personal Productivity (M365 Copilot): 1-2 hours saved/week, 70% report quality improvement
- Knowledge Discovery (RAG bots): 50% reduction in time-to-find, 30% reduction in Tier 1 tickets
- Document Processing (AI Builder): 90% reduction in manual entry, days to minutes
- Coding Assistance (GitHub Copilot): 55% faster for repetitive tasks

## Five Bigger Bets (6-18 Month Horizon)

Big Bets are "AI-native" transformations that reshape core business processes. They require custom development, deep integration, and agentic capabilities. High risk but competitive differentiation.

For each Bigger Bet, provide:
- **The Opportunity**: What is it? This should be an "AI-native" transformation, not just AI-enabled.
- **Why It Matters for {company_name}**: Strategic importance, competitive moat creation
- **Why It Won** (Prioritization): Must reference at least two prioritization filters and one constraint (data, change, risk, or cost)
- **Technology Architecture**:
  - Specific tools/services (with citations per Research Protocol)
  - RAG vs Fine-Tuning decision (default to RAG unless style/format change required)
  - Agent orchestration approach (single agent vs multi-agent)
- **Implementation**: Months, team composition, investment level, dependencies
- **ROI Model**: Use the appropriate model (Productivity, Revenue, or Risk) with specific numbers
  - Baseline being transformed (current cost, cycle time, error rate)
  - Target state metrics
  - Adoption curve assumptions (expect productivity to dip during learning before surging)
  - Time to breakeven
  - 3-year NPV if applicable
- **Risk Factors and Mitigation**: Technical, organizational, competitive risks
- **Governance Tier**: Green/Yellow/Red based on data sensitivity and autonomy level
- **Success Metrics**: Milestones at 6, 12, 18 months

Big Bet Categories (adapt to {company_name}):
- Agentic Operations: Autonomous agents monitoring signals, making decisions within parameters
- Generative Product/Service: AI-generated offerings that change the business model
- Autonomous Customer Service: Tier 1 fully handled by agents with resolution authority
- Legacy Modernization: AI agents analyzing and migrating legacy systems

## Three Things NOT to Pursue (Explicit Deprioritization)

Boards care deeply about what they are choosing NOT to fund. Identify 3 AI initiatives or domains that {company_name} should explicitly deprioritize in the next 12-18 months:

Optionality Guardrail: Deprioritized initiatives must include:
- The condition under which we would revisit them
- The signal that would indicate the condition has changed
Never frame deprioritization as permanent or use "only viable path" language.

For each deprioritized item:
- **What it is**: The AI initiative or domain being deprioritized
- **Why it is tempting**: Why might someone advocate for this?
- **Why NOT now**: What makes this wrong for {company_name} at this time?
- **Revisit trigger**: Under what specific, measurable conditions should this be reconsidered?
- **Signal to watch**: What observable signal would indicate the trigger condition has changed?

Examples of valid deprioritization reasons:
- Data foundation not ready (revisit when data debt score improves to X)
- Higher-ROI opportunities should come first (revisit after Quick Wins prove value)
- Market/technology not mature enough (revisit when vendor X releases GA version)
- Organizational capacity constraints (revisit after CoE is staffed)
- Competitive dynamics do not require it yet (revisit if competitor Y launches)

=============================================================================
ORGANIZATIONAL MODEL
=============================================================================

## AI Practice Group Structure

Recommend how {company_name} should organize for sustained AI innovation:

**Governance Model: The Federated Approach**
Best practice is a Federated (Hybrid) Model: Central CoE sets "non-negotiables" (security, responsible AI, tech stack) while embedded AI Champions in business units drive execution.

Core CoE Roles:
- AI Strategy Lead (aligns with corporate strategy)
- AI Governance/Ethics Officer (compliance, bias audits, risk thresholds)
- Data Stewards (quality, lineage, access policies)
- MLOps Engineers (deployment, drift monitoring, retraining)
- Change Management Lead (adoption, training, workforce anxiety)

**Governance "Traffic Light" System for AI Approval**

**Green (Low Risk)**: Internal, non-PII data. Standard productivity tasks.
- Tools: M365 Copilot, Pre-built Agents
- Approval: Auto-approved / Department Lead

**Yellow (Medium Risk)**: Customer data, internal code, proprietary IP.
- Tools: Azure AI Foundry with RAG, Copilot Studio with specific connectors
- Approval: AI CoE Review required; Standard content filters enabled

**Red (High Risk)**: Health/Financial decisions, high-volume automated actions, autonomous external agents.
- Tools: Custom Models with strict Human-in-the-Loop gates and Red Teaming
- Approval: Board/Ethics Committee sign-off required

**Key Roles to Hire or Develop**
- What skills do they need? (AI engineers, prompt engineers, data scientists, AI product managers)
- Build vs. hire vs. partner?
- Training and upskilling existing staff

**Living Strategy Process**
- How often should AI strategy be reviewed? (quarterly recommended)
- How do they stay current with rapidly evolving technology?
- How do they capture learnings and scale successes?

## Operating Model for Experimentation and Failure

AI initiatives will fail. A mature organization plans for this:
- **Expected failure rate**: What percentage of AI pilots should be expected to fail or pivot? (20-40% is healthy)
- **Fast failure detection**: How quickly can {company_name} determine an initiative is not working? What signals trigger review?
- **Pivot authority**: Who has authority to stop, pivot, or kill an AI project? At what investment threshold?
- **Learning capture**: How are lessons from failed initiatives captured and shared?
- **Psychological safety**: How does leadership signal that smart failures are acceptable?

This section signals maturity to the board and reassures them that risk is being managed, not ignored.

## Investment Framework

**Year 1 Investment Estimate**
- Technology costs (licenses, compute, services)
- People costs (new hires, training, contractors)
- Implementation costs (consulting, integration)
- Total investment range

**ROI Framework**
- How to measure AI ROI (productivity gains, cost savings, revenue impact)
- Payback period expectations
- How to track and report to the board

**Build vs. Buy vs. Partner**
- When to build custom solutions
- When to buy off-the-shelf
- When to partner with consultants or vendors

=============================================================================
RISK ANALYSIS
=============================================================================

## The Cost of Inaction
"Wait and see" is a degradation strategy. Quantify the cost of NOT acting:
- **Data Debt Accumulation**: Every day without unified data governance increases future integration cost. Data quality degrades, "cleanup tax" rises.
- **Competitive Disadvantage**: Competitors using agentic AI for 24/7 service or dynamic pricing will seize market share expensive to recapture.
- **Talent Drain**: Top talent expects modern tools. Forcing developers to code without AI assistants is a retention risk.
- **Efficiency Gap**: Creates pricing disadvantage as competitors operate at lower cost.

## Technology Risks
- Vendor lock-in considerations
- Model obsolescence (AI changes fast, plan for it)
- Integration complexity (especially with legacy systems lacking APIs)
- Data quality dependencies (garbage in, garbage out)
- Runaway costs from agentic loops without FinOps controls

## Organizational Risks
- Productivity may dip during learning phase before surging. Leadership must be prepared for a 2-4 month adjustment.
- Change resistance and adoption challenges
- Skills gaps (AI fluency, not just literacy)
- Competing priorities and "initiative fatigue"

## AI-Specific Security Risks
- **Jailbreaks and Prompt Injection**: Attackers manipulating agents to reveal data or perform unauthorized actions
- **Hallucinations**: Mitigation requires strict Groundedness Checks and Human-in-the-Loop for high-stakes decisions
- **Model Drift**: Agents degrade as data patterns change; requires continuous monitoring

=============================================================================
BOARD SUMMARY (ONE PAGE)
=============================================================================

CRITICAL: This section must fit on ONE PAGE (approximately 500-600 words).
This is what the board will actually read. Everything else is supporting detail.

**Strategic Thesis** (1 paragraph)
Restate the AI strategic thesis from the beginning. This is what the board is aligning around.
Include: current state, transformation goal, dominant value lever, what we will NOT do.

**The 5 Most Important Decisions**

Present as a concise list:
- [Initiative 1]: $X investment, Y% ROI / $Z savings, Q1-Q2
- [Initiative 2]: $X investment, Y% ROI / $Z savings, Q1-Q3
- [Initiative 3]: $X investment, Y% ROI / $Z savings, Q2-Q4
- [Initiative 4]: $X investment, Y% ROI / $Z savings, Q2-Q4
- [Initiative 5]: $X investment, Y% ROI / $Z savings, Q3-Q4

**Investment Summary**

Total Year 1 Investment Ask:
- Quick Wins: $X
- Bigger Bets (initial funding): $Y
- Organizational/People (CoE, training, change management): $Z
- **Total: $X+Y+Z**

**Expected Year 1 Returns**
- Hard savings: $X
- Productivity gains: Y FTE equivalent
- Risk reduction: [quantified if possible]
- Strategic value: [qualitative, 1 sentence]

**What We Are Choosing NOT to Do**

Brief restatement of the 3 deprioritized items:
- [Item]: [One sentence why not now, when to revisit]
- [Item]: [One sentence why not now, when to revisit]
- [Item]: [One sentence why not now, when to revisit]

**Key Risks Acknowledged**

One sentence each on the top 3 risks and how they are being managed.

=============================================================================
NEXT STEPS (Next 30 Days)
=============================================================================

Specific, actionable next steps with owners:
- [Action item] - Owner: [Role] - By: [Date]
- [Action item] - Owner: [Role] - By: [Date]
- [Action item] - Owner: [Role] - By: [Date]
- [Action item] - Owner: [Role] - By: [Date]
- [Action item] - Owner: [Role] - By: [Date]

=============================================================================
CITATIONS
=============================================================================

All vendor services, capabilities, and benchmarks cited in this document should be listed here
with their source URLs and dates. Group by section for easy reference.

=============================================================================
DOWNSTREAM TRANSLATION NOTE
=============================================================================

This output is intended to inform internal thinking and deck creation. When reused externally, conclusions should be softened, hypotheses foregrounded, and language reframed for diplomacy.
"""


def process_csv(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    cloud_vendor: str = "azure",
    no_qa: bool = False
) -> None:
    import csv
    console.header("Batch Processing", file_path)
    console.info(f"Mode: {mode}")

    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = row.get("company_name", "").strip()
            website = row.get("website", "").strip()
            if company or website:
                try:
                    perform_research(
                        company,
                        ensure_valid_url(website) if website else None,
                        mode=mode,
                        citation_style=citation_style,
                        ai_strategy=ai_strategy,
                        cloud_vendor=cloud_vendor,
                        no_qa=no_qa
                    )
                except Exception as e:
                    console.error(f"Failed: {company or website} - {e}")


def cleanup():
    gc.collect()


atexit.register(cleanup)


def _list_recent_outputs():
    """List recent research outputs from the output directory."""
    import glob
    from datetime import datetime

    output_files = glob.glob(os.path.join(OUTPUT_DIR, "*.docx"))
    if not output_files:
        print("No recent outputs found.")
        return

    # Sort by modification time, newest first
    output_files.sort(key=os.path.getmtime, reverse=True)

    print("\nRECENT RESEARCH OUTPUTS")
    print("-" * 80)
    print(f"{'#':<3} {'Report':<40} {'Date':<12} {'Size':<8} {'QA Grade':<10}")
    print("-" * 80)

    for i, filepath in enumerate(output_files[:20], 1):
        filename = os.path.basename(filepath)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        size_kb = os.path.getsize(filepath) / 1024

        # Look for corresponding QA report
        qa_grade = _get_qa_grade_for_report(filepath)
        qa_display = f"{qa_grade}/100" if qa_grade is not None else "N/A"

        # Truncate filename if too long
        display_name = filename[:37] + "..." if len(filename) > 40 else filename

        print(f"{i:2}. {display_name:<40} {mtime.strftime('%Y-%m-%d'):<12} {size_kb:6.1f}KB {qa_display:<10}")

    if len(output_files) > 20:
        print(f"... and {len(output_files) - 20} more files")
    print("-" * 80)


def _get_qa_grade_for_report(report_path: str) -> int | None:
    """
    Get QA grade for a report by finding its corresponding QA report file.

    Args:
        report_path: Path to the main report file

    Returns:
        QA grade (0-100) or None if no QA report found
    """
    try:
        from pathlib import Path

        report_file = Path(report_path)
        # Extract company name from filename (remove extension and date)
        filename = report_file.stem

        # Remove common suffixes to get company name
        for suffix in ["_Strategic_Overview", "_Company_Overview", "_AI_Strategy"]:
            if suffix in filename:
                company_part = filename.split(suffix)[0]
                break
        else:
            company_part = filename

        # Look for QA report files
        output_dir = Path(OUTPUT_DIR)
        qa_patterns = [
            f"{company_part}*QA_Report*.txt",
            f"*{company_part}*QA_Report*.txt"
        ]

        qa_files = []
        for pattern in qa_patterns:
            matches = list(output_dir.glob(pattern))
            qa_files.extend(matches)

        if not qa_files:
            return None

        # Get the most recent QA file
        latest_qa = max(qa_files, key=lambda f: f.stat().st_mtime)

        # Parse the grade from the QA report
        content = latest_qa.read_text(encoding='utf-8')
        for line in content.split('\n'):
            if line.startswith('Quality Score:'):
                # Extract score like "Quality Score: 85/100"
                parts = line.split(':')[1].strip().split('/')
                if parts and parts[0].isdigit():
                    return int(parts[0])

        return None

    except Exception:
        return None


def _check_api_quota():
    """Check if Gemini API quota is available by making a lightweight test call."""
    from google import genai

    from primr.config.settings import get_settings

    settings = get_settings()

    if not settings.api.gemini_key:
        console.error("GEMINI_API_KEY not configured in .env")
        return

    console.banner("API Quota Check")
    console.info("Testing Gemini API availability...")

    try:
        client = genai.Client(api_key=settings.api.gemini_key)

        # Make a minimal API call to test quota
        response = client.models.generate_content(
            model=PrimrModels.FAST_MODEL,  # Use fast model for quick check
            contents="Say 'OK' in one word."
        )

        if response and response.text:
            console.ok("API quota is available")
            console.info("You can run research now.")
        else:
            console.warn("API responded but with empty content")

    except Exception as e:
        error_str = str(e).lower()

        if "resource_exhausted" in error_str and ("per_day" in error_str or "quota" in error_str):
            console.error("Daily API quota is EXHAUSTED")
            console.info("Options:")
            console.info("  1. Wait until quota resets (usually midnight PT)")
            console.info("  2. Upgrade your API plan at https://ai.google.dev")
            console.info("  3. Use a different API key")
        elif "429" in str(e):
            console.warn("Rate limited - try again in a few minutes")
        elif "invalid" in error_str and "key" in error_str:
            console.error("Invalid API key")
        else:
            console.error(f"API check failed: {e}")


def _list_strategies():
    """List available strategy modules from the strategies/ directory."""
    from primr.prompts.registry import get_registry

    console.banner("Available Strategy Modules")

    registry = get_registry()
    strategies = registry.discover()

    if not strategies:
        console.info("No strategy modules found.")
        console.info("Strategy modules are YAML files in src/primr/prompts/strategies/")
        return

    console.info(f"Found {len(strategies)} strategy module(s):\n")

    for strategy in strategies:
        status = ""
        # Check if it's a placeholder
        if strategy.config_path.exists():
            import yaml
            with open(strategy.config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                meta = data.get("meta", {})
                if meta.get("status") == "placeholder":
                    status = " (placeholder)"

        console.step(f"{strategy.name}{status}")
        console.info(f"  Display Name: {strategy.display_name}")
        if strategy.description:
            console.info(f"  Description: {strategy.description}")
        if strategy.data_sources:
            console.info(f"  Data Sources: {len(strategy.data_sources)} file(s)")
        print()

    console.info("Use --strategy <name> to generate a specific strategy (coming in v1.2.6)")


def _clean_temp_files():
    """Clean up temporary files from working directory."""
    import glob

    # Clean working directory
    working_dirs = glob.glob(os.path.join(WORKING_DIR, "*"))
    temp_files = glob.glob(os.path.join(WORKING_DIR, "*.tmp"))

    cleaned = 0

    # Remove empty working directories
    for d in working_dirs:
        if os.path.isdir(d):
            try:
                # Only remove if empty or contains only temp files
                contents = os.listdir(d)
                if not contents:
                    os.rmdir(d)
                    cleaned += 1
            except Exception:
                pass

    # Remove temp files
    for f in temp_files:
        try:
            os.remove(f)
            cleaned += 1
        except Exception:
            pass

    print(f"Cleaned {cleaned} temporary files/directories.")


def _open_file(filepath: str) -> None:
    """Open a file with the system default application."""
    import platform
    import subprocess

    try:
        if platform.system() == 'Windows':
            os.startfile(filepath)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', filepath], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', filepath], check=True)
    except Exception as e:
        console.warn(f"Could not open file: {e}")


def run_doctor():
    """
    Run system diagnostics to verify Primr is properly configured.

    Checks:
    - Python version
    - API keys (GEMINI_API_KEY, SEARCH_API_KEY, SEARCH_ENGINE_ID)
    - API key format validation
    - Playwright browsers
    - Output directory writable
    - Working directory writable
    - Cache directory accessible
    - API quota availability
    """
    from primr.utils.type_guards import ConfigSchema, validate_config

    console.banner("Primr Doctor")
    console.blank()

    all_passed = True
    warnings_count = 0

    # 1. Python version
    console.step("Environment")
    py_version = sys.version_info
    if py_version >= (3, 10):
        console.ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        console.error(f"Python {py_version.major}.{py_version.minor} (need 3.10+)")
        all_passed = False

    # 2. API Keys with enhanced validation
    console.step("API Configuration")

    # Build config dict from environment
    env_config = {
        "gemini_key": os.environ.get("GEMINI_API_KEY", ""),
        "search_key": os.environ.get("SEARCH_API_KEY", ""),
        "search_engine_id": os.environ.get("SEARCH_ENGINE_ID", ""),
    }

    # Define validation schema
    api_schema = ConfigSchema(
        required_keys=["gemini_key"],
        optional_keys={"search_key": "", "search_engine_id": ""},
        type_hints={"gemini_key": str, "search_key": str, "search_engine_id": str},
        validators={
            "gemini_key": lambda v: len(v) >= 10 if v else False,
            "search_key": lambda v: len(v) >= 10 if v else True,  # Optional
        }
    )

    # Validate config
    validate_config(env_config, api_schema)

    # Report validation results
    gemini_key = env_config.get("gemini_key", "")
    if gemini_key and len(gemini_key) >= 10:
        # Check format (Gemini keys typically start with "AI")
        if gemini_key.startswith("AI"):
            console.ok("GEMINI_API_KEY configured (valid format)")
        else:
            console.ok("GEMINI_API_KEY configured")
            console.warn("  Key format unusual (expected to start with 'AI')")
            warnings_count += 1
    else:
        console.error("GEMINI_API_KEY not set or invalid")
        console.info("  Get your key at: https://ai.google.dev/")
        all_passed = False

    search_key = env_config.get("search_key", "")
    if search_key and len(search_key) >= 10:
        console.ok("SEARCH_API_KEY configured")
    else:
        console.warn("SEARCH_API_KEY not set (optional, for Google Search)")
        warnings_count += 1

    search_engine = env_config.get("search_engine_id", "")
    if search_engine:
        console.ok("SEARCH_ENGINE_ID configured")
    else:
        console.warn("SEARCH_ENGINE_ID not set (optional, for Google Search)")
        warnings_count += 1

    # 3. Playwright browsers
    console.step("Dependencies")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright():
            console.ok("Playwright browsers available")
    except Exception as e:
        console.warn(f"Playwright not ready: {e}")
        console.info("  Run: playwright install chromium")
        warnings_count += 1

    # 4. Directory checks
    console.step("File System")

    # Output directory
    try:
        test_file = os.path.join(OUTPUT_DIR, ".primr_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        console.ok("Output directory writable")
    except Exception as e:
        console.error(f"Cannot write to output directory: {e}")
        all_passed = False

    # Working directory
    try:
        os.makedirs(WORKING_DIR, exist_ok=True)
        test_file = os.path.join(WORKING_DIR, ".primr_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        console.ok("Working directory writable")
    except Exception as e:
        console.error(f"Cannot write to working directory: {e}")
        all_passed = False

    # Cache directory
    try:
        cache_path = os.path.join(LOGS_DIR, "cache.db")
        if os.path.exists(cache_path):
            cache_size = os.path.getsize(cache_path) / (1024 * 1024)  # MB
            console.ok(f"Cache accessible ({cache_size:.1f} MB)")
        else:
            console.ok("Cache directory ready")
    except Exception as e:
        console.warn(f"Cache check failed: {e}")
        warnings_count += 1

    # 5. API quota check (quick test)
    console.step("API Connectivity")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=PrimrModels.FAST_MODEL,
                contents="Reply with exactly: hello",
            )
            # Check if we got any response at all (connection works)
            if response and (response.text or response.candidates):
                console.ok("Gemini API responding")
            else:
                # Still connected, just empty - not a failure
                console.ok("Gemini API connected")
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                console.error("Gemini API quota exceeded - wait and retry")
                all_passed = False
            elif "invalid" in error_str and "key" in error_str:
                console.error("Gemini API key is invalid")
                all_passed = False
            else:
                console.warn(f"Gemini API test failed: {e}")
                warnings_count += 1
    else:
        console.warn("Skipping API test (no key configured)")
        warnings_count += 1

    # 6. QA System Configuration
    console.step("Quality Assurance")
    try:
        from primr.qa.analyzer import QAAnalyzer
        from primr.qa.integration import QAIntegration

        # Test QA system initialization
        QAIntegration()
        qa_analyzer = QAAnalyzer()

        if qa_analyzer.ai_client:
            console.ok("QA system initialized")
            console.info(f"  QA Model: {qa_analyzer.model_name}")
        else:
            console.warn("QA system initialized but AI client unavailable")
            console.info("  QA will use fallback analysis if needed")
            warnings_count += 1

    except Exception as e:
        console.warn(f"QA system check failed: {e}")
        console.info("  QA analysis may not work properly")
        warnings_count += 1

    # Summary
    console.blank()
    if all_passed and warnings_count == 0:
        console.success_box("All checks passed", "Primr is ready to use")
    elif all_passed:
        console.success_box(f"Ready with {warnings_count} warning(s)", "Primr can run, but some features may be limited")
    else:
        console.error("Some checks failed - fix issues above before running research")

    return 0 if all_passed else 1


# Mode name mapping (new -> old internal names)
MODE_MAP = {
    "scrape": "scrape-only",
    "deep": "deep-research",
    "full": "complete",
    "parallel": "hybrid",
    # Also accept old names for backwards compatibility
    "structured": "structured",
    "deep-research": "deep-research",
    "complete": "complete",
    "hybrid": "hybrid",
    "scrape-only": "scrape-only",
}


# =============================================================================
# CLI ENTRY POINT (delegated to cli.py)
# =============================================================================
# The main() function is imported from cli.py at the top of this file.
# This avoids duplicate argument parsers and keeps CLI logic in one place.
main = _main_new  # Re-export from cli.py


# =============================================================================
# LEGACY COMPATIBILITY - Helper functions used by the old main()
# These are kept for any code that might import them directly.
# =============================================================================


def _legacy_main_removed():
    """
    The duplicate main() function has been removed.

    CLI logic is now centralized in cli.py. This module re-exports
    main = _main_new from cli.py for backward compatibility.
    """
    raise NotImplementedError("Use main() which delegates to cli.py")


if __name__ == "__main__":
    main()
