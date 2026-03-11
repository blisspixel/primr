"""
Tests for the PromptComposer.

Includes property-based tests using Hypothesis for comprehensive validation.
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from primr.prompts.composer import PromptComposer, get_composer
from primr.prompts.exceptions import PromptConfigNotFoundError
from primr.prompts.schema import ComposedPrompt, PromptContext


class TestPromptComposer:
    """Tests for PromptComposer class."""

    def test_compose_company_overview(self):
        """Should compose company_overview prompt."""
        composer = PromptComposer()
        context = PromptContext(
            company_name="Acme Corp",
            website_url="https://acme.example",
        )
        result = composer.compose("company_overview", context)

        assert isinstance(result, ComposedPrompt)
        assert len(result.content) > 0
        assert "Acme Corp" in result.content
        assert result.section_count > 0

    def test_compose_strategic_layer(self):
        """Should compose strategic_layer prompt."""
        composer = PromptComposer()
        context = PromptContext(
            company_name="Acme Corp",
            website_url="https://acme.com",
        )
        result = composer.compose("strategic_layer", context)

        assert isinstance(result, ComposedPrompt)
        assert len(result.content) > 0
        assert "Acme Corp" in result.content

    def test_compose_with_stage1_context(self):
        """Should include hierarchy of truth when stage1 context is available."""
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            has_stage1_context=True,
        )
        result = composer.compose("strategic_layer", context)

        assert "HIERARCHY OF TRUTH" in result.content
        assert "File Search Store" in result.content

    def test_compose_without_stage1_context(self):
        """Should not include hierarchy of truth when no stage1 context."""
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            has_stage1_context=False,
        )
        result = composer.compose("company_overview", context)

        # Should still be a valid prompt
        assert len(result.content) > 0
        assert "Test Corp" in result.content

    def test_variable_substitution(self):
        """Should substitute all variables."""
        composer = PromptComposer()
        context = PromptContext(
            company_name="MyCompany",
            website_url="https://mycompany.com",
            cloud_vendor="azure",
            current_date="January 1, 2025",
        )
        result = composer.compose("company_overview", context)

        assert "MyCompany" in result.content
        assert "https://mycompany.com" in result.content
        assert "January 1, 2025" in result.content

    def test_list_prompts(self):
        """Should list available prompts."""
        composer = PromptComposer()
        prompts = composer.list_prompts()

        assert isinstance(prompts, list)
        assert "company_overview" in prompts
        assert "strategic_layer" in prompts

    def test_missing_prompt_raises(self):
        """Should raise PromptConfigNotFoundError for missing prompt."""
        composer = PromptComposer()
        context = PromptContext(company_name="Test")

        with pytest.raises(PromptConfigNotFoundError):
            composer.compose("nonexistent_prompt", context)

    def test_includes_epistemic_rules(self):
        """Should include epistemic rules in output."""
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        result = composer.compose("company_overview", context)

        assert "EPISTEMIC RULES" in result.content
        # Check for specific rules
        assert "fact" in result.content.lower() or "inference" in result.content.lower()

    def test_includes_formatting_rules(self):
        """Should include formatting rules in output."""
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        result = composer.compose("company_overview", context)

        assert "FORMATTING" in result.content

    def test_tracks_source_files(self):
        """Should track source files used."""
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        result = composer.compose("company_overview", context)

        assert len(result.source_files) > 0
        assert "company_overview.yaml" in result.source_files

    def test_tracks_substituted_variables(self):
        """Should track which variables were substituted."""
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test",
            website_url="https://test.com",
        )
        result = composer.compose("company_overview", context)

        assert "company_name" in result.variables_substituted
        assert "website_url" in result.variables_substituted


class TestPromptComposerValidation:
    """Tests for config validation."""

    def test_validate_valid_config(self):
        """Should return empty list for valid config."""
        composer = PromptComposer()
        config_path = composer.prompts_dir / "company_overview.yaml"
        errors = composer.validate_config(config_path)

        assert errors == []

    def test_validate_missing_file(self):
        """Should return error for missing file."""
        composer = PromptComposer()
        errors = composer.validate_config(Path("/nonexistent/file.yaml"))

        assert len(errors) > 0
        assert "not found" in errors[0].lower()

    def test_validate_invalid_yaml(self):
        """Should return error for invalid YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()

            composer = PromptComposer()
            errors = composer.validate_config(Path(f.name))

            assert len(errors) > 0


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_composer_singleton(self):
        """get_composer should return singleton."""
        composer1 = get_composer()
        composer2 = get_composer()
        assert composer1 is composer2


