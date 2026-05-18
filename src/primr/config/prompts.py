"""
Prompt template management with lazy loading and type-safe access.

This module provides a centralized registry for prompt templates with:
- Lazy loading from prompts.json
- Type-safe template rendering with variable validation
- Clear error messages for missing prompts or variables

Usage:
    from primr.config.prompts import generate_prompt, list_prompts

    # Generate a prompt with variables
    prompt = generate_prompt("industry", company_name="Acme Corp", company_website="acme.example")

    # List available prompts
    available = list_prompts()

    # Get template for inspection
    template = get_prompt_template("industry")
    print(template.required_vars)
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


class PromptError(Exception):
    """Raised when prompt generation fails."""


@dataclass(frozen=True)
class PromptTemplate:
    """A single prompt template with metadata."""

    name: str
    template: str
    required_vars: frozenset[str]
    description: str | None = None

    def render(self, **kwargs: Any) -> str:
        """
        Render template with provided variables.

        Raises:
            PromptError: If required variables are missing.
        """
        missing = self.required_vars - set(kwargs.keys())
        if missing:
            raise PromptError(
                f"Missing required variables for '{self.name}': {', '.join(sorted(missing))}"
            )
        return self.template.format(**kwargs)


class PromptRegistry:
    """
    Registry of prompt templates with lazy loading.

    Thread-safe singleton that loads prompts on first access.
    """

    _instance: "PromptRegistry | None" = None
    _prompts: dict[str, PromptTemplate] | None = None

    def __new__(cls) -> "PromptRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get(self, name: str) -> PromptTemplate:
        """Get a prompt template by name."""
        self._ensure_loaded()
        if name not in self._prompts:
            available = ", ".join(sorted(self._prompts.keys()))
            raise PromptError(f"Prompt '{name}' not found. Available: {available}")
        return self._prompts[name]

    def render(self, name: str, **kwargs: Any) -> str:
        """Render a prompt template with substitutions."""
        return self.get(name).render(**kwargs)

    def list_prompts(self) -> list[str]:
        """List all available prompt names."""
        self._ensure_loaded()
        return sorted(self._prompts.keys())

    def _ensure_loaded(self) -> None:
        """Load prompts if not already loaded."""
        if self._prompts is None:
            self._prompts = _load_prompts_from_file()

    def reload(self) -> None:
        """Force reload prompts from file."""
        self._prompts = _load_prompts_from_file()


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================


def get_registry() -> PromptRegistry:
    """Get the prompt registry singleton."""
    return PromptRegistry()


def generate_prompt(template_name: str, **kwargs: Any) -> str:
    """
    Generate prompt from template with substitutions.

    This is the primary interface for prompt generation.

    Args:
        template_name: Name of the prompt template
        **kwargs: Variables to substitute into the template

    Returns:
        Rendered prompt string

    Raises:
        PromptError: If template not found or variables missing
    """
    return get_registry().render(template_name, **kwargs)


def list_prompts() -> list[str]:
    """List all available prompt template names."""
    return get_registry().list_prompts()


def get_prompt_template(name: str) -> PromptTemplate:
    """Get a prompt template by name for inspection."""
    return get_registry().get(name)


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================


def _load_prompts_from_file() -> dict[str, PromptTemplate]:
    """Load prompts from prompts.json and parse into templates."""
    prompts_file = Path(__file__).parent / "prompts.json"

    if not prompts_file.exists():
        raise PromptError(f"Prompts file not found: {prompts_file}")

    with open(prompts_file, encoding="utf-8") as f:
        raw_prompts = json.load(f)

    templates = {}
    for name, template_str in raw_prompts.items():
        required_vars = _extract_template_vars(template_str)
        templates[name] = PromptTemplate(
            name=name, template=template_str, required_vars=frozenset(required_vars)
        )

    return templates


def _extract_template_vars(template: str) -> set[str]:
    """Extract variable names from a format string template."""
    return set(re.findall(r"\{(\w+)\}", template))
