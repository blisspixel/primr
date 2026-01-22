"""
Vendor-specific AI research generation and caching.

This module manages cloud vendor AI capabilities research:
- Generates fresh research using Deep Research
- Caches research with monthly expiration
- Prefers manually curated files when available

Usage:
    from primr.core.vendor_research import (
        get_or_generate_vendor_research,
        is_vendor_research_current,
    )

    # Get vendor research (generates if needed)
    paths = get_or_generate_vendor_research("azure")

    # Check if current month's research exists
    is_current = is_vendor_research_current("azure")
"""
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from typing import Callable

from primr.config.config import PROJECT_ROOT
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("vendor_research")


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class VendorResearchFile:
    """Metadata about a vendor research file."""
    path: Path
    vendor: str
    month: str
    is_manual: bool

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def age_days(self) -> int:
        if not self.exists:
            return -1
        mtime = datetime.fromtimestamp(self.path.stat().st_mtime)
        return (datetime.now() - mtime).days


@dataclass
class VendorResearchResult:
    """Result of vendor research retrieval/generation."""
    files: tuple[VendorResearchFile, ...]
    generated: bool
    duration_seconds: float
    error: str | None = None

    @property
    def paths(self) -> list[Path]:
        return [f.path for f in self.files if f.exists]


# =============================================================================
# PROTOCOLS
# =============================================================================

class VendorPromptBuilder(Protocol):
    """Protocol for vendor-specific prompt construction."""

    def build(self, vendor: str, current_date: str) -> str:
        """Build the research prompt for a vendor."""
        ...


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================

def get_vendor_research_path(vendor: str, month: str | None = None) -> Path:
    """
    Get path for vendor research file.

    Uses current month if month not specified.

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        month: Month string (YYYY-MM format), defaults to current

    Returns:
        Path to vendor research file
    """
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    filename = f"vendor-research-{vendor.lower()}-{month}.txt"
    return Path(PROJECT_ROOT) / "docs" / filename


def get_manual_research_path(vendor: str) -> Path | None:
    """
    Get path to manually curated research file if it exists.

    Args:
        vendor: Cloud vendor

    Returns:
        Path to manual research file, or None if not found
    """
    # Azure has a manually curated Ignite analysis
    if vendor.lower() == "azure":
        manual_path = Path(PROJECT_ROOT) / "docs" / "research latest microsoft ignite analysis.txt"
        if manual_path.exists():
            return manual_path
    return None


def is_vendor_research_current(vendor: str) -> bool:
    """
    Check if we have current month's vendor research.

    Args:
        vendor: Cloud vendor

    Returns:
        True if current research exists
    """
    # Azure has a manually curated file that's always preferred
    if vendor.lower() == "azure":
        manual_path = get_manual_research_path(vendor)
        if manual_path:
            return True

    research_path = get_vendor_research_path(vendor)
    return research_path.exists()


def get_or_generate_vendor_research_sync(
    vendor: str,
    force_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None
) -> list[str]:
    """
    Get vendor research files, generating if needed (synchronous).

    Priority order:
    1. Manually curated files (e.g., Ignite analysis for Azure)
    2. Current month's auto-generated research
    3. Generate fresh research if nothing available

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        force_refresh: If True, regenerate even if current exists
        on_progress: Optional progress callback

    Returns:
        List of paths to vendor research files
    """
    result_paths = []

    # Azure: always include manually curated Ignite analysis
    if vendor.lower() == "azure":
        manual_path = get_manual_research_path(vendor)
        if manual_path:
            result_paths.append(str(manual_path))

    # Check for current month's auto-generated research
    research_path = get_vendor_research_path(vendor)
    if research_path.exists() and not force_refresh:
        result_paths.append(str(research_path))
        console.info(f"Using existing vendor research: {research_path.name}")
        logger.info(f"Reusing vendor research file: {research_path}")
    elif not result_paths or force_refresh:
        # Only auto-generate if we have nothing or force refresh
        generated = generate_vendor_research_sync(vendor, on_progress)
        if generated:
            result_paths.append(generated)

    return result_paths