# =============================================================================
# Property-Based Tests
# =============================================================================


class TestVariableSubstitutionProperties:
    """
    Property-based tests for variable substitution.

    **Feature: deep-research-prompt-architecture, Property 4: Variable Substitution Completeness**
    **Validates: Requirements 9.1, 9.2, 9.3, 9.4**
    """

    @given(
        company_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            min_size=1,
            max_size=30,
        ).filter(lambda x: x.strip() and "{" not in x and "}" not in x),
    )
    @settings(max_examples=50)
    def test_company_name_always_substituted(self, company_name: str):
        """
        Property: Company name should always appear in the output.

        **Feature: deep-research-prompt-architecture, Property 4: Variable Substitution Completeness**
        **Validates: Requirements 9.1, 9.2, 9.3, 9.4**
        """
        company_name = company_name.strip()
        assume(len(company_name) > 0)

        composer = PromptComposer()
        context = PromptContext(
            company_name=company_name,
            website_url="https://example.com",
        )
        result = composer.compose("company_overview", context)

        # Property: Company name should appear in output
        assert company_name in result.content

    @given(
        company_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
    )
    @settings(max_examples=30)
    def test_no_raw_placeholders_in_output(self, company_name: str):
        """
        Property: No raw placeholders should remain in output.

        **Feature: deep-research-prompt-architecture, Property 5: Missing Variable Graceful Handling**
        **Validates: Requirements 9.5**
        """
        assume(company_name.strip())
        assume("{" not in company_name and "}" not in company_name)

        composer = PromptComposer()
        context = PromptContext(
            company_name=company_name.strip(),
            # Deliberately omit website_url
        )
        result = composer.compose("company_overview", context)

        # Property: No raw {variable} placeholders should remain
        # (except in documentation/examples)
        assert "{company_name}" not in result.content
        assert "{website_url}" not in result.content


class TestContextAwareProperties:
    """
    Property-based tests for context-aware prompt building.

    **Feature: deep-research-prompt-architecture, Property 13: Context-Aware Prompt Building**
    **Validates: Requirements 10.1, 10.2, 10.4**
    """

    def test_stage1_context_includes_hierarchy(self):
        """
        Property: When has_stage1_context=True, output includes hierarchy of truth.

        **Feature: deep-research-prompt-architecture, Property 13: Context-Aware Prompt Building**
        **Validates: Requirements 10.1, 10.2, 10.4**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            has_stage1_context=True,
        )
        result = composer.compose("strategic_layer", context)

        # Property: Should include hierarchy of truth instructions
        assert "HIERARCHY OF TRUTH" in result.content or "File Search Store" in result.content

    def test_no_stage1_context_still_valid(self):
        """
        Property: When has_stage1_context=False, output is still complete.

        **Feature: deep-research-prompt-architecture, Property 14: Standalone Prompt Completeness**
        **Validates: Requirements 10.5**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            has_stage1_context=False,
        )
        result = composer.compose("company_overview", context)

        # Property: Should still be a valid, complete prompt
        assert len(result.content) > 1000  # Substantial content
        assert "Test Corp" in result.content
        assert result.section_count > 0


