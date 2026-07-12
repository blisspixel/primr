"""
AI strategy generation using Deep Research.

This module generates comprehensive AI strategy recommendations:
- Board-level AI roadmaps
- Vendor-specific technology recommendations
- ROI models and prioritization frameworks

Usage:
    from primr.core.ai_strategy import (
        generate_ai_strategy,
        Platform,
        AIStrategyConfig,
    )

    # Generate AI strategy
    result = await generate_ai_strategy(
        company_name="Acme Corp",
        platform=Platform.AZURE,
        company_research_path="path/to/research.md"
    )
"""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from primr.config.config import OUTPUT_DIR, PROJECT_ROOT
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("ai_strategy")


# =============================================================================
# ENUMS
# =============================================================================


class Platform(Enum):
    """Supported platforms for strategy generation."""

    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    AGNOSTIC = "agnostic"
    PRIVATE = "private"

    @property
    def display_name(self) -> str:
        """Human-readable platform name."""
        names = {
            "azure": "Microsoft Azure",
            "aws": "Amazon Web Services (AWS)",
            "gcp": "Google Cloud Platform (GCP)",
            "agnostic": "Cloud Agnostic (Multi-Cloud)",
            "private": "Private Cloud / NVIDIA",
        }
        return names.get(self.value, self.value.upper())

    @classmethod
    def from_string(cls, value: str) -> "Platform":
        """Create Platform from string, case-insensitive. Supports aliases."""
        _aliases = {
            "microsoft": "azure",
            "amazon": "aws",
            "google": "gcp",
            "nvidia": "private",
        }
        normalized = _aliases.get(value.lower(), value.lower())
        try:
            return cls(normalized)
        except ValueError:
            logger.warning("Unknown platform '%s', defaulting to agnostic", value)
            return cls.AGNOSTIC


# Deprecated alias for backward compatibility
CloudVendor = Platform


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass(frozen=True)
class AIStrategyConfig:
    """Configuration for AI strategy generation."""

    company_name: str
    platform: Platform
    company_research_path: str | None = None
    force_refresh_vendor: bool = False
    timeout_seconds: int = 1800  # 30 minutes
    allow_vendor_refresh: bool | None = None

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.company_name or not self.company_name.strip():
            errors.append("Company name is required")
        if self.company_research_path:
            if not os.path.exists(self.company_research_path):
                errors.append(f"Company research file not found: {self.company_research_path}")
            elif os.path.getsize(self.company_research_path) == 0:
                errors.append(f"Company research file is empty: {self.company_research_path}")
        return errors


@dataclass
class AIStrategyResult:
    """Result of AI strategy generation."""

    docx_path: str | None
    md_path: str | None
    txt_path: str | None
    content: str
    duration_seconds: float
    vendor_research_paths: list[str]
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.docx_path is not None and self.error is None

    @property
    def output_paths(self) -> list[str]:
        """All generated output paths."""
        paths = []
        if self.docx_path:
            paths.append(self.docx_path)
        if self.md_path:
            paths.append(self.md_path)
        if self.txt_path:
            paths.append(self.txt_path)
        return paths


@dataclass
class StrategyPromptContext:
    """Context for building AI strategy prompts."""

    company_name: str
    platform: Platform
    current_date: str
    vendor_guidance: str
    vendor_name: str


# =============================================================================
# PROTOCOLS
# =============================================================================


class StrategyPromptBuilder(Protocol):
    """Protocol for strategy prompt construction."""

    def build(self, context: StrategyPromptContext) -> str:
        """Build the strategy prompt."""
        ...


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================


