"""
Legacy AI strategy runtime extracted from research_agent.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from primr.ai.llm import llm
from primr.config.config import OUTPUT_DIR
from primr.config.models import LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS
from primr.config.settings import get_settings
from primr.core.strategy_context import stable_vendor_context_snapshots
from primr.core.vendor_research import (
    get_or_generate_vendor_research_sync,
    get_vendor_research_path,
)
from primr.output.markdown_converter import markdown_to_docx
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("core.ai_strategy_runtime")


def _notify_strategy_task_observer(
    observer: Callable[[str], None] | None,
    event: str,
) -> None:
    """Keep run-local accounting failures outside the delivery path."""
    if observer is None:
        return
    try:
        observer(event)
    except Exception as exc:
        logger.debug(
            "AI Strategy task observer failed: failure_type=%s",
            type(exc).__name__,
        )


def _generate_strategy_content(
    *,
    prompt: str,
    context_files: list[str],
    lite_strategy: bool,
    company_name: str,
    platform: str,
    strategy_task_observer: Callable[[str], None] | None,
) -> tuple[str | None, str]:
    """Run one strategy provider call while caller-owned snapshots stay live."""

    if lite_strategy:
        console.info("AI Strategy: Starting research (Pro mode)...")
        from primr.ai.routing import Role, pick_model_for_role
        from primr.core.strategy_context import build_bounded_lite_strategy_prompt

        combined_prompt = build_bounded_lite_strategy_prompt(prompt, context_files)
        strategy_content = llm(
            combined_prompt,
            model_type="reasoning",
            temperature=1.0,
            thinking_level="high",
            model=pick_model_for_role(Role.REASONING),
            max_tokens=LITE_AI_STRATEGY_MAX_OUTPUT_TOKENS,
        )
        if not strategy_content or not strategy_content.strip():
            console.error("AI Strategy Pro generation failed - empty response")
            return None, ""
        return strategy_content, ""

    from primr.ai.deep_research import ResearchStatus, get_deep_research_client
    from primr.utils.async_utils import run_sync

    console.info("AI Strategy: Starting research (background mode)...")
    client = get_deep_research_client()

    def progress_callback(progress) -> None:
        if progress.message:
            console.info(f"AI Strategy: {progress.message}")

    _notify_strategy_task_observer(strategy_task_observer, "started")
    result = run_sync(
        client.research(
            query=prompt,
            output_format=None,
            on_progress=progress_callback,
            context_files=context_files if context_files else None,
            timeout=1800,
            job_metadata={
                "report_kind": "ai_strategy",
                "strategy_type": "ai",
                "company_name": company_name,
                "cloud_vendor": platform.lower(),
            },
        )
    )
    if result.status != ResearchStatus.COMPLETED or not result.content:
        _notify_strategy_task_observer(strategy_task_observer, "failed")
        console.error("AI Strategy research failed")
        return None, ""
    _notify_strategy_task_observer(strategy_task_observer, "completed")
    interaction_id = getattr(result, "interaction_id", "")
    return result.content, interaction_id if isinstance(interaction_id, str) else ""


def generate_ai_strategy_section(
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
    """Generate AI strategy using the legacy sync runtime."""
    preflight_errors: list[str] = []

    if not company_name or not company_name.strip():
        preflight_errors.append("Company name is required for AI strategy generation")

    valid_vendors = ["azure", "aws", "gcp", "agnostic", "private"]
    if platform.lower() not in valid_vendors:
        preflight_errors.append(
            f"Invalid cloud vendor: {platform}. Must be one of: {', '.join(valid_vendors)}"
        )

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
        with open(test_file, "w", encoding="utf-8") as handle:
            handle.write("test")
        os.remove(test_file)
    except Exception as exc:
        preflight_errors.append(f"Output directory not writable: {OUTPUT_DIR} ({exc})")

    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        console.error("Fix these issues before running expensive Deep Research")
        return None

    console.info("Pre-flight checks passed")

    try:
        prompt = build_ai_strategy_prompt(company_name, platform, discovery_notes_content)

        context_files: list[str] = []
        if company_research_path and os.path.exists(company_research_path):
            context_files.append(company_research_path)

            # Attach the run's recon context when it sits alongside the report so
            # the strategy addresses the full observed vendor stack (identity,
            # cloud, AI providers), not only the report narrative or one platform.
            recon_sibling = os.path.join(
                os.path.dirname(company_research_path), "_recon_context.txt"
            )
            if os.path.exists(recon_sibling) and recon_sibling not in context_files:
                context_files.append(recon_sibling)
                console.info("Using recon context (observed vendor stack) as strategy context")

        vendor_doc_paths: list[str] = []
        if force_refresh_vendor:
            # Freshness-aware: reuse a cache newer than the freshness window,
            # regenerate only when it is stale or missing. This is what
            # --refresh-vendor-research means, so a habitual flag does not
            # re-bill a paid Deep Research task every run.
            console.info(
                f"Ensuring fresh {platform.upper()} vendor research "
                f"(reuse if within the freshness window, regenerate if stale or missing)..."
            )
            if vendor_refresh_observer is None:
                vendor_doc_paths = get_or_generate_vendor_research_sync(
                    platform,
                    force_refresh=False,
                    allow_auto_refresh=True,
                    lite=lite_strategy,
                )
            else:
                vendor_doc_paths = get_or_generate_vendor_research_sync(
                    platform,
                    force_refresh=False,
                    allow_auto_refresh=True,
                    task_observer=vendor_refresh_observer,
                    lite=lite_strategy,
                )
        elif platform.lower() != "agnostic":
            vendor_doc_paths = get_or_generate_vendor_research_sync(
                platform,
                allow_auto_refresh=False,
                lite=lite_strategy,
            )

        if vendor_doc_paths:
            console.info(
                f"Using {len(vendor_doc_paths)} {platform.upper()} research doc(s) as context"
            )

        agnostic_path = str(get_vendor_research_path("agnostic"))
        if os.path.exists(agnostic_path) and agnostic_path not in vendor_doc_paths:
            vendor_doc_paths.append(agnostic_path)
            console.info("Using cross-industry AI research as additional context")

        with stable_vendor_context_snapshots(vendor_doc_paths) as vendor_snapshots:
            safe_context_files = context_files + [
                snapshot.snapshot_path for snapshot in vendor_snapshots
            ]
            strategy_content, pending_interaction_id = _generate_strategy_content(
                prompt=prompt,
                context_files=safe_context_files,
                lite_strategy=lite_strategy,
                company_name=company_name,
                platform=platform,
                strategy_task_observer=strategy_task_observer,
            )
        if not strategy_content:
            return None

        date_str = datetime.now().strftime("%m-%d-%Y")
        vendor_tag = f"_{platform.upper()}" if platform.lower() != "agnostic" else ""
        base_name = f"{company_name}_AI_Strategy{vendor_tag}_{date_str}"
        destination_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)
        destination_dir.mkdir(parents=True, exist_ok=True)
        internal_dir = Path(diagnostics_dir) if diagnostics_dir is not None else destination_dir
        internal_dir.mkdir(parents=True, exist_ok=True)

        md_path = destination_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(strategy_content)
        console.ok(f"AI Strategy MD: {base_name}.md", show_time=False)

        txt_path: Path | None = None
        if write_txt or diagnostics_dir is not None:
            txt_path = (destination_dir if write_txt else internal_dir) / f"{base_name}.txt"
            with open(txt_path, "w", encoding="utf-8") as handle:
                handle.write(strategy_content)
            if write_txt:
                console.ok(f"AI Strategy TXT: {base_name}.txt", show_time=False)

        docx_path = destination_dir / f"{base_name}.docx"
        durable_docx_path: Path | None = None
        try:
            subtitle = " | ".join([datetime.now().strftime("%B %d, %Y"), platform.title()])
            markdown_to_docx(
                markdown_text=strategy_content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle,
            )
            console.ok(f"AI Strategy DOCX: {base_name}.docx", show_time=False)
            durable_docx_path = docx_path
        except PermissionError:
            timestamp = datetime.now().strftime("%H%M%S")
            docx_path = destination_dir / f"{base_name}_{timestamp}.docx"
            console.warn(f"Original file locked, saving as: {base_name}_{timestamp}.docx")
            markdown_to_docx(
                markdown_text=strategy_content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle,
            )
            durable_docx_path = docx_path
        except Exception as exc:
            console.warn(f"DOCX conversion failed: {exc}")
            docx_path = md_path

        if pending_interaction_id:
            from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

            required_outputs = [md_path]
            if txt_path is not None:
                required_outputs.append(txt_path)
            if durable_docx_path is not None:
                required_outputs.append(durable_docx_path)
            if durable_docx_path is None or not acknowledge_pending_job_after_outputs(
                pending_interaction_id, required_outputs
            ):
                console.warn("AI Strategy was saved, but its pending job remains listed.")

        return str(docx_path)

    except Exception as exc:
        console.error(f"AI Strategy generation failed: {exc}")
        logger.exception("AI Strategy error")
        return None


def build_ai_strategy_prompt(
    company_name: str, platform: str, discovery_notes_content: str | None = None
) -> str:
    """Build the canonical YAML-defined board-level AI strategy prompt.

    This compatibility seam is used by the standard and fast CLI paths. Keeping
    it delegated to the same composer as the async/MCP path prevents policy,
    evidence, and section-order drift between transports.
    """
    from primr.prompts.loader import build_ai_strategy_prompt as build_from_yaml

    normalized_platform = platform.lower()
    if normalized_platform not in {"azure", "aws", "gcp", "agnostic", "private"}:
        normalized_platform = "agnostic"
    return build_from_yaml(
        company_name=company_name,
        platform=normalized_platform,
        discovery_notes_content=discovery_notes_content,
    )
