"""
Legacy AI strategy runtime extracted from research_agent.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from primr.ai.llm import llm
from primr.config.config import OUTPUT_DIR
from primr.config.settings import get_settings
from primr.core.vendor_research import (
    generate_vendor_research_sync,
    get_or_generate_vendor_research_sync,
    get_vendor_research_path,
)
from primr.output.markdown_converter import markdown_to_docx
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("core.ai_strategy_runtime")


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

        vendor_doc_paths: list[str] = []
        if platform.lower() != "agnostic":
            if force_refresh_vendor:
                console.info(f"Force refreshing {platform.upper()} vendor research...")
                generated = generate_vendor_research_sync(platform)
                vendor_doc_paths = [generated] if generated else []
            else:
                vendor_doc_paths = get_or_generate_vendor_research_sync(platform)

            for vendor_doc_path in vendor_doc_paths:
                if vendor_doc_path and os.path.exists(vendor_doc_path):
                    context_files.append(vendor_doc_path)

            if vendor_doc_paths:
                console.info(
                    f"Using {len(vendor_doc_paths)} {platform.upper()} research doc(s) as context"
                )

        agnostic_path = str(get_vendor_research_path("agnostic"))
        if os.path.exists(agnostic_path):
            context_files.append(agnostic_path)
            console.info("Using cross-industry AI research as additional context")

        pending_interaction_id = ""
        if lite_strategy:
            console.info("AI Strategy: Starting research (Pro mode)...")
            context_parts: list[str] = []
            for context_file in context_files:
                try:
                    with open(context_file, encoding="utf-8") as handle:
                        content = handle.read()
                    if content.strip():
                        context_parts.append(
                            f"--- Context: {os.path.basename(context_file)} ---\n{content}"
                        )
                except Exception as exc:
                    logger.warning("Failed to read context file %s: %s", context_file, exc)

            if context_parts:
                combined_context = "\n\n".join(context_parts)
                combined_prompt = (
                    "Use the following context documents to inform your analysis:\n\n"
                    f"{combined_context}\n\n"
                    "---\n\n"
                    f"{prompt}"
                )
            else:
                combined_prompt = prompt

            strategy_content = llm(
                combined_prompt,
                model_type="section_writing",
                temperature=1.0,
                thinking_level="high",
            )

            if not strategy_content or not strategy_content.strip():
                console.error("AI Strategy Pro generation failed - empty response")
                return None
        else:
            from primr.ai.deep_research import ResearchStatus, get_deep_research_client

            console.info("AI Strategy: Starting research (background mode)...")
            client = get_deep_research_client()

            def progress_callback(progress) -> None:
                if progress.message:
                    console.info(f"AI Strategy: {progress.message}")

            from primr.utils.async_utils import run_sync

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
                console.error("AI Strategy research failed")
                return None

            strategy_content = result.content
            result_interaction_id = getattr(result, "interaction_id", "")
            pending_interaction_id = (
                result_interaction_id if isinstance(result_interaction_id, str) else ""
            )

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
    """Build the legacy Deep Research prompt for board-level AI strategy."""
    current_date = datetime.now().strftime("%B %Y")

    vendor_names = {
        "azure": "Microsoft Azure",
        "aws": "Amazon Web Services (AWS)",
        "gcp": "Google Cloud Platform (GCP)",
        "agnostic": "all major cloud vendors (Azure, AWS, GCP)",
        "private": "Private Cloud / NVIDIA",
    }
    vendor_name = vendor_names.get(platform.lower(), vendor_names["agnostic"])

    vendor_specific_guidance = {
        "azure": """
KEY AZURE AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):
- Microsoft 365 Copilot
- Copilot Studio
- Azure OpenAI Service
- Azure AI Foundry
- Microsoft Fabric
- Azure AI Search
Search for the latest announcements from Microsoft Ignite 2025 and recent Azure updates.
""",
        "aws": """
KEY AWS AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):
- Amazon Q
- Amazon Bedrock
- Amazon Bedrock Agents
- Amazon SageMaker
- Amazon QuickSight Q
Search for the latest announcements from AWS re:Invent 2024 and recent AWS updates.
""",
        "gcp": """
KEY GOOGLE CLOUD AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):
- Gemini for Google Workspace
- Vertex AI
- Vertex AI Agent Builder
- BigQuery with Gemini
- Vertex AI Search
Search for the latest announcements from Google Cloud Next 2024 and recent GCP updates.
""",
        "agnostic": """
MULTI-CLOUD AI STRATEGY (search for latest as of {current_date}):
Compare Azure, AWS, and GCP by model platforms, copilots, agents, data platforms, and governance.
Search for the latest announcements from all three vendors' recent conferences.
""",
        "private": """
KEY PRIVATE CLOUD / NVIDIA AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):
- NVIDIA DGX Cloud
- NVIDIA AI Enterprise
- NVIDIA NIM
- NVIDIA NeMo
- NVIDIA Omniverse
Search for the latest from NVIDIA GTC 2025 and partner announcements.
""",
    }

    vendor_guidance = vendor_specific_guidance.get(
        platform.lower(), vendor_specific_guidance["agnostic"]
    ).format(current_date=current_date)

    discovery_notes_block = ""
    if discovery_notes_content:
        discovery_notes_block = f"""
DISCOVERY NOTES (INTERNAL INSIGHTS)
Use these notes from company conversations to ground the recommendations:

{discovery_notes_content}
"""

    return f"""You are a senior AI strategy consultant. Generate a comprehensive AI roadmap for board-level decision making.

# AI Strategy: {company_name}

**Prepared by:** Primr Research System
**Date:** {current_date}

CRITICAL: This strategy must reflect the AI landscape as of {current_date}. You MUST actively search for current announcements and cite them.

You have access to research about {company_name} in the context files. Use that foundation to develop a practical AI strategy for leadership.

{discovery_notes_block}

CLOUD VENDOR FOCUS: {vendor_name}
{vendor_guidance}

Use compact [cite: N] references for major factual claims and recommendations, and end with a single ## Sources section listing URLs.

Cover:
- AI strategic thesis
- executive summary
- likely current state hypotheses
- competitive AI landscape
- recommended AI architecture posture
- productivity AI by persona
- process automation
- conversational AI
- agentic AI
- generative BI and analytics
- traditional AI/ML
- quick wins, bigger bets, and deprioritizations

Be specific, honest, and actionable. Begin the document now.
"""