def generate_ai_strategy_sync(
    company_name: str,
    platform: str | Platform,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    on_progress: Callable[[str], None] | None = None,
    *,
    allow_vendor_refresh: bool | None = None,
) -> str | None:
    """
    Generate AI strategy using Deep Research (synchronous).

    Args:
        company_name: Name of the company
        platform: Platform preference
        company_research_path: Path to company research markdown
        force_refresh_vendor: If True, regenerate vendor research
        on_progress: Optional progress callback
        allow_vendor_refresh: Override environment-driven vendor refresh behavior

    Returns:
        Path to generated DOCX file, or None if failed
    """
    from primr.utils.async_utils import run_sync

    result = run_sync(
        generate_ai_strategy(
            company_name=company_name,
            platform=platform,
            company_research_path=company_research_path,
            force_refresh_vendor=force_refresh_vendor,
            allow_vendor_refresh=allow_vendor_refresh,
            on_progress=on_progress,
        )
    )

    return result.docx_path if result.success else None


async def generate_ai_strategy(
    company_name: str,
    platform: str | Platform,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    on_progress: Callable[[str], None] | None = None,
    *,
    allow_vendor_refresh: bool | None = None,
) -> AIStrategyResult:
    """
    Generate AI strategy using Deep Research (async).

    Creates comprehensive AI roadmap covering:
    - Strategic thesis and prioritization
    - Quick wins and bigger bets
    - ROI models and governance framework

    Args:
        company_name: Name of the company
        platform: Platform preference (string or Platform enum)
        company_research_path: Path to company research markdown
        force_refresh_vendor: If True, regenerate vendor research
        on_progress: Optional progress callback
        allow_vendor_refresh: Override environment-driven vendor refresh behavior

    Returns:
        AIStrategyResult with output paths and metadata
    """
    import time

    start_time = time.time()

    # Normalize platform
    if isinstance(platform, str):
        vendor = Platform.from_string(platform)
    else:
        vendor = platform

    # Build config
    config = AIStrategyConfig(
        company_name=company_name,
        platform=vendor,
        company_research_path=company_research_path,
        force_refresh_vendor=force_refresh_vendor,
        allow_vendor_refresh=allow_vendor_refresh,
    )

    # Pre-flight validation
    preflight_errors = _validate_preflight(config)
    if preflight_errors:
        for err in preflight_errors:
            console.error(f"  - {err}")
        return AIStrategyResult(
            docx_path=None,
            md_path=None,
            txt_path=None,
            content="",
            duration_seconds=time.time() - start_time,
            vendor_research_paths=[],
            error="; ".join(preflight_errors),
        )

    console.info("Pre-flight checks passed")

    # Gather context files
    context_files, vendor_paths = await _gather_context(config, on_progress)

    # Build prompt
    prompt = build_ai_strategy_prompt(company_name, vendor)

    recovered_interaction_id: str | None = None

    def capture_recovered_interaction(interaction_id: str) -> None:
        nonlocal recovered_interaction_id
        recovered_interaction_id = interaction_id

    # Execute Deep Research
    content = await _execute_strategy_research(
        prompt=prompt,
        context_files=context_files,
        timeout=config.timeout_seconds,
        on_progress=on_progress,
        on_recovery_ready=capture_recovered_interaction,
    )

    if not content:
        return AIStrategyResult(
            docx_path=None,
            md_path=None,
            txt_path=None,
            content="",
            duration_seconds=time.time() - start_time,
            vendor_research_paths=vendor_paths,
            error="AI Strategy research failed",
        )

    # Save outputs
    output_paths = _save_strategy_outputs(
        content=content, company_name=company_name, platform=vendor
    )
    if recovered_interaction_id and all(output_paths.values()):
        from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

        if not acknowledge_pending_job_after_outputs(
            recovered_interaction_id,
            [path for path in output_paths.values() if path],
        ):
            console.warn(
                "AI Strategy outputs were saved, but the pending job record could not be updated."
            )

    # Record usage for standalone invocations (MCP generate_strategy and
    # CLI --ai-strategy-only do not flow through the main research
    # pipeline's tracking seam). Without this, paid Deep Research runs
    # for strategy generation were invisible to primr show-usage and
    # downstream budget alerts.
    try:
        from primr.config.models import DEEP_RESEARCH_COST
        from primr.utils.usage_tracker import get_usage_tracker

        tracker = get_usage_tracker()
        elapsed_s = max(0.0, time.time() - start_time)
        vendor_label = vendor.value if hasattr(vendor, "value") else str(vendor)
        tracker.record_usage(
            mode=f"standalone_ai_strategy_{vendor_label}",
            company=company_name,
            input_tokens=0,
            output_tokens=0,
            duration_seconds=elapsed_s,
            # Provider billing varies by token and tool use. Record the same
            # conservative planning estimate used by the approval gate.
            deep_research_cost=DEEP_RESEARCH_COST.standard_task_cost,
        )
        tracker.save()
    except Exception as exc:
        # Tracking failure must never fail the strategy run itself.
        logger.debug("Standalone AI strategy usage tracking skipped: %s", exc)

    return AIStrategyResult(
        docx_path=output_paths.get("docx"),
        md_path=output_paths.get("md"),
        txt_path=output_paths.get("txt"),
        content=content,
        duration_seconds=time.time() - start_time,
        vendor_research_paths=vendor_paths,
    )


