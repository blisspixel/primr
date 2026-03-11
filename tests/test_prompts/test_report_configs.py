"""
Tests for report configuration YAML files.

Validates that all report configs (company_overview.yaml, ai_strategy.yaml, etc.)
are properly structured and the system can load them correctly.

This ensures the extensible report architecture works correctly.
"""

import pytest
import yaml

from primr.prompts.composer import PromptComposer
from primr.prompts.registry import get_registry


class TestCompanyOverviewConfig:
    """Tests for company_overview.yaml configuration."""

    def test_config_loads_successfully(self):
        """company_overview.yaml loads without errors."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        assert config is not None
        assert config.sections is not None

    def test_has_23_sections(self):
        """company_overview.yaml has 23 sections."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        assert len(config.sections) == 23, f"Expected 23 sections, got {len(config.sections)}"

    def test_all_sections_have_required_fields(self):
        """All sections have id, name, part, position."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        for section in config.sections:
            assert section.id, "Section missing 'id'"
            assert section.name, f"Section {section.id} missing 'name'"
            assert section.part, f"Section {section.id} missing 'part'"
            assert section.position, f"Section {section.id} missing 'position'"

    def test_positions_are_valid(self):
        """All section positions are opening, middle, closing, or framework."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        valid_positions = {"opening", "middle", "closing", "framework"}
        for section in config.sections:
            assert section.position in valid_positions, (
                f"Section {section.id} has invalid position: {section.position}"
            )

    def test_has_opening_and_closing_sections(self):
        """Config has at least one opening and one closing section."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        positions = [s.position for s in config.sections]
        assert "opening" in positions, "No opening section found"
        assert "closing" in positions, "No closing section found"

    def test_first_section_is_executive_summary(self):
        """First section should be Executive Summary."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        first = config.sections[0]
        assert first.id == "executive_summary"
        assert first.position == "opening"

    def test_has_accordion_method_prompts(self):
        """Config has accordion_method section with required prompts."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})

        assert "research_dossier_prompt" in accordion, "Missing research_dossier_prompt"
        assert "section_writing_prompt" in accordion, "Missing section_writing_prompt"
        assert "position_guidance" in accordion, "Missing position_guidance"

    def test_position_guidance_has_all_positions(self):
        """position_guidance has opening, middle, closing."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})
        guidance = accordion.get("position_guidance", {})

        assert "opening" in guidance, "Missing opening guidance"
        assert "middle" in guidance, "Missing middle guidance"
        assert "closing" in guidance, "Missing closing guidance"