async def get_or_generate_vendor_research(
    vendor: str,
    force_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None
) -> VendorResearchResult:
    """
    Get vendor research files, generating if needed (async).

    Priority order:
    1. Manually curated files (e.g., Ignite analysis for Azure)
    2. Current month's auto-generated research
    3. Generate fresh research if nothing available

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        force_refresh: If True, regenerate even if current exists
        on_progress: Optional progress callback

    Returns:
        VendorResearchResult with file paths
    """
    import time
    start_time = time.time()
    files = []
    generated = False

    # Azure: always include manually curated Ignite analysis
    if vendor.lower() == "azure":
        manual_path = get_manual_research_path(vendor)
        if manual_path:
            files.append(VendorResearchFile(
                path=manual_path,
                vendor=vendor,
                month="manual",
                is_manual=True
            ))

    # Check for current month's auto-generated research
    current_month = datetime.now().strftime("%Y-%m")
    research_path = get_vendor_research_path(vendor)

    if research_path.exists() and not force_refresh:
        # Reuse existing research from this month
        files.append(VendorResearchFile(
            path=research_path,
            vendor=vendor,
            month=current_month,
            is_manual=False
        ))
        console.info(f"Using existing vendor research: {research_path.name}")
        logger.info(f"Reusing vendor research file: {research_path}")
    elif not files or force_refresh:
        # Generate fresh research only if:
        # 1. No files at all (not even manual), OR
        # 2. Force refresh requested
        result = await generate_vendor_research(vendor, on_progress)
        if result:
            files.append(VendorResearchFile(
                path=Path(result),
                vendor=vendor,
                month=current_month,
                is_manual=False
            ))
            generated = True

    return VendorResearchResult(
        files=tuple(files),
        generated=generated,
        duration_seconds=time.time() - start_time
    )


