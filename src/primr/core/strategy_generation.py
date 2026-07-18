"""
Generic strategy generation helpers.

This module owns YAML-driven strategy prompt construction and the generic
Deep Research execution path for non-AI strategy documents. Keeping this
logic out of ``research_agent.py`` makes the stage boundary easier to test
and evolve without touching the main orchestration hub.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import yaml

from primr.ai.deep_research import ResearchStatus, get_deep_research_client
from primr.config.settings import get_settings
from primr.output.markdown_converter import markdown_to_docx
from primr.output.output_utils import OUTPUT_DIR
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("core.strategy_generation")


def _emit_legacy_skill_files(strategy_content: str, strategy_path: Path) -> None:
    """Preserve the documented per-role artifacts for the legacy skills strategy."""
    try:
        from primr.output.skills_generator import write_skill_files

        roles_root = strategy_path.parent / strategy_path.stem
        written = write_skill_files(strategy_content, roles_root)
        if written:
            console.info(
                f"Skills Ideation: emitted {len(written)} per-role SKILL.md files "
                f"under {roles_root.name}/roles/"
            )
        else:
            console.warn(
                "Skills Ideation: no role blocks parsed; per-role SKILL.md files were not emitted"
            )
    except Exception as exc:
        logger.warning("Skills Ideation per-role emission failed: %s", exc)


def build_strategy_prompt_from_yaml(
    strategy_config: dict, company_name: str, discovery_notes_content: str | None = None
) -> str:
    """
    Build a Deep Research prompt from a strategy YAML configuration.

    Args:
        strategy_config: Parsed YAML configuration.
        company_name: Name of the company.
        discovery_notes_content: Optional freeform meeting insights.

    Returns:
        Formatted prompt string for Deep Research.
    """
    current_date = datetime.now().strftime("%B %Y")

    meta = strategy_config.get("meta", {})
    strategy_name = meta.get("name", "Strategy Document")

    prompt_parts = [
        f"# {strategy_name} for {company_name}",
        f"Date: {current_date}\n",
    ]

    if "document_purpose" in strategy_config:
        prompt_parts.extend(["## YOUR ROLE AND TASK", strategy_config["document_purpose"], ""])

    if "context_instructions" in strategy_config:
        prompt_parts.extend(["## HOW TO USE CONTEXT", strategy_config["context_instructions"], ""])

    if "writing_standards" in strategy_config:
        prompt_parts.extend(
            ["## WRITING QUALITY STANDARDS", strategy_config["writing_standards"], ""]
        )

    if "epistemic_rules" in strategy_config:
        prompt_parts.append("## EPISTEMIC RULES (CRITICAL)")
        epistemic = strategy_config["epistemic_rules"]
        for rule_name, rule_text in epistemic.items():
            prompt_parts.append(f"### {rule_name.replace('_', ' ').title()}")
            prompt_parts.append(rule_text)
            prompt_parts.append("")

    if discovery_notes_content:
        prompt_parts.extend(
            [
                "## DISCOVERY NOTES (INTERNAL INSIGHTS)",
                "You have access to internal discovery notes from conversations with the company.",
                "Use these to ground your recommendations in their actual situation:",
                "",
                discovery_notes_content,
                "",
            ]
        )

    if "sections" in strategy_config:
        prompt_parts.extend(
            [
                "## DOCUMENT STRUCTURE",
                "Generate a comprehensive strategy document with the following sections:\n",
            ]
        )

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

    prompt_parts.extend(
        [
            "## FINAL INSTRUCTIONS",
            f"Generate a comprehensive {strategy_name} for {company_name}.",
            "Follow ALL the rules above, especially:",
            "- Use the Strategic Overview from File Search Store as PRIMARY source",
            "- Frame assessments as hypotheses to validate, not facts",
            "- Connect every recommendation to THIS company's specific situation",
            "- Include the Facilitation Toolkit sections (board presentation, stakeholder inception, workshop design)",
            "- Use compact [cite: N] references for major recommendations and factual claims; keep dense source listings in the final ## Sources appendix",
            "- End with a single ## Sources section listing the URLs you cited",
            "- Be specific, honest, and actionable",
            "",
            "Begin the document now.",
        ]
    )

    return "\n".join(prompt_parts)


def generate_generic_strategy(
    strategy_name: str,
    strategy_yaml: str,
    company_name: str,
    company_research_path: str | None = None,
    discovery_notes_content: str | None = None,
    output_dir: str | Path | None = None,
    diagnostics_dir: str | Path | None = None,
    write_txt: bool = True,
) -> str | None:
    """
    Generate a strategy document using Deep Research and the strategy YAML definition.
    """
    strategy_yaml_path = (
        Path(__file__).parent.parent / "prompts" / "strategies" / f"{strategy_yaml}.yaml"
    )
    if not strategy_yaml_path.exists():
        console.error(f"Strategy YAML not found: {strategy_yaml_path}")
        return None

    with open(strategy_yaml_path, encoding="utf-8") as handle:
        strategy_config = yaml.safe_load(handle)

    meta = strategy_config.get("meta", {})
    strategy_display_name = meta.get("name", strategy_name)
    destination_dir = Path(output_dir) if output_dir is not None else Path(OUTPUT_DIR)

    preflight_errors: list[str] = []

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
        destination_dir.mkdir(parents=True, exist_ok=True)
        test_file = destination_dir / ".write_test"
        with test_file.open("w", encoding="utf-8") as handle:
            handle.write("test")
        test_file.unlink()
    except Exception as exc:
        preflight_errors.append(f"Output directory not writable: {destination_dir} ({exc})")

    if preflight_errors:
        console.error("Pre-flight validation failed:")
        for err in preflight_errors:
            console.error(f"  - {err}")
        return None

    console.info("Pre-flight checks passed")

    try:
        prompt = build_strategy_prompt_from_yaml(
            strategy_config=strategy_config,
            company_name=company_name,
            discovery_notes_content=discovery_notes_content,
        )

        context_files: list[str] = []
        if company_research_path and os.path.exists(company_research_path):
            context_files.append(company_research_path)
            console.info("Using Strategic Overview as context")

        client = get_deep_research_client()

        def progress_callback(progress) -> None:
            if progress.message:
                console.info(f"{strategy_display_name}: {progress.message}")

        from primr.utils.async_utils import run_sync

        result = run_sync(
            client.research(
                query=prompt,
                output_format=None,
                on_progress=progress_callback,
                context_files=context_files if context_files else None,
                timeout=1800,
                job_metadata={
                    "report_kind": strategy_name,
                    "strategy_type": strategy_name,
                    "company_name": company_name,
                    "cloud_vendor": "agnostic",
                },
            )
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error(f"{strategy_display_name} research failed")
            return None

        result_interaction_id = getattr(result, "interaction_id", "")
        pending_interaction_id = (
            result_interaction_id if isinstance(result_interaction_id, str) else ""
        )

        date_str = datetime.now().strftime("%m-%d-%Y")
        output_filename = meta.get("output_filename", f"{{company_name}}_{strategy_name}")
        base_name = output_filename.format(company_name=company_name) + f"_{date_str}"
        destination_dir.mkdir(parents=True, exist_ok=True)
        internal_dir = Path(diagnostics_dir) if diagnostics_dir is not None else destination_dir
        internal_dir.mkdir(parents=True, exist_ok=True)

        md_path = destination_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(result.content)
        console.ok(f"{strategy_display_name} MD: {base_name}.md", show_time=False)

        txt_path: Path | None = None
        if write_txt or diagnostics_dir is not None:
            txt_path = (destination_dir if write_txt else internal_dir) / f"{base_name}.txt"
            with open(txt_path, "w", encoding="utf-8") as handle:
                handle.write(result.content)
            if write_txt:
                console.ok(f"{strategy_display_name} TXT: {base_name}.txt", show_time=False)

        docx_path = destination_dir / f"{base_name}.docx"
        durable_docx_path: Path | None = None
        try:
            subtitle = datetime.now().strftime("%B %d, %Y")
            markdown_to_docx(
                markdown_text=result.content,
                output_path=Path(docx_path),
                title=f"{strategy_display_name}: {company_name}",
                subtitle=subtitle,
            )
            console.ok(f"{strategy_display_name} DOCX: {base_name}.docx", show_time=False)
            durable_docx_path = docx_path
        except PermissionError:
            timestamp = datetime.now().strftime("%H%M%S")
            docx_path = destination_dir / f"{base_name}_{timestamp}.docx"
            console.warn(f"Original file locked, saving as: {base_name}_{timestamp}.docx")
            markdown_to_docx(
                markdown_text=result.content,
                output_path=Path(docx_path),
                title=f"{strategy_display_name}: {company_name}",
                subtitle=subtitle,
            )
            durable_docx_path = docx_path
        except Exception as exc:
            console.warn(f"DOCX conversion failed: {exc}")
            docx_path = md_path

        from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

        required_outputs = [md_path]
        if txt_path is not None:
            required_outputs.append(txt_path)
        if durable_docx_path is not None:
            required_outputs.append(durable_docx_path)
        if durable_docx_path is None or not acknowledge_pending_job_after_outputs(
            pending_interaction_id, required_outputs
        ):
            console.warn(f"{strategy_display_name} was saved, but its pending job remains listed.")

        if strategy_name == "skills":
            _emit_legacy_skill_files(result.content, md_path)

        return str(docx_path)

    except Exception as exc:
        console.error(f"{strategy_display_name} generation failed: {exc}")
        logger.exception("%s error", strategy_display_name)
        return None