def build_ai_strategy_prompt(company_name: str, platform: Platform) -> str:
    """
    Build Deep Research prompt for AI strategy.

    Uses externalized YAML configuration from src/primr/prompts/ai_strategy.yaml

    Args:
        company_name: Name of the company
        platform: Platform preference

    Returns:
        Complete prompt string for Deep Research
    """
    from primr.prompts import build_ai_strategy_prompt as build_from_yaml

    return build_from_yaml(
        company_name=company_name,
        platform=platform.value,
    )


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================


def _validate_preflight(config: AIStrategyConfig) -> list[str]:
    """Validate prerequisites for AI strategy generation."""
    from primr.config.settings import get_settings

    errors = config.validate()

    # Validate API key
    settings = get_settings()
    if not settings.api.gemini_key:
        errors.append("GEMINI_API_KEY not configured")

    # Check output directory is writable
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_file = os.path.join(OUTPUT_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        errors.append(f"Output directory not writable: {OUTPUT_DIR} ({e})")

    return errors


async def _gather_context(
    config: AIStrategyConfig, on_progress: Callable[[str], None] | None = None
) -> tuple[list[str], list[str]]:
    """
    Gather context files for AI strategy generation.

    Uses data sources defined in the strategy YAML configuration,
    filtered by the specified cloud vendor.

    Returns:
        Tuple of (context_files, vendor_research_paths)
    """
    from primr.prompts.registry import get_registry

    context_files = []
    vendor_paths = []

    if config.company_research_path and os.path.exists(config.company_research_path):
        context_files.append(config.company_research_path)

    registry = get_registry()
    vendor_str = config.platform.value

    yaml_context_files = registry.get_context_files("ai", vendor=vendor_str)

    for path in yaml_context_files:
        if path.exists():
            path_str = str(path)
            if path_str not in context_files:
                context_files.append(path_str)
                vendor_paths.append(path_str)

    if yaml_context_files:
        console.info(
            f"Using {len(yaml_context_files)} vendor research file(s) from strategy config"
        )

    if not yaml_context_files:
        from primr.core.vendor_research import (
            generate_vendor_research,
            get_or_generate_vendor_research,
        )

        if config.platform != Platform.AGNOSTIC:
            if config.force_refresh_vendor:
                console.info(f"Force refreshing {vendor_str.upper()} vendor research...")
                generated = await generate_vendor_research(vendor_str, on_progress)
                if generated:
                    vendor_paths = [generated]
            else:
                result = await get_or_generate_vendor_research(
                    vendor_str,
                    force_refresh=False,  # Explicitly pass force_refresh
                    on_progress=on_progress,
                    allow_auto_refresh=config.allow_vendor_refresh,
                )
                vendor_paths = [str(p) for p in result.paths]

            for path in vendor_paths:
                if path and os.path.exists(path):
                    context_files.append(path)

            if vendor_paths:
                console.info(
                    f"Using {len(vendor_paths)} {vendor_str.upper()} research doc(s) as context"
                )

        agnostic_path = (
            Path(PROJECT_ROOT)
            / "vendor-research"
            / f"vendor-research-agnostic-{datetime.now().strftime('%Y-%m')}.txt"
        )
        if agnostic_path.exists() and str(agnostic_path) not in context_files:
            context_files.append(str(agnostic_path))

    return context_files, vendor_paths


async def _poll_for_completion(
    client,
    interaction_id: str,
    prompt: str,
    max_poll_time: int = 1800,
    poll_interval: int = 120,
    on_recovery_ready: Callable[[str], None] | None = None,
) -> str | None:
    """Poll for job completion after streaming interruption."""
    from primr.ai.deep_research import save_pending_job

    console.info("AI Strategy: Streaming interrupted, polling for completion...")
    console.info(f"AI Strategy: Job ID: {interaction_id}")
    save_pending_job(interaction_id, "ai_strategy", prompt[:100])

    loop = asyncio.get_running_loop()
    poll_start = loop.time()

    while (loop.time() - poll_start) < max_poll_time:
        await asyncio.sleep(poll_interval)
        elapsed = int(loop.time() - poll_start)
        console.status_with_time(f"AI Strategy: Checking status... ({elapsed}s elapsed)")

        check_result = client.check_job(interaction_id)
        status = check_result.get("status", "unknown")

        if status == "completed":
            content = check_result.get("content", "")
            if content:
                console.ok("AI Strategy: Job completed!")
                if on_recovery_ready:
                    on_recovery_ready(interaction_id)
                return content
            console.warn("AI Strategy: Job completed but no content returned")
            return None
        elif status == "failed":
            console.error(f"AI Strategy: Job failed: {check_result.get('error', 'Unknown')}")
            return None
        elif status != "in_progress":
            logger.warning(f"Unknown job status: {status}")

    console.warn(f"AI Strategy: Still running after {max_poll_time}s")
    console.info("AI Strategy: Check later with: primr --check-jobs")
    return None


async def _execute_strategy_research(
    prompt: str,
    context_files: list[str],
    timeout: int,
    on_progress: Callable[[str], None] | None = None,
    on_recovery_ready: Callable[[str], None] | None = None,
) -> str | None:
    """Execute Deep Research for AI strategy with polling fallback."""
    from primr.ai.deep_research import ResearchStatus, get_deep_research_client, save_pending_job

    client = get_deep_research_client()
    interaction_id = None

    def progress_callback(progress):
        nonlocal interaction_id
        if progress.message:
            if on_progress:
                on_progress(progress.message)
            console.status_with_time(f"AI Strategy: {progress.message}")
        if hasattr(progress, "interaction_id") and progress.interaction_id:
            interaction_id = progress.interaction_id

    try:
        result = await client.research(
            query=prompt,
            output_format=None,
            on_progress=progress_callback,
            context_files=context_files if context_files else None,
            timeout=timeout,
        )

        if result.status == ResearchStatus.COMPLETED and result.content:
            result_interaction_id = getattr(result, "interaction_id", "")
            if (
                isinstance(result_interaction_id, str)
                and result_interaction_id
                and on_recovery_ready
            ):
                on_recovery_ready(result_interaction_id)
            return result.content

        # Get interaction ID from result if not captured from progress
        if result.interaction_id:
            interaction_id = result.interaction_id

        # Poll for completion if we have an interaction ID
        if interaction_id:
            return await _poll_for_completion(
                client,
                interaction_id,
                prompt,
                on_recovery_ready=on_recovery_ready,
            )

        error_msg = result.error if hasattr(result, "error") and result.error else "Unknown error"
        console.error(f"AI Strategy research failed: {error_msg}")
        return None

    except Exception as e:
        console.error(f"AI Strategy generation failed: {e}")
        logger.exception("AI Strategy error")
        if interaction_id:
            save_pending_job(interaction_id, "ai_strategy", prompt[:100])
            console.info("AI Strategy: Job may still be running. Check with: primr --check-jobs")
        return None


def _process_citations(content: str) -> str:
    """
    Process citations in AI strategy content.

    - Converts [cite: X, Y, Z] to clean [1] [2] [3] format
    - Resolves Google redirect URLs to final destinations
    """
    import re
    from urllib.parse import urlparse

    from primr.ai.deep_research import resolve_citation_urls_sync

    # Convert inline [cite: X, Y, Z] references to clean [1] [2] [3] format
    def replace_cite_ref(match: re.Match) -> str:
        nums_str = match.group(1)
        nums = [n.strip() for n in nums_str.split(",")]
        refs = [f"[{num}]" for num in nums]
        return " ".join(refs)

    content = re.sub(r"\[cite:\s*([\d,\s]+)\]", replace_cite_ref, content)

    # Extract citations from Sources section
    citations: list[dict[str, str]] = []
    sources_match = re.search(r"\*\*Sources:\*\*\s*([\s\S]*?)$", content)
    if sources_match:
        sources_text = sources_match.group(1)
        citation_pattern = r"(\d+)\.\s*\[([^\]]+)\]\(([^)]+)\)"
        for match in re.finditer(citation_pattern, sources_text):
            citations.append(
                {"number": match.group(1), "title": match.group(2), "url": match.group(3)}
            )

    # Resolve redirect URLs
    if citations:
        logger.info(f"Resolving {len(citations)} AI strategy citation URLs...")
        citations = resolve_citation_urls_sync(citations)
        logger.info("AI strategy citation URLs resolved")

        # Rebuild Sources section with resolved URLs
        if sources_match:
            sources_header = "**Sources:**\n"
            cleaned_lines = []
            for citation in citations:
                num = citation.get("number", "")
                url = citation.get("url", "")
                title = citation.get("title", "")

                if url:
                    parsed = urlparse(url)
                    domain = parsed.netloc.replace("www.", "")
                    # Use domain as display text if title looks like a redirect URL
                    if "vertexaisearch" in title.lower() or not title:
                        display_text = domain
                    else:
                        display_text = title
                    cleaned_lines.append(f"{num}. [{display_text}]({url})")
                elif title:
                    cleaned_lines.append(f"{num}. {title}")

            new_sources = sources_header + "\n".join(cleaned_lines)
            content = content[: sources_match.start()] + new_sources

    return content


def _save_strategy_outputs(
    content: str, company_name: str, platform: Platform
) -> dict[str, str | None]:
    """Save AI strategy outputs in multiple formats."""
    from primr.output.markdown_converter import markdown_to_docx

    # Process citations (resolve URLs, clean formatting)
    content = _process_citations(content)

    date_str = datetime.now().strftime("%m-%d-%Y")
    vendor_tag = f"_{platform.value.upper()}" if platform.value.lower() != "agnostic" else ""
    base_name = f"{company_name}_AI_Strategy{vendor_tag}_{date_str}"
    outputs: dict[str, str | None] = {"md": None, "txt": None, "docx": None}

    try:
        # Save markdown
        md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        outputs["md"] = md_path
        console.ok(f"AI Strategy MD: {base_name}.md", show_time=False)

        # Save plain text
        txt_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(content)
        outputs["txt"] = txt_path
        console.ok(f"AI Strategy TXT: {base_name}.txt", show_time=False)

        # Convert to DOCX
        docx_path = os.path.join(OUTPUT_DIR, f"{base_name}.docx")
        subtitle_parts = [datetime.now().strftime("%B %d, %Y")]
        subtitle_parts.append(f"Cloud Vendor: {platform.value.upper()}")
        subtitle = " | ".join(subtitle_parts)

        try:
            markdown_to_docx(
                markdown_text=content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle,
            )
            outputs["docx"] = docx_path
            console.ok(f"AI Strategy DOCX: {base_name}.docx", show_time=False)
        except PermissionError:
            # File locked - try with timestamp
            timestamp = datetime.now().strftime("%H%M%S")
            docx_path = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.docx")
            console.warn(f"Original file locked, saving as: {base_name}_{timestamp}.docx")
            markdown_to_docx(
                markdown_text=content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle,
            )
            outputs["docx"] = docx_path

    except Exception as e:
        console.warn(f"Output generation failed: {e}")
        logger.exception("AI Strategy output error")

    return outputs


# Usage tracking removed — consolidated in research_agent.py main pipeline
