"""
Unit tests for the prompts module.

Tests prompt loading, variable extraction, and error handling.
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestPromptTemplate:
    """Tests for PromptTemplate dataclass."""

    def test_render_with_all_variables(self):
        """Template renders correctly when all variables provided."""
        from primr.config.prompts import PromptTemplate

        template = PromptTemplate(
            name="test",
            template="Hello {name}, welcome to {place}!",
            required_vars=frozenset({"name", "place"})
        )

        result = template.render(name="Alice", place="Wonderland")
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_render_raises_on_missing_variable(self):
        """Template raises PromptError when required variable is missing."""
        from primr.config.prompts import PromptTemplate, PromptError

        template = PromptTemplate(
            name="test",
            template="Hello {name}, welcome to {place}!",
            required_vars=frozenset({"name", "place"})
        )

        with pytest.raises(PromptError) as exc_info:
            template.render(name="Alice")

        assert "place" in str(exc_info.value)
        assert "test" in str(exc_info.value)

    def test_render_ignores_extra_variables(self):
        """Template ignores extra variables not in template."""
        from primr.config.prompts import PromptTemplate

        template = PromptTemplate(
            name="test",
            template="Hello {name}!",
            required_vars=frozenset({"name"})
        )

        result = template.render(name="Alice", extra="ignored")
        assert result == "Hello Alice!"

    def test_template_is_frozen(self):
        """PromptTemplate is immutable (frozen dataclass)."""
        from primr.config.prompts import PromptTemplate

        template = PromptTemplate(
            name="test",
            template="Hello {name}!",
            required_vars=frozenset({"name"})
        )

        with pytest.raises(AttributeError):
            template.name = "changed"


class TestPromptRegistry:
    """Tests for PromptRegistry singleton."""

    def test_registry_is_singleton(self):
        """PromptRegistry returns same instance."""
        from primr.config.prompts import PromptRegistry

        registry1 = PromptRegistry()
        registry2 = PromptRegistry()

        assert registry1 is registry2

    def test_get_returns_template(self):
        """get() returns a PromptTemplate for valid name."""
        from primr.config.prompts import get_registry, PromptTemplate

        registry = get_registry()
        template = registry.get("industry")

        assert isinstance(template, PromptTemplate)
        assert template.name == "industry"

    def test_get_raises_on_unknown_prompt(self):
        """get() raises PromptError for unknown prompt name."""
        from primr.config.prompts import get_registry, PromptError

        registry = get_registry()

        with pytest.raises(PromptError) as exc_info:
            registry.get("nonexistent_prompt_xyz")

        assert "nonexistent_prompt_xyz" in str(exc_info.value)
        assert "Available" in str(exc_info.value)

    def test_list_prompts_returns_sorted_names(self):
        """list_prompts() returns sorted list of prompt names."""
        from primr.config.prompts import get_registry

        registry = get_registry()
        prompts = registry.list_prompts()

        assert isinstance(prompts, list)
        assert len(prompts) > 0
        assert prompts == sorted(prompts)

    def test_render_generates_prompt(self):
        """render() generates prompt with substitutions."""
        from primr.config.prompts import get_registry

        registry = get_registry()
        result = registry.render(
            "industry",
            company_name="Tesla",
            company_website="tesla.com",
            scraped_insights="Electric vehicles"
        )

        assert "Tesla" in result
        assert "tesla.com" in result


class TestPublicInterface:
    """Tests for public interface functions."""

    def test_generate_prompt_works(self):
        """generate_prompt() generates prompt correctly."""
        from primr.config.prompts import generate_prompt

        result = generate_prompt(
            "company_name",
            company_name="Tesla",
            company_website="tesla.com"
        )

        assert "Tesla" in result
        assert "tesla.com" in result

    def test_generate_prompt_raises_on_missing_vars(self):
        """generate_prompt() raises PromptError on missing variables."""
        from primr.config.prompts import generate_prompt, PromptError

        with pytest.raises(PromptError):
            generate_prompt("industry")  # Missing required vars

    def test_list_prompts_returns_all_prompts(self):
        """list_prompts() returns all available prompts."""
        from primr.config.prompts import list_prompts

        prompts = list_prompts()

        # Should include known prompts from prompts.json
        assert "industry" in prompts
        assert "company_name" in prompts
        assert "value_theory" in prompts

    def test_get_prompt_template_returns_template(self):
        """get_prompt_template() returns template for inspection."""
        from primr.config.prompts import get_prompt_template, PromptTemplate

        template = get_prompt_template("industry")

        assert isinstance(template, PromptTemplate)
        assert "company_name" in template.required_vars
        assert "company_website" in template.required_vars


class TestVariableExtraction:
    """Tests for variable extraction from templates."""

    def test_extract_simple_variables(self):
        """Extracts simple {var} patterns."""
        from primr.config.prompts import _extract_template_vars

        result = _extract_template_vars("Hello {name}, welcome to {place}!")

        assert result == {"name", "place"}

    def test_extract_no_variables(self):
        """Returns empty set for template with no variables."""
        from primr.config.prompts import _extract_template_vars

        result = _extract_template_vars("Hello world!")

        assert result == set()

    def test_extract_duplicate_variables(self):
        """Handles duplicate variables correctly."""
        from primr.config.prompts import _extract_template_vars

        result = _extract_template_vars("{name} said hello to {name}")

        assert result == {"name"}

    def test_extract_underscore_variables(self):
        """Extracts variables with underscores."""
        from primr.config.prompts import _extract_template_vars

        result = _extract_template_vars("{company_name} at {company_website}")

        assert result == {"company_name", "company_website"}


class TestPromptsJsonLoading:
    """Tests for loading prompts from prompts.json."""

    def test_prompts_json_loads_successfully(self):
        """prompts.json loads without errors."""
        from primr.config.prompts import get_registry

        registry = get_registry()
        prompts = registry.list_prompts()

        # Should have loaded prompts
        assert len(prompts) > 0

    def test_all_prompts_have_required_vars(self):
        """All loaded prompts have required_vars extracted."""
        from primr.config.prompts import get_registry

        registry = get_registry()

        for name in registry.list_prompts():
            template = registry.get(name)
            # required_vars should be a frozenset
            assert isinstance(template.required_vars, frozenset)

    def test_industry_prompt_has_expected_vars(self):
        """Industry prompt has expected variables."""
        from primr.config.prompts import get_prompt_template

        template = get_prompt_template("industry")

        assert "company_name" in template.required_vars
        assert "company_website" in template.required_vars
        assert "scraped_insights" in template.required_vars