class TestSectionCompletenessProperties:
    """
    Property-based tests for section completeness.

    **Feature: deep-research-prompt-architecture, Property 6: Section Completeness**
    **Validates: Requirements 3.1, 3.5**
    """

    def test_all_sections_present(self):
        """
        Property: All sections from config should appear in output.

        **Feature: deep-research-prompt-architecture, Property 6: Section Completeness**
        **Validates: Requirements 3.1, 3.5**
        """
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        result = composer.compose("company_overview", context)

        # Load the config to get expected sections
        config = composer._load_config("company_overview")

        # Property: All section names should appear in output
        for section in config.sections:
            assert section.name in result.content, f"Missing section: {section.name}"

    def test_section_count_matches(self):
        """
        Property: Section count in result should match config.

        **Feature: deep-research-prompt-architecture, Property 6: Section Completeness**
        **Validates: Requirements 3.1, 3.5**
        """
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        result = composer.compose("company_overview", context)

        # Load the config
        config = composer._load_config("company_overview")

        # Property: Section count should match
        assert result.section_count == len(config.sections)


class TestSectionSpecRenderingProperties:
    """
    Property-based tests for section spec rendering.

    **Feature: deep-research-prompt-architecture, Property 7: Section Spec Rendering**
    **Validates: Requirements 6.2, 6.3, 6.4**
    """

    def test_section_purpose_included(self):
        """
        Property: Section purpose should be included in output.

        **Feature: deep-research-prompt-architecture, Property 7: Section Spec Rendering**
        **Validates: Requirements 6.2, 6.3, 6.4**
        """
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        result = composer.compose("company_overview", context)

        # Load the config
        config = composer._load_config("company_overview")

        # Property: At least some section purposes should appear
        purposes_found = 0
        for section in config.sections:
            if section.purpose and section.purpose in result.content:
                purposes_found += 1

        assert purposes_found > 0, "No section purposes found in output"


class TestVendorSpecificContentProperties:
    """
    Property-based tests for vendor-specific content.

    **Feature: deep-research-prompt-architecture, Property 15: Vendor-Specific Content**
    **Validates: Requirements 5.2**
    """

    @given(
        vendor=st.sampled_from(["azure", "aws", "gcp", "agnostic"]),
    )
    @settings(max_examples=20)
    def test_vendor_specific_content_included(self, vendor: str):
        """
        Property: For any AI strategy prompt with a specific cloud_vendor,
        the output SHALL contain vendor-specific guidance.

        **Feature: deep-research-prompt-architecture, Property 15: Vendor-Specific Content**
        **Validates: Requirements 5.2**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            cloud_vendor=vendor,
            has_stage1_context=True,
        )
        result = composer.compose_strategy("ai_strategy", context)

        # Property: Vendor-specific content should be present
        vendor_indicators = {
            "azure": ["Azure", "Microsoft"],
            "aws": ["AWS", "Amazon"],
            "gcp": ["GCP", "Google Cloud", "Vertex"],
            "agnostic": ["agnostic", "compare", "multi-cloud"],
        }

        indicators = vendor_indicators.get(vendor, [])
        found = any(indicator in result.content for indicator in indicators)
        assert found, f"No vendor-specific content found for {vendor}"

    def test_azure_includes_azure_services(self):
        """
        Property: Azure vendor should include Azure-specific services.

        **Feature: deep-research-prompt-architecture, Property 15: Vendor-Specific Content**
        **Validates: Requirements 5.2**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            cloud_vendor="azure",
            has_stage1_context=True,
        )
        result = composer.compose_strategy("ai_strategy", context)

        # Should include Azure-specific services
        assert "Azure" in result.content
        assert "Microsoft" in result.content or "Copilot" in result.content

    def test_aws_includes_aws_services(self):
        """
        Property: AWS vendor should include AWS-specific services.

        **Feature: deep-research-prompt-architecture, Property 15: Vendor-Specific Content**
        **Validates: Requirements 5.2**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            cloud_vendor="aws",
            has_stage1_context=True,
        )
        result = composer.compose_strategy("ai_strategy", context)

        # Should include AWS-specific services
        assert "AWS" in result.content or "Amazon" in result.content
        assert "Bedrock" in result.content or "SageMaker" in result.content

    def test_gcp_includes_gcp_services(self):
        """
        Property: GCP vendor should include GCP-specific services.

        **Feature: deep-research-prompt-architecture, Property 15: Vendor-Specific Content**
        **Validates: Requirements 5.2**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            cloud_vendor="gcp",
            has_stage1_context=True,
        )
        result = composer.compose_strategy("ai_strategy", context)

        # Should include GCP-specific services
        assert "Google" in result.content or "GCP" in result.content
        assert "Vertex" in result.content or "Gemini" in result.content


