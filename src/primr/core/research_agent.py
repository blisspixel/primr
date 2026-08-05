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
    result = perform_research("Acme Corp", "https://acme.example")

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

# From cli module
# From ai_strategy module
from primr.core.ai_strategy import (
    CloudVendor,
    Platform,
)
from primr.core.ai_strategy_runtime import (
    build_ai_strategy_prompt as _build_ai_strategy_prompt_impl,
)
from primr.core.ai_strategy_runtime import (
    generate_ai_strategy_section as _generate_ai_strategy_section_impl,
)

# Backward-compatible re-export: the CLI entry point lives in cli.py, but
# ``primr.__main__`` and external callers import ``main`` from this module.
from primr.core.cli import main as main

# From deep_research_runner module
from primr.core.deep_research_runner import (
    DeepResearchConfig,
    DeepResearchMode,
)
from primr.core.fast_mode_helpers import (
    _compute_fast_report_qa_metrics,
    _enforce_fast_section_quality_guards,
)
from primr.core.fast_mode_helpers import (
    _parse_batch_sections as _parse_batch_sections,
)
from primr.core.fast_run_collection import collect_research_data
from primr.core.fast_run_gaps import deepen_research
from primr.core.fast_run_hiring import collect_fenced_hiring_block, collect_hiring_block
from primr.core.fast_run_sections import write_report_sections
from primr.core.fast_run_strategy import run_strategy_phase
from primr.core.fast_run_trust import polish_and_gate_fast_report
from primr.core.fast_run_validation import cross_validate_and_enrich
from primr.core.fast_run_workbook import build_day1_hypothesis_tree, generate_analysis_workbook
from primr.core.insights_assembly import build_combined_insights, build_external_sources_raw
from primr.core.platform_mapper import restore_strategy_platforms
from primr.core.report_cleanup import (
    _INTERNAL_REFERENCE_TERMS as _INTERNAL_REFERENCE_TERMS,
)
from primr.core.report_cleanup import (
    _clean_fast_report_output,
    _preserves_report_structure,
    _strip_internal_source_placeholders,
)
from primr.core.report_cleanup import (
    _extract_markdown_headings as _extract_markdown_headings,
)
from primr.core.report_cleanup import (
    _rewrite_cite_from_url_tags as _rewrite_cite_from_url_tags,
)
from primr.core.report_cleanup import (
    _rewrite_inline_confidence_citations as _rewrite_inline_confidence_citations,
)
from primr.core.report_cleanup import (
    _sanitize_numeric_cite_bracket as _sanitize_numeric_cite_bracket,
)
from primr.core.report_cleanup import (
    _strip_unresolved_section_cross_references as _strip_unresolved_section_cross_references,
)
from primr.core.resilience_listeners import (
    _build_health_listener as _build_health_listener,
)
from primr.core.run_state_io import (
    _append_background_abort as _append_background_abort,
)
from primr.core.run_state_io import (
    _append_model_health_event as _append_model_health_event,
)
from primr.core.run_state_io import (
    _append_recovery_event as _append_recovery_event,
)
from primr.core.run_state_io import (
    _append_run_event,
    _ensure_resilience_keys,
    _load_run_state,
    _save_run_state,
    _update_run_state,
)
from primr.core.run_state_io import (
    _init_run_state_with_resilience as _init_run_state_with_resilience,
)
from primr.core.run_state_io import (
    _run_state_file as _run_state_file,
)
from primr.core.section_parsing import (
    _extract_generated_section_blocks as _extract_generated_section_blocks,
)
from primr.core.section_parsing import (
    _normalize_generated_section_payload as _normalize_generated_section_payload,
)
from primr.core.section_parsing import (
    _parse_single_section,
)
from primr.core.section_parsing import (
    _parse_structured_section_envelopes as _parse_structured_section_envelopes,
)
from primr.core.section_planning import (
    _HIGH_DEPTH_SECTION_IDS as _HIGH_DEPTH_SECTION_IDS,
)
from primr.core.section_planning import (
    _determine_section_reasoning_mode as _determine_section_reasoning_mode,
)
from primr.core.section_planning import (
    _get_section_max_tokens as _get_section_max_tokens,
)
from primr.core.section_planning import (
    _get_section_word_target,
)
from primr.core.section_planning import (
    _group_sections_by_part as _group_sections_by_part,
)
from primr.core.section_prompts import (
    _build_fast_batch_prompt as _build_fast_batch_prompt,
)
from primr.core.section_prompts import (
    _build_fast_section_prompt,
    _load_fast_feedback_guidance,
)
from primr.core.section_regeneration import (
    _fast_regenerate_section as _fast_regenerate_section,
)
from primr.core.section_regeneration import (
    _strategy_regenerate_section as _strategy_regenerate_section,
)
from primr.core.source_relevance import _assess_source_relevance as _assess_source_relevance
from primr.core.strategy_artifacts import (
    _clean_strategy_output,
    _compute_strategy_qa_metrics,
    _ensure_strategy_source_inventory,
    _normalize_fast_citations,
    _normalize_strategy_source_urls,
    _split_markdown_sections,
)
from primr.core.strategy_artifacts import (
    _extract_strategy_citation_definitions as _extract_strategy_citation_definitions,
)
from primr.core.strategy_artifacts import (
    _is_auditable_source_url as _is_auditable_source_url,
)
from primr.core.strategy_artifacts import (
    _strategy_money_to_millions as _strategy_money_to_millions,
)
from primr.core.strategy_generation import (
    build_strategy_prompt_from_yaml as _build_strategy_prompt_from_yaml_impl,
)
from primr.core.strategy_generation import (
    generate_generic_strategy as _generate_generic_strategy_impl,
)
from primr.core.workspace import (
    acquire_company_run_lease_for_target,
    release_resume_leases_on_exit,
)
from primr.data.link_selection import select_links_with_llm as _select_discovered_links
from primr.output.artifact_validation import (
    _FORBIDDEN_INTERNAL_TERMS as _FORBIDDEN_INTERNAL_TERMS,
)
from primr.output.artifact_validation import (
    _FORBIDDEN_OUTPUT_CLEANERS as _FORBIDDEN_OUTPUT_CLEANERS,
)
from primr.output.artifact_validation import (
    _FORBIDDEN_OUTPUT_PATTERNS as _FORBIDDEN_OUTPUT_PATTERNS,
)
from primr.output.artifact_validation import (
    _ArtifactValidation,
    _auto_strip_forbidden_patterns,
    _validate_output_docx,
    _validate_output_markdown,
    _write_output_validation_report,
)
from primr.output.artifact_validation import (
    _extract_docx_text as _extract_docx_text,
)
from primr.output.artifact_validation import (
    _scan_forbidden_output_patterns as _scan_forbidden_output_patterns,
)

# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    "CloudVendor",
    "DeepResearchConfig",
    "DeepResearchMode",
    "Platform",
    "consolidate_working_folder",
    "create_working_folder",
    "ensure_valid_url",
    "generate_initial_overview",
    "get_user_input",
    "improve_output_file",
    "main",
    "perform_research",
    "process_csv",
    "research_section",
    "run_doctor",
    "run_research",
    "save_section_output",
    "validate_context_files",
]

import asyncio
import atexit
import gc
import json
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from primr.core.research_framing import ResearchFraming
    from primr.output.final_artifact import GeneratedSection
    from primr.prompts.loader import SectionConfig

from primr.ai.grading_agent import grade_report
from primr.ai.llm import llm
from primr.ai.routing import Role, pick_model_for_role
from primr.ai.summarize import summarize_scraped_content
from primr.config.config import (
    GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT,
    LOGS_DIR,
    MAX_EXTERNAL_SEARCH_QUERIES,
    MAX_EXTERNAL_SOURCES,
    MIN_SCRAPED_CHARS,
    MIN_SCRAPED_PAGES,
    OUTPUT_DIR,
    WORKING_DIR,
)
from primr.config.env import load_primr_env
from primr.config.models import PrimrModels
from primr.config.sections_config import SECTION_KEY_MAP


def _default_writing_model() -> str:
    """Resolve the default writing-tier model via the routing layer.

    The routing layer honors the active eval recipe override (set by the eval
    generation runner via EvalRecipeOverride), so each writing-stage entry
    point that uses this default automatically picks up the slot's writing
    model when the eval is running. Production calls without an active recipe
    fall through to the default routing (Grok 4.20-NR when XAI_API_KEY is set,
    Pro model otherwise).

    Replaces direct references to ``GROK_MODEL_WRITING`` for default resolution
    so the recipe override actually flows through to writing calls.
    """
    return pick_model_for_role(Role.WRITING)


from primr.core.research_orchestrator import (
    ResearchConfig,
    ResearchMode,
    get_orchestrator,
)
from primr.data.scrape import fetch_web_content, scrape_external_sources_validated
from primr.data.search_utils import (
    generate_external_search_queries,
    generate_search_queries,
    search_web,
)
from primr.output.output_utils import generate_final_report
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import correlation_scope, log_structured
from primr.utils.url_helpers import normalized_hostname
from primr.utils.validators import sanitize_for_filename

load_primr_env()

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


def select_links_with_llm(
    links: list,
    company_name: str,
    website: str,
    max_links: int = 50,
    organization_type: str = "commercial",
) -> list[str]:
    """Backward-compatible link-selection entry point."""

    return _select_discovered_links(
        links,
        company_name,
        website,
        max_links=max_links,
        organization_type=organization_type,
        model_call=llm,
    )


def create_working_folder(company_name, website, reuse_incomplete: bool = False):
    """
    Create working folder for research artifacts with timestamped run ID.

    Each run gets its own subfolder like: working/Company_Name/2026-01-09_0915/
    This prevents mixing old and new data from different runs.
    """
    from primr.core.workspace import (
        ResumeLeaseError,
        acquire_resume_lease,
        derive_working_folder_name,
    )
    from primr.core.workspace import create_working_folder as allocate_working_folder

    folder_name = derive_working_folder_name(company_name, website)

    company_root = os.path.join(WORKING_DIR, folder_name)

    # Optional resume behavior: reuse latest incomplete run folder for this company
    if reuse_incomplete and os.path.isdir(company_root):
        run_dirs = sorted(
            [d for d in os.listdir(company_root) if os.path.isdir(os.path.join(company_root, d))],
            reverse=True,
        )
        for run_id in run_dirs:
            candidate = os.path.join(company_root, run_id)
            state_path = os.path.join(candidate, "_run_state.json")
            if not os.path.exists(state_path):
                continue
            try:
                with open(state_path, encoding="utf-8") as f:
                    state = json.load(f)
                if not isinstance(state, dict):
                    continue
                status = str(state.get("status", "")).lower()
                if status in {"running", "failed", "cancelled", "canceled"}:
                    acquire_resume_lease(candidate)
                    logger.info(f"Reusing incomplete working folder: {candidate}")
                    return candidate
            except ResumeLeaseError:
                raise
            except Exception as e:
                logger.debug("Failed to read run state for resume candidate %s: %s", candidate, e)
                continue

    folder_path = allocate_working_folder(company_name, website, base_dir=WORKING_DIR)
    logger.info(f"Created working folder: {folder_path}")
    return folder_path


def ensure_valid_url(website):
    if not website:
        return None
    website = website.strip()
    if website.startswith(("http://", "https://")):
        return website
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

    # Extract company name from folder - skip timestamped leaf dirs like 2026-03-04_1530
    basename = os.path.basename(folder_path)
    if re.match(r"^\d{4}-\d{2}-\d{2}", basename):
        # Timestamped run folder; company name is the parent
        company_name = os.path.basename(os.path.dirname(folder_path)).replace("_", " ")
    else:
        company_name = basename.replace("_", " ")

    # Build consolidated document
    lines = [
        f"# Research Context: {company_name}",
        f"Source: {folder_path}",
        "",
        "This document contains research findings from the Structured Pipeline.",
        "",
        "---",
        "",
    ]

    # Read each file and add to document
    for txt_file in sorted(txt_files):
        filename = os.path.basename(txt_file)
        section_name = filename.replace(".txt", "").replace("_", " ").title()

        try:
            with open(txt_file, encoding="utf-8") as f:
                content = f.read().strip()

            if content:
                lines.extend([f"## {section_name}", "", content, "", "---", ""])
        except Exception as e:
            logger.warning(f"Failed to read {txt_file}: {e}")

    # Write to temp file
    # NOTE: We must close the fd from mkstemp before opening the file by path
    content = "\n".join(lines)
    fd, filepath = tempfile.mkstemp(
        suffix=".txt", prefix=f"{company_name.replace(' ', '_')}_context_"
    )
    os.close(fd)  # Close the fd - we'll open by path

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Consolidated {len(txt_files)} files into {filepath}")
    return filepath


# Supported file types for Deep Research File Search
SUPPORTED_CONTEXT_EXTENSIONS = {".txt", ".pdf", ".md", ".json", ".csv"}


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
        elif ext in {".docx", ".doc"}:
            # Word docs - suggest converting to PDF
            invalid_files.append(
                (
                    file_path,
                    "Word docs not directly supported. Convert to PDF or use the .txt output",
                )
            )
            warnings.append("Tip: Use the _Company_Overview.txt file from output/ instead of .docx")
        elif ext in {".xlsx", ".xls"}:
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


def research_section(
    section_name, company_name, website, industry, folder_path, overview, summarized_insights
):
    section_key = SECTION_KEY_MAP.get(section_name)

    if not section_key or section_key not in PROMPTS:
        return ""

    if section_name in ["Company Name", "Website", "Industry"]:
        value = (
            company_name
            if section_name == "Company Name"
            else website
            if section_name == "Website"
            else industry
        )
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
        "value_theory": overview,
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

            if (
                needs_research
                and score is not None
                and score < GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT
            ):
                queries = generate_search_queries(company_name, website, section_name, ai_response)
                for query in queries[:2]:
                    results = search_web(query, company_name, website)
                    if results:
                        formatted = "\n".join(
                            f"- [{r.get('title', 'Source')}]({r.get('url', '')}): {r.get('snippet', '')}"
                            for r in results[:5]
                        )
                        ai_input += f"\n\n## Additional Research\n{formatted}"
                        ai_response = llm(ai_input, model_type="report")
                        break
        except Exception as e:
            logger.warning(f"Grading/refinement failed for section '{section_name}': {e}")

    if not ai_response or len(ai_response.strip()) < 50:
        ai_response = f"No detailed {section_name} information available for {company_name}."

    save_section_output(folder_path, section_key, ai_response)
    return ai_response


