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

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from primr.config.config import PROJECT_ROOT
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.user_cache import get_user_cache_subdir, migrate_legacy_file

logger = get_logger("vendor_research")

# Default weekly TTL: vendor news (model releases, cloud feature announcements)
# shifts often enough that one week balances freshness against regeneration
# cost. Override per machine with PRIMR_VENDOR_NEWS_TTL_DAYS (e.g. dial down
# during Ignite/re:Invent week, up for slow vendors).
DEFAULT_VENDOR_NEWS_TTL_DAYS = 7


def get_vendor_news_ttl_days() -> int:
    """Resolve the vendor-news freshness TTL (days), env-overridable."""
    raw = os.environ.get("PRIMR_VENDOR_NEWS_TTL_DAYS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
            logger.warning(
                "PRIMR_VENDOR_NEWS_TTL_DAYS must be positive, got %r — using default %d",
                raw,
                DEFAULT_VENDOR_NEWS_TTL_DAYS,
            )
        except ValueError:
            logger.warning(
                "PRIMR_VENDOR_NEWS_TTL_DAYS is not an integer: %r — using default %d",
                raw,
                DEFAULT_VENDOR_NEWS_TTL_DAYS,
            )
    return DEFAULT_VENDOR_NEWS_TTL_DAYS


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


def get_vendor_research_dir() -> Path:
    """Directory holding generated vendor research (per-user cache)."""
    return get_user_cache_subdir("vendor-research")


def get_vendor_research_path(vendor: str, month: str | None = None) -> Path:
    """
    Get path for vendor research file.

    Uses current month if month not specified. Files live in the per-user
    cache (``primr.utils.user_cache``) so vendor research is shared across
    invocation directories — back-to-back runs in different company folders
    reuse one file per vendor instead of regenerating (~$0.50 Deep Research
    each). A file at the legacy ``PROJECT_ROOT/vendor-research/`` location is
    migrated to the cache on first access.

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        month: Month string (YYYY-MM format), defaults to current

    Returns:
        Path to vendor research file
    """
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    filename = f"vendor-research-{vendor.lower()}-{month}.txt"
    new_path = get_vendor_research_dir() / filename

    legacy_path = Path(PROJECT_ROOT) / "vendor-research" / filename
    migrate_legacy_file(legacy_path, new_path)

    return new_path


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


def is_vendor_research_current(vendor: str, max_age_days: int | None = None) -> bool:
    """
    Check if we have fresh vendor research (within max_age_days).

    AI moves fast — monthly is too stale, biweekly is borderline. The
    default TTL is weekly, overridable via ``PRIMR_VENDOR_NEWS_TTL_DAYS``
    (see :func:`get_vendor_news_ttl_days`).

    Args:
        vendor: Cloud vendor
        max_age_days: Maximum age in days before research is considered
            stale. ``None`` (default) resolves the configured TTL.

    Returns:
        True if current research exists and is fresh enough
    """
    if max_age_days is None:
        max_age_days = get_vendor_news_ttl_days()
    # Check manually curated files — these are always preferred but still age-checked
    manual_path = get_manual_research_path(vendor)
    if manual_path and manual_path.exists():
        mtime = datetime.fromtimestamp(manual_path.stat().st_mtime)
        age_days = (datetime.now() - mtime).days
        if age_days <= max_age_days:
            return True

    research_path = get_vendor_research_path(vendor)
    if not research_path.exists():
        return False
    mtime = datetime.fromtimestamp(research_path.stat().st_mtime)
    age_days = (datetime.now() - mtime).days
    return age_days <= max_age_days


def get_or_generate_vendor_research_sync(
    vendor: str, force_refresh: bool = False, on_progress: Callable[[str], None] | None = None
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

    # See get_or_generate_vendor_research (async) for the cost-cap-driven
    # reason this defaults to reusing stale rather than auto-refreshing.
    research_path = get_vendor_research_path(vendor)
    research_exists, age_days = _vendor_research_age(research_path)
    is_fresh = research_exists and age_days is not None and age_days <= get_vendor_news_ttl_days()
    is_stale = research_exists and not is_fresh
    refresh_now = force_refresh or (is_stale and _allow_vendor_auto_refresh())

    if is_fresh and not force_refresh:
        result_paths.append(str(research_path))
        console.info(f"Using vendor research: {research_path.name} ({age_days}d old)")
        logger.info("Reusing vendor research file: %s (age: %dd)", research_path, age_days)
    elif is_stale and not refresh_now:
        result_paths.append(str(research_path))
        console.warn(
            f"Vendor research is {age_days}d old (>{get_vendor_news_ttl_days()}d TTL) — reusing without refresh "
            "(set PRIMR_ALLOW_VENDOR_REFRESH=1 or pass force_refresh=True to regenerate)"
        )
    elif refresh_now or not result_paths:
        generated = generate_vendor_research_sync(vendor, on_progress)
        if generated:
            result_paths.append(generated)

    return result_paths


def _vendor_research_age(research_path: Path) -> tuple[bool, int | None]:
    """Return (exists, age_in_days) for a vendor research cache file."""
    if not research_path.exists():
        return False, None
    mtime = datetime.fromtimestamp(research_path.stat().st_mtime)
    return True, (datetime.now() - mtime).days


def _allow_vendor_auto_refresh() -> bool:
    """Gate auto-refresh of stale vendor research on an explicit env opt-in.

    See ``get_or_generate_vendor_research`` for the cost-cap rationale.
    """
    import os as _os

    return _os.environ.get("PRIMR_ALLOW_VENDOR_REFRESH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


async def get_or_generate_vendor_research(
    vendor: str, force_refresh: bool = False, on_progress: Callable[[str], None] | None = None
) -> VendorResearchResult:
    """Get vendor research files, generating only when explicitly approved.

    Priority order:
    1. Manually curated files (e.g., Ignite analysis for Azure)
    2. Fresh (≤14d) auto-generated research
    3. Stale auto-generated research is REUSED, not refreshed, unless
       ``force_refresh=True`` or ``PRIMR_ALLOW_VENDOR_REFRESH=1``. The
       MCP/static cost-cap estimate does not include a ~$0.50 Deep
       Research refresh, so silently triggering one would bypass the
       approved spend ceiling.
    4. Generate fresh research when nothing exists at all.
    """
    import time

    start_time = time.time()
    files: list[VendorResearchFile] = []
    generated = False
    current_month = datetime.now().strftime("%Y-%m")

    if vendor.lower() == "azure":
        manual_path = get_manual_research_path(vendor)
        if manual_path:
            files.append(
                VendorResearchFile(path=manual_path, vendor=vendor, month="manual", is_manual=True)
            )

    research_path = get_vendor_research_path(vendor)
    research_exists, age_days = _vendor_research_age(research_path)
    is_fresh = research_exists and age_days is not None and age_days <= get_vendor_news_ttl_days()
    is_stale = research_exists and not is_fresh
    refresh_now = force_refresh or (is_stale and _allow_vendor_auto_refresh())

    if is_fresh and not force_refresh:
        files.append(
            VendorResearchFile(
                path=research_path, vendor=vendor, month=current_month, is_manual=False
            )
        )
        console.info(f"Using vendor research: {research_path.name} ({age_days}d old)")
        logger.info("Reusing vendor research file: %s (age: %dd)", research_path, age_days)
    elif is_stale and not refresh_now:
        files.append(
            VendorResearchFile(
                path=research_path, vendor=vendor, month=current_month, is_manual=False
            )
        )
        console.warn(
            f"Vendor research is {age_days}d old (>{get_vendor_news_ttl_days()}d TTL) — reusing without refresh "
            "(set PRIMR_ALLOW_VENDOR_REFRESH=1 or pass force_refresh=True to regenerate)"
        )
        logger.info(
            "Stale vendor research kept: %s (age=%dd, allow_auto_refresh=False)",
            research_path,
            age_days,
        )
    elif refresh_now or not files:
        if research_exists and not force_refresh:
            console.info(
                f"Vendor research is {age_days}d old (>{get_vendor_news_ttl_days()}d TTL) — refreshing..."
            )
        result = await generate_vendor_research(vendor, on_progress)
        if result:
            files.append(
                VendorResearchFile(
                    path=Path(result), vendor=vendor, month=current_month, is_manual=False
                )
            )
            generated = True

    return VendorResearchResult(
        files=tuple(files), generated=generated, duration_seconds=time.time() - start_time
    )


def generate_vendor_research_sync(
    vendor: str, on_progress: Callable[[str], None] | None = None
) -> str | None:
    """
    Generate fresh vendor AI research using Deep Research (synchronous).

    Args:
        vendor: Cloud vendor (azure, aws, gcp, agnostic)
        on_progress: Optional progress callback

    Returns:
        Path to generated research file, or None if failed
    """
    from primr.utils.async_utils import run_sync

    return run_sync(generate_vendor_research(vendor, on_progress))


async def generate_vendor_research(
    vendor: str, on_progress: Callable[[str], None] | None = None
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
            timeout=1800,  # 30 min timeout
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error("Vendor research generation failed")
            return None

        # Save to docs folder
        research_path = get_vendor_research_path(vendor)
        research_path.parent.mkdir(parents=True, exist_ok=True)

        research_path.write_text(result.content, encoding="utf-8")

        # Deep Research is a flat per-task cost (API doesn't expose tokens)
        from primr.config.models import DEEP_RESEARCH_COST

        actual_cost = DEEP_RESEARCH_COST.standard_task_cost
        duration_str = f"{result.duration_seconds / 60:.1f}m"

        console.ok(
            f"Vendor research saved: {research_path.name} ({duration_str}, ~${actual_cost:.2f})"
        )
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
    valid_vendors = ["azure", "aws", "gcp", "agnostic", "private"]
    if vendor.lower() not in valid_vendors:
        errors.append(f"Invalid vendor: {vendor}. Must be one of: {', '.join(valid_vendors)}")

    # Validate API key
    settings = get_settings()
    if not settings.api.gemini_key:
        errors.append("GEMINI_API_KEY not configured")

    # Check the actual output directory is writable. Generated vendor research
    # is saved in the per-user cache (see get_vendor_research_path), so
    # validate that directory — or an unwritable output dir is only discovered
    # after the expensive Deep Research call has completed.
    vendor_dir = get_vendor_research_dir()
    try:
        vendor_dir.mkdir(parents=True, exist_ok=True)
        test_file = vendor_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        errors.append(f"Vendor research directory not writable: {vendor_dir} ({e})")

    return errors


def _get_vendor_metadata(vendor: str) -> dict[str, str]:
    """Get vendor-specific metadata."""
    metadata = {
        "azure": {
            "name": "Microsoft Azure",
            "conference": "Microsoft Ignite, Microsoft Build",
            "platform": "Azure OpenAI Service and Azure AI Foundry",
        },
        "aws": {
            "name": "Amazon Web Services (AWS)",
            "conference": "AWS re:Invent, AWS Summit",
            "platform": "Amazon Bedrock",
        },
        "gcp": {
            "name": "Google Cloud Platform (GCP)",
            "conference": "Google Cloud Next, Google I/O",
            "platform": "Vertex AI",
        },
        "agnostic": {
            "name": "the AI Industry (cross-vendor)",
            "conference": "NeurIPS, major vendor conferences",
            "platform": "major model providers and cloud platforms",
        },
        "private": {
            "name": "Private Cloud / NVIDIA",
            "conference": "NVIDIA GTC, VMware Explore, Red Hat Summit, Dell Tech World, HPE Discover",
            "platform": "NVIDIA AI Enterprise, NIM, NeMo, DGX, and private cloud AI infrastructure",
        },
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

# {meta["name"]} AI Services and Capabilities

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
Many companies are interested in adopting AI in {current_date}. For {meta["name"]},
I need a comprehensive overview of the latest AI services, capabilities, and best
practices that we should keep in mind when advising enterprise customers on AI strategy.

Search for the latest updates from {meta["conference"]} and recent announcements.

SECTION STRUCTURE:

## Executive Summary
Key themes and strategic direction for {meta["name"]} AI in {current_date}.

## Foundation Models and AI Services
For {meta["platform"]}, provide:
- Which models are available (provider, model family, version)
- What has changed or been announced in the past 2 weeks
- What is new in the past 3 months
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

## What's New and Changed
Bulleted list with dates and sources. Split into: last 2 weeks (top priority) and last 3 months.
Prioritize: model releases, GA announcements, pricing changes, capability updates.

## Sources
List all sources with URLs and dates.
"""
