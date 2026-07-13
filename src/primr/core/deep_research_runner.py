"""
Deep Research runner for autonomous AI-powered company research.

This module handles Deep Research execution:
- Pre-flight validation before expensive API calls
- Deep Research API orchestration
- Result processing and output generation

Usage:
    from primr.core.deep_research_runner import (
        perform_deep_research,
        validate_preflight,
        DeepResearchConfig,
    )

    # Validate before running
    preflight = validate_preflight(config)
    if preflight.is_valid:
        result = await perform_deep_research(config)
"""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from primr.config.config import OUTPUT_DIR
from primr.core.workspace import create_working_folder, save_section_output
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import correlation_scope, log_structured

logger = get_logger("deep_research_runner")


# =============================================================================
# ENUMS
# =============================================================================


class PreflightStatus(Enum):
    """Status of a preflight check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class DeepResearchMode(Enum):
    """Deep Research execution modes."""

    DEEP_RESEARCH = "deep-research"
    COMPLETE = "complete"
    HYBRID = "hybrid"

    @property
    def display_name(self) -> str:
        """Human-readable mode name."""
        names = {
            "deep-research": "Deep Research",
            "complete": "Complete (Two-Step)",
            "hybrid": "Hybrid",
        }
        return names.get(self.value, self.value)

    @classmethod
    def from_string(cls, value: str) -> "DeepResearchMode":
        """Create mode from string."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.DEEP_RESEARCH


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class PreflightCheck:
    """Result of a single preflight check."""

    name: str
    status: PreflightStatus
    message: str
    guidance: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == PreflightStatus.PASSED

    @property
    def failed(self) -> bool:
        return self.status == PreflightStatus.FAILED