def run_research(
    company_name: str,
    website: str,
    on_progress: Callable[[str], None] | None = None,
    fail_on_low_scrape: bool = True,
    folder_path: str | None = None,
) -> dict | None:
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

    folder_path = folder_path or create_working_folder(company_name, website)
    progress(f"> Working folder: {folder_path}")

    # Scrape website - saves raw scrapes incrementally to _raw_scrapes folder
    # fetch_web_content already shows completion message, no need to duplicate
    scraped_data = (
        fetch_web_content(website, company_name, max_pages=50, working_folder=folder_path)
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
        quality_ok, quality_reason = _validate_scrape_quality(scraped_data)
        if not quality_ok:
            console.fail(quality_reason)
            console.muted("  Re-run with --skip-scrape-validation to continue anyway")
            return None

    # External research - with LLM validation to ensure correct company
    # This prevents including content from similarly-named but unrelated companies
    # (e.g., a SaaS vendor and an unrelated services firm that share the same trade name)
    progress("Searching for external sources...")

    external_data = {}
    total_search_results = 0
    if website:
        from primr.data.scrape import scrape_external_sources_validated
        from primr.data.search_utils import search_web

        # Generate targeted search queries using LLM
        progress("Generating search strategy...")
        external_queries = generate_external_search_queries(
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
                    r for r in results[:5] if website.lower() not in r.get("url", "").lower()
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
        scraped_insights=summarized,
    )
    industry = llm(industry_prompt, model_type="research").strip() or "Unknown"
    progress(f"+ Industry: {industry}")

    # Overview
    progress("Generating overview...")
    overview = generate_initial_overview(company_name, website, industry, folder_path)
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

            content = research_section(
                section, company_name, website, industry, folder_path, overview, summarized
            )
            if content:
                section_results[section_key] = content

    # Final timing for sections
    progress(
        f"+ {total_analysis} sections complete ({format_time(time_module.time() - sections_start)})"
    )

    console.progress_done()
    return section_results


def perform_scrape_only(
    company_name: str | None,
    website: str | None,
    start_time: float,
    max_scrape_time: int | None = None,
    fail_on_low_scrape: bool = True,
    folder_path: str | None = None,
) -> str | None:
    """
    Scrape mode: Build site corpus + extract insights.

    Delegates to fetch_web_content() for all scraping work.

    Cost: ~$0.01-0.05 (LLM for summarization only)
    """
    if not website:
        console.fail("Scrape mode requires a website URL")
        return None

    display_name = company_name or normalized_hostname(website, strip_www=True)

    # Create working folder (silent)
    folder_path = folder_path or create_working_folder(company_name, website)
    _update_run_state(folder_path, current_phase="scrape", status="running")
    _append_run_event(folder_path, "scrape", "started", "Scrape-only mode started")

    # Build Site Corpus (shows its own progress)
    corpus = fetch_web_content(
        website=website,
        company_name=company_name or display_name,
        max_pages=50,
        working_folder=folder_path,
    )

    pages_scraped = len(corpus)
    total_chars = sum(len(c or "") for c in corpus.values())

    if pages_scraped == 0:
        console.fail("Could not scrape any pages - site may be blocking")
        console.muted('Try: primr "Company" url --mode deep')
        _update_run_state(folder_path, status="failed", current_phase="scrape")
        _append_run_event(folder_path, "scrape", "failed", "No pages scraped")
        return None

    if website and fail_on_low_scrape:
        quality_ok, quality_reason = _validate_scrape_quality(corpus)
        if not quality_ok:
            console.fail(quality_reason)
            console.muted("Re-run with --skip-scrape-validation to continue anyway")
            _update_run_state(folder_path, status="failed", current_phase="scrape")
            _append_run_event(folder_path, "scrape", "failed", quality_reason)
            return None

    # Save combined corpus
    scraped_file = os.path.join(folder_path, "scraped_content.txt")
    with open(scraped_file, "w", encoding="utf-8") as f:
        f.write(f"# {display_name} - Scraped Content\n")
        f.write(f"# URL: {website}\n")
        f.write(f"# Pages: {pages_scraped}\n\n")
        for url, content in corpus.items():
            f.write(f"\n{'=' * 60}\n")
            f.write(f"URL: {url}\n")
            f.write(f"{'=' * 60}\n")
            f.write(content[:5000] + "\n")

    # Extract Insights (LLM)
    console.status("Extracting insights...")

    summarized = summarize_scraped_content(company_name, website, corpus, folder_path)
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

    from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
    from primr.core.vendor_refresh_outcome import (
        VendorRefreshTracker,
        persist_vendor_refresh_outcome,
    )

    persist_strategy_outcome(folder_path, StrategyOutcomeTracker(()).snapshot())
    persist_vendor_refresh_outcome(folder_path, VendorRefreshTracker(()).snapshot())
    _update_run_state(
        folder_path,
        status="completed",
        current_phase="complete",
        completed_at=datetime.now().isoformat(),
        pages_scraped=pages_scraped,
        scraped_chars=total_chars,
    )
    _append_run_event(folder_path, "scrape", "completed", "Scrape-only mode completed")

    return folder_path


def _write_section_with_retry(
    section: "SectionConfig",
    section_index: int,
    all_section_names: list[str],
    written_sections: list["GeneratedSection"],
    company_name: str,
    website: str | None,
    analysis_workbook: str,
    raw_corpus_subset: str,
    external_sources_raw: str,
    source_urls: list[str],
    report_system: str,
    reasoning_mode: str = "standard",
    model: str | None = None,
    framing_block: str = "",
) -> "GeneratedSection | None":
    """Write a single section with one retry if output is thin.

    Returns the parsed section, or ``None`` on failure.

    NOTE (pipeline-resilience): The thin-section retry below is a *content
    quality* retry (re-prompt when word count is too low), not an API error
    retry.  It is intentionally retained alongside the stage-level
    RecoveryExecutor which handles API failures, model fallback, and
    skip/abort.  The two layers are complementary.
    """

    word_target = _get_section_word_target(section)

    prompt = _build_fast_section_prompt(
        company_name,
        website,
        analysis_workbook,
        raw_corpus_subset,
        external_sources_raw,
        source_urls,
        section,
        written_sections,
        section_index,
        all_section_names,
        reasoning_mode,
        framing_block=framing_block,
    )

    writing_model = model or _default_writing_model()
    # v1.26.0: route section writes through the circuit breaker so a quota
    # event on the primary writing model fails over to the next provider
    # in UTILITY_FALLBACK_CHAIN instead of killing the whole section.
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    try:
        section_content = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=_get_section_max_tokens(section),
            temperature=0.6,
            system_prompt=report_system,
        )
    except Exception as section_err:
        logger.warning("Section '%s' failed: %s", section.name, section_err)
        log_structured(
            "warning", "Fast mode section failed", section=section.name, error=str(section_err)
        )
        return None

    if not section_content or not section_content.strip():
        logger.warning("Section '%s' returned empty", section.name)
        return None

    parsed = _parse_single_section(section_content, section)

    # Thin-section retry: if < 50% of target, retry once
    if parsed.words < word_target * 0.5:
        logger.warning(
            "Section '%s' too thin (%d/%d words), retrying",
            section.name,
            parsed.words,
            word_target,
        )
        retry_prompt = (
            f"IMPORTANT: Your previous attempt produced only {parsed.words} words. "
            f"The minimum target is {word_target} words. Write a substantive, strategist-grade, "
            f"decision-useful section. If direct evidence is limited, deepen the analysis with explicit "
            f"inference and strategic implications rather than staying thin.\n\n" + prompt
        )
        try:
            retry_content = call_with_failover(
                LLMRole.WRITING,
                retry_prompt,
                preferred_model=writing_model,
                max_tokens=_get_section_max_tokens(section),
                temperature=0.6,
                system_prompt=report_system,
            )
            if retry_content and retry_content.strip():
                retry_parsed = _parse_single_section(retry_content, section)
                if retry_parsed.words > parsed.words:
                    parsed = retry_parsed
        except Exception as retry_err:
            logger.warning("Section '%s' retry failed: %s", section.name, retry_err)

    return parsed


def _fast_coherence_pass(
    company_name: str,
    website: str | None,
    report_content: str,
    model: str | None = None,
) -> str:
    """Run a coherence pass over the assembled fast-mode report.

    Tasks:
    1. Remove cross-section repetition → replace with cross-references
    2. Smooth transitions between sections
    3. Ensure framework sections reference earlier analytical sections
    4. Fix terminology consistency

    Guards against destructive compression - rejects output that loses
    too many words or sections.
    """
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    if not report_content.strip():
        return report_content

    # Skip coherence pass for reports that would exceed the output token budget.
    # ~1.4 tokens per word; prompt overhead ~2K tokens; max_tokens=32K.
    word_count = len(report_content.split())
    max_output_words = 20_000  # ~28K tokens, leaving headroom within 32K cap
    if word_count > max_output_words:
        logger.info(
            "Skipping coherence pass: report is %d words (exceeds %d word limit for single-pass editing)",
            word_count,
            max_output_words,
        )
        return report_content

    prompt = f"""You are a copy editor making MINIMAL tweaks to a strategic company overview.
The report was written section-by-section. Your ONLY job is light polish.

Company: {company_name}
Website: {website or "N/A"}

CRITICAL: Output MUST be at least 98% of the original word count. You are NOT rewriting.

YOUR THREE TASKS - nothing else:
1. TERMINOLOGY: If the company/product name varies (e.g. "Northgate" vs "Northgate Gonzalez"),
   pick one form and use it consistently. Fix obvious typos only.
2. CROSS-REFERENCES: If the EXACT same sentence (same fact, same number) appears in two
   sections, replace the SECOND occurrence with "As noted in [Section Name]..." Keep all
   surrounding paragraphs intact.
3. TRANSITIONS: Add ONE linking sentence at the start of each section (e.g. "Building on
   the financial profile above...") if no transition exists.

ABSOLUTE PROHIBITIONS:
- Do NOT delete ANY paragraph, bullet, subsection, or table
- Do NOT remove or rename ## headings
- Do NOT remove [cite: N], confidence labels, or "What to validate:" lines
- Do NOT rewrite sentences for style - only fix terminology and add cross-references
- Do NOT summarize, condense, or merge sections
- Do NOT add new facts or analysis
- Every paragraph in the input MUST appear in the output

If in doubt, leave the text unchanged. Err on the side of doing nothing.

Return the full markdown report. No preamble.

--- REPORT START ---
{report_content}
--- REPORT END ---
"""
    writing_model = model or _default_writing_model()
    try:
        polished = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=32_000,
            temperature=0.3,
            system_prompt=(
                "You are a meticulous editorial analyst improving coherence and flow "
                "across a multi-section strategic report. Preserve ALL depth and evidence. "
                "Make only surgical edits to duplicate sentences - never delete paragraphs."
            ),
        )
        if not polished or not polished.strip():
            return report_content

        # Guard: reject destructive compression
        original_words = len(report_content.split())
        polished_words = len(polished.split())
        _, original_sections = _split_markdown_sections(report_content)
        _, polished_sections = _split_markdown_sections(polished)

        if polished_words < int(original_words * 0.96):
            logger.warning(
                "Coherence pass dropped too many words (%d → %d), using original",
                original_words,
                polished_words,
            )
            return report_content
        if len(polished_sections) < len(original_sections):
            logger.warning(
                "Coherence pass lost sections (%d → %d), using original",
                len(original_sections),
                len(polished_sections),
            )
            return report_content

        return polished
    except Exception:
        logger.warning("Coherence pass failed, using original report", exc_info=True)
        return report_content


def _repair_strategy_artifact_issues(
    strategy_content: str,
    company_name: str,
    vendor: str,
    strategy_label: str,
    source_urls: list[str],
    issues: list[str],
    model: str | None = None,
) -> str:
    """Run one focused repair pass for strategy artifact issues before shipping."""
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    if not strategy_content.strip() or not issues:
        return strategy_content

    source_block = "\n".join(f"- {url}" for url in source_urls[:12]) if source_urls else "(none)"
    issue_block = "\n".join(f"- {issue}" for issue in issues)
    vendor_label = vendor.upper() if vendor and vendor != "agnostic" else strategy_label
    prompt = f"""Repair this strategy document for shipping. Keep the same structure, depth,
and consultant-grade detail, but fix the specific trust and artifact problems listed below.

COMPANY: {company_name}
STRATEGY: {strategy_label}
VENDOR CONTEXT: {vendor_label}

ISSUES TO FIX:
{issue_block}

ALLOWED SOURCE URLS:
{source_block}

DOCUMENT:
{strategy_content}

RULES:
- Preserve the depth and specificity of the document
- Keep dense references in a final ## Sources appendix, not as raw source dumps in body prose
- Reconcile all budget numbers so Year 1 investment, investment framework, and board summary agree
- Remove unsupported or malformed source references
- Use only the allowed source URLs when citing
- Every [cite: N] used in the body must have a valid matching definition in ## Sources
- Do not invent new URLs, vendors, metrics, or budget totals
- Return only the repaired markdown document"""

    system_prompt = (
        "You are a meticulous strategy editor repairing a document for shipment. "
        "Preserve depth, improve auditability, and resolve contradictions conservatively."
    )

    writing_model = model or _default_writing_model()
    try:
        repaired = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=20_000,
            temperature=0.2,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        log_structured("warning", "Strategy artifact repair failed", error=str(exc))
        return strategy_content

    return repaired.strip() if repaired and repaired.strip() else strategy_content


def _prepare_strategy_for_output(
    strategy_content: str,
    company_name: str,
    vendor: str,
    strategy_label: str,
    source_urls: list[str],
    model: str | None = None,
) -> tuple[str, dict[str, int | float | bool], list[str]]:
    """Normalize, validate, and repair strategy output before artifact shipping."""
    normalized_source_urls, rejected_source_urls = _normalize_strategy_source_urls(source_urls)

    prepared = _clean_strategy_output(strategy_content)
    prepared = _ensure_strategy_source_inventory(prepared, normalized_source_urls)
    qa = _compute_strategy_qa_metrics(prepared)

    repair_issues: list[str] = []
    if qa["budget_inconsistent"]:
        repair_issues.append("budget_inconsistent")
    if qa["missing_citations"]:
        repair_issues.append("missing_citations")
    if qa["invalid_source_urls"] or rejected_source_urls:
        repair_issues.append("invalid_source_urls")
    if qa["placeholder_refs"]:
        repair_issues.append("placeholder_refs")

    if repair_issues:
        prepared = _repair_strategy_artifact_issues(
            prepared,
            company_name,
            vendor,
            strategy_label,
            normalized_source_urls,
            repair_issues,
            model=model,
        )
        prepared = _clean_strategy_output(prepared)
        prepared = _ensure_strategy_source_inventory(prepared, normalized_source_urls)
        qa = _compute_strategy_qa_metrics(prepared)

    return prepared, qa, rejected_source_urls


def _repair_fast_report_citation_integrity(
    company_name: str,
    website: str | None,
    report_content: str,
    source_urls: list[str],
    model: str | None = None,
) -> str:
    """Repair missing citation linkage while preserving report structure."""
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    if not report_content.strip() or not source_urls:
        return report_content

    source_block = "\n".join(f"{i}. {u}" for i, u in enumerate(source_urls, 1))
    prompt = f"""You are repairing citation integrity in a strategic markdown report.

Company: {company_name}
Website: {website or "N/A"}

Your job:
- Keep ALL existing ## headings, sections, tables, and prose intact
- Add compact inline citations as [cite: N] only where major factual claims or numeric claims appear
- Add a final ## Sources appendix that maps each [cite: N] to one of the allowed URLs below
- Reuse citation numbers consistently for the same URL
- Do NOT invent URLs or add claims
- Do NOT remove any 'What to validate:' lines
- Output must preserve the existing section order and at least 98% of the original word count

Allowed URLs:
{source_block}

Return the full corrected markdown report only.

--- REPORT START ---
{report_content}
--- REPORT END ---
"""
    writing_model = model or _default_writing_model()
    try:
        repaired = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=40_000,
            temperature=0.2,
            system_prompt="You are a meticulous editor fixing citations in-place without rewriting content.",
        )
    except Exception as repair_err:
        logger.warning("Citation repair pass failed: %s", repair_err)
        return report_content

    if not repaired or not repaired.strip():
        return report_content

    repaired = _clean_fast_report_output(repaired)
    repaired = _normalize_fast_citations(repaired, source_urls=source_urls)
    repaired = _enforce_fast_section_quality_guards(repaired)

    if not _preserves_report_structure(report_content, repaired):
        logger.warning("Citation repair changed report structure too much; keeping original")
        return report_content

    repaired_metrics = _compute_fast_report_qa_metrics(repaired)
    if (
        repaired_metrics["citations_used"] > 0
        and repaired_metrics["citations_defined"] > 0
        and repaired_metrics["missing_citations"] == 0
    ):
        return repaired

    return report_content