def generate_vendor_research_sync(
    vendor: str,
    on_progress: Callable[[str], None] | None = None
) -> str | None:
    """
    Generate fresh vendor AI research using Deep Research (synchronous).

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        on_progress: Optional progress callback

    Returns:
        Path to generated research file, or None if failed
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(generate_vendor_research(vendor, on_progress))


async def generate_vendor_research(
    vendor: str,
    on_progress: Callable[[str], None] | None = None
) -> str | None:
    """
    Generate fresh vendor AI research using Deep Research (async).

    Creates comprehensive overview of latest AI services and capabilities
    for the specified cloud vendor.

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        on_progress: Optional progress callback

    Returns:
        Path to generated research file, or None if failed
    """
    from primr.ai.deep_research import ResearchStatus, get_deep_research_client
    from primr.config.settings import get_settings

    # Pre-flight validation
    preflight_errors = _validate_vendor_research_preflight(vendor)
    if preflight_errors:
        for err in preflight_errors:
            console.error(f"  - {err}")
        return None

    # Build prompt
    prompt = _build_vendor_prompt(vendor)

    console.info(f"Generating fresh {vendor.upper()} AI research...")
    console.info("Estimated: 5-10 min, ~$0.50")

    client = get_deep_research_client()

    def progress_callback(progress):
        if progress.message:
            if on_progress:
                on_progress(progress.message)
            console.info(f"Vendor Research: {progress.message}")

    try:
        result = await client.research(
            query=prompt,
            output_format=None,
            on_progress=progress_callback,
            timeout=1800  # 30 min timeout
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error("Vendor research generation failed")
            return None

        # Save to docs folder
        research_path = get_vendor_research_path(vendor)
        research_path.parent.mkdir(parents=True, exist_ok=True)

        research_path.write_text(result.content, encoding="utf-8")

        # Calculate actual cost
        output_tokens = len(result.content) // 4
        input_tokens = 5000
        actual_cost = (input_tokens / 1_000_000) * 2.0 + (output_tokens / 1_000_000) * 12.0
        duration_str = f"{result.duration_seconds / 60:.1f}m"

        console.ok(f"Vendor research saved: {research_path.name} ({duration_str}, ~${actual_cost:.2f})")
        return str(research_path)

    except Exception as e:
        console.error(f"Vendor research failed: {e}")
        logger.exception("Vendor research error")
        return None


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================

def _validate_vendor_research_preflight(vendor: str) -> list[str]:
    """Validate prerequisites for vendor research generation."""
    from primr.config.settings import get_settings

    errors = []

    # Validate vendor
    valid_vendors = ["azure", "aws", "gcp", "agnostic"]
    if vendor.lower() not in valid_vendors:
        errors.append(f"Invalid vendor: {vendor}. Must be one of: {', '.join(valid_vendors)}")

    # Validate API key
    settings = get_settings()
    if not settings.api.gemini_key:
        errors.append("GEMINI_API_KEY not configured")

    # Check docs directory is writable
    docs_dir = Path(PROJECT_ROOT) / "docs"
    try:
        docs_dir.mkdir(parents=True, exist_ok=True)
        test_file = docs_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        errors.append(f"Docs directory not writable: {docs_dir} ({e})")

    return errors


def _get_vendor_metadata(vendor: str) -> dict[str, str]:
    """Get vendor-specific metadata."""
    metadata = {
        "azure": {
            "name": "Microsoft Azure",
            "conference": "Microsoft Ignite, Microsoft Build",
            "platform": "Azure OpenAI Service and Azure AI Foundry"
        },
        "aws": {
            "name": "Amazon Web Services (AWS)",
            "conference": "AWS re:Invent, AWS Summit",
            "platform": "Amazon Bedrock"
        },
        "gcp": {
            "name": "Google Cloud Platform (GCP)",
            "conference": "Google Cloud Next, Google I/O",
            "platform": "Vertex AI"
        },
        "agnostic": {
            "name": "the AI Industry (cross-vendor)",
            "conference": "NeurIPS, major vendor conferences",
            "platform": "major model providers and cloud platforms"
        }
    }
    return metadata.get(vendor.lower(), metadata["agnostic"])


def _build_vendor_prompt(vendor: str) -> str:
    """Build Deep Research prompt for vendor research."""
    current_date = datetime.now().strftime("%B %Y")
    meta = _get_vendor_metadata(vendor)

    return f"""You are an AI technology analyst. Research the latest AI services and capabilities.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# {meta['name']} AI Services and Capabilities

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

RESEARCH GOAL:
Many companies are interested in adopting AI in {current_date}. For {meta['name']}, 
I need a comprehensive overview of the latest AI services, capabilities, and best 
practices that we should keep in mind when advising enterprise customers on AI strategy.

Search for the latest updates from {meta['conference']} and recent announcements.

SECTION STRUCTURE:

## Executive Summary
Key themes and strategic direction for {meta['name']} AI in {current_date}.

## Foundation Models and AI Services
For {meta['platform']}, provide:
- Which models are available (provider, model family, version)
- What is new in the past 6 months
- GA vs Preview status for each model
- Customization options

## Productivity AI and Copilots
- Enterprise productivity tools with AI
- Integration with existing workflows
- Licensing and deployment models

## Agentic AI and Automation
- Agent building platforms and tools
- Orchestration capabilities
- Multi-agent scenarios

## Data and Analytics AI
- AI-powered analytics and BI
- Data platform integration
- Vector search and RAG capabilities

## AI Development Platform
- Model hosting options
- Developer tools and SDKs
- MLOps and deployment

## Security and Governance
- AI governance tools
- Data protection and compliance
- Identity and access for AI

## New in the Past 6 Months
Bulleted list of recent changes with dates and sources.

## Sources
List all sources with URLs and dates.
"""
