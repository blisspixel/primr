"""
Prompt configuration loader.

Loads prompt configurations from YAML files and builds prompt strings.
This separates prompt engineering from code, making prompts:
- Reviewable as standalone artifacts
- Versionable independently from code
- Customizable by users
- Easier to iterate on

Note: The main prompt building functions (build_company_overview_prompt,
build_ai_strategy_prompt) now delegate to PromptComposer for consistency.
The dataclasses and load_prompt_config are kept for backward compatibility.
"""

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
    position: str = "middle"  # opening, middle, closing, or framework
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
        position=data.get("position", "middle"),
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

    This function delegates to PromptComposer.compose() internally,
    maintaining backward compatibility with the existing API.

    Args:
        company_name: Name of the company to research
        query: Optional custom query (ignored - kept for backward compatibility)
        website_url: Optional company website URL

    Returns:
        Complete prompt string for Deep Research
    """
    from primr.prompts.composer import PromptComposer
    from primr.prompts.schema import PromptContext

    current_date = datetime.now().strftime("%B %Y")

    # Create context for the composer
    context = PromptContext(
        company_name=company_name,
        website_url=website_url,
        current_date=current_date,
        has_stage1_context=False,  # Company overview is stage 1, no prior context
    )

    # Use PromptComposer to build the prompt
    composer = PromptComposer()
    composed = composer.compose("company_overview", context)

    return composed.content


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