def _polish_fast_report_for_trust(
    company_name: str,
    website: str | None,
    report_content: str,
    source_urls: list[str],
    model: str | None = None,
) -> str:
    """
    Run a lightweight post-write polish pass for fast mode trust/readability.

    Goals:
    - keep prose readable and concise
    - ensure confidence labels are present on non-obvious claims
    - improve citation discipline while keeping citations compact
    - preserve section structure and core meaning
    """
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    if not report_content.strip():
        return report_content

    source_block = (
        "\n".join(f"{i}. {u}" for i, u in enumerate(source_urls, 1)) if source_urls else "(none)"
    )
    feedback_guidance = _load_fast_feedback_guidance()
    feedback_block = (
        f"\n10. Apply this prior-eval feedback guidance where relevant:\n{feedback_guidance}\n"
        if feedback_guidance
        else ""
    )
    prompt = f"""You are editing a strategic report for quality and trust, not rewriting from scratch.

Company: {company_name}
Website: {website or "N/A"}

Rules:
1. Preserve the report structure and section headings.
2. Keep prose readable for executives; do not overstuff citations inline.
3. Use compact inline citations only as [cite: N].
4. Ensure non-obvious claims include confidence labels:
   (Confirmed), (Reported), (Estimated), or (Hypothesis).
5. Add/retain a single "## Sources" section at the end only.
6. Do NOT invent sources. Only use these source URLs:
{source_block}
7. Replace any unsupported numeric precision with cautious language:
   "Not publicly disclosed" or low-confidence qualitative ranges.
8. Remove repeated or contradictory claims; prefer one clear statement with
   the best available evidence and confidence tag.
9. Ensure each section ends with "What to validate:" and one concrete check.
{feedback_block}

Return the fully edited markdown report only.

--- REPORT START ---
{report_content}
--- REPORT END ---
"""
    writing_model = model or _default_writing_model()
    try:
        polished = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=10_000,
            temperature=0.2,
            system_prompt=(
                "You are a meticulous editorial QA analyst improving evidence discipline and readability."
            ),
        )
        if not polished or not polished.strip():
            return report_content

        # Guard against destructive compression/truncation from the polish pass.
        original_words = len(report_content.split())
        polished_words = len(polished.split())
        _, original_sections = _split_markdown_sections(report_content)
        _, polished_sections = _split_markdown_sections(polished)
        if original_words < 100:
            min_words = 1
        elif original_words >= 1200:
            min_words = max(1200, int(original_words * 0.70))
        else:
            min_words = max(50, int(original_words * 0.50))
        if original_words >= 1200:
            min_sections = max(1, len(original_sections))
        else:
            min_sections = max(1, int(len(original_sections) * 0.70))
        if polished_words < min_words or len(polished_sections) < min_sections:
            return report_content
        return polished
    except Exception as e:
        log_structured(
            "warning",
            "Trust polish pass failed, using unpolished report",
            error=str(e),
        )
        return report_content


def _fast_cross_validate(
    company_name: str,
    website: str | None,
    report_content: str,
    source_urls: list[str],
    model: str | None = None,
    reasoning_session: Any = None,
) -> dict:
    """
    Phase 5 helper: Grok reviews the assembled report for quality issues.

    When `reasoning_session` is supplied (a `ContinuousReasoningSession`), the
    review runs as a follow-up turn inside the same session that produced the
    workbook, so the validator inherits the original corpus and workbook
    reasoning instead of re-reading just the report.

    Returns:
        {"weak_sections": [{"title": str, "reason": str, "queries": [str, str]}],
         "contradictions": [str]}
    """
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    source_list = "\n".join(f"- {url}" for url in source_urls[:50])

    if reasoning_session is not None:
        # Continuous mode: the session already contains the corpus + workbook
        # reasoning from Phase 3. Skip re-feeding sources; ask the model to
        # validate the report against what it already analyzed.
        prompt = f"""You produced the analysis workbook for {company_name} in your earlier turn.
Below is the assembled consulting brief that was written from that workbook. Review it for
quality issues, drawing on the corpus and reasoning you already have in context.

REPORT:
{report_content[:120_000]}

ADDITIONAL SOURCES (gathered during gap-fill, may not have been in your earlier context):
{source_list}

Return JSON (no markdown fencing, just raw JSON):
{{
  "weak_sections": [
    {{"title": "exact ## heading", "reason": "why it's weak", "queries": ["search query 1", "search query 2"]}}
  ],
  "contradictions": ["description of contradiction between sections"]
}}

A section is WEAK if it:
- Makes claims without citing any source
- Uses only generic industry statements, not company-specific evidence
- Is significantly shorter than other sections
- Relies heavily on the company's own marketing claims without external validation
- Drifts from the strategic analysis the workbook called for, or contradicts the workbook's own evidence

Limit: max 3 weak sections, max 3 contradictions. Only flag genuinely weak sections.
If the report is solid, return empty arrays."""
    else:
        prompt = f"""Review this consulting brief for {company_name}. Identify quality issues.

REPORT:
{report_content[:120_000]}

AVAILABLE SOURCES:
{source_list}

Return JSON (no markdown fencing, just raw JSON):
{{
  "weak_sections": [
    {{"title": "exact ## heading", "reason": "why it's weak", "queries": ["search query 1", "search query 2"]}}
  ],
  "contradictions": ["description of contradiction between sections"]
}}

A section is WEAK if it:
- Makes claims without citing any source
- Uses only generic industry statements, not company-specific evidence
- Is significantly shorter than other sections
- Relies heavily on the company's own marketing claims without external validation

Limit: max 3 weak sections, max 3 contradictions. Only flag genuinely weak sections.
If the report is solid, return empty arrays."""

    system_prompt = (
        "You are a quality reviewer for consulting research briefs. "
        "Identify sections that need more evidence or have quality issues. "
        "Return structured JSON only."
    )

    try:
        if reasoning_session is not None:
            response = reasoning_session.send(
                prompt,
                temperature=0.2,
                max_tokens=5_000,
            )
        else:
            response = call_with_failover(
                LLMRole.REASONING,
                prompt,
                preferred_model=model,
                max_tokens=5_000,
                temperature=0.2,
                system_prompt=system_prompt,
            )
    except Exception as e:
        log_structured("warning", "Cross-validation failed", error=str(e))
        return {"weak_sections": [], "contradictions": [], "_failed": True}

    if not response or not response.strip():
        return {"weak_sections": [], "contradictions": []}

    # Parse JSON from response
    try:
        # Strip markdown code fencing if present (```json, ```JSON, ``` etc.)
        text = response.strip()
        if text.startswith("```"):
            # Remove opening fence line (```json, ```JSON, ```, etc.)
            first_newline = text.find("\n")
            text = text[first_newline + 1 :] if first_newline != -1 else text[3:]
            # Remove closing fence
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()

        # Try to extract JSON object if surrounded by prose
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Look for JSON object within the text
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                result = json.loads(text[brace_start : brace_end + 1])
            else:
                raise

        if not isinstance(result, dict):
            log_structured(
                "warning", "Cross-validation JSON is not a dict", type=type(result).__name__
            )
            return {"weak_sections": [], "contradictions": []}

        # Enforce limits and validate types
        raw_weak = result.get("weak_sections", [])
        weak = [w for w in (raw_weak if isinstance(raw_weak, list) else []) if isinstance(w, dict)][
            :3
        ]
        raw_contradictions = result.get("contradictions", [])
        contradictions = [
            c
            for c in (raw_contradictions if isinstance(raw_contradictions, list) else [])
            if isinstance(c, str)
        ][:3]

        return {"weak_sections": weak, "contradictions": contradictions}
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        log_structured("warning", "Cross-validation JSON parse failed, retrying", error=str(e))

        # NOTE (pipeline-resilience): format-correction retry only (re-prompt on
        # JSON parse failure), not API error retry — RecoveryExecutor owns that.
        # Retry with tighter prompt including the failed response
        retry_prompt = (
            "Your previous response could not be parsed as JSON. "
            "Return ONLY a JSON object, no markdown fencing, no prose before or after.\n\n"
            f"Previous response (first 2000 chars):\n{response[:2000]}\n\n"
            "Fix the JSON and return ONLY this structure:\n"
            '{"weak_sections": [{"title": "...", "reason": "...", "queries": ["...", "..."]}], '
            '"contradictions": ["..."]}'
        )
        try:
            retry_response = call_with_failover(
                LLMRole.REASONING,
                retry_prompt,
                max_tokens=3_000,
                temperature=0.1,
                system_prompt="Return valid JSON only. No markdown, no prose.",
            )
            if retry_response and retry_response.strip():
                retry_text = retry_response.strip()
                brace_start = retry_text.find("{")
                brace_end = retry_text.rfind("}")
                if brace_start != -1 and brace_end > brace_start:
                    result = json.loads(retry_text[brace_start : brace_end + 1])
                    if isinstance(result, dict):
                        raw_weak = result.get("weak_sections", [])
                        weak = [
                            w
                            for w in (raw_weak if isinstance(raw_weak, list) else [])
                            if isinstance(w, dict)
                        ][:3]
                        raw_contradictions = result.get("contradictions", [])
                        contradictions = [
                            c
                            for c in (
                                raw_contradictions if isinstance(raw_contradictions, list) else []
                            )
                            if isinstance(c, str)
                        ][:3]
                        return {"weak_sections": weak, "contradictions": contradictions}
        except Exception as retry_err:
            log_structured(
                "debug", "Cross-validation retry JSON parse failed", error=str(retry_err)
            )

        # Last resort: regex extraction of weak section titles and reasons
        try:
            weak_sections = []
            title_pattern = re.compile(r'"title"\s*:\s*"([^"]+)"')
            reason_pattern = re.compile(r'"reason"\s*:\s*"([^"]+)"')
            titles = title_pattern.findall(response)
            reasons = reason_pattern.findall(response)
            for i, title in enumerate(titles[:3]):
                weak_sections.append(
                    {
                        "title": title,
                        "reason": reasons[i] if i < len(reasons) else "Needs more evidence",
                        "queries": [f"{company_name} {title.lower()}"],
                    }
                )
            if weak_sections:
                log_structured(
                    "info", "Cross-validation recovered via regex", count=len(weak_sections)
                )
                return {"weak_sections": weak_sections, "contradictions": []}
        except Exception as regex_err:
            log_structured("debug", "Cross-validation regex fallback failed", error=str(regex_err))

        log_structured("warning", "Cross-validation JSON parse failed after all retries")
        return {"weak_sections": [], "contradictions": [], "_failed": True}


# ── Strategy enrichment helpers (Phase 6 quality pass) ──────────────────


def _strategy_cross_validate(
    company_name: str,
    strategy_content: str,
    vendor: str,
    source_urls: list[str],
    model: str | None = None,
    label: str = "AI Strategy",
) -> dict:
    """Review strategy quality and return weak sections plus issues."""
    from primr.core.strategy_enrichment_contract import strategy_document_context
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    source_list = "\n".join(f"- {url}" for url in source_urls[:50])
    document_label, emphasis = strategy_document_context(label, vendor)

    prompt = f"""Review this {document_label} for {company_name}. Identify quality issues.

{emphasis}

STRATEGY DOCUMENT:
{strategy_content[:120_000]}

AVAILABLE SOURCES:
{source_list}

Return JSON (no markdown fencing, just raw JSON):
{{
  "weak_sections": [
    {{"title": "exact ## heading", "reason": "why it's weak", "queries": ["search query 1", "search query 2"]}}
  ],
  "issues": ["description of quality issue"]
}}

A section is WEAK if it:
- Makes current company, market, product, price, or availability claims without cited evidence
- Uses generic recommendations that could apply to ANY company
- Lacks decision criteria, measurable outcomes, validation actions, or accountable ownership
- Doesn't connect capabilities to THIS company's specific needs or challenges
- Presents the platform emphasis as a predetermined answer or forces product names without current official support

Limit: max 2 weak sections, max 2 issues. Only flag genuinely weak sections.
If the strategy is solid, return empty arrays."""

    system_prompt = (
        f"You are a quality reviewer for a {document_label}. {emphasis} Identify sections "
        "that need more evidence or are too generic. "
        "Return structured JSON only."
    )

    try:
        response = call_with_failover(
            LLMRole.REASONING,
            prompt,
            preferred_model=model,
            max_tokens=4_000,
            temperature=0.2,
            system_prompt=system_prompt,
        )
    except Exception as e:
        log_structured("warning", "Strategy cross-validation failed", error=str(e))
        return {"weak_sections": [], "issues": [], "_failed": True}

    if not response or not response.strip():
        return {"weak_sections": [], "issues": []}

    # Parse JSON from response (same pattern as _fast_cross_validate)
    try:
        text = response.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            text = text[first_newline + 1 :] if first_newline != -1 else text[3:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                result = json.loads(text[brace_start : brace_end + 1])
            else:
                raise

        if not isinstance(result, dict):
            return {"weak_sections": [], "issues": []}

        raw_weak = result.get("weak_sections", [])
        weak = [w for w in (raw_weak if isinstance(raw_weak, list) else []) if isinstance(w, dict)][
            :2
        ]
        raw_issues = result.get("issues", [])
        issues = [
            i for i in (raw_issues if isinstance(raw_issues, list) else []) if isinstance(i, str)
        ][:2]

        return {"weak_sections": weak, "issues": issues}
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        log_structured("warning", "Strategy cross-validation JSON parse failed", error=str(e))
        return {"weak_sections": [], "issues": [], "_failed": True}


def _strategy_polish(
    company_name: str,
    vendor: str,
    strategy_content: str,
    model: str | None = None,
    label: str = "AI Strategy",
) -> str:
    """Polish strategy coherence and evidence without destructive compression."""
    from primr.core.strategy_enrichment_contract import strategy_document_context
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    if not strategy_content.strip():
        return strategy_content

    document_label, emphasis = strategy_document_context(label, vendor)
    prompt = f"""You are editing a {document_label} for {company_name} for coherence,
evidence discipline, and specificity.

{emphasis}

TASKS (in priority order):
1. DEDUPLICATION: When the same point appears in multiple sections, keep the first
   occurrence and replace later duplicates with a cross-reference.
2. EVIDENCE DISCIPLINE: For each major recommendation, ensure it has:
   - A confidence label: Confirmed, Reported, Estimated, or Hypothesis
   - A compact [cite: N] reference where available, with dense references consolidated in the final Sources appendix
   - Current product, pricing, availability, and lifecycle claims retained only when supported by a cited official source
   - Capability requirements and validation actions used when current official evidence is unavailable
3. SPECIFICITY CHECK: Replace generic recommendations with company-specific ones.
   BAD: "Leverage AI/ML capabilities to improve operations"
   GOOD: "Test assisted review in [specific company process] against [specific outcome and guardrail]"
4. TERMINOLOGY: Standardize how {company_name}, observed ecosystems, and
   competitors are named without implying unverified adoption.

STRICT RULES:
- Do NOT remove or rename ## section headings
- Do NOT remove confidence labels or source citations
- Do NOT add new strategic recommendations - only improve existing ones
- Do NOT delete paragraphs - only edit individual sentences
- PRESERVE all depth and analysis
- Output MUST contain at least 90% of the original word count

Return the fully edited markdown strategy document only. No preamble or commentary.

--- STRATEGY START ---
{strategy_content}
--- STRATEGY END ---"""

    writing_model = model or _default_writing_model()
    try:
        polished = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=32_000,
            temperature=0.3,
            system_prompt=(
                f"You are a meticulous editorial analyst polishing a {document_label} "
                f"for {company_name}. {emphasis} "
                "Improve evidence discipline and specificity while preserving ALL depth and analysis. "
                "Make only surgical edits."
            ),
        )
        if not polished or not polished.strip():
            return strategy_content

        # Guard: reject destructive compression
        original_words = len(strategy_content.split())
        polished_words = len(polished.split())
        _, original_sections = _split_markdown_sections(strategy_content)
        _, polished_sections = _split_markdown_sections(polished)

        if polished_words < int(original_words * 0.90):
            logger.warning(
                "Strategy polish dropped too many words (%d → %d), using original",
                original_words,
                polished_words,
            )
            return strategy_content
        if len(polished_sections) < len(original_sections):
            logger.warning(
                "Strategy polish lost sections (%d → %d), using original",
                len(original_sections),
                len(polished_sections),
            )
            return strategy_content

        return polished
    except Exception:
        logger.warning("Strategy polish failed, using original", exc_info=True)
        return strategy_content


