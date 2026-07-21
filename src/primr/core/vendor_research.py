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

    # Get cached vendor research. Generation requires explicit opt-in.
    paths = get_or_generate_vendor_research("azure")

    # Check if current month's research exists
    is_current = is_vendor_research_current("azure")
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from primr.ai.deep_research import ResearchProgress, ResearchResult

from primr.config.config import PROJECT_ROOT
from primr.utils.atomic_io import atomic_write_text
from primr.utils.console import get_console
from primr.utils.fs_safety import check_dir_atomic_writable
from primr.utils.logging_config import get_logger
from primr.utils.user_cache import get_user_cache_subdir, migrate_legacy_file

logger = get_logger("vendor_research")

# Default weekly TTL: vendor news (model releases, cloud feature announcements)
# shifts often enough that one week balances freshness against regeneration
# cost. Override per machine with PRIMR_VENDOR_NEWS_TTL_DAYS (e.g. dial down
# during Ignite/re:Invent week, up for slow vendors).
DEFAULT_VENDOR_NEWS_TTL_DAYS = 7
_vendor_task_counter_lock = threading.Lock()
_vendor_tasks_started = 0


def get_vendor_research_tasks_started() -> int:
    """Return the process-lifetime count of vendor provider tasks started."""

    with _vendor_task_counter_lock:
        return _vendor_tasks_started


def _record_vendor_research_task_started() -> None:
    """Increment the task counter immediately before provider submission."""

    global _vendor_tasks_started
    with _vendor_task_counter_lock:
        _vendor_tasks_started += 1


def _notify_task_observer(
    observer: Callable[[str], None] | None,
    event: str,
) -> None:
    """Notify run-local accounting without letting telemetry break delivery."""

    if observer is None:
        return
    try:
        observer(event)
    except Exception as exc:
        logger.debug(
            "Vendor research task observer failed: failure_type=%s",
            type(exc).__name__,
        )


