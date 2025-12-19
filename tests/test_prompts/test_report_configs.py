"""
Tests for report configuration YAML files.

Validates that all report configs (company_overview.yaml, ai_strategy.yaml, etc.)
are properly structured and the system can load them correctly.

This ensures the extensible report architecture works correctly.
"""

import pytest
import yaml
from pathlib import Path

from primr.prompts.composer import PromptComposer
from primr.prompts.registry import StrategyModuleRegistry, get_registry


class TestCompanyOverviewConfig:
    """Tests for company_overview.yaml configuration."""

    def test_config_loads_successfully(self):
        """company_overview.yaml loads without errors."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")
        
        assert config is not None
        assert config.sections is not None

    def test_has_20_sections(self):
        """company_overview.yaml has 20 sections."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")
        
        assert len(config.sections) == 20, f"Expected 20 sections, got {len(config.sections)}"

    def test_all_sections_have_required_fields(self):
        """All sections have id, name, part, position."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")
        
        for section in config.sections:
            assert section.id, f"Section missing 'id'"
            assert section.name, f"Section {section.id} missing 'name'"
            assert section.part, f"Section {section.id} missing 'part'"
            assert section.position, f"Section {section.id} missing 'position'"

    def test_positions_are_valid(self):
        """All section positions are opening, middle, or closing."""
        composer = PromptComposer()
        config = composer._load_config("company_overview")
        
        valid_positions = {"opening", "middle", "closing"}
        for section in config.sections:
            assert section.position in valid_positions, \
                f"Section {section.id} has invalid position: {section.position}"

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
            assert re.match(r'^[a-z][a-z0-9_]*$', section_id), \
                f"Invalid section ID: {section_id} (should be snake_case)"


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