def _enrich_strategy_content(
    strategy_content: str,
    company_name: str,
    vendor: str,
    label: str,
    source_urls: list[str],
    source_urls_seen: set[str],
    analysis_workbook: str,
    website: str | None,
    grok_reasoning: str | None = None,
    grok_writing: str | None = None,
) -> str:
    """Cross-validate, enrich weak sections, then polish with safe fallbacks."""
    if not strategy_content or not strategy_content.strip():
        return strategy_content

    # Show vendor suffix only when vendor is a real cloud vendor (not the label itself)
    vendor_label = (
        f" ({vendor.upper()})" if vendor.lower() not in ("agnostic", label.lower()) else ""
    )

    # Step 1: Cross-validate
    try:
        with console.timed_operation(f"Reviewing {label}{vendor_label}"):
            cv_result = _strategy_cross_validate(
                company_name,
                strategy_content,
                vendor,
                source_urls,
                model=grok_reasoning,
                label=label,
            )
    except Exception as e:
        log_structured("warning", "Strategy CV failed, skipping enrichment", error=str(e))
        return strategy_content

    weak_sections = cv_result.get("weak_sections", [])
    issues = cv_result.get("issues", [])
    cv_failed = cv_result.pop("_failed", False)

    if cv_failed:
        console.warn(
            f"Strategy cross-validation failed for {label}{vendor_label} - skipping enrichment"
        )

    if issues:
        for issue in issues:
            console.info(f"Strategy issue: {issue[:100]}")

    # Step 2: Enrich weak sections
    sections_enriched = 0
    if weak_sections:
        # Build heading lookup for case-insensitive matching
        _, parsed_sections = _split_markdown_sections(strategy_content)
        heading_lookup = {h.lower(): h for h, _ in parsed_sections}

        for ws in weak_sections[:2]:
            raw_title = str(ws.get("title", "")).strip().lstrip("#").strip()
            queries = ws.get("queries", [])
            if not isinstance(queries, list):
                queries = [str(queries)] if queries else []
            reason = str(ws.get("reason", ""))

            if not raw_title or not queries:
                continue

            section_title: str = heading_lookup.get(raw_title.lower(), raw_title)
            console.info(f"Weak: {section_title} - {reason[:80]}")

            # Search for additional evidence
            new_evidence_parts: list[str] = []
            with console.timed_operation(f"Enriching: {section_title}"):
                for q in queries[:2]:
                    results = search_web(q, company_name, website)
                    if results:
                        filtered = [
                            r
                            for r in results[:3]
                            if (not website or website.lower() not in r.get("url", "").lower())
                            and r.get("url", "") not in source_urls_seen
                        ]
                        scraped = scrape_external_sources_validated(
                            filtered,
                            company_name=company_name,
                            website=website,
                            max_sources=3,
                        )
                        for url, content in scraped.items():
                            if url not in source_urls_seen:
                                source_urls.append(url)
                                source_urls_seen.add(url)
                                new_evidence_parts.append(f"[Source: {url}]\n{content[:12_000]}")

            if not new_evidence_parts:
                continue

            new_evidence = "\n\n".join(new_evidence_parts)

            # Find section in strategy content
            section_pattern = re.compile(
                rf"(## {re.escape(section_title)}\n.*?)(?=\n## |\Z)",
                re.DOTALL,
            )
            match = section_pattern.search(strategy_content)
            if not match:
                log_structured("warning", "Strategy CV: section not found", section=section_title)
                continue

            original_section = match.group(1)

            # Regenerate the section
            with console.timed_operation(f"Rewriting: {section_title}"):
                regenerated = _strategy_regenerate_section(
                    company_name,
                    vendor,
                    section_title,
                    original_section,
                    new_evidence,
                    analysis_workbook,
                    model=grok_writing,
                    label=label,
                )

            if regenerated and regenerated != original_section:
                if not regenerated.endswith("\n"):
                    regenerated += "\n"
                strategy_content = (
                    strategy_content[: match.start()]
                    + regenerated
                    + strategy_content[match.end() :]
                )
                sections_enriched += 1
                console.ok(f"Enriched: {section_title}")
    else:
        console.ok("Strategy review: no sections flagged for enrichment")

    if sections_enriched > 0:
        log_structured("info", "Strategy sections enriched", count=sections_enriched, vendor=vendor)

    # Step 3: Polish pass
    try:
        with console.timed_operation(f"Polishing {label}{vendor_label}"):
            strategy_content = _strategy_polish(
                company_name, vendor, strategy_content, model=grok_writing, label=label
            )
    except Exception as e:
        log_structured("warning", "Strategy polish failed, keeping unpolished", error=str(e))

    return strategy_content


def _compute_session_llm_cost() -> float:
    """Current actual LLM spend for this run, in USD.

    Per-model Grok session cost (cache-aware: cached input tokens are billed
    at the model's cached rate) plus the Gemini client's accumulated cost.
    Used by the end-of-run summary and the ``--budget`` checkpoint, so both
    report the same number.
    """
    from primr.ai.grok_client import get_grok_session_usage_by_model

    usage_by_model = get_grok_session_usage_by_model()
    grok_cost = 0.0
    for model_name, tokens in usage_by_model.items():
        cost_model = (
            model_name if PrimrModels.get_model_config(model_name) else PrimrModels.GROK_MODEL
        )
        grok_cost += PrimrModels.calculate_cost(
            cost_model,
            tokens["input_tokens"],
            tokens["output_tokens"],
            cached_input_tokens=tokens.get("cached_input_tokens", 0),
        )

    from primr.ai.client import get_client

    flash_cost = get_client().get_usage_summary().get("total_cost", 0.0)
    return grok_cost + flash_cost