def get_vendor_news_ttl_days() -> int:
    """Resolve the vendor-news freshness TTL (days), env-overridable."""
    raw = os.environ.get("PRIMR_VENDOR_NEWS_TTL_DAYS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
            logger.warning(
                "PRIMR_VENDOR_NEWS_TTL_DAYS must be positive, got %r; using default %d",
                raw,
                DEFAULT_VENDOR_NEWS_TTL_DAYS,
            )
        except ValueError:
            logger.warning(
                "PRIMR_VENDOR_NEWS_TTL_DAYS is not an integer: %r; using default %d",
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
    invocation directories. Back-to-back runs in different company folders
    reuse one file per vendor instead of starting another paid Deep Research
    task. A file at the legacy ``PROJECT_ROOT/vendor-research/`` location is
    migrated to the cache on first access.

    Args:
        vendor: Cloud vendor (azure, aws, gcp, private, agnostic)
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

    AI moves fast. Monthly is too stale and biweekly is borderline. The
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
    # Check manually curated files. They are preferred but still age-checked.
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
    vendor: str,
    force_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
    *,
    allow_auto_refresh: bool | None = None,
    task_observer: Callable[[str], None] | None = None,
    lite: bool = True,
) -> list[str]:
    """
    Get vendor research files, generating only after explicit opt-in (synchronous).

    Priority order:
    1. Manually curated files (e.g., Ignite analysis for Azure)
    2. Current month's auto-generated research
    3. Stale auto-generated research is reused unless explicit refresh is enabled
    4. Missing auto-generated research is skipped unless explicit refresh is enabled

    Args:
        vendor: Cloud vendor (azure, aws, gcp, private, agnostic)
        force_refresh: If True, regenerate even if current exists
        on_progress: Optional progress callback
        allow_auto_refresh: Override environment-driven refresh behavior. Pass
            False from estimate-bound integrated runs so only explicit
            ``force_refresh`` can start a paid refresh task.

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
    auto_refresh_enabled, refresh_hint = _resolve_vendor_refresh_policy(allow_auto_refresh)
    refresh_now = force_refresh or (is_stale and auto_refresh_enabled)
    generate_missing_now = not research_exists and auto_refresh_enabled

    if is_fresh and not force_refresh:
        result_paths.append(str(research_path))
        get_console().info(f"Using vendor research: {research_path.name} ({age_days}d old)")
        logger.info("Reusing vendor research file: %s (age: %dd)", research_path, age_days)
    elif is_stale and not refresh_now:
        result_paths.append(str(research_path))
        get_console().warn(
            f"Vendor research is {age_days}d old (>{get_vendor_news_ttl_days()}d TTL) - reusing without refresh "
            f"({refresh_hint})"
        )
    elif refresh_now or generate_missing_now:
        generated = _generate_vendor_research_sync(vendor, on_progress, task_observer, lite)
        if generated:
            result_paths.append(generated)
        elif research_exists:
            result_paths.append(str(research_path))
            get_console().warn("Vendor research refresh failed; reusing the existing cached file")
            logger.warning(
                "Vendor research refresh failed; cached fallback retained: vendor=%s age_days=%s",
                vendor,
                age_days,
            )
    elif not research_exists and not result_paths:
        get_console().warn(
            "No cached vendor research found; skipping automatic Deep Research generation "
            f"({refresh_hint})"
        )
        logger.info("Vendor research missing and auto-generation disabled: %s", research_path)

    return result_paths


def _generate_vendor_research_sync(
    vendor: str,
    on_progress: Callable[[str], None] | None,
    task_observer: Callable[[str], None] | None,
    lite: bool = True,
) -> str | None:
    """Generate vendor research while preserving legacy mock call shapes."""
    if task_observer is None:
        return generate_vendor_research_sync(vendor, on_progress, lite=lite)
    return generate_vendor_research_sync(
        vendor, on_progress, task_observer=task_observer, lite=lite
    )


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


def vendor_auto_refresh_enabled() -> bool:
    """Return whether the explicit environment refresh opt-in is active."""
    return _allow_vendor_auto_refresh()


def _resolve_vendor_refresh_policy(allow_auto_refresh: bool | None) -> tuple[bool, str]:
    """Resolve the effective refresh gate and the user-facing opt-in hint."""
    enabled = _allow_vendor_auto_refresh() if allow_auto_refresh is None else allow_auto_refresh
    hint = (
        "automatic refresh is disabled for this call"
        if allow_auto_refresh is False
        else "set PRIMR_ALLOW_VENDOR_REFRESH=1 or pass force_refresh=True"
    )
    return enabled, hint


def _acknowledge_vendor_research_output(interaction_id: object, research_path: Path) -> bool:
    """Clear the pending job after its durable output has been written."""
    from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

    return not (
        isinstance(interaction_id, str)
        and interaction_id
        and not acknowledge_pending_job_after_outputs(interaction_id, [research_path])
    )


def _record_vendor_research_usage(vendor: str, duration_seconds: float, cost: float) -> None:
    """Persist standalone vendor-research usage without failing the deliverable."""
    try:
        from primr.utils.usage_tracker import get_usage_tracker

        tracker = get_usage_tracker()
        tracker.record_usage(
            mode=f"vendor_research_{vendor.lower()}",
            company=vendor.upper(),
            input_tokens=0,
            output_tokens=0,
            duration_seconds=max(0.0, duration_seconds),
            deep_research_cost=cost,
        )
        tracker.save()
    except Exception as exc:
        logger.debug(
            "Vendor research usage tracking skipped: failure_type=%s",
            type(exc).__name__,
        )


async def get_or_generate_vendor_research(
    vendor: str,
    force_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
    *,
    allow_auto_refresh: bool | None = None,
    lite: bool = True,
) -> VendorResearchResult:
    """Get cached vendor research, generating only after explicit refresh approval."""
    import time

    start_time = time.time()
    files: list[VendorResearchFile] = []
    generated = False
    current_month = datetime.now().strftime("%Y-%m")

    if vendor.lower() == "azure":
        manual_path = get_manual_research_path(vendor)
        if manual_path:
            files.append(_vendor_research_file(manual_path, vendor, "manual", is_manual=True))

    research_path = get_vendor_research_path(vendor)
    research_exists, age_days = _vendor_research_age(research_path)
    is_fresh = research_exists and age_days is not None and age_days <= get_vendor_news_ttl_days()
    is_stale = research_exists and not is_fresh
    auto_refresh_enabled, refresh_hint = _resolve_vendor_refresh_policy(allow_auto_refresh)
    refresh_now = force_refresh or (is_stale and auto_refresh_enabled)
    generate_missing_now = not research_exists and auto_refresh_enabled

    if is_fresh and not force_refresh:
        files.append(_vendor_research_file(research_path, vendor, current_month))
        get_console().info(f"Using vendor research: {research_path.name} ({age_days}d old)")
        logger.info("Reusing vendor research file: %s (age: %dd)", research_path, age_days)
    elif is_stale and not refresh_now:
        files.append(_vendor_research_file(research_path, vendor, current_month))
        get_console().warn(
            f"Vendor research is {age_days}d old (>{get_vendor_news_ttl_days()}d TTL) - reusing without refresh "
            f"({refresh_hint})"
        )
        logger.info(
            "Stale vendor research kept: %s (age=%dd, allow_auto_refresh=False)",
            research_path,
            age_days,
        )
    elif refresh_now or generate_missing_now:
        if research_exists and not force_refresh:
            get_console().info(
                f"Vendor research is {age_days}d old (>{get_vendor_news_ttl_days()}d TTL) - refreshing..."
            )
        result = await generate_vendor_research(vendor, on_progress, lite=lite)
        if result:
            files.append(_vendor_research_file(Path(result), vendor, current_month))
            generated = True
        elif research_exists:
            files.append(_vendor_research_file(research_path, vendor, current_month))
            get_console().warn("Vendor research refresh failed; reusing the existing cached file")
            logger.warning(
                "Vendor research refresh failed; cached fallback retained: vendor=%s age_days=%s",
                vendor,
                age_days,
            )
    elif not research_exists and not files:
        get_console().warn(
            "No cached vendor research found; skipping automatic Deep Research generation "
            f"({refresh_hint})"
        )
        logger.info("Vendor research missing and auto-generation disabled: %s", research_path)

    return VendorResearchResult(
        files=tuple(files), generated=generated, duration_seconds=time.time() - start_time
    )


def _vendor_research_file(
    path: Path,
    vendor: str,
    month: str,
    *,
    is_manual: bool = False,
) -> VendorResearchFile:
    """Build consistent metadata for a cached or generated research file."""
    return VendorResearchFile(path=path, vendor=vendor, month=month, is_manual=is_manual)


def generate_vendor_research_sync(
    vendor: str,
    on_progress: Callable[[str], None] | None = None,
    *,
    emit_console: bool = True,
    task_observer: Callable[[str], None] | None = None,
    lite: bool = True,
) -> str | None:
    """
    Generate fresh vendor AI research (synchronous).

    Defaults to the grounded lite engine; pass ``lite=False`` for Deep Research.

    Args:
        vendor: Cloud vendor (azure, aws, gcp, private, agnostic)
        on_progress: Optional progress callback
        lite: Use the grounded lite engine (default) vs Deep Research.

    Returns:
        Path to generated research file, or None if failed
    """
    from primr.utils.async_utils import run_sync

    return run_sync(
        generate_vendor_research(
            vendor,
            on_progress,
            emit_console=emit_console,
            task_observer=task_observer,
            lite=lite,
        )
    )


async def generate_vendor_research(
    vendor: str,
    on_progress: Callable[[str], None] | None = None,
    *,
    emit_console: bool = True,
    task_observer: Callable[[str], None] | None = None,
    lite: bool = True,
) -> str | None:
    """
    Generate fresh vendor AI research (async).

    By default (``lite=True``) this uses one grounded Google Search call to
    produce a current, cited brief for a fraction of the Deep Research cost.
    Pass ``lite=False`` (the ``--deep-research`` opt-in) for the heavyweight
    Deep Research agent.

    Args:
        vendor: Cloud vendor (azure, aws, gcp, private, agnostic)
        on_progress: Optional progress callback
        lite: Use the grounded lite engine (default) vs Deep Research.

    Returns:
        Path to generated research file, or None if failed
    """
    from primr.ai.deep_research import get_deep_research_client

    emit_console = emit_console and not get_console().quiet

    if lite:
        return generate_vendor_news_lite(
            vendor,
            on_progress,
            emit_console=emit_console,
            task_observer=task_observer,
        )

    if not _vendor_generation_preflight_passed(vendor, emit_console, task_observer):
        return None

    # Build prompt
    prompt = _build_vendor_prompt(vendor)

    if emit_console:
        get_console().info(f"Generating fresh {vendor.upper()} AI research...")
    from primr.config.models import DEEP_RESEARCH_COST

    if emit_console:
        get_console().info(
            f"Estimated: 5-10 min, ~${DEEP_RESEARCH_COST.standard_task_cost:.2f} planning cost"
        )

    client = get_deep_research_client()
    progress_callback = _vendor_progress_callback(on_progress, emit_console)
    return await _submit_vendor_research(
        vendor,
        prompt,
        client,
        progress_callback,
        DEEP_RESEARCH_COST.standard_task_cost,
        emit_console=emit_console,
        task_observer=task_observer,
    )


async def _submit_vendor_research(
    vendor: str,
    prompt: str,
    client,
    progress_callback: Callable[[ResearchProgress], None],
    actual_cost: float,
    *,
    emit_console: bool,
    task_observer: Callable[[str], None] | None,
) -> str | None:
    """Submit one provider task and account for every submitted outcome."""
    import time

    _record_vendor_research_task_started()
    _notify_task_observer(task_observer, "started")
    submitted_at = time.monotonic()
    usage_recorded = False
    try:
        result = await client.research(
            query=prompt,
            output_format=None,
            on_progress=progress_callback,
            timeout=1800,  # 30 min timeout
        )

        # The provider task has completed and may be billed even when local
        # publication subsequently fails. Record it before touching the cache.
        _record_vendor_research_usage(
            vendor,
            float(result.duration_seconds),
            actual_cost,
        )
        usage_recorded = True

        return _publish_vendor_research(
            vendor,
            result,
            actual_cost,
            emit_console=emit_console,
            task_observer=task_observer,
        )

    except Exception as exc:
        if not usage_recorded:
            _record_vendor_research_usage(
                vendor,
                time.monotonic() - submitted_at,
                actual_cost,
            )
        _notify_task_observer(task_observer, "failed")
        failure_type = type(exc).__name__
        if emit_console:
            get_console().error(f"Vendor research failed ({failure_type})")
        logger.warning(
            "Vendor research failed: vendor=%s failure_type=%s",
            vendor,
            failure_type,
        )
        return None


def _vendor_generation_preflight_passed(
    vendor: str,
    emit_console: bool,
    task_observer: Callable[[str], None] | None,
) -> bool:
    """Report local generation prerequisites before provider submission."""
    errors = _validate_vendor_research_preflight(vendor)
    if not errors:
        return True
    _notify_task_observer(task_observer, "failed")
    if emit_console:
        for error in errors:
            get_console().error(f"  - {error}")
    return False


def _vendor_progress_callback(
    on_progress: Callable[[str], None] | None,
    emit_console: bool,
) -> Callable[[ResearchProgress], None]:
    """Build the progress adapter shared by provider and CLI callbacks."""

    def callback(progress: ResearchProgress) -> None:
        if not progress.message:
            return
        if on_progress:
            on_progress(progress.message)
        if emit_console:
            get_console().info(f"Vendor Research: {progress.message}")

    return callback


def _publish_vendor_research(
    vendor: str,
    result: ResearchResult,
    actual_cost: float,
    *,
    emit_console: bool,
    task_observer: Callable[[str], None] | None,
) -> str | None:
    """Publish a successful provider result and report its durable outcome."""
    from primr.ai.deep_research import ResearchStatus

    if result.status != ResearchStatus.COMPLETED or not result.content:
        _notify_task_observer(task_observer, "failed")
        if emit_console:
            get_console().error("Vendor research generation failed")
        return None

    research_path = get_vendor_research_path(vendor)
    research_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(research_path, result.content)
    _acknowledge_published_vendor_research(result, research_path, emit_console)

    duration_str = f"{result.duration_seconds / 60:.1f}m"
    if emit_console:
        get_console().ok(
            f"Vendor research saved: {research_path.name} ({duration_str}, ~${actual_cost:.2f})"
        )
    _notify_task_observer(task_observer, "completed")
    return str(research_path)


def _lite_vendor_news_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Metered cost of one grounded lite brief: tokens plus a grounding request."""
    from primr.config.models import PrimrModels

    # Google Search grounding is billed per grounded request (~$0.035 after the
    # free tier); token cost uses the conservative tier for the reasoning model.
    grounding = 0.035
    try:
        token_cost = PrimrModels.calculate_cost_conservative(model, input_tokens, output_tokens)
    except Exception:
        token_cost = 0.0
    return round(token_cost + grounding, 6)


def generate_vendor_news_lite(
    vendor: str,
    on_progress: Callable[[str], None] | None = None,
    *,
    emit_console: bool = True,
    task_observer: Callable[[str], None] | None = None,
) -> str | None:
    """Generate a current, cited vendor AI-news brief with one grounded call.

    Uses Gemini + the live Google Search grounding tool instead of the
    heavyweight Deep Research agent: current and sourced, but a metered model
    call (~$0.06-0.20) rather than a flat Deep Research task. Returns the cache
    path, or ``None`` when the engine is unavailable so the caller can fall back.
    """
    from primr.ai.providers.gemini import GeminiProvider
    from primr.config.models import PrimrModels

    if not _vendor_generation_preflight_passed(vendor, emit_console, task_observer):
        return None

    provider = GeminiProvider()
    if not provider.is_available():
        if emit_console:
            get_console().warn("Grounded AI-news engine unavailable (no Gemini key)")
        return None

    prompt = _build_vendor_prompt(vendor)
    model = PrimrModels.PRO_MODEL
    if emit_console:
        get_console().info(f"Gathering current {vendor.upper()} AI news (grounded web search)...")
    if on_progress:
        on_progress(f"Searching the live web for {vendor.upper()} AI updates")

    _notify_task_observer(task_observer, "started")
    try:
        result = provider.search_and_summarize(prompt, model=model, max_tokens=12_000)
    except Exception as exc:
        _notify_task_observer(task_observer, "failed")
        if emit_console:
            get_console().error(f"Grounded AI-news generation failed ({type(exc).__name__})")
        logger.warning(
            "Lite vendor news failed: vendor=%s failure_type=%s", vendor, type(exc).__name__
        )
        return None

    if result is None or not result.text.strip():
        _notify_task_observer(task_observer, "failed")
        if emit_console:
            get_console().error("Grounded AI-news generation returned an empty brief")
        return None

    cost = _lite_vendor_news_cost(model, result.input_tokens, result.output_tokens)
    research_path = get_vendor_research_path(vendor)
    research_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(research_path, result.text)
    _record_vendor_research_usage(vendor, 0.0, cost)
    if emit_console:
        get_console().ok(
            f"AI news saved: {research_path.name} "
            f"({len(result.search_queries)} live searches, "
            f"{len(result.citations)} sources, ~${cost:.2f})"
        )
    _notify_task_observer(task_observer, "completed")
    return str(research_path)


def _acknowledge_published_vendor_research(
    result: ResearchResult,
    research_path: Path,
    emit_console: bool,
) -> None:
    """Acknowledge a durable cache without turning bookkeeping into data loss."""
    try:
        acknowledged = _acknowledge_vendor_research_output(result.interaction_id, research_path)
        if not acknowledged and emit_console:
            get_console().warn("Vendor research was saved, but its pending job remains listed.")
    except Exception as exc:
        logger.warning(
            "Vendor research pending-job acknowledgement failed: failure_type=%s",
            type(exc).__name__,
        )
        if emit_console:
            get_console().warn("Vendor research was saved, but its pending job remains listed.")


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================


def _validate_vendor_research_preflight(vendor: str) -> list[str]:
    """Validate prerequisites for vendor research generation."""
    from primr.config.settings import get_settings
    from primr.utils.errors import ConfigurationError

    errors = []

    # Validate vendor
    valid_vendors = ["azure", "aws", "gcp", "agnostic", "private"]
    if vendor.lower() not in valid_vendors:
        errors.append(f"Invalid vendor: {vendor}. Must be one of: {', '.join(valid_vendors)}")

    # Validate API key
    settings = get_settings()
    try:
        gemini_key = settings.api.gemini_key
    except ConfigurationError:
        gemini_key = None
    if not gemini_key:
        errors.append("GEMINI_API_KEY not configured")
    elif len(gemini_key) < 10:
        errors.append("GEMINI_API_KEY appears invalid (too short)")

    # Check the actual output directory is writable. Generated vendor research
    # is saved in the per-user cache (see get_vendor_research_path), so
    # validate that directory, or an unwritable output dir is only discovered
    # after the expensive Deep Research call has completed.
    vendor_dir = get_vendor_research_dir()
    writable, error = check_dir_atomic_writable(vendor_dir)
    if not writable:
        errors.append(f"Vendor research directory not writable: {error}")

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