@dataclass
class PreflightResult:
    """Aggregated result of all preflight checks."""

    checks: list[PreflightCheck] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if all checks passed (no failures)."""
        return not any(c.failed for c in self.checks)

    @property
    def errors(self) -> list[str]:
        """List of error messages from failed checks."""
        return [c.message for c in self.checks if c.failed]

    @property
    def warnings(self) -> list[str]:
        """List of warning messages."""
        return [c.message for c in self.checks if c.status == PreflightStatus.WARNING]

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.failed)

    def add(self, check: PreflightCheck) -> None:
        """Add a check result."""
        self.checks.append(check)


@dataclass(frozen=True)
class DeepResearchConfig:
    """Configuration for Deep Research execution."""

    company_name: str | None
    website: str | None
    mode: DeepResearchMode
    citation_style: str = "numbered"
    ai_strategy: bool = False
    platform: str = "agnostic"
    context_files: tuple[str, ...] = ()
    refresh_vendor_research: bool = False
    timeout_seconds: int = 1800  # 30 minutes

    @property
    def display_name(self) -> str:
        """Get display name from company or website."""
        if self.company_name:
            return self.company_name
        if self.website:
            return urlparse(self.website).netloc
        return "Unknown"

    @classmethod
    def from_args(
        cls, company_name: str | None, website: str | None, mode: str, **kwargs
    ) -> "DeepResearchConfig":
        """Create config from CLI arguments."""
        context_files = kwargs.pop("context_files", None) or []
        return cls(
            company_name=company_name,
            website=website,
            mode=DeepResearchMode.from_string(mode),
            context_files=tuple(context_files),
            **kwargs,
        )


@dataclass
class DeepResearchResult:
    """Result of Deep Research execution."""

    docx_path: str | None
    md_path: str | None
    raw_content: str
    section_results: dict[str, str]
    citations: list[str]
    duration_seconds: float
    ai_strategy_path: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.docx_path is not None and self.error is None

    @property
    def section_count(self) -> int:
        return len(self.section_results)

    @property
    def citation_count(self) -> int:
        return len(self.citations)


# =============================================================================
# PROTOCOLS
# =============================================================================


class DeepResearchProgress(Protocol):
    """Protocol for progress reporting during Deep Research."""

    def on_progress(self, message: str) -> None:
        """Called with progress updates."""
        ...

    def on_phase_start(self, phase: int, total: int, name: str) -> None:
        """Called when a phase starts."""
        ...

    def on_phase_complete(self, name: str) -> None:
        """Called when a phase completes."""
        ...


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================


def validate_preflight(config: DeepResearchConfig) -> PreflightResult:
    """
    Validate all prerequisites before running Deep Research.

    Checks:
    - Company name or website provided
    - Context files exist and are readable
    - API key is configured
    - Output directory is writable

    Args:
        config: Deep Research configuration

    Returns:
        PreflightResult with all check results
    """
    from primr.config.settings import get_settings

    result = PreflightResult()

    # Check 1: Company name or website
    if config.company_name or config.website:
        result.add(
            PreflightCheck(
                name="company_info",
                status=PreflightStatus.PASSED,
                message="Company name or website provided",
            )
        )
    else:
        result.add(
            PreflightCheck(
                name="company_info",
                status=PreflightStatus.FAILED,
                message="Must provide company name or website",
                guidance="Use --company or --website argument",
            )
        )

    # Check 2: Context files
    if config.context_files:
        for f in config.context_files:
            if not os.path.exists(f):
                result.add(
                    PreflightCheck(
                        name="context_file",
                        status=PreflightStatus.FAILED,
                        message=f"Context file not found: {f}",
                        guidance="Verify the file path is correct",
                    )
                )
            elif not os.path.isfile(f):
                result.add(
                    PreflightCheck(
                        name="context_file",
                        status=PreflightStatus.FAILED,
                        message=f"Context path is not a file: {f}",
                        guidance="Provide a file path, not a directory",
                    )
                )
            elif os.path.getsize(f) == 0:
                result.add(
                    PreflightCheck(
                        name="context_file",
                        status=PreflightStatus.FAILED,
                        message=f"Context file is empty: {f}",
                        guidance="Provide a non-empty file",
                    )
                )
            else:
                result.add(
                    PreflightCheck(
                        name="context_file",
                        status=PreflightStatus.PASSED,
                        message=f"Context file valid: {os.path.basename(f)}",
                    )
                )

    # Check 3: API key
    settings = get_settings()
    if settings.api.gemini_key:
        result.add(
            PreflightCheck(
                name="api_key", status=PreflightStatus.PASSED, message="GEMINI_API_KEY configured"
            )
        )
    else:
        result.add(
            PreflightCheck(
                name="api_key",
                status=PreflightStatus.FAILED,
                message="GEMINI_API_KEY not configured",
                guidance="Set GEMINI_API_KEY in .env file",
            )
        )

    # Check 4: Output directory writable
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_file = os.path.join(OUTPUT_DIR, ".write_test")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_file)
        result.add(
            PreflightCheck(
                name="output_dir",
                status=PreflightStatus.PASSED,
                message="Output directory writable",
            )
        )
    except Exception as e:
        result.add(
            PreflightCheck(
                name="output_dir",
                status=PreflightStatus.FAILED,
                message=f"Output directory not writable: {e}",
                guidance=f"Check permissions on {OUTPUT_DIR}",
            )
        )

    return result


def perform_deep_research_sync(
    config: DeepResearchConfig, on_progress: Callable[[str], None] | None = None
) -> DeepResearchResult:
    """
    Perform Deep Research (synchronous wrapper).

    Args:
        config: Deep Research configuration
        on_progress: Optional progress callback

    Returns:
        DeepResearchResult with outputs and metadata
    """
    from primr.utils.async_utils import run_sync

    return run_sync(perform_deep_research(config, on_progress))


async def perform_deep_research(
    config: DeepResearchConfig, on_progress: Callable[[str], None] | None = None
) -> DeepResearchResult:
    """
    Perform Deep Research using the orchestrator (async).

    Executes:
    1. Pre-flight validation
    2. Deep Research API call
    3. Result processing and output generation
    4. Optional AI strategy generation

    Args:
        config: Deep Research configuration
        on_progress: Optional progress callback

    Returns:
        DeepResearchResult with outputs and metadata
    """
    start_time = time.time()

    # Pre-flight validation
    preflight = validate_preflight(config)
    if not preflight.is_valid:
        console.error("Pre-flight validation failed:")
        for err in preflight.errors:
            console.error(f"  - {err}")
        console.error("Fix these issues before running expensive Deep Research")
        return DeepResearchResult(
            docx_path=None,
            md_path=None,
            raw_content="",
            section_results={},
            citations=[],
            duration_seconds=time.time() - start_time,
            error="; ".join(preflight.errors),
        )

    display_name = config.display_name

    # Execute research
    with correlation_scope("deep_research", company=display_name, mode=config.mode.value):
        log_structured(
            "info", "Starting deep research", company=display_name, mode=config.mode.value
        )

        # Execute Deep Research
        research_result = await _execute_research(config, on_progress)
        if not research_result:
            return DeepResearchResult(
                docx_path=None,
                md_path=None,
                raw_content="",
                section_results={},
                citations=[],
                duration_seconds=time.time() - start_time,
                error="Deep Research execution failed",
            )

        # Process results
        outputs = _process_results(config, research_result)

        # Generate AI strategy if requested
        ai_strategy_path = None
        if config.ai_strategy:
            ai_strategy_path = await _generate_ai_strategy(config, outputs.get("raw_md_path"))

        # Usage tracked by the main research pipeline (research_agent.py)

        return DeepResearchResult(
            docx_path=outputs.get("docx_path"),
            md_path=outputs.get("raw_md_path"),
            raw_content=research_result.raw_content or "",
            section_results=research_result.section_results,
            citations=research_result.citations,
            duration_seconds=time.time() - start_time,
            ai_strategy_path=ai_strategy_path,
        )


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================


async def _execute_research(
    config: DeepResearchConfig, on_progress: Callable[[str], None] | None = None
) -> Any | None:
    """Execute Deep Research via orchestrator."""
    from primr.core.research_orchestrator import ResearchMode, get_orchestrator

    # Map mode
    mode_map = {
        DeepResearchMode.DEEP_RESEARCH: ResearchMode.DEEP_RESEARCH,
        DeepResearchMode.COMPLETE: ResearchMode.COMPLETE,
        DeepResearchMode.HYBRID: ResearchMode.HYBRID,
    }
    research_mode = mode_map.get(config.mode, ResearchMode.DEEP_RESEARCH)

    def progress_callback(msg: str) -> None:
        # Only call the parent callback - it handles console output
        # Don't duplicate with console.status_with_time here
        if on_progress:
            on_progress(msg)
        log_structured("debug", f"Deep research progress: {msg}")

    try:
        orchestrator = get_orchestrator()

        # No heartbeat - the progress_callback provides phase-aware status updates
        result = await orchestrator.research(
            company_name=config.company_name or config.display_name,
            website=config.website,
            mode=research_mode,
            on_progress=progress_callback,
            context_files=list(config.context_files) if config.context_files else None,
        )

        if not result.success:
            console.error(f"Research failed: {result.error}")
            log_structured("error", "Deep research failed", error=result.error)
            return None

        log_structured("info", "Deep research complete", sections=len(result.section_results))
        return result

    except Exception as e:
        console.error(f"Deep research failed: {e}")
        logger.exception("Deep research error")
        return None


def _process_results(config: DeepResearchConfig, result: Any) -> dict[str, str | None]:
    """Process Deep Research results and generate outputs."""
    outputs: dict[str, str | None] = {}

    # Save section results to working folder
    folder_path = create_working_folder(config.company_name, config.website)

    for section_key, content in result.section_results.items():
        save_section_output(folder_path, section_key, content)

    # Save raw markdown
    raw_md_path = None
    if result.raw_content:
        raw_md_path = os.path.join(folder_path, "deep_research_output.md")
        with open(raw_md_path, "w", encoding="utf-8") as f:
            f.write(result.raw_content)
        outputs["raw_md_path"] = raw_md_path

    # Generate DOCX
    if result.raw_content:
        durable_report_paths: list[Path] = []
        docx_path = _convert_deep_research_to_docx(
            result.raw_content,
            config.company_name or config.display_name,
            config.website,
            written_paths=durable_report_paths,
        )
        outputs["docx_path"] = docx_path

        pending_interaction_id = getattr(result, "pending_interaction_id", "")
        if isinstance(pending_interaction_id, str) and pending_interaction_id:
            from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

            if not docx_path or not acknowledge_pending_job_after_outputs(
                pending_interaction_id, durable_report_paths
            ):
                console.warn(
                    "Deep Research output is incomplete; its pending job remains recoverable."
                )

    return outputs


def _convert_deep_research_to_docx(
    markdown_content: str,
    company_name: str,
    website: str | None,
    written_paths: list[Path] | None = None,
) -> str | None:
    """
    Convert Deep Research markdown to DOCX and other formats.

    Outputs:
    - {company}_Strategic_Overview_{date}.md
    - {company}_Strategic_Overview_{date}.txt
    - {company}_Strategic_Overview_{date}.docx
    """
    from primr.output.markdown_converter import markdown_to_docx

    date_str = datetime.now().strftime("%m-%d-%Y")
    base_name = f"{company_name}_Strategic_Overview_{date_str}"

    try:
        from primr.output.final_artifact import normalize_final_punctuation

        markdown_content = normalize_final_punctuation(markdown_content)

        # Save markdown
        md_path = Path(OUTPUT_DIR) / f"{base_name}.md"
        md_path.write_text(markdown_content, encoding="utf-8")
        if written_paths is not None:
            written_paths.append(md_path)
        console.ok(f"MD saved: {base_name}.md", show_time=False)

        # Save plain text
        txt_path = Path(OUTPUT_DIR) / f"{base_name}.txt"
        txt_path.write_text(markdown_content, encoding="utf-8")
        if written_paths is not None:
            written_paths.append(txt_path)
        console.ok(f"TXT saved: {base_name}.txt", show_time=False)

        # Build subtitle
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
                subtitle=subtitle,
            )
        except PermissionError:
            # File locked - try with timestamp
            timestamp = datetime.now().strftime("%H%M%S")
            file_name = f"{base_name}_{timestamp}.docx"
            docx_path = Path(OUTPUT_DIR) / file_name
            console.warn(f"Original file locked, saving as: {file_name}")
            markdown_to_docx(
                markdown_text=markdown_content,
                output_path=docx_path,
                title=f"Strategic Company Overview: {company_name}",
                subtitle=subtitle,
            )

        console.ok(f"DOCX saved: {docx_path.name}", show_time=False)
        if written_paths is not None:
            written_paths.append(docx_path)
        return str(docx_path)

    except Exception as e:
        console.error(f"Failed to convert markdown to DOCX: {e}")
        logger.exception("Markdown to DOCX conversion failed")
        return None


async def _generate_ai_strategy(
    config: DeepResearchConfig, company_research_path: str | None
) -> str | None:
    """Generate AI strategy if requested."""
    from primr.core.ai_strategy import generate_ai_strategy

    console.phase_banner(3, 3, "AI Strategy Analysis", "Generating AI recommendations", "5-10 min")

    # No heartbeat - the progress callback provides phase-aware status updates
    result = await generate_ai_strategy(
        company_name=config.company_name or config.display_name,
        platform=config.platform,
        company_research_path=company_research_path,
        force_refresh_vendor=config.refresh_vendor_research,
    )

    if result.success:
        console.phase_complete("AI Strategy Analysis")
        return result.docx_path

    return None


# Usage tracking removed — consolidated in research_agent.py main pipeline
