"""
Prompt configuration loader.

Loads prompt configurations from YAML files and builds prompt strings.
This separates prompt engineering from code, making prompts:
- Reviewable as standalone artifacts
- Versionable independently from code
- Customizable by users
- Easier to iterate on
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from primr.utils.logging_config import get_logger

logger = get_logger("prompts.loader")

# Directory containing prompt YAML files
PROMPTS_DIR = Path(__file__).parent


@dataclass
class SectionConfig:
    """Configuration for a single prompt section."""
    id: str
    name: str
    part: int
    purpose: str
    covers: list[str] = field(default_factory=list)
    depth: str = ""
    subsections: list["SectionConfig"] = field(default_factory=list)


@dataclass
class PromptConfig:
    """Complete prompt configuration loaded from YAML."""
    meta: dict[str, Any]
    document_purpose: str
    epistemic_rules: dict[str, str]
    formatting: dict[str, str]
    sections: list[SectionConfig]
    raw_config: dict[str, Any]  # Full YAML for custom access
    
    @property
    def name(self) -> str:
        return self.meta.get("name", "Unknown")
    
    @property
    def version(self) -> str:
        return self.meta.get("version", "0.0.0")


def load_prompt_config(prompt_name: str) -> PromptConfig:
    """
    Load a prompt configuration from YAML.
    
    Args:
        prompt_name: Name of the prompt (e.g., "company_overview", "ai_strategy")
        
    Returns:
        PromptConfig with all configuration loaded
        
    Raises:
        PromptConfigNotFoundError: If the YAML file doesn't exist
        PromptConfigValidationError: If the YAML is invalid
    """
    from primr.prompts.exceptions import (
        PromptConfigNotFoundError,
        PromptConfigValidationError,
    )

    yaml_path = PROMPTS_DIR / f"{prompt_name}.yaml"
    
    if not yaml_path.exists():
        available = get_available_prompts()
        raise PromptConfigNotFoundError(
            prompt_name=prompt_name,
            searched_paths=[str(yaml_path)],
            available_prompts=available,
        )
    
    try:
        with open(yaml_path, encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PromptConfigValidationError(
            config_path=str(yaml_path),
            errors=[f"YAML parse error: {e}"],
        ) from e
    
    if not raw_config:
        raise PromptConfigValidationError(
            config_path=str(yaml_path),
            errors=["Empty or invalid YAML file"],
        )
    
    # Parse sections
    sections = []
    for section_data in raw_config.get("sections", []):
        section = _parse_section(section_data)
        sections.append(section)
    
    return PromptConfig(
        meta=raw_config.get("meta", {}),
        document_purpose=raw_config.get("document_purpose", ""),
        epistemic_rules=raw_config.get("epistemic_rules", {}),
        formatting=raw_config.get("formatting", {}),
        sections=sections,
        raw_config=raw_config,
    )


def _parse_section(data: dict[str, Any]) -> SectionConfig:
    """Parse a section configuration from YAML data."""
    subsections = []
    for sub_data in data.get("subsections", []):
        subsections.append(_parse_section(sub_data))
    
    return SectionConfig(
        id=data.get("id", ""),
        name=data.get("name", ""),
        part=data.get("part", 0),
        purpose=data.get("purpose", ""),
        covers=data.get("covers", []),
        depth=data.get("depth", ""),
        subsections=subsections,
    )


def get_available_prompts() -> list[str]:
    """Get list of available prompt configurations."""
    prompts = []
    for path in PROMPTS_DIR.glob("*.yaml"):
        prompts.append(path.stem)
    return sorted(prompts)


def build_company_overview_prompt(
    company_name: str,
    query: str | None = None,
    website_url: str | None = None,
) -> str:
    """
    Build a company overview prompt from YAML configuration.
    
    Args:
        company_name: Name of the company to research
        query: Optional custom query (defaults to standard research query)
        website_url: Optional company website URL
        
    Returns:
        Complete prompt string for Deep Research
    """
    config = load_prompt_config("company_overview")
    current_date = datetime.now().strftime("%B %Y")
    
    # Build the query
    if not query:
        website_context = f" ({website_url})" if website_url else ""
        query = f"Research {company_name}{website_context} and produce a comprehensive strategic overview."
    
    # Build priority source instruction
    priority_source = ""
    if website_url:
        priority_source = f"Priority Source: Analyze {website_url} first.\n\n"
    
    # Start building the prompt - clean header format like Tundra example
    lines = [
        "You are a senior strategy consultant preparing pre-meeting research for a client engagement.",
        "",
        "=" * 77,
        "DOCUMENT PURPOSE",
        "=" * 77,
        "",
        config.document_purpose.replace("{company_name}", company_name).strip(),
        "",
        "=" * 77,
        "OUTPUT FORMAT (Use this exact header format)",
        "=" * 77,
        "",
        f"# Strategic Company Overview: {company_name}",
        "",
        f"*{current_date}*",
        "",
        f"**Company Name:** {company_name}",
    ]
    
    # Add website if provided
    if website_url:
        lines.append(f"**Website:** {website_url}")
    
    lines.extend([
        "**Industry:** [Identify the industry]",
        "",
    ])
    
    # Add key metrics format if present
    key_metrics = config.raw_config.get("key_metrics", {}).get("format", "")
    if key_metrics:
        lines.append(key_metrics.strip())
        lines.append("")
    
    lines.extend([
        "Then continue with the sections below using clean ## Section Name headers.",
        "",
        "=" * 77,
        "RESEARCH INSTRUCTIONS",
        "=" * 77,
        "",
        query,
        "",
        priority_source,
    ])
    
    # Add depth requirement
    lines.extend([
        "DEPTH REQUIREMENT: This document must be THOROUGH. Each section needs substantive analysis with specific evidence, not surface-level summaries. Include data tables where they add clarity. A consultant should be able to read this and walk into a meeting genuinely understanding the business.",
        "",
    ])
    
    # Add epistemic rules
    lines.append("EPISTEMIC RULES:")
    for rule_name, rule_text in config.epistemic_rules.items():
        lines.append(f"- {rule_text.strip()}")
    lines.append("")
    
    # Add formatting rules
    lines.append("FORMATTING:")
    for format_name, format_text in config.formatting.items():
        lines.append(f"- {format_text}")
    lines.extend([
        "",
        "DOCUMENT STYLE:",
        "- Use clean ## Section Name headers for each section",
        "- Write in a professional, modern consulting style",
        "- Keep formatting minimal and readable",
        "",
    ])
    
    # Group sections by part (but don't output part headers)
    sections_by_part: dict[int, list[SectionConfig]] = {}
    for section in config.sections:
        if section.part not in sections_by_part:
            sections_by_part[section.part] = []
        sections_by_part[section.part].append(section)
    
    # Build sections - NO PART HEADERS, just clean section flow
    lines.extend([
        "=" * 77,
        "SECTIONS TO INCLUDE",
        "=" * 77,
        "",
    ])
    
    for part_num in sorted(sections_by_part.keys()):
        for section in sections_by_part[part_num]:
            lines.extend(_build_section_text(section, company_name))
    
    return "\n".join(lines)


def _build_section_text(section: SectionConfig, company_name: str) -> list[str]:
    """Build text for a single section."""
    lines = [
        f"## {section.name}",
        "",
    ]
    
    if section.purpose:
        lines.append(section.purpose.replace("{company_name}", company_name))
        lines.append("")
    
    if section.covers:
        lines.append("Cover:")
        for item in section.covers:
            lines.append(f"- {item.replace('{company_name}', company_name)}")
        lines.append("")
    
    if section.depth:
        lines.append(section.depth.replace("{company_name}", company_name))
        lines.append("")
    
    # Handle subsections
    for subsection in section.subsections:
        lines.extend(_build_subsection_text(subsection, company_name))
    
    return lines


def _build_subsection_text(section: SectionConfig, company_name: str) -> list[str]:
    """Build text for a subsection."""
    lines = [
        f"### {section.name}",
        "",
    ]
    
    if section.covers:
        for item in section.covers:
            lines.append(f"- {item.replace('{company_name}', company_name)}")
        lines.append("")
    
    if section.depth:
        lines.append(section.depth.replace("{company_name}", company_name))
        lines.append("")
    
    return lines


def build_ai_strategy_prompt(
    company_name: str,
    cloud_vendor: str = "agnostic",
    current_date: str | None = None,
) -> str:
    """
    Build an AI strategy prompt from YAML configuration.
    
    This function delegates to PromptComposer.compose_strategy() internally,
    maintaining backward compatibility with the existing API.
    
    Args:
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference (azure, aws, gcp, agnostic)
        current_date: Optional date string (defaults to current date)
        
    Returns:
        Complete prompt string for Deep Research
    """
    from primr.prompts.composer import PromptComposer
    from primr.prompts.schema import PromptContext
    
    if not current_date:
        current_date = datetime.now().strftime("%B %Y")
    
    # Create context for the composer
    context = PromptContext(
        company_name=company_name,
        cloud_vendor=cloud_vendor,
        current_date=current_date,
        has_stage1_context=True,  # AI strategy always uses company overview as context
    )
    
    # Use PromptComposer to build the prompt
    composer = PromptComposer()
    composed = composer.compose_strategy("ai_strategy", context)
    
    return composed.content