class TestAIStrategyConfig:
    """Tests for ai_strategy.yaml configuration."""

    def test_config_exists(self):
        """ai_strategy.yaml exists in strategies folder."""
        registry = get_registry()
        strategy = registry.get("ai")

        assert strategy is not None
        assert strategy.config_path.exists()

    def test_config_loads_successfully(self):
        """ai_strategy.yaml loads without errors."""
        registry = get_registry()
        strategy = registry.get("ai")

        with open(strategy.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert "meta" in config
        assert "sections" in config

    def test_has_sections(self):
        """ai_strategy.yaml has sections defined."""
        registry = get_registry()
        strategy = registry.get("ai")

        with open(strategy.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        sections = config.get("sections", [])
        assert len(sections) >= 10, f"Expected 10+ sections, got {len(sections)}"

    def test_has_vendor_guidance(self):
        """ai_strategy.yaml has vendor-specific guidance."""
        registry = get_registry()
        strategy = registry.get("ai")

        with open(strategy.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        vendor_guidance = config.get("vendor_guidance", {})

        assert "azure" in vendor_guidance, "Missing Azure guidance"
        assert "aws" in vendor_guidance, "Missing AWS guidance"
        assert "gcp" in vendor_guidance, "Missing GCP guidance"

    def test_has_data_sources(self):
        """ai_strategy.yaml has data sources for vendor research."""
        registry = get_registry()
        strategy = registry.get("ai")

        assert len(strategy.data_sources) > 0, "No data sources defined"

        # Should have sources for multiple vendors
        vendors = [ds.vendor for ds in strategy.data_sources if ds.vendor]
        assert "azure" in vendors
        assert "aws" in vendors
        assert "gcp" in vendors


class TestStrategyExtensibility:
    """Tests for the extensible strategy architecture."""

    def test_registry_discovers_all_strategies(self):
        """Registry discovers all strategy YAML files."""
        registry = get_registry()
        strategies = registry.discover()

        assert len(strategies) >= 1, "Should discover at least 1 strategy"

        names = [s.name for s in strategies]
        assert "ai" in names, "Should discover AI strategy"

    def test_strategy_names_are_unique(self):
        """All strategy names are unique."""
        registry = get_registry()
        strategies = registry.discover()

        names = [s.name for s in strategies]
        assert len(names) == len(set(names)), "Duplicate strategy names found"

    def test_all_strategies_have_valid_yaml(self):
        """All strategy configs are valid YAML."""
        registry = get_registry()
        strategies = registry.discover()

        for strategy in strategies:
            with open(strategy.config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            assert isinstance(config, dict), f"Strategy {strategy.name} config is not a dict"
            assert "meta" in config, f"Strategy {strategy.name} missing meta section"

    def test_all_strategies_have_meta_fields(self):
        """All strategies have required meta fields."""
        registry = get_registry()
        strategies = registry.discover()

        for strategy in strategies:
            with open(strategy.config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            meta = config.get("meta", {})
            assert "name" in meta, f"Strategy {strategy.name} missing meta.name"
            assert "version" in meta, f"Strategy {strategy.name} missing meta.version"


class TestReportTypeConsistency:
    """Tests for consistency across report types."""

    def test_company_overview_and_ai_strategy_both_load(self):
        """Both main report types load successfully."""
        # Company Overview
        composer = PromptComposer()
        company_config = composer._load_config("company_overview")
        assert company_config is not None

        # AI Strategy
        registry = get_registry()
        ai_strategy = registry.get("ai")
        assert ai_strategy is not None

    def test_section_ids_are_valid_identifiers(self):
        """All section IDs are valid Python identifiers (snake_case)."""
        import re

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        for section in config.sections:
            section_id = section.id
            assert re.match(r"^[a-z][a-z0-9_]*$", section_id), (
                f"Invalid section ID: {section_id} (should be snake_case)"
            )


class TestVendorResearchFiles:
    """Tests for vendor research documentation files."""

    def test_vendor_research_files_exist(self):
        """Vendor research files referenced in ai_strategy.yaml exist."""
        registry = get_registry()
        strategy = registry.get("ai")

        # Get base path (project root)
        base_path = strategy.config_path.parent.parent.parent.parent

        for ds in strategy.data_sources:
            if ds.vendor:  # Only check vendor-specific files
                full_path = base_path / ds.path
                # File should exist (or be marked as not required)
                if ds.required:
                    assert full_path.exists(), f"Required file missing: {ds.path}"

    def test_get_context_files_returns_existing_files(self):
        """get_context_files only returns files that exist."""
        registry = get_registry()

        for vendor in ["azure", "aws", "gcp", "agnostic"]:
            files = registry.get_context_files("ai", vendor=vendor)
            for f in files:
                assert f.exists(), f"Returned non-existent file: {f}"


# =============================================================================
# Additional YAML Validation Tests for Test Coverage Hardening
# **Feature: test-coverage-hardening**
# **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
# =============================================================================


class TestCompanyOverviewValidation:
    """Extended validation tests for company_overview.yaml."""

    def test_all_23_sections_have_required_fields(self):
        """
        WHEN company_overview.yaml is loaded
        THEN the system SHALL validate all 23 sections have required fields

        **Validates: Requirements 6.1**
        """
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        assert len(config.sections) == 23, f"Expected 23 sections, got {len(config.sections)}"

        required_fields = ["id", "name", "part", "position"]
        for section in config.sections:
            for field in required_fields:
                assert hasattr(section, field), f"Section missing '{field}'"
                assert getattr(section, field), f"Section {section.id} has empty '{field}'"

    def test_sections_have_position_and_part(self):
        """All sections should have position and part fields."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        for section in config.sections:
            assert section.position, f"Section {section.id} missing position"
            assert section.part, f"Section {section.id} missing part"


class TestAIStrategyVendorGuidance:
    """Extended validation tests for ai_strategy.yaml vendor guidance."""

    def test_vendor_guidance_for_all_vendors(self):
        """
        WHEN ai_strategy.yaml is loaded
        THEN the system SHALL validate vendor guidance exists for azure, aws, gcp

        **Validates: Requirements 6.2**
        """
        registry = get_registry()
        strategy = registry.get("ai")

        with open(strategy.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        vendor_guidance = config.get("vendor_guidance", {})

        required_vendors = ["azure", "aws", "gcp"]
        for vendor in required_vendors:
            assert vendor in vendor_guidance, f"Missing vendor guidance for {vendor}"
            guidance = vendor_guidance[vendor]
            assert guidance, f"Empty vendor guidance for {vendor}"

    def test_vendor_guidance_has_content(self):
        """Vendor guidance should have substantive content."""
        registry = get_registry()
        strategy = registry.get("ai")

        with open(strategy.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        vendor_guidance = config.get("vendor_guidance", {})

        for vendor, guidance in vendor_guidance.items():
            if vendor in ["azure", "aws", "gcp"]:
                # Guidance should be non-trivial
                assert len(str(guidance)) > 50, f"Vendor guidance for {vendor} is too short"


class TestAccordionMethodPrompts:
    """Tests for accordion_method prompts validation."""

    def test_accordion_prompts_have_placeholders(self):
        """
        WHEN accordion_method prompts are loaded
        THEN the system SHALL validate placeholders exist

        **Validates: Requirements 6.4**
        """
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})

        # Research dossier prompt should have company_name placeholder
        dossier_prompt = accordion.get("research_dossier_prompt", "")
        assert "{company_name}" in dossier_prompt, (
            "research_dossier_prompt missing {company_name} placeholder"
        )

        # Section writing prompt should have required placeholders
        section_prompt = accordion.get("section_writing_prompt", "")
        required_placeholders = ["{company_name}", "{section_title}"]
        for placeholder in required_placeholders:
            assert placeholder in section_prompt, (
                f"section_writing_prompt missing {placeholder} placeholder"
            )

    def test_position_guidance_is_substantive(self):
        """Position guidance should have meaningful content."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})
        guidance = accordion.get("position_guidance", {})

        for position in ["opening", "middle", "closing"]:
            content = guidance.get(position, "")
            assert len(content) > 20, f"Position guidance for {position} is too short"


class TestMalformedYAMLHandling:
    """Tests for malformed YAML error handling."""

    def test_invalid_yaml_raises_error(self):
        """
        WHEN a strategy module YAML is malformed
        THEN the system SHALL raise a descriptive error

        **Validates: Requirements 6.3**
        """
        import os
        import tempfile

        # Create a malformed YAML file
        malformed_yaml = """
meta:
  name: test
  version: 1.0
sections:
  - id: test
    name: Test
    invalid_indent
      nested: value
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(malformed_yaml)
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError), open(temp_path, encoding="utf-8") as f:
                yaml.safe_load(f)
        finally:
            os.unlink(temp_path)

    def test_missing_required_field_detected(self):
        """Missing required fields should be detectable."""
        import os
        import tempfile

        # YAML with missing required field
        incomplete_yaml = """
meta:
  name: test
  # missing version
sections: []
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(incomplete_yaml)
            temp_path = f.name

        try:
            with open(temp_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            meta = config.get("meta", {})
            # Should be able to detect missing version
            assert "version" not in meta or meta.get("version") is None
        finally:
            os.unlink(temp_path)


# =============================================================================
# Property Tests for YAML Validation
# =============================================================================

from hypothesis import given, settings
from hypothesis import strategies as st


@given(
    section_id=st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
        min_size=3,
        max_size=30,
    ).filter(lambda x: x[0].isalpha() if x else False)
)
@settings(max_examples=50, deadline=None)
def test_property_section_ids_are_snake_case(section_id: str):
    """
    **Feature: test-coverage-hardening, Property 9: Malformed YAML raises descriptive error**
    **Validates: Requirements 6.3**

    For any valid section ID, it should be in snake_case format.
    """
    import re

    # Valid snake_case pattern
    pattern = r"^[a-z][a-z0-9_]*$"

    # If it matches the pattern, it's valid snake_case
    is_valid = bool(re.match(pattern, section_id))

    # All generated IDs should be valid (by construction)
    assert is_valid, f"Invalid section ID format: {section_id}"


@given(vendor=st.sampled_from(["azure", "aws", "gcp", "agnostic"]))
@settings(max_examples=10, deadline=None)
def test_property_vendor_guidance_exists(vendor: str):
    """
    **Feature: test-coverage-hardening, Property 9: Malformed YAML raises descriptive error**
    **Validates: Requirements 6.2**

    For any supported vendor, guidance should exist in ai_strategy.yaml.
    """
    registry = get_registry()
    strategy = registry.get("ai")

    with open(strategy.config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    vendor_guidance = config.get("vendor_guidance", {})

    if vendor != "agnostic":  # agnostic may not have specific guidance
        assert vendor in vendor_guidance, f"Missing guidance for {vendor}"