class TestCustomStrategySharedComponentsProperties:
    """
    Property-based tests for custom strategy shared components.

    **Feature: deep-research-prompt-architecture, Property 11: Custom Strategy Shared Components**
    **Validates: Requirements 11.3**
    """

    @given(
        strategy=st.sampled_from(["ai_strategy", "cloud_migration", "data_strategy"]),
    )
    @settings(max_examples=15)
    def test_all_strategies_include_shared_components(self, strategy: str):
        """
        Property: For any custom strategy module, the composed prompt SHALL include
        the same shared components as built-in modules.

        **Feature: deep-research-prompt-architecture, Property 11: Custom Strategy Shared Components**
        **Validates: Requirements 11.3**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            cloud_vendor="agnostic",
            has_stage1_context=True,
        )

        try:
            result = composer.compose_strategy(strategy, context)
        except FileNotFoundError:
            # Strategy may not exist yet, skip
            pytest.skip(f"Strategy {strategy} not found")
            return

        # Property: All strategies should include epistemic rules
        assert "EPISTEMIC RULES" in result.content, f"Strategy {strategy} missing epistemic rules"

        # Property: All strategies should include formatting rules
        assert "FORMATTING" in result.content, f"Strategy {strategy} missing formatting rules"

    def test_cloud_migration_includes_shared_components(self):
        """
        Property: Cloud migration strategy should include shared components.

        **Feature: deep-research-prompt-architecture, Property 11: Custom Strategy Shared Components**
        **Validates: Requirements 11.3**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            has_stage1_context=True,
        )
        result = composer.compose_strategy("cloud_migration", context)

        # Should include shared epistemic rules
        assert "EPISTEMIC RULES" in result.content
        # Should include shared formatting rules
        assert "FORMATTING" in result.content

    def test_data_strategy_includes_shared_components(self):
        """
        Property: Data strategy should include shared components.

        **Feature: deep-research-prompt-architecture, Property 11: Custom Strategy Shared Components**
        **Validates: Requirements 11.3**
        """
        composer = PromptComposer()
        context = PromptContext(
            company_name="Test Corp",
            has_stage1_context=True,
        )
        result = composer.compose_strategy("data_strategy", context)

        # Should include shared epistemic rules
        assert "EPISTEMIC RULES" in result.content
        # Should include shared formatting rules
        assert "FORMATTING" in result.content

    def test_strategies_discovered(self):
        """
        Property: All strategy YAML files should be discoverable.

        **Feature: deep-research-prompt-architecture, Property 9: Strategy Module Discovery**
        **Validates: Requirements 4.5, 11.1, 11.4**
        """
        composer = PromptComposer()
        strategies = composer.list_strategies()

        # Should discover all strategies
        assert len(strategies) >= 3  # ai, cloud_migration, data

        # Check specific strategies exist
        # Note: list_strategies() strips _strategy suffix, so:
        # - ai_strategy.yaml -> "ai"
        # - cloud_migration.yaml -> "cloud_migration"
        # - data_strategy.yaml -> "data"
        strategy_names = set(strategies)
        assert "ai" in strategy_names or "ai_strategy" in strategy_names
        assert "cloud_migration" in strategy_names
        assert "data" in strategy_names or "data_strategy" in strategy_names
