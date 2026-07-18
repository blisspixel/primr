"""
Prompt Composer for the Deep Research prompt architecture.

This module provides the central component for composing prompts from YAML
configurations with shared components and variable substitution.

Usage:
    composer = PromptComposer()
    prompt = composer.compose(
        "company_overview",
        PromptContext(company_name="Acme Corp", website_url="https://acme.example")
    )
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from primr.prompts.exceptions import (
    PromptConfigNotFoundError,
    PromptConfigValidationError,
)
from primr.prompts.schema import (
    ComposedPrompt,
    DataSource,
    PromptConfig,
    PromptContext,
    SectionSpec,
)
from primr.prompts.shared_loader import SharedComponentLoader
from primr.utils.content_sanitizer import sanitize_for_llm
from primr.utils.logging_config import get_logger

logger = get_logger("prompts.composer")

# Directory containing prompt YAML files
PROMPTS_DIR = Path(__file__).parent


class PromptComposer:
    """
    Composes prompts from YAML configurations with shared components.

    The composer:
    1. Loads the prompt configuration from YAML
    2. Loads shared components (epistemic rules, formatting, personas)
    3. Merges shared components with prompt-specific overrides
    4. Substitutes variables ({company_name}, {website_url}, etc.)
    5. Builds the final prompt string

    Example:
        composer = PromptComposer()
        prompt = composer.compose(
            "company_overview",
            PromptContext(company_name="Acme Corp", website_url="https://acme.example")
        )
        print(prompt.content)
    """

    def __init__(self, prompts_dir: Path | None = None):
        """
        Initialize the composer.

        Args:
            prompts_dir: Optional custom path to prompts directory.
                        Defaults to src/primr/prompts/
        """
        self._prompts_dir = prompts_dir or PROMPTS_DIR
        self._shared_loader = SharedComponentLoader(self._prompts_dir / "shared")
        self._config_cache: dict[str, PromptConfig] = {}

    @property
    def prompts_dir(self) -> Path:
        """Get the prompts directory path."""
        return self._prompts_dir

    def compose(
        self,
        prompt_name: str,
        context: PromptContext,
    ) -> ComposedPrompt:
        """
        Compose a complete prompt from YAML config and context.

        Args:
            prompt_name: Name of the prompt config (e.g., "company_overview")
            context: Runtime context for variable substitution

        Returns:
            ComposedPrompt with fully assembled content

        Raises:
            PromptConfigNotFoundError: If the prompt config doesn't exist
            PromptConfigValidationError: If the YAML is invalid
        """
        # Load the prompt config
        config = self._load_config(prompt_name)

        # Load shared components
        shared = self._shared_loader.load()

        # Build the prompt content
        content = self._build_prompt(config, shared, context)

        # Track source files
        source_files = [f"{prompt_name}.yaml"]
        if (self._prompts_dir / "shared" / "epistemic_rules.yaml").exists():
            source_files.append("shared/epistemic_rules.yaml")
        if (self._prompts_dir / "shared" / "formatting.yaml").exists():
            source_files.append("shared/formatting.yaml")
        if (self._prompts_dir / "shared" / "personas.yaml").exists():
            source_files.append("shared/personas.yaml")

        # Track substituted variables
        variables_substituted = self._get_substituted_variables(context)

        return ComposedPrompt(
            content=content,
            source_files=source_files,
            section_count=len(config.sections),
            variables_substituted=variables_substituted,
        )

    def compose_strategy(
        self,
        strategy_name: str,
        context: PromptContext,
    ) -> ComposedPrompt:
        """
        Compose a strategy module prompt.

        Args:
            strategy_name: Name of the strategy (e.g., "ai", "cloud")
            context: Runtime context for variable substitution

        Returns:
            ComposedPrompt with strategy-specific content
        """
        # Strategy configs are in strategies/ subdirectory
        config_path = self._prompts_dir / "strategies" / f"{strategy_name}_strategy.yaml"
        if not config_path.exists():
            # Try without _strategy suffix
            config_path = self._prompts_dir / "strategies" / f"{strategy_name}.yaml"

        if not config_path.exists():
            raise PromptConfigNotFoundError(
                prompt_name=strategy_name,
                searched_paths=[
                    str(self._prompts_dir / "strategies" / f"{strategy_name}_strategy.yaml"),
                    str(self._prompts_dir / "strategies" / f"{strategy_name}.yaml"),
                ],
                available_prompts=self.list_strategies(),
            )

        # Load and compose
        config = self._load_config_from_path(config_path)
        shared = self._shared_loader.load()
        content = self._build_prompt(config, shared, context)

        return ComposedPrompt(
            content=content,
            source_files=[f"strategies/{config_path.name}"],
            section_count=len(config.sections),
            variables_substituted=self._get_substituted_variables(context),
        )

    def list_prompts(self) -> list[str]:
        """List all available prompt configurations."""
        prompts = []
        for path in self._prompts_dir.glob("*.yaml"):
            prompts.append(path.stem)
        return sorted(prompts)

    def list_strategies(self) -> list[str]:
        """List all available strategy modules."""
        strategies_dir = self._prompts_dir / "strategies"
        if not strategies_dir.exists():
            return []

        strategies = []
        for path in strategies_dir.glob("*.yaml"):
            name = path.stem
            # Remove _strategy suffix if present
            if name.endswith("_strategy"):
                name = name[:-9]
            strategies.append(name)
        return sorted(strategies)

    def validate_config(self, config_path: Path) -> list[str]:
        """
        Validate a prompt config file against the schema.

        Args:
            config_path: Path to the YAML file

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not config_path.exists():
            errors.append(f"File not found: {config_path}")
            return errors

        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            errors.append(f"Invalid YAML: {e}")
            return errors

        if not isinstance(data, dict):
            errors.append("YAML must be a dictionary")
            return errors

        # Check required fields
        if "meta" not in data:
            errors.append("Missing required field: meta")
        if "sections" not in data:
            errors.append("Missing required field: sections")

        # Validate sections
        sections = data.get("sections", [])
        if not isinstance(sections, list):
            errors.append("sections must be a list")
        else:
            for i, section in enumerate(sections):
                if not isinstance(section, dict):
                    errors.append(f"Section {i} must be a dictionary")
                    continue
                if "id" not in section:
                    errors.append(f"Section {i} missing required field: id")
                if "name" not in section:
                    errors.append(f"Section {i} missing required field: name")
                if "purpose" not in section or not section.get("purpose"):
                    errors.append(
                        f"Section {i} ({section.get('id', 'unknown')}) missing or empty purpose"
                    )

        return errors

    def _load_config(self, prompt_name: str) -> PromptConfig:
        """Load a prompt configuration by name."""
        if prompt_name in self._config_cache:
            return self._config_cache[prompt_name]

        config_path = self._prompts_dir / f"{prompt_name}.yaml"
        if not config_path.exists():
            raise PromptConfigNotFoundError(
                prompt_name=prompt_name,
                searched_paths=[str(config_path)],
                available_prompts=self.list_prompts(),
            )

        config = self._load_config_from_path(config_path)
        self._config_cache[prompt_name] = config
        return config

    def _load_config_from_path(self, config_path: Path) -> PromptConfig:
        """Load a prompt configuration from a specific path."""
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise PromptConfigValidationError(
                config_path=str(config_path),
                errors=[f"YAML parse error: {e}"],
            ) from e

        if not data:
            raise PromptConfigValidationError(
                config_path=str(config_path),
                errors=["Empty YAML file"],
            )

        # Parse sections
        sections = []
        for section_data in data.get("sections", []):
            sections.append(SectionSpec.from_dict(section_data))

        # Parse data sources
        data_sources = []
        for ds_data in data.get("data_sources", []):
            data_sources.append(DataSource.from_dict(ds_data))

        is_strategy_config = config_path.parent.name == "strategies"
        epistemic_rules = data.get("epistemic_rules_override", {})
        formatting_rules = data.get("formatting_override", {})
        if is_strategy_config:
            epistemic_rules = data.get("epistemic_rules", epistemic_rules)
            formatting_rules = data.get("formatting", formatting_rules)

        return PromptConfig(
            meta=data.get("meta", {}),
            document_purpose=data.get("document_purpose", ""),
            sections=sections,
            raw_config=data,
            epistemic_rules_override=epistemic_rules,
            formatting_override=formatting_rules,
            persona_override=data.get("persona"),
            vendor_guidance=data.get("vendor_guidance", {}),
            data_sources=data_sources,
            heuristics=data.get("heuristics", {}),
        )

    def _build_prompt(
        self,
        config: PromptConfig,
        shared: Any,
        context: PromptContext,
    ) -> str:
        """Build the complete prompt string."""
        lines: list[str] = []

        # Get persona
        persona_name = config.persona_override or shared.default_persona
        persona = shared.get_persona(persona_name)
        if persona:
            lines.append(persona.strip())
            lines.append("")

        # Add current date context (CRITICAL for LLMs to understand temporal context)
        current_date = context.current_date or datetime.now().strftime("%B %d, %Y")
        current_year = datetime.now().year
        current_month_year = datetime.now().strftime("%B %Y")
        lines.extend(
            [
                "=" * 77,
                "CURRENT DATE CONTEXT",
                "=" * 77,
                "",
                f"REMINDER: It is {current_month_year}. Please use the latest insights and technologies for NOW and the NEAR FUTURE.",
                "",
                f"You are operating in {current_year}, not in your training data timeframe. When you see '{current_year}' or '{current_year + 1}', these are CURRENT or NEAR-FUTURE, not distant future.",
                "",
            ]
        )

        # Add document purpose
        if config.document_purpose:
            lines.extend(
                [
                    "=" * 77,
                    "DOCUMENT PURPOSE",
                    "=" * 77,
                    "",
                    config.document_purpose.strip(),
                    "",
                ]
            )

        # Add context instructions if available and context is present
        if context.has_stage1_context:
            context_instructions = config.raw_config.get("context_instructions", "")
            if context_instructions:
                lines.extend(
                    [
                        "=" * 77,
                        "CONTEXT INSTRUCTIONS",
                        "=" * 77,
                        "",
                        context_instructions.strip(),
                        "",
                    ]
                )

            # Add shared evidence-handling instructions. Presence in the
            # context store does not make a source verified or authoritative.
            lines.extend(
                [
                    "HIERARCHY OF EVIDENCE:",
                    "- Use File Search Store material as supplied context, preserving each source's type, recency, scope, and confidence",
                    "- Do not treat a synthesis, scrape, recon interpretation, or meeting perspective as verified solely because it is in the store",
                    "- Use current primary web sources to validate time-sensitive and external claims when browsing is available",
                    "- Surface material conflicts; prefer scoped first-hand internal evidence only for facts it can directly establish",
                    "",
                ]
            )

        # Add discovery notes if provided
        if context.discovery_notes_content:
            lines.extend(
                [
                    "=" * 77,
                    "DISCOVERY INSIGHTS (FROM MEETINGS)",
                    "=" * 77,
                    "",
                    "The following insights were captured from discovery meetings with this company.",
                    "Treat them as operator-supplied evidence of internal priorities and constraints.",
                    "Preserve the perspective and uncertainty of the people who supplied them.",
                    "",
                    "NOTES ARE FREEFORM - extract what's relevant for this strategy.",
                    "",
                    # Operator notes are important evidence but are still sanitized
                    # in case pasted text carries scraped content with stray directives.
                    # They are not hard-fenced because the framing above is intentional.
                    sanitize_for_llm(context.discovery_notes_content.strip())[0],
                    "",
                ]
            )

        # Add hard requirements if present
        hard_requirements = config.raw_config.get("hard_requirements", "")
        if hard_requirements:
            lines.extend(
                [
                    "=" * 77,
                    "HARD REQUIREMENTS",
                    "=" * 77,
                    "",
                    hard_requirements.strip(),
                    "",
                ]
            )

        # Add output format header
        current_date = context.current_date or datetime.now().strftime("%B %d, %Y")
        lines.extend(
            [
                "=" * 77,
                "OUTPUT FORMAT",
                "=" * 77,
                "",
                f"# {config.name}: {context.company_name}",
                "",
                f"**Date:** {current_date}",
                "",
            ]
        )

        # Add key metrics format if present
        key_metrics = config.raw_config.get("key_metrics", {}).get("format", "")
        if key_metrics:
            lines.append(key_metrics.strip())
            lines.append("")

        lines.extend(["---", ""])

        # Add research instructions
        lines.extend(
            [
                "=" * 77,
                "RESEARCH INSTRUCTIONS",
                "=" * 77,
                "",
            ]
        )

        # Add priority source if website provided
        if context.website_url:
            lines.append(f"Priority Source: Analyze {context.website_url} first.")
            lines.append("")

        # Add writing standards if present (quality-focused guidance)
        writing_standards = config.raw_config.get("writing_standards", "")
        if writing_standards:
            lines.extend(
                [
                    "WRITING STANDARDS:",
                    writing_standards.strip(),
                    "",
                ]
            )
        else:
            # Default depth requirement if no writing standards specified
            lines.extend(
                [
                    "DEPTH REQUIREMENT: This document must be THOROUGH. Each section needs ",
                    "substantive analysis with specific evidence, not surface-level summaries. ",
                    "Include data tables where they add clarity.",
                    "",
                ]
            )

        # Add epistemic rules (merged with overrides)
        lines.append("EPISTEMIC RULES:")
        epistemic_rules = dict(shared.epistemic_rules)
        epistemic_rules.update(config.epistemic_rules_override)
        for rule_text in epistemic_rules.values():
            lines.append(f"- {rule_text.strip()}")
        lines.append("")

        # Add formatting rules (merged with overrides)
        lines.append("FORMATTING:")
        formatting_rules = dict(shared.formatting_rules)
        formatting_rules.update(config.formatting_override)
        for rule_text in formatting_rules.values():
            lines.append(f"- {rule_text.strip()}")
        lines.append("")

        # Add heuristics if present
        if config.heuristics:
            lines.append("HEURISTICS AND RULES OF THUMB:")
            for text in config.heuristics.values():
                lines.append(f"- {text.strip()}")
            lines.append("")

        # Add vendor guidance if applicable
        if config.vendor_guidance and context.platform:
            vendor_config = config.vendor_guidance.get(
                context.platform.lower(), config.vendor_guidance.get("agnostic", {})
            )
            if vendor_config:
                lines.extend(self._build_vendor_context(vendor_config, context))

        # Build sections - no numbered parts, just flow naturally
        sections_by_part = config.get_sections_by_part()

        for part_num in sorted(sections_by_part.keys()):
            for section in sections_by_part[part_num]:
                lines.extend(self._build_section(section, context))

        # Add footer if present
        footer = config.raw_config.get("footer", "")
        if footer:
            lines.append(footer.strip())

        # Join and substitute variables
        content = "\n".join(lines)
        content = self._substitute_variables(content, context)

        return content

    def _build_section(
        self,
        section: SectionSpec,
        context: PromptContext,
    ) -> list[str]:
        """Build text for a single section."""
        lines = [
            f"## {section.name}",
            "",
        ]

        if section.purpose:
            lines.append(section.purpose)
            lines.append("")

        if section.covers:
            lines.append("Cover:")
            for item in section.covers:
                lines.append(f"- {item}")
            lines.append("")

        if section.depth:
            lines.append(section.depth)
            lines.append("")

        # Handle subsections
        for subsection in section.subsections:
            lines.extend(self._build_subsection(subsection, context))

        return lines

    def _build_subsection(
        self,
        section: SectionSpec,
        context: PromptContext,
    ) -> list[str]:
        """Build text for a subsection."""
        lines = [
            f"### {section.name}",
            "",
        ]

        if section.covers:
            for item in section.covers:
                lines.append(f"- {item}")
            lines.append("")

        if section.depth:
            lines.append(section.depth)
            lines.append("")

        return lines

    def _build_vendor_context(
        self,
        vendor_config: dict[str, Any],
        context: PromptContext,
    ) -> list[str]:
        """Build vendor-specific context for the prompt."""
        lines = []
        display_name = vendor_config.get("display_name", context.platform.upper())

        lines.extend(
            [
                f"TECHNOLOGY ECOSYSTEM EMPHASIS: {display_name}",
                "",
            ]
        )

        # Add key services if present
        key_services = vendor_config.get("key_services", {})
        if key_services:
            lines.append(f"KEY {display_name.upper()} SERVICES TO RESEARCH:")
            lines.append("")
            for category, services in key_services.items():
                category_name = category.replace("_", " ").title()
                lines.append(f"{category_name}:")
                for service in services:
                    lines.append(f"- {service}")
                lines.append("")

        # Add guidance for agnostic
        guidance = vendor_config.get("guidance", "")
        if guidance:
            lines.append(guidance.strip())
            lines.append("")

        # Add comparison areas for agnostic
        comparison_areas = vendor_config.get("comparison_areas", [])
        if comparison_areas:
            lines.append("Key areas to compare:")
            for area in comparison_areas:
                lines.append(f"- {area}")
            lines.append("")

        # Add research sources
        research_sources = vendor_config.get("research_sources", "")
        if research_sources:
            lines.append(f"Search for the latest announcements from {research_sources}.")
            lines.append("")

        return lines

    def _substitute_variables(self, content: str, context: PromptContext) -> str:
        """Substitute variables in the content."""
        # Standard variables
        content = content.replace("{company_name}", context.company_name)

        if context.website_url:
            content = content.replace("{website_url}", context.website_url)
        else:
            # Remove lines that only contain the placeholder
            content = re.sub(r"^.*\{website_url\}.*$\n?", "", content, flags=re.MULTILINE)

        if context.current_date:
            content = content.replace("{current_date}", context.current_date)
        else:
            content = content.replace("{current_date}", datetime.now().strftime("%B %d, %Y"))

        content = content.replace("{platform}", context.platform)
        # Also support legacy {cloud_vendor} in YAML templates
        content = content.replace("{cloud_vendor}", context.platform)

        # Custom variables
        for name, value in context.custom_vars.items():
            content = content.replace(f"{{{name}}}", value)

        return content

    def _get_substituted_variables(self, context: PromptContext) -> list[str]:
        """Get list of variables that were substituted."""
        variables = ["company_name"]
        if context.website_url:
            variables.append("website_url")
        if context.current_date:
            variables.append("current_date")
        if context.platform:
            variables.append("platform")
        variables.extend(context.custom_vars.keys())
        return variables


# Module-level singleton for convenience
_default_composer: PromptComposer | None = None


def get_composer() -> PromptComposer:
    """
    Get the default prompt composer.

    Returns a singleton instance for convenience.

    Returns:
        PromptComposer instance
    """
    global _default_composer
    if _default_composer is None:
        _default_composer = PromptComposer()
    return _default_composer