def perform_fast_research(
    company_name: str | None,
    website: str | None,
    start_time: float,
    ai_strategy: bool = False,
    platforms: tuple[str, ...] = ("agnostic",),
    strategy_types: list[str] | None = None,
    max_scrape_time: int | None = None,
    discovery_notes_content: str | None = None,
    *,
    refresh_vendor_research: bool = False,
    framing: "ResearchFraming | None" = None,
    folder_path: str | None = None,
    resume_local: bool = False,
    grok_tier: str = "hybrid",
    continuous_reasoning: bool = True,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
) -> str | None:
    """
    Fast research mode using Grok 4.3 hybrid with accordion-style batch writing.

    Pipeline:
    1. Data collection: scrape 50 pages + 10 search queries via Gemini Flash
    2. Research deepening: Grok gap analysis → targeted search → fill
    3. Grok analysis call: structured workbook from enriched data
    4. Grok report writing: 5 batch calls (one per YAML part), each writing
       2-7 sections with rolling context from completed batches
    5. Cross-validation: find weak spots → targeted search → re-write ≤3 sections
    6. Optional strategy generation via Grok (AI strategy per vendor,
       and/or YAML-defined strategies like CX, security, data fabric)

    Target: ~20-30 min, ~$0.20
    """

    from primr.ai.grok_client import ContinuousReasoningSession
    from primr.core.fast_run_setup import resolve_fast_run_setup

    framing_block = framing.to_prompt_block() if framing is not None else ""

    # Stage 0 (extracted: core/fast_run_setup.py - roadmap #23 Batch A):
    # session reset, model resolution + routing + eval-recipe override,
    # continuous-reasoning flag, run identity, phase plan.
    setup = resolve_fast_run_setup(
        company_name=company_name,
        website=website,
        ai_strategy=ai_strategy,
        strategy_types=strategy_types,
        grok_tier=grok_tier,
        continuous_reasoning=continuous_reasoning,
        folder_path=folder_path,
    )
    grok_reasoning = setup.grok_reasoning
    grok_writing = setup.grok_writing
    grok_reasoning_effort = setup.grok_reasoning_effort
    continuous_reasoning = setup.continuous_reasoning
    display_name = setup.display_name
    folder_path = setup.folder_path
    if output_dir is not None:
        _update_run_state(folder_path, output_dir=str(output_dir))

    # Session is constructed lazily at the workbook stage so the workbook's
    # system prompt becomes a real `role: system` message instead of being
    # folded into the first user turn (which the v1 pilot showed measurably
    # degrades workbook quality).
    reasoning_session: ContinuousReasoningSession | None = None

    try:
        has_strategies = setup.has_strategies
        total_phases = setup.total_phases

        # =================================================================
        # Phase 1: Data collection (extracted: core/fast_run_collection.py)
        # =================================================================
        _collected = collect_research_data(
            company_name=company_name,
            website=website,
            folder_path=folder_path,
            total_phases=total_phases,
            public_output_dir=str(output_dir) if output_dir is not None else None,
        )
        scraped_data = _collected.scraped_data
        pages_scraped = _collected.pages_scraped
        summarized = _collected.summarized
        raw_corpus = _collected.raw_corpus
        external_query_count = _collected.external_query_count
        source_urls = _collected.source_urls
        source_urls_seen = _collected.source_urls_seen
        external_text_parts = _collected.external_text_parts
        external_raw_parts = _collected.external_raw_parts
        _recovery_executor = _collected.recovery_executor

        # =================================================================
        # Hiring Signals - discover open postings, extract strategic signals.
        # Not numbered as a full phase so we avoid renumbering the five
        # downstream banners, but announced clearly. The resulting block is
        # threaded through BOTH the initial insights build and the Phase 2
        # gap-filling rebuild so it survives every refresh of insights.txt
        # and external_sources_raw.
        # =================================================================
        hiring_block = collect_hiring_block(
            company_label=company_name or display_name,
            website=website,
            scraped_data=scraped_data,
            folder_path=folder_path,
        )

        # Combine Flash-summarized insights (for working folder)
        combined_insights = build_combined_insights(summarized, external_text_parts, hiring_block)

        # Save insights to working folder
        insights_file = os.path.join(folder_path, "insights.txt")
        with open(insights_file, "w", encoding="utf-8") as f:
            f.write(combined_insights)

        # Build raw external sources string for Grok (hiring signals ride along).
        external_sources_raw = build_external_sources_raw(external_raw_parts, hiring_block)

        # Day-1 hypothesis tree (tradecraft Step 4): build it once here, before the
        # deepening stage, so gap queries can test under-evidenced branches and the
        # workbook reuses the same tree. No-op (empty block) when the run is
        # unframed, so default runs are byte-identical.
        day1_block, _day1_tree = build_day1_hypothesis_tree(
            company_name or display_name, framing, raw_corpus, external_sources_raw, folder_path
        )

        # =================================================================
        # Phase 2: Research Deepening (extracted: core/fast_run_gaps.py)
        # =================================================================
        _gaps = deepen_research(
            company_name=company_name,
            company_label=company_name or display_name,
            website=website,
            raw_corpus=raw_corpus,
            external_sources_raw=external_sources_raw,
            combined_insights=combined_insights,
            summarized=summarized,
            hiring_block=hiring_block,
            source_urls=source_urls,
            source_urls_seen=source_urls_seen,
            external_text_parts=external_text_parts,
            external_raw_parts=external_raw_parts,
            grok_reasoning=grok_reasoning,
            folder_path=folder_path,
            insights_file=insights_file,
            total_phases=total_phases,
            hypothesis_block=day1_block,
        )
        external_sources_raw = _gaps.external_sources_raw
        combined_insights = _gaps.combined_insights
        gap_search_count = _gaps.gap_search_count

        validated_source_urls = list(source_urls)
        validated_source_count = len(validated_source_urls)

        # =================================================================
        # Phase 3: Grok analysis call (extracted: core/fast_run_workbook.py)
        # =================================================================
        analysis_workbook, reasoning_session = generate_analysis_workbook(
            company_label=company_name or display_name,
            website=website,
            raw_corpus=raw_corpus,
            external_sources_raw=external_sources_raw,
            combined_insights=combined_insights,
            grok_reasoning=grok_reasoning,
            grok_reasoning_effort=grok_reasoning_effort,
            continuous_reasoning=continuous_reasoning,
            reasoning_session=reasoning_session,
            recovery_executor=_recovery_executor,
            folder_path=folder_path,
            total_phases=total_phases,
            framing_block=framing_block,
            framing=framing,
            prebuilt_day1_block=day1_block,
        )

        # =================================================================
        # Phase 4: Report writing (extracted: core/fast_run_sections.py)
        # =================================================================
        _sections_result = write_report_sections(
            company_label=company_name or display_name,
            website=website,
            analysis_workbook=analysis_workbook,
            raw_corpus=raw_corpus,
            external_sources_raw=external_sources_raw,
            source_urls=source_urls,
            grok_writing=grok_writing,
            recovery_executor=_recovery_executor,
            folder_path=folder_path,
            total_phases=total_phases,
            framing_block=framing_block,
        )
        if _sections_result.report_content is None:
            return None
        report_content = _sections_result.report_content
        written_sections = _sections_result.written_sections
        total_words = _sections_result.total_words

        # =================================================================
        # Phase 5: Cross-Validation (extracted: core/fast_run_validation.py)
        # =================================================================
        _cv = cross_validate_and_enrich(
            company_name=company_name,
            company_label=company_name or display_name,
            website=website,
            report_content=report_content,
            source_urls=source_urls,
            source_urls_seen=source_urls_seen,
            analysis_workbook=analysis_workbook,
            grok_reasoning=grok_reasoning,
            grok_writing=grok_writing,
            reasoning_session=reasoning_session,
            recovery_executor=_recovery_executor,
            folder_path=folder_path,
            total_phases=total_phases,
        )
        report_content = _cv.report_content
        unresolved_contradictions = _cv.unresolved_contradictions
        cv_search_count = _cv.cv_search_count

        # Trust polish + citation repair stage (extracted: core/fast_run_trust.py)
        _trust = polish_and_gate_fast_report(
            company_label=company_name or display_name,
            website=website,
            report_content=report_content,
            source_urls=source_urls,
            grok_writing=grok_writing,
            folder_path=folder_path,
            unresolved_contradictions=unresolved_contradictions,
        )
        report_content = _trust.report_content
        qa_metrics = _trust.qa_metrics
        report_trust_stats = list(_trust.report_trust_stats)

        # Save report via existing output pipeline
        # Note: unresolved contradictions are surfaced as QA warnings above
        # but do NOT block DOCX shipping - the contradictions are already
        # noted inline and the user gets the full report.
        report_gate_issues = []
        if qa_metrics["citations_used"] == 0 or qa_metrics["citations_defined"] == 0:
            console.warn(
                "Report validation warning: "
                + f"citation_integrity {qa_metrics['citations_used']}/{qa_metrics['citations_defined']}"
            )
        docx_path = _convert_deep_research_to_docx(
            report_content,
            company_name or display_name,
            website,
            gate_issues=report_gate_issues,
            output_dir=output_dir,
            diagnostics_dir=diagnostics_dir,
            write_txt=write_txt,
        )

        # Also save raw markdown for AI strategy context
        raw_md_path = os.path.join(folder_path, "report.md")
        with open(raw_md_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        # =================================================================
        # Phase 6: Strategy Generation (extracted: core/fast_run_strategy.py)
        # =================================================================
        _strategy_result = run_strategy_phase(
            has_strategies=has_strategies,
            ai_strategy=ai_strategy,
            platforms=platforms,
            strategy_types=strategy_types,
            company_label=company_name or display_name,
            website=website,
            report_content=report_content,
            analysis_workbook=analysis_workbook,
            validated_source_urls=validated_source_urls,
            discovery_notes_content=discovery_notes_content,
            refresh_vendor_research=refresh_vendor_research,
            grok_reasoning=grok_reasoning,
            grok_writing=grok_writing,
            folder_path=folder_path,
            output_dir=output_dir,
            diagnostics_dir=diagnostics_dir,
            write_txt=write_txt,
            recovery_executor=_recovery_executor,
            total_phases=total_phases,
        )
        strategy_paths = _strategy_result.strategy_paths
        strategy_trust_stats = _strategy_result.strategy_trust_stats

        # =================================================================
        # Summary (extracted: core/fast_run_summary.py - roadmap #23 Batch A)
        # =================================================================
        from primr.core.fast_run_summary import finalize_fast_run

        return finalize_fast_run(
            start_time=start_time,
            docx_path=docx_path,
            strategy_paths=strategy_paths,
            output_dir=output_dir,
            company_name=company_name,
            display_name=display_name,
            folder_path=folder_path,
            written_sections_count=len(written_sections),
            total_words=total_words,
            validated_source_count=validated_source_count,
            pages_scraped=pages_scraped,
            grok_tier=grok_tier,
            report_trust_stats=report_trust_stats,
            strategy_trust_stats=strategy_trust_stats,
            search_query_count=external_query_count + gap_search_count + cv_search_count,
            vendor_refresh_tasks_started=_strategy_result.vendor_refresh_tasks_started,
            strategy_outcome=_strategy_result.strategy_outcome,
            vendor_refresh_outcome=_strategy_result.vendor_refresh_outcome,
        )

    except Exception as e:
        console.error(f"Fast research failed: {e}")
        log_structured("error", "Fast research failed", error=str(e), error_type=type(e).__name__)
        logger.exception("Fast research failed")
        return None


def _save_strategy_output(
    strategy_content: str,
    company_name: str,
    platform: str,
    strategy_label: str = "AI_Strategy",
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
) -> str | None:
    """Save strategy markdown/txt/docx output. Returns docx path or None."""
    from primr.output.markdown_converter import markdown_to_docx
    from primr.output.output_utils import OUTPUT_DIR

    date_str = datetime.now().strftime("%m-%d-%Y")
    vendor_suffix = f"_{platform.upper()}" if platform != "agnostic" else ""
    base_name = f"{sanitize_for_filename(company_name, max_length=200)}_{strategy_label}{vendor_suffix}_{date_str}"
    destination_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
    destination_dir.mkdir(parents=True, exist_ok=True)
    internal_dir = Path(diagnostics_dir) if diagnostics_dir is not None else destination_dir
    internal_dir.mkdir(parents=True, exist_ok=True)

    # Human-readable title for DOCX
    display_label = strategy_label.replace("_", " ")

    try:
        strategy_content, markdown_validation, salvaged = _salvage_markdown_for_shipping(
            strategy_content,
            kind="strategy",
        )

        md_path = destination_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(strategy_content)

        if write_txt or diagnostics_dir is not None:
            txt_path = (destination_dir if write_txt else internal_dir) / f"{base_name}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(strategy_content)
        if salvaged:
            console.info(f"Adaptive salvage cleaned {display_label} markdown before shipping")

        strategy_gate_issues = list(markdown_validation["issues"])
        strategy_gate_errors = list(markdown_validation["errors"])
        strategy_advisory_issues: list[str] = []
        strategy_qa = _compute_strategy_qa_metrics(strategy_content)
        if strategy_qa["budget_inconsistent"]:
            strategy_advisory_issues.append("budget_inconsistent")
        if strategy_qa["missing_citations"]:
            strategy_advisory_issues.append(f"missing_citations:{strategy_qa['missing_citations']}")
        if strategy_qa["invalid_source_urls"]:
            strategy_advisory_issues.append(
                f"invalid_source_urls:{strategy_qa['invalid_source_urls']}"
            )
        if strategy_gate_issues:
            report_path = _write_output_validation_report(
                md_path,
                "markdown",
                strategy_gate_issues,
                strategy_gate_errors,
                diagnostics_dir=diagnostics_dir,
            )
            console.warn(f"{display_label} artifact issues: " + ", ".join(strategy_gate_issues[:3]))
            console.warn(
                "DOCX shipping gate failed for strategy markdown; saved MD/TXT only"
                + (f" ({report_path.name})" if report_path else "")
            )
            return str(md_path)
        if strategy_advisory_issues or strategy_gate_errors:
            report_path = _write_output_validation_report(
                md_path,
                "markdown",
                strategy_advisory_issues,
                strategy_gate_errors,
                diagnostics_dir=diagnostics_dir,
            )
            console.warn(
                f"{display_label} validation warnings: "
                + ", ".join((strategy_advisory_issues or strategy_gate_errors)[:3])
                + (f" ({report_path.name})" if report_path else "")
            )

        docx_path = destination_dir / f"{base_name}.docx"
        try:
            markdown_to_docx(
                markdown_text=strategy_content,
                output_path=docx_path,
                title=f"{display_label}: {company_name}",
                subtitle=f"{platform.upper()} | {datetime.now().strftime('%B %d, %Y')}"
                if platform != "agnostic"
                else datetime.now().strftime("%B %d, %Y"),
            )
        except Exception as e:
            logger.warning(f"DOCX conversion failed: {e}")
            return str(md_path)

        docx_validation = _validate_output_docx(docx_path)
        if not docx_validation["passed"]:
            report_path = _write_output_validation_report(
                docx_path,
                "docx",
                docx_validation["issues"],
                docx_validation["errors"],
                diagnostics_dir=diagnostics_dir,
            )
            try:
                docx_path.unlink(missing_ok=True)
            except Exception as cleanup_err:
                logger.warning(
                    "Failed to remove blocked strategy DOCX %s: %s", docx_path, cleanup_err
                )
            console.warn(
                "DOCX shipping gate failed for rendered strategy; saved MD/TXT only"
                + (f" ({report_path.name})" if report_path else "")
            )
            return str(md_path)

        if docx_validation["errors"]:
            report_path = _write_output_validation_report(
                docx_path,
                "docx",
                docx_validation["issues"],
                docx_validation["errors"],
                diagnostics_dir=diagnostics_dir,
            )
            console.warn(
                "DOCX validator encountered non-fatal errors; shipping strategy DOCX"
                + (f" ({report_path.name})" if report_path else "")
            )

        return str(docx_path)
    except Exception as e:
        logger.error(f"Failed to save strategy output: {e}")
        return None


def _extract_domain(url: str) -> str | None:
    """Extract domain from a URL for recon lookup.

    Uses recon's own validator for normalization.
    Returns None if the URL cannot be parsed into a valid domain.
    """
    try:
        from recon_tool.validator import validate_domain

        raw = normalized_hostname(url)
        return validate_domain(raw)
    except (ValueError, Exception):
        return None


@release_resume_leases_on_exit
def perform_research(
    company_name: str | None = None,
    website: str | None = None,
    mode: str = "structured",
    citation_style: str = "numbered",
    ai_strategy: bool = False,
    platforms: tuple[str, ...] | None = None,
    output_dir: str | Path | None = None,
    skip_confirm: bool = False,
    context_files: list[Any] | None = None,
    refresh_vendor_research: bool = False,
    strategies: list[str] | None = None,
    strategy_only: bool = False,
    no_qa: bool = False,
    max_scrape_time: int | None = None,
    discovery_notes_path: str | None = None,
    framing_purpose: str | None = None,
    framing_audience: str | None = None,
    framing_decision: str | None = None,
    framing_question: str | None = None,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    skip_scrape_validation: bool = False,
    resume_local: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    skip_recon: bool = False,
    continuous_reasoning: bool = True,
    run_context: dict[str, str] | None = None,
) -> str | None:
    if not company_name and not website:
        console.error("No company name or website provided")
        return None

    display_name: str = company_name or normalized_hostname(website or "", strip_www=True)
    acquire_company_run_lease_for_target(company_name, website, base_dir=WORKING_DIR)
    folder_path = create_working_folder(company_name, website, reuse_incomplete=resume_local)
    if run_context is not None:
        run_context["working_folder"] = folder_path
    explicit_platforms = platforms is not None
    if platforms is None:
        from primr.core.platform_mapper import DEFAULT_PLATFORM_FALLBACK

        platforms = DEFAULT_PLATFORM_FALLBACK
    platform_selection_source = "explicit" if explicit_platforms else "default_agnostic"
    run_output_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
    run_output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir: Path | None = None
    write_public_txt = True
    if output_dir is not None:
        diagnostics_dir = Path(folder_path) / "_diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        write_public_txt = False
    existing_state = _load_run_state(folder_path)
    resume_state = existing_state if resume_local else None
    platforms, platform_selection_source = restore_strategy_platforms(
        tuple(platforms), platform_selection_source, explicit_platforms, resume_state
    )
    if resume_local and existing_state:
        # Ensure resilience keys exist even on resumed runs (NFR 3 backwards compat)
        _ensure_resilience_keys(existing_state)
        _save_run_state(folder_path, existing_state)
        _update_run_state(
            folder_path,
            company_name=company_name or display_name,
            website=website,
            mode=mode,
            status="running",
            current_phase="initializing",
            ai_strategy=ai_strategy,
            cloud_vendors=list(platforms),
            strategy_platform_source=platform_selection_source,
            working_folder=folder_path,
        )
        _append_run_event(
            folder_path, "initializing", "resumed", "Resuming from existing local run folder"
        )
    else:
        _init_run_state_with_resilience(
            folder_path,
            {
                "company_name": company_name or display_name,
                "website": website,
                "mode": mode,
                "status": "running",
                "current_phase": "initializing",
                "ai_strategy": ai_strategy,
                "cloud_vendors": list(platforms),
                "strategy_platform_source": platform_selection_source,
                "working_folder": folder_path,
                "started_at": datetime.now().isoformat(),
                "events": [],
            },
        )
        _append_run_event(folder_path, "initializing", "started", "Run initialized")
    _update_run_state(folder_path, output_dir=str(run_output_dir))  # working-brief public root
    # Resolve operator framing (Step 1): helper owns the discovery-notes read.
    from primr.core.research_framing import resolve_run_framing

    framing, discovery_notes_content, framing_error = resolve_run_framing(
        discovery_notes_path=discovery_notes_path,
        purpose=framing_purpose,
        audience=framing_audience,
        decision=framing_decision,
        core_question=framing_question,
    )
    if framing_error:
        logger.error(framing_error)
        console.error(framing_error)
        _update_run_state(folder_path, status="failed", current_phase="initializing")
        _append_run_event(folder_path, "initializing", "failed", framing_error)
        return None

    recon_info = None  # TenantInfo | None
    recon_context_path: str | None = None

    if not skip_recon and website:
        domain = _extract_domain(website)
        if domain:
            try:
                _update_run_state(folder_path, current_phase="recon")
                _append_run_event(folder_path, "recon", "started", f"Running recon on {domain}")

                from recon_tool.resolver import resolve_tenant

                # Use asyncio.run() (not get_event_loop) so this works on Python 3.14,
                # where get_event_loop() raises "no current event loop" with no running loop.
                # Mirrors skill_pack/evidence.py. This path is synchronous (no loop running).
                info, _recon_results = asyncio.run(
                    asyncio.wait_for(resolve_tenant(domain), timeout=15.0)
                )
                recon_info = info  # noqa: F841 - kept for future downstream use

                from primr.core.platform_mapper import map_platforms, select_strategy_platforms

                detected_platforms = tuple(map_platforms(info.slugs))
                platforms, recon_detected_platforms, platform_selection_source, message = (
                    select_strategy_platforms(
                        detected_platforms, tuple(platforms) if explicit_platforms else None
                    )
                )
                console.info(message)

                from primr.core.recon_context import format_recon_context

                recon_text = format_recon_context(info)
                recon_context_path = os.path.join(folder_path, "_recon_context.txt")
                with open(recon_context_path, "w", encoding="utf-8") as f:
                    f.write(recon_text)

                console.ok(
                    f"Recon: {len(info.services)} services, "
                    f"{len(info.insights)} insights, "
                    f"strategy platform: {', '.join(platforms)}"
                )

                _update_run_state(
                    folder_path,
                    cloud_vendors=list(platforms),
                    strategy_platform_source=platform_selection_source,
                    recon_detected_platforms=list(recon_detected_platforms),
                    recon_service_count=len(info.services),
                    recon_signal_count=len(info.insights),
                )
                _append_run_event(
                    folder_path,
                    "recon",
                    "completed",
                    f"{len(info.services)} services detected",
                )

            except Exception as exc:
                console.warn(f"Recon: {exc} - continuing without domain intelligence")
                _append_run_event(folder_path, "recon", "failed", str(exc))
                # Keep existing platforms (user-specified or default)

    if recon_context_path and os.path.exists(recon_context_path):
        if context_files is None:
            context_files = []
        context_files.insert(0, recon_context_path)

    from primr.core.research_runtime_plan import prepare_research_runtime

    preparation = prepare_research_runtime(
        mode=mode,
        display_name=display_name,
        explicit_fast_mode=fast_mode,
        premium_mode=premium_mode,
        xai_available=bool(os.environ.get("XAI_API_KEY")),
        platform_count=len(platforms),
        ai_strategy=ai_strategy,
        strategy_types=strategies,
        refresh_vendor_research=refresh_vendor_research,
        skip_confirm=skip_confirm,
        lite_strategy=lite_strategy,
        verify=verify,
        grok_tier=grok_tier,
    )
    runtime_plan = preparation.plan
    if preparation.status == "invalid":
        console.error(runtime_plan.error_message or "Unsupported research runtime")
        _update_run_state(folder_path, status="failed", current_phase="initializing")
        return None
    if preparation.status == "cancelled":
        console.info("Research cancelled by user")
        _update_run_state(folder_path, status="cancelled", current_phase="initializing")
        _append_run_event(
            folder_path,
            "initializing",
            "cancelled",
            "Run cancelled by user at cost confirmation",
        )
        return None

    start_time = time.time()

    # Wrap entire research flow in correlation context for tracing
    with correlation_scope("research", company=display_name, mode=mode):
        log_structured(
            "info",
            "Starting research job",
            company=display_name,
            mode=mode,
            ai_strategy=ai_strategy,
        )

        # Fast mode: Grok 4.3 hybrid accordion batch pipeline
        # Activated by: explicit --fast, or auto-detect (complete mode + XAI_API_KEY + not premium)
        if runtime_plan.use_fast and not premium_mode:
            _update_run_state(folder_path, current_phase="fast_mode", status="running")
            _append_run_event(folder_path, "fast_mode", "started", "Fast mode pipeline started")
            fast_path = perform_fast_research(
                company_name,
                website,
                start_time,
                ai_strategy=ai_strategy,
                platforms=platforms,
                strategy_types=strategies,
                max_scrape_time=max_scrape_time,
                discovery_notes_content=discovery_notes_content,
                refresh_vendor_research=refresh_vendor_research,
                framing=framing,
                folder_path=folder_path,
                resume_local=resume_local,
                grok_tier=grok_tier,
                continuous_reasoning=continuous_reasoning,
                output_dir=run_output_dir,
                diagnostics_dir=diagnostics_dir,
                write_txt=write_public_txt,
            )
            if fast_path:
                if verify:
                    _run_claim_verification_non_blocking(
                        company_name or display_name, website or "", fast_path
                    )
                _update_run_state(
                    folder_path,
                    status="completed",
                    current_phase="complete",
                    completed_at=datetime.now().isoformat(),
                )
                _append_run_event(
                    folder_path, "complete", "completed", "Fast mode completed", output=fast_path
                )
            else:
                _update_run_state(folder_path, status="failed", current_phase="fast_mode")
                _append_run_event(folder_path, "fast_mode", "failed", "Fast mode failed")
            return fast_path

        # Handle scrape-only mode - scrape and extract insights
        if mode == "scrape-only":
            _update_run_state(folder_path, current_phase="scrape", status="running")
            return perform_scrape_only(
                company_name,
                website,
                start_time,
                max_scrape_time,
                fail_on_low_scrape=not skip_scrape_validation,
                folder_path=folder_path,
            )

        # Check if using Deep Research, Complete, or Hybrid mode
        if mode in ("deep-research", "complete", "hybrid"):
            _update_run_state(folder_path, current_phase="deep_research", status="running")
            return perform_deep_research(
                company_name,
                website,
                mode,
                start_time,
                citation_style,
                ai_strategy,
                platforms,
                context_files,
                refresh_vendor_research,
                strategies=strategies,
                strategy_only=strategy_only,
                discovery_notes_path=discovery_notes_path,
                discovery_notes_content=discovery_notes_content,
                lite_strategy=lite_strategy,
                fail_on_low_scrape=not skip_scrape_validation,
                folder_path=folder_path,
                output_dir=run_output_dir,
                diagnostics_dir=diagnostics_dir,
                write_txt=write_public_txt,
            )

        try:
            # Phase 1: Data Collection
            console.phase_banner(
                1, 4, "Data Collection", "Scraping website and external sources", "5-10 min"
            )
            _update_run_state(folder_path, current_phase="data_collection", status="running")
            _append_run_event(folder_path, "data_collection", "started", "Data collection started")

            # Scrape website
            with console.timed_operation("Website scrape", show_spinner=False):
                scraped_data = (
                    fetch_web_content(
                        website, company_name, max_pages=50, working_folder=folder_path
                    )
                    if website
                    else {}
                )
                pages_scraped = len(scraped_data)
            log_structured("info", "Website scraping complete", pages=pages_scraped)

            # Warn if scraping was very limited
            if pages_scraped <= 2 and website:
                console.warn("Limited website access - report will rely more on web research")

            if website and not skip_scrape_validation:
                quality_ok, quality_reason = _validate_scrape_quality(scraped_data)
                if not quality_ok:
                    console.fail(quality_reason)
                    console.muted("  Re-run with --skip-scrape-validation to continue anyway")
                    _update_run_state(folder_path, status="failed", current_phase="data_collection")
                    _append_run_event(folder_path, "data_collection", "failed", quality_reason)
                    return None

            # External research - with LLM validation to ensure correct company
            # This prevents including content from similarly-named but unrelated companies
            with console.timed_operation("Searching external sources (with validation)"):
                # Generate targeted search queries using LLM
                external_queries = generate_external_search_queries(
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

                external_data = {}
                max_external_sources = MAX_EXTERNAL_SOURCES

                for query in all_queries:
                    if len(external_data) >= max_external_sources:
                        break

                    results = search_web(query, company_name, website)
                    if results:
                        filtered = [
                            r
                            for r in results[:5]
                            if not website or website.lower() not in r.get("url", "").lower()
                        ]
                        remaining_slots = max_external_sources - len(external_data)
                        scraped = scrape_external_sources_validated(
                            filtered,
                            company_name=company_name,
                            website=website,
                            max_sources=min(2, remaining_slots),
                        )
                        external_data.update(scraped)
            log_structured(
                "info", "External sources complete (validated)", sources=len(external_data)
            )

            all_scraped = {**scraped_data, **external_data}
            console.phase_complete(
                "Data Collection",
                [
                    ("Pages scraped", str(pages_scraped)),
                    ("External sources", str(len(external_data))),
                ],
            )

            # Phase 2: Analysis
            console.phase_banner(2, 4, "Analysis", "Processing and summarizing content", "3-5 min")
            _update_run_state(folder_path, current_phase="analysis", status="running")
            _append_run_event(folder_path, "analysis", "started", "Analysis started")

            with console.timed_operation("Summarizing content"):
                summarized = summarize_scraped_content(
                    company_name, website, all_scraped, folder_path
                )
                if not summarized.strip():
                    summarized = "No insights extracted."

            # Industry identification
            with console.timed_operation("Identifying industry"):
                industry_prompt = generate_prompt(
                    "industry",
                    company_name=company_name,
                    company_website=website or "N/A",
                    scraped_insights=summarized,
                )
                industry = llm(industry_prompt, model_type="research").strip() or "Unknown"
            console.info(f"Industry: {industry}")
            console.phase_complete("Analysis")

            # Phase 3: Report Generation
            console.phase_banner(
                3, 4, "Report Generation", "Building comprehensive report sections", "10-15 min"
            )
            _update_run_state(folder_path, current_phase="report_generation", status="running")
            _append_run_event(
                folder_path, "report_generation", "started", "Report generation started"
            )

            # Overview
            with console.timed_operation("Building overview"):
                overview = generate_initial_overview(company_name, website, industry, folder_path)

            # Value theory
            with console.timed_operation("Value analysis"):
                value_prompt = generate_prompt(
                    "value_theory", company_name=company_name, company_website=website or "N/A"
                )
                value_theory = llm(value_prompt, model_type="research").strip()

                value_file = os.path.join(folder_path, "value_theory.txt")
                with open(value_file, "w", encoding="utf-8") as f:
                    f.write(value_theory or "N/A")

            # Sections
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

            section_start = time.time()
            for i, section in enumerate(sections):
                console.progress_with_time(i + 1, len(sections), section, section_start)
                research_section(
                    section, company_name, website, industry, folder_path, overview, summarized
                )

            console.progress_done()
            console.phase_complete("Report Generation", [("Sections", str(len(sections)))])

            # Phase 4: Output
            total_phases = 4 + (1 if ai_strategy else 0) + (1 if verify else 0)
            console.phase_banner(
                4, total_phases, "Finalizing", "Generating output documents", "1-2 min"
            )
            _update_run_state(folder_path, current_phase="finalizing", status="running")
            _append_run_event(folder_path, "finalizing", "started", "Finalizing output documents")
            with console.timed_operation("Generating documents"):
                docx_path = generate_final_report(
                    company_name or display_name,
                    citation_style=citation_style,
                    output_dir=run_output_dir,
                    diagnostics_dir=diagnostics_dir,
                    write_txt=write_public_txt,
                )

            from primr.core.standard_strategy import run_standard_ai_strategy

            standard_strategy = run_standard_ai_strategy(
                enabled=ai_strategy,
                company_name=company_name or display_name,
                platform=platforms[0],
                folder_path=folder_path,
                total_phases=total_phases,
                refresh_vendor_research=refresh_vendor_research,
                discovery_notes_content=discovery_notes_content,
                lite_strategy=lite_strategy,
                output_dir=run_output_dir,
                diagnostics_dir=diagnostics_dir,
                write_txt=write_public_txt,
                consolidate_context=consolidate_working_folder,
                generate_strategy=_generate_ai_strategy_section,
            )
            ai_strategy_path = standard_strategy.output_path

            # Run QA analysis if enabled (default: enabled, --no-qa disables)
            qa_result = None
            ai_strategy_qa_result = None
            if not no_qa:
                try:
                    from primr.qa.integration import QAIntegration
                    from primr.qa.models import QAOptions

                    verbose_mode = hasattr(console, "verbose") and console.verbose

                    qa_options = QAOptions(
                        enabled=True, save_detailed=True, verbose_cli=verbose_mode
                    )
                    qa_integration = QAIntegration(qa_options)

                    # QA for main Strategic Overview report
                    if docx_path:
                        txt_report_path = Path(docx_path).with_suffix(".txt")
                        if not txt_report_path.exists() and diagnostics_dir is not None:
                            txt_report_path = diagnostics_dir / txt_report_path.name
                        if txt_report_path.exists():
                            qa_result = qa_integration.run_post_generation_qa(
                                txt_report_path, company_name or display_name
                            )

                    # QA for AI Strategy report
                    if ai_strategy_path:
                        ai_strategy_txt = Path(ai_strategy_path).with_suffix(".txt")
                        if not ai_strategy_txt.exists() and diagnostics_dir is not None:
                            ai_strategy_txt = diagnostics_dir / ai_strategy_txt.name
                        if ai_strategy_txt.exists():
                            ai_strategy_qa_result = qa_integration.run_post_generation_qa(
                                ai_strategy_txt, f"{company_name or display_name} (AI Strategy)"
                            )

                except Exception as e:
                    logger.warning(f"QA analysis failed: {e}")

            if verify and docx_path:
                _run_claim_verification_non_blocking(
                    company_name or display_name,
                    website or "",
                    docx_path,
                    phase=6 if ai_strategy else 5,
                )

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

            from primr.core.standard_run_summary import finalize_standard_run

            finalize_standard_run(
                mode=mode,
                display_name=display_name,
                folder_path=folder_path,
                elapsed=elapsed,
                time_str=time_str,
                sections_generated=len(sections),
                docx_path=docx_path,
                strategy=standard_strategy,
            )

            return docx_path

        except Exception as e:
            console.error(f"Research failed: {e}")
            log_structured("error", "Research failed", error=str(e), error_type=type(e).__name__)
            logger.exception("Research failed")
            _update_run_state(folder_path, status="failed", current_phase="error")
            _append_run_event(folder_path, "error", "failed", str(e))
            return None


def perform_deep_research(
    company_name: str | None,
    website: str | None,
    mode: str,
    start_time: float,
    citation_style: str = "numbered",
    ai_strategy: bool = False,
    platforms: tuple[str, ...] = ("agnostic",),
    context_files: list[Any] | None = None,
    refresh_vendor_research: bool = False,
    strategies: list[str] | None = None,
    strategy_only: bool = False,
    discovery_notes_path: str | None = None,
    discovery_notes_content: str | None = None,
    lite_strategy: bool = False,
    fail_on_low_scrape: bool = True,
    folder_path: str | None = None,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
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
        platforms: Platform(s) for AI recommendations
        context_files: Optional list of files (PDFs, docs) to upload as context for Deep Research
        refresh_vendor_research: If True, force regenerate vendor research
        strategies: List of strategy module names to generate (e.g., ['ai', 'cloud'])
        strategy_only: If True, skip company overview and only run strategies
        discovery_notes_path: Path to discovery notes file (for logging/tracking)
        discovery_notes_content: Loaded content of discovery notes (freeform meeting insights)
    """
    display_name: str = company_name or normalized_hostname(website or "", strip_www=True)
    folder_path = folder_path or create_working_folder(company_name, website)
    run_output_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
    run_output_dir.mkdir(parents=True, exist_ok=True)
    if diagnostics_dir is not None:
        Path(diagnostics_dir).mkdir(parents=True, exist_ok=True)
    _update_run_state(folder_path, current_phase="preflight", status="running")
    _append_run_event(folder_path, "preflight", "started", "Deep research run started")

    # =================================================================
    # PRE-FLIGHT VALIDATION - Verify everything BEFORE expensive API calls
    # =================================================================
    preflight_errors = []

    if not company_name and not website:
        preflight_errors.append("Must provide company name or website")

    if context_files:
        for f in context_files:
            if not os.path.exists(f):
                preflight_errors.append(f"Context file not found: {f}")
            elif not os.path.isfile(f):
                preflight_errors.append(f"Context path is not a file: {f}")
            elif os.path.getsize(f) == 0:
                preflight_errors.append(f"Context file is empty: {f}")

    from primr.config.settings import get_settings

    settings = get_settings()
    if not settings.api.gemini_key:
        preflight_errors.append("GEMINI_API_KEY not configured")

    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        console.error("Fix these issues before running expensive Deep Research")
        _update_run_state(folder_path, status="failed", current_phase="preflight")
        _append_run_event(
            folder_path,
            "preflight",
            "failed",
            "Pre-flight validation failed",
            errors=preflight_errors,
        )
        return None

    # Pre-run cleanup: leaked File Search Stores have NO TTL and cost money.
    try:
        from primr.ai.deep_research import cleanup_orphaned_resources

        orphans = cleanup_orphaned_resources()
        if orphans["caches_deleted"] or orphans["stores_deleted"]:
            console.warn(
                f"Cleaned up {orphans['caches_deleted']} orphaned cache(s) "
                f"and {orphans['stores_deleted']} orphaned store(s) from prior run"
            )
    except Exception as e:
        logger.debug(f"Pre-run resource cleanup check failed (non-fatal): {e}")

    mode_map = {
        "deep-research": (ResearchMode.DEEP_RESEARCH, "Deep Research"),
        "complete": (ResearchMode.COMPLETE, "Complete (Two-Step)"),
        "hybrid": (ResearchMode.HYBRID, "Hybrid"),
    }
    research_mode, mode_label = mode_map.get(mode, (ResearchMode.DEEP_RESEARCH, "Deep Research"))

    with correlation_scope("deep_research", company=display_name, mode=mode):
        log_structured("info", "Starting deep research", company=display_name, mode=mode)

        # For COMPLETE mode, the orchestrator handles all phase banners
        # For simple DEEP_RESEARCH mode, we show our own phase banners
        is_simple_deep_research = mode == "deep-research"

        if is_simple_deep_research:
            context_info = ""
            if context_files:
                context_info = f" with {len(context_files)} context file(s)"
            console.phase_banner(
                1, 3, f"{mode_label}{context_info}", "Autonomous AI research", "10-15 min"
            )
        _update_run_state(folder_path, current_phase="deep_research", status="running")
        _append_run_event(folder_path, "deep_research", "started", f"{mode_label} started")

        last_phase: list[str | None] = [None]  # list = mutable cell for closure
        last_update_time = [time.time()]

        def progress_callback(msg: str) -> None:
            # Extract phase from message (e.g., "Searching sources (2m 30s)")
            phase = msg.split(" (")[0].strip() if " (" in msg else msg.strip()

            display_msg = msg.lstrip(". ")

            # Show indented sub-status messages (e.g. "  Uploading Stage 1 context")
            if msg.startswith("  "):
                console.muted(f"  {msg.strip()}")
                log_structured("debug", f"Deep research progress: {msg}")
                return

            if phase and phase != last_phase[0] and not phase.startswith("  "):
                last_phase[0] = phase
                last_update_time[0] = time.time()
                console.info(display_msg)
            elif time.time() - last_update_time[0] > 120:
                last_update_time[0] = time.time()
                console.muted(f"  Still working... {display_msg}")

            log_structured("debug", f"Deep research progress: {msg}")

        # Hiring signals ride into the Deep Research stage-1 context, fenced
        # (roadmap #3). Strategy-only runs skip (no overview to enrich), and
        # the legacy parallel hybrid path skips too - it never consumes
        # stage-1 context, so gathering would spend the stage and drop it.
        hiring_context = (
            ""
            if strategy_only or mode == "hybrid"
            else collect_fenced_hiring_block(
                company_label=display_name,
                website=website,
                scraped_data={},
                folder_path=folder_path,
            )
        )

        try:
            orchestrator = get_orchestrator()

            from primr.utils.async_utils import run_sync

            result = run_sync(
                orchestrator.research(
                    company_name=company_name or display_name,
                    website=website,
                    mode=research_mode,
                    config=ResearchConfig(
                        mode=research_mode,
                        fail_on_low_scrape=fail_on_low_scrape,
                        supplemental_context=hiring_context or None,
                        folder_path=folder_path,
                    ),
                    on_progress=progress_callback,
                    context_files=context_files,
                )
            )

            if not result.success:
                console.fail(f"Research failed: {result.error}")
                log_structured("error", "Deep research failed", error=result.error)
                _update_run_state(folder_path, status="failed", current_phase="deep_research")
                _append_run_event(
                    folder_path,
                    "deep_research",
                    "failed",
                    "Deep research failed",
                    error=result.error,
                )

                # Save partial results if the structured phase produced anything
                if result.section_results:
                    partial_folder = folder_path
                    partial_count = 0
                    for section_key, content in result.section_results.items():
                        save_section_output(partial_folder, section_key, content)
                        partial_count += 1
                    console.warn(
                        f"Saved {partial_count} partial sections from data collection to: {partial_folder}"
                    )
                    console.muted(
                        "  Tip: Re-run with --mode scrape to generate a report from scraped data"
                    )
                else:
                    console.muted("  Tip: Check logs for details, or re-run with --mode scrape")

                return None

            # Use sections_written for accurate count (accordion method tracks this)
            section_count = (
                result.sections_written
                if result.sections_written > 0
                else len(result.section_results)
            )
            log_structured("info", "Deep research complete", sections=section_count)

            # Calculate word and page count from raw content. Round to nearest
            # page and floor at 1 for any non-empty report - plain floor
            # division shows "~0 pages" for 1-499-word reports.
            word_count = len(result.raw_content.split()) if result.raw_content else 0
            page_count = max(1, round(word_count / 500)) if word_count else 0  # ~500 words/page

            if is_simple_deep_research:
                console.phase_complete(
                    "Deep Research",
                    [
                        ("Pages", f"~{page_count}"),
                        ("Words", f"{word_count:,}"),
                        ("Chapters", str(section_count)),
                    ],
                )
                console.phase_banner(
                    2, 3, "Processing Results", "Saving and converting output", "1-2 min"
                )
            _append_run_event(
                folder_path,
                "deep_research",
                "completed",
                "Deep research completed",
                pages=page_count,
                chapters=section_count,
            )
            _update_run_state(folder_path, current_phase="processing_results", status="running")

            with console.timed_operation("Saving results"):
                for section_key, content in result.section_results.items():
                    save_section_output(folder_path, section_key, content)

            raw_md_path = None
            if result.raw_content:
                raw_md_path = os.path.join(folder_path, "deep_research_output.md")
                with open(raw_md_path, "w", encoding="utf-8") as f:
                    f.write(result.raw_content)

            with console.timed_operation("Generating documents"):
                durable_report_paths: list[Path] = []
                if result.raw_content and mode in ("deep-research", "complete", "hybrid"):
                    # Deep Research: convert markdown directly to DOCX (preserves structure)
                    docx_path = _convert_deep_research_to_docx(
                        result.raw_content,
                        company_name or display_name,
                        website,
                        output_dir=run_output_dir,
                        diagnostics_dir=diagnostics_dir,
                        write_txt=write_txt,
                        written_paths=durable_report_paths,
                    )
                else:
                    # Structured pipeline: use DocumentBuilder to assemble sections
                    docx_path = generate_final_report(
                        company_name or display_name,
                        citation_style=citation_style,
                        output_dir=run_output_dir,
                        diagnostics_dir=diagnostics_dir,
                        write_txt=write_txt,
                    )

            pending_interaction_id = getattr(result, "pending_interaction_id", "")
            if isinstance(pending_interaction_id, str) and pending_interaction_id:
                from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

                if not docx_path or not acknowledge_pending_job_after_outputs(
                    pending_interaction_id, durable_report_paths
                ):
                    console.warn(
                        "Deep Research output is incomplete; its pending job remains recoverable."
                    )

            if is_simple_deep_research:
                console.phase_complete("Processing Results")

            strategies_to_run: list[str] = []
            if strategies:
                strategies_to_run = strategies
            elif ai_strategy:
                strategies_to_run = ["ai"]

            strategy_paths: dict[str, str] = {}
            strategy_deep_research_tasks_started = 0
            from primr.core.strategy_outcome import (
                StrategyOutcomeTracker,
                StrategyTaskTracker,
                expected_strategy_targets,
                persist_strategy_outcome,
                strategy_target,
            )

            strategy_outcome_tracker = StrategyOutcomeTracker(
                expected_strategy_targets(strategies_to_run, platforms)
            )
            strategy_task_tracker = StrategyTaskTracker()
            from primr.core.deep_vendor_refresh import prepare_deep_strategy_vendor_refreshes

            vendor_refresh_result = prepare_deep_strategy_vendor_refreshes(
                refresh_vendor_research, strategies_to_run, platforms, mode, folder_path
            )
            if strategies_to_run:
                from primr.core.deep_budget import (
                    skip_optional_strategy_if_over_budget,
                )
                from primr.core.strategy_loop import (
                    count_strategy_phases,
                    record_strategy_completion,
                    strategy_display_labels,
                    strategy_vendors,
                )
                from primr.core.strategy_prompt_parts import write_strategy_context_bundle

                _update_run_state(
                    folder_path, current_phase="strategy_generation", status="running"
                )
                _append_run_event(
                    folder_path,
                    "strategy_generation",
                    "started",
                    "Strategy generation started",
                    strategies=strategies_to_run,
                )
                base_phase = 3
                total_phase_count = count_strategy_phases(strategies_to_run, platforms)
                strategy_context_path = write_strategy_context_bundle(folder_path, raw_md_path)

                phase_offset = 0
                skip_remaining_strategies = False
                for strategy_name in strategies_to_run:
                    for vendor in strategy_vendors(strategy_name, platforms):
                        target = strategy_target(strategy_name, vendor)
                        if skip_optional_strategy_if_over_budget(
                            mode=mode,
                            optional_strategy_tasks_started=strategy_task_tracker.started_count,
                            vendor_refresh_tasks_started=vendor_refresh_result.started_count,
                            folder_path=folder_path,
                            strategy_name=strategy_name,
                            platform=vendor,
                        ):
                            strategy_outcome_tracker.mark_skipped(target)
                            strategy_outcome_tracker.mark_remaining_skipped()
                            skip_remaining_strategies = True
                            break

                        phase_num = base_phase + phase_offset
                        total_phases = base_phase + total_phase_count - 1
                        display_strategy_name, vendor_label = strategy_display_labels(
                            strategy_name, vendor, platforms
                        )

                        console.phase_banner(
                            phase_num,
                            total_phases,
                            f"{display_strategy_name}{vendor_label} Analysis",
                            f"Generating {display_strategy_name.lower()} recommendations{vendor_label.lower()}",
                            "5-10 min",
                        )

                        strategy_path = _generate_strategy_section(
                            strategy_name=strategy_name,
                            company_name=company_name or display_name,
                            platform=vendor,
                            company_research_path=strategy_context_path or raw_md_path,
                            force_refresh_vendor=False,
                            discovery_notes_content=discovery_notes_content,
                            lite_strategy=lite_strategy,
                            output_dir=run_output_dir,
                            diagnostics_dir=diagnostics_dir,
                            write_txt=write_txt,
                            strategy_task_observer=strategy_task_tracker.observe,
                        )

                        if strategy_path:
                            record_strategy_completion(
                                strategy_paths=strategy_paths,
                                strategy_name=strategy_name,
                                vendor=vendor,
                                platforms=platforms,
                                output_path=strategy_path,
                                folder_path=folder_path,
                                display_strategy_name=display_strategy_name,
                                vendor_label=vendor_label,
                            )
                            strategy_outcome_tracker.mark_completed(target)
                        else:
                            strategy_outcome_tracker.mark_failed(target)
                            _append_run_event(
                                folder_path,
                                "strategy_generation",
                                "failed",
                                f"{display_strategy_name}{vendor_label} failed",
                                strategy=strategy_name,
                                platform=vendor,
                            )

                        phase_offset += 1
                    if skip_remaining_strategies:
                        break

            strategy_deep_research_tasks_started = strategy_task_tracker.started_count
            strategy_outcome = strategy_outcome_tracker.snapshot()
            persist_strategy_outcome(folder_path, strategy_outcome)

            elapsed = time.time() - start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

            console.ok(f"Complete in {time_str}")
            _update_run_state(
                folder_path,
                status="completed",
                current_phase="complete",
                completed_at=datetime.now().isoformat(),
                duration_seconds=elapsed,
            )
            _append_run_event(folder_path, "complete", "completed", f"Run completed in {time_str}")

            if docx_path:
                console.success_box("Report ready", str(Path(docx_path).resolve()))

            for strat_key, strategy_path in strategy_paths.items():
                from primr.prompts.registry import get_registry

                registry = get_registry()
                if "_" in strat_key and strat_key.split("_", 1)[0] == "ai":
                    base_name = "ai"
                    vendor_suffix = f" ({strat_key.split('_', 1)[1].upper()})"
                else:
                    base_name = strat_key
                    vendor_suffix = ""
                strategy_module = registry.get(base_name)
                strat_display_name = (
                    strategy_module.display_name
                    if strategy_module
                    else base_name.replace("_", " ").title()
                )
                console.success_box(
                    f"{strat_display_name}{vendor_suffix}", str(Path(strategy_path).resolve())
                )

            # Cost reconciliation, summary display, usage record, job summary.
            from primr.core.deep_run_summary import finalize_deep_run

            finalize_deep_run(
                mode=mode,
                mode_label=mode_label,
                result=result,
                ai_strategy=ai_strategy,
                platforms=platforms,
                lite_strategy=lite_strategy,
                strategies=strategies,
                strategy_deep_research_tasks_started=strategy_deep_research_tasks_started,
                refresh_vendor_research=refresh_vendor_research,
                vendor_refresh_tasks_started=vendor_refresh_result.started_count,
                strategy_outcome=strategy_outcome,
                vendor_refresh_outcome=vendor_refresh_result.outcome,
                time_str=time_str,
                elapsed=elapsed,
                display_name=display_name,
                docx_path=docx_path,
            )

            return docx_path

        except Exception as e:
            console.error(f"Deep research failed: {e}")
            log_structured(
                "error", "Deep research failed", error=str(e), error_type=type(e).__name__
            )
            logger.exception("Deep research failed")
            _update_run_state(folder_path, status="failed", current_phase="error")
            _append_run_event(folder_path, "error", "failed", str(e))
            return None
        finally:
            # Post-run: verify no resources leaked (safety net)
            try:
                from primr.ai.deep_research import cleanup_orphaned_resources

                leaked = cleanup_orphaned_resources()
                if leaked["caches_deleted"] or leaked["stores_deleted"]:
                    logger.warning(
                        f"Post-run cleanup found leaked resources: "
                        f"{leaked['caches_deleted']} cache(s), {leaked['stores_deleted']} store(s)"
                    )
            except Exception as cleanup_err:
                logger.debug(f"Post-run resource cleanup failed (non-fatal): {cleanup_err}")


def _prepare_report_markdown_for_shipping(markdown_content: str) -> str:
    """Apply deterministic cleanup before report artifact validation/shipping."""
    from primr.output.final_artifact import canonicalize_final_markdown

    prepared = _clean_fast_report_output(markdown_content)
    prepared = canonicalize_final_markdown(prepared)
    prepared = _normalize_fast_citations(prepared)
    prepared = _strip_internal_source_placeholders(prepared)
    prepared = _enforce_fast_section_quality_guards(prepared)
    prepared = canonicalize_final_markdown(prepared)
    return prepared


def _prepare_strategy_markdown_for_shipping(strategy_content: str) -> str:
    """Apply deterministic cleanup before strategy artifact validation/shipping."""
    from primr.output.final_artifact import canonicalize_final_markdown

    prepared = canonicalize_final_markdown(strategy_content)
    prepared = _clean_strategy_output(prepared)
    prepared = canonicalize_final_markdown(prepared)
    return prepared


def _prepare_markdown_for_shipping(content: str, kind: str) -> str:
    if kind == "strategy":
        return _prepare_strategy_markdown_for_shipping(content)
    return _prepare_report_markdown_for_shipping(content)


def _salvage_markdown_for_shipping(
    markdown_content: str,
    kind: str,
) -> tuple[str, _ArtifactValidation, bool]:
    """Run one deterministic salvage pass before blocking artifact shipping.

    Three escalation levels:
    1. Validate raw content - if clean, ship as-is.
    2. Run kind-specific cleanup pipeline - if clean, ship salvaged.
    3. Auto-strip ALL forbidden patterns (last resort) - if clean, ship.

    Level 3 ensures any new forbidden pattern added to the scanner is
    automatically cleaned without needing a matching cleanup rule.
    """
    validation = _validate_output_markdown(markdown_content)
    if validation["passed"]:
        return markdown_content, validation, False

    prepared = _prepare_markdown_for_shipping(markdown_content, kind)
    if prepared == markdown_content:
        stripped = _auto_strip_forbidden_patterns(markdown_content)
        if stripped != markdown_content:
            stripped_validation = _validate_output_markdown(stripped)
            if stripped_validation["passed"]:
                return stripped, stripped_validation, True
            if len(stripped_validation["issues"]) < len(validation["issues"]):
                return stripped, stripped_validation, True
        return markdown_content, validation, False

    prepared_validation = _validate_output_markdown(prepared)
    if prepared_validation["passed"]:
        return prepared, prepared_validation, True

    stripped = _auto_strip_forbidden_patterns(prepared)
    if stripped != prepared:
        stripped_validation = _validate_output_markdown(stripped)
        if stripped_validation["passed"]:
            return stripped, stripped_validation, True
        if len(stripped_validation["issues"]) < len(prepared_validation["issues"]):
            return stripped, stripped_validation, True

    if len(prepared_validation["issues"]) < len(validation["issues"]):
        return prepared, prepared_validation, True

    return markdown_content, validation, False


def _convert_deep_research_to_docx(
    markdown_content: str,
    company_name: str,
    website: str | None,
    gate_issues: list[str] | None = None,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
    written_paths: list[Path] | None = None,
) -> str | None:
    """Convert Deep Research markdown to validated MD, TXT, and DOCX outputs."""
    from primr.output.markdown_converter import markdown_to_docx
    from primr.output.output_utils import OUTPUT_DIR

    date_str = datetime.now().strftime("%m-%d-%Y")
    base_name = f"{sanitize_for_filename(company_name, 200)}_Strategic_Overview_{date_str}"
    destination_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
    destination_dir.mkdir(parents=True, exist_ok=True)
    internal_dir = Path(diagnostics_dir) if diagnostics_dir is not None else destination_dir
    internal_dir.mkdir(parents=True, exist_ok=True)

    try:
        markdown_content, markdown_validation, salvaged = _salvage_markdown_for_shipping(
            markdown_content,
            kind="report",
        )

        # Save markdown (.md)
        md_path = destination_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        if written_paths is not None:
            written_paths.append(md_path)
        console.ok(f"MD saved: {base_name}.md", show_time=False)

        # Save plain text (.txt). For custom output directories, keep this
        # machine-facing mirror in the diagnostics folder so the requested
        # output path stays focused on customer-facing deliverables.
        if write_txt or diagnostics_dir is not None:
            txt_path = (destination_dir if write_txt else internal_dir) / f"{base_name}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            if written_paths is not None:
                written_paths.append(txt_path)
            if write_txt:
                console.ok(f"TXT saved: {base_name}.txt", show_time=False)
        if salvaged:
            console.info("Adaptive salvage cleaned report markdown before shipping")

        # Build subtitle with date and website
        subtitle_parts = [datetime.now().strftime("%B %d, %Y")]
        if website:
            subtitle_parts.append(website)
        subtitle = " | ".join(subtitle_parts)

        combined_markdown_issues = list(markdown_validation["issues"])
        if gate_issues:
            combined_markdown_issues.extend(gate_issues)
        if combined_markdown_issues:
            report_path = _write_output_validation_report(
                md_path,
                "markdown",
                combined_markdown_issues,
                markdown_validation["errors"],
                diagnostics_dir=diagnostics_dir,
            )
            console.warn("Report artifact issues: " + ", ".join(combined_markdown_issues[:3]))
            console.warn(
                "DOCX shipping gate failed for report markdown; saved MD/TXT only"
                + (f" ({report_path.name})" if report_path else "")
            )
            return None

        # Convert to DOCX
        docx_path = destination_dir / f"{base_name}.docx"
        try:
            markdown_to_docx(
                markdown_text=markdown_content,
                output_path=docx_path,
                title=f"Strategic Company Overview: {company_name}",
                subtitle=subtitle,
            )
        except PermissionError:
            # File is probably open in Word - try with timestamp suffix
            timestamp = datetime.now().strftime("%H%M%S")
            file_name = f"{base_name}_{timestamp}.docx"
            docx_path = destination_dir / file_name
            console.warn(f"Original file locked, saving as: {file_name}")
            markdown_to_docx(
                markdown_text=markdown_content,
                output_path=docx_path,
                title=f"Strategic Company Overview: {company_name}",
                subtitle=subtitle,
            )

        docx_validation = _validate_output_docx(docx_path)
        if not docx_validation["passed"]:
            report_path = _write_output_validation_report(
                docx_path,
                "docx",
                docx_validation["issues"],
                docx_validation["errors"],
                diagnostics_dir=diagnostics_dir,
            )
            try:
                docx_path.unlink(missing_ok=True)
            except Exception as cleanup_err:
                logger.warning("Failed to remove blocked DOCX %s: %s", docx_path, cleanup_err)
            console.warn(
                "DOCX shipping gate failed for rendered report; saved MD/TXT only"
                + (f" ({report_path.name})" if report_path else "")
            )
            return None

        if docx_validation["errors"]:
            report_path = _write_output_validation_report(
                docx_path,
                "docx",
                docx_validation["issues"],
                docx_validation["errors"],
                diagnostics_dir=diagnostics_dir,
            )
            console.warn(
                "DOCX validator encountered non-fatal errors; shipping report DOCX"
                + (f" ({report_path.name})" if report_path else "")
            )

        console.ok(f"DOCX saved: {docx_path.name}", show_time=False)
        if written_paths is not None:
            written_paths.append(docx_path)
        return str(docx_path)

    except Exception as e:
        console.error(f"Failed to convert markdown to DOCX: {e}")
        logger.exception("Markdown to DOCX conversion failed")
        return None


def _generate_strategy_section(
    strategy_name: str,
    company_name: str,
    platform: str,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    discovery_notes_content: str | None = None,
    lite_strategy: bool = False,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
    strategy_task_observer: Callable[[str], None] | None = None,
) -> str | None:
    """Dispatch one YAML-backed strategy and report its durable artifact."""
    strategy_map = {
        "customer_experience": "customer_experience",
        "modern_security_compliance": "modern_security_compliance",
        "data_fabric_strategy": "data_fabric_strategy",
        "skills": "skills",
    }

    if strategy_name == "ai":
        return _generate_ai_strategy_section(
            company_name=company_name,
            platform=platform,
            company_research_path=company_research_path,
            force_refresh_vendor=force_refresh_vendor,
            discovery_notes_content=discovery_notes_content,
            lite_strategy=lite_strategy,
            output_dir=output_dir,
            diagnostics_dir=diagnostics_dir,
            write_txt=write_txt,
            strategy_task_observer=strategy_task_observer,
        )

    if strategy_name in strategy_map:
        return _generate_generic_strategy(
            strategy_name=strategy_name,
            strategy_yaml=strategy_map[strategy_name],
            company_name=company_name,
            company_research_path=company_research_path,
            discovery_notes_content=discovery_notes_content,
            output_dir=output_dir,
            diagnostics_dir=diagnostics_dir,
            write_txt=write_txt,
            strategy_task_observer=strategy_task_observer,
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
    discovery_notes_content: str | None = None,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
    strategy_task_observer: Callable[[str], None] | None = None,
) -> str | None:
    return _generate_generic_strategy_impl(
        strategy_name=strategy_name,
        strategy_yaml=strategy_yaml,
        company_name=company_name,
        company_research_path=company_research_path,
        discovery_notes_content=discovery_notes_content,
        output_dir=output_dir,
        diagnostics_dir=diagnostics_dir,
        write_txt=write_txt,
        strategy_task_observer=strategy_task_observer,
    )


def _build_strategy_prompt_from_yaml(
    strategy_config: dict, company_name: str, discovery_notes_content: str | None = None
) -> str:
    return _build_strategy_prompt_from_yaml_impl(
        strategy_config=strategy_config,
        company_name=company_name,
        discovery_notes_content=discovery_notes_content,
    )


def _generate_ai_strategy_section(
    company_name: str,
    platform: str,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    discovery_notes_content: str | None = None,
    lite_strategy: bool = False,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
    vendor_refresh_observer: Callable[[str], None] | None = None,
    strategy_task_observer: Callable[[str], None] | None = None,
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
        platform: Platform preference (azure, aws, gcp)
        company_research_path: Path to company research markdown (used as context)
        force_refresh_vendor: If True, regenerate vendor research even if current
        discovery_notes_content: Optional freeform meeting insights from discovery

    Returns:
        Path to the generated DOCX file, or None if generation failed
    """
    return _generate_ai_strategy_section_impl(
        company_name=company_name,
        platform=platform,
        company_research_path=company_research_path,
        force_refresh_vendor=force_refresh_vendor,
        discovery_notes_content=discovery_notes_content,
        lite_strategy=lite_strategy,
        output_dir=output_dir,
        diagnostics_dir=diagnostics_dir,
        write_txt=write_txt,
        vendor_refresh_observer=vendor_refresh_observer,
        strategy_task_observer=strategy_task_observer,
    )


def _build_ai_strategy_prompt(
    company_name: str, platform: str, discovery_notes_content: str | None = None
) -> str:
    return _build_ai_strategy_prompt_impl(
        company_name=company_name,
        platform=platform,
        discovery_notes_content=discovery_notes_content,
    )


def _run_claim_verification_non_blocking(
    company_name: str,
    company_url: str,
    report_path: str,
    *,
    phase: int | None = None,
) -> Any:
    try:
        if phase is not None:
            console.phase_banner(
                phase, phase, "Claim Verification", "Verifying factual claims", "1-3 min"
            )
        result = _run_verification(company_name, company_url, report_path)
        if result:
            from primr.core.verification_summary import build_verification_display_stats

            stats = build_verification_display_stats(result)
            console.phase_complete("Claim Verification", stats.phase)
            console.trust_summary("Report Trust", stats.trust_summary)
        elif phase is not None:
            console.phase_complete("Claim Verification", [("Status", "No claims found")])
        return result
    except Exception as e:
        logger.warning(f"Claim verification failed: {e}")
        console.warn(f"Verification failed (non-blocking): {e}")


def _run_verification(
    company_name: str,
    company_url: str,
    report_path: str,
) -> Any:
    """Run claim verification on a report. Returns VerificationResult or None."""
    import asyncio
    from pathlib import Path

    from primr.agentic.subagents.base import SubagentContext
    from primr.agentic.subagents.verifier import VerifierSubagent

    txt_path = Path(report_path).with_suffix(".txt")
    if not txt_path.exists():
        txt_path = Path(report_path)
        if txt_path.suffix in (".docx", ".pdf"):
            logger.warning(
                f"Verification: no .txt companion found, using {txt_path.suffix} file directly"
            )
            return None

    context = SubagentContext(
        company_name=company_name,
        company_url=company_url,
        working_dir=txt_path.parent,
        parent_results={"report_path": txt_path},
    )
    verifier = VerifierSubagent(context)

    try:
        asyncio.get_running_loop()
        # Already in an async context - run in a thread to avoid RuntimeError
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, verifier.execute()).result()
    except RuntimeError:
        # No running loop - safe to use asyncio.run directly
        result = asyncio.run(verifier.execute())

    if result.is_success and result.data:
        return result.data
    return None


def improve_output_file(
    file_path: str, *, in_place: bool = False, use_agentic: bool = False
) -> str | None:
    """Improve an existing markdown/text output artifact with deterministic + optional agentic QA cleanup."""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        console.error(f"Improve failed: file not found: {file_path}")
        return None

    if path.suffix.lower() not in {".md", ".txt"}:
        console.error(
            "Improve supports .md or .txt files. Convert DOCX/PDF to markdown/text first."
        )
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        console.error(f"Improve failed: could not read file: {e}")
        return None

    is_strategy = "# AI Strategy:" in content or "_AI_Strategy_" in path.name

    if is_strategy:
        improved = content
        if use_agentic:
            cv = _strategy_cross_validate("Company", improved, "agnostic", [])
            if cv.get("weak_sections") or cv.get("issues"):
                improved = _strategy_polish("Company", "agnostic", improved)
        improved = _clean_strategy_output(improved)
        qa = _compute_strategy_qa_metrics(improved)
        console.info(
            "Improve QA (strategy): "
            f"placeholders={qa['placeholder_refs']}, "
            f"sources={qa['source_urls']}, "
            f"budget={'OK' if not qa['budget_inconsistent'] else 'WARN'}, "
            f"gate={'PASS' if qa['qa_gate_passed'] else 'WARN'}"
        )
    else:
        improved = content
        if use_agentic:
            cv = _fast_cross_validate("Company", None, improved, [])
            if cv.get("weak_sections") or cv.get("contradictions"):
                improved = _polish_fast_report_for_trust("Company", None, improved, [])
        improved = _clean_fast_report_output(improved)
        improved = _normalize_fast_citations(improved)
        improved = _strip_internal_source_placeholders(improved)
        improved = _enforce_fast_section_quality_guards(improved)
        qa = _compute_fast_report_qa_metrics(improved)
        console.info(
            "Improve QA (report): "
            f"labels={qa['confidence_labels']}, "
            f"cites={qa['citations_used']}/{qa['citations_defined']}, "
            f"validate={qa['sections_with_validate']}/{qa['section_count']}, "
            f"gate={'PASS' if qa['qa_gate_passed'] else 'WARN'}"
        )

    # Enforced write allowlist (roadmap #11): the agentic improve stage may
    # only write the target artifact (or its _improved sibling) - never run
    # state, raw scrapes, or anything else. Architectural constraint, not a
    # trust-based policy.
    from primr.utils.write_guard import ArtifactWriteGuard, WriteGuardError

    guard = ArtifactWriteGuard(path)
    out_path = path if in_place else path.with_name(f"{path.stem}_improved{path.suffix}")
    try:
        guard.write_text(out_path, improved)
    except WriteGuardError as e:
        console.error(f"Improve blocked by write guard: {e}")
        return None
    except Exception as e:
        console.error(f"Improve failed: could not write output: {e}")
        return None

    return str(out_path)


def process_csv(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    platforms: tuple[str, ...] | None = None,
    no_qa: bool = False,
) -> None:
    """Retain the legacy export while enforcing the governed batch approval."""
    from primr.core.cli_batch_runtime import process_batch as run_governed_batch

    run_governed_batch(
        file_path,
        mode=mode,
        citation_style=citation_style,
        ai_strategy=ai_strategy,
        platforms=platforms,
        skip_confirm=False,
        no_qa=no_qa,
        research_runner=perform_research,
    )


def cleanup():
    gc.collect()


atexit.register(cleanup)


def run_doctor():
    """Run system diagnostics.

    Delegates to the maintained implementation in ``cli_doctor`` - the legacy
    inline body this module carried (plus its private helpers
    ``_list_recent_outputs`` / ``_get_qa_grade_for_report`` /
    ``_check_api_quota`` / ``_list_strategies`` / ``_clean_temp_files`` /
    ``_open_file``) was an unmaintained duplicate with zero callers, superseded
    by the v1.25.x ``cli_doctor`` extraction. Kept as a public name for
    backward compatibility (exported in ``__all__``).
    """
    from primr.core.cli_doctor import run_doctor as _cli_run_doctor

    return _cli_run_doctor()


if __name__ == "__main__":
    main()
