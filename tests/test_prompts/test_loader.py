"""
Tests for the prompt configuration loader.
"""

import pytest

from primr.prompts import (
    load_prompt_config,
    build_company_overview_prompt,
    build_ai_strategy_prompt,
    get_available_prompts,
    PromptConfigNotFoundError,
)
from primr.prompts.loader import PromptConfig  # Use the loader's PromptConfig
from primr.prompts.composer import PromptComposer


class TestGetAvailablePrompts:
    """Tests for get_available_prompts function."""

    def test_returns_list(self):
        """Should return a list of prompt names."""
        prompts = get_available_prompts()
        assert isinstance(prompts, list)

    def test_includes_company_overview(self):
        """Should include company_overview prompt."""
        prompts = get_available_prompts()
        assert "company_overview" in prompts

    def test_includes_strategic_layer(self):
        """Should include strategic_layer prompt."""
        prompts = get_available_prompts()
        assert "strategic_layer" in prompts

    def test_ai_strategy_in_strategies_dir(self):
        """AI strategy should be in strategies directory."""
        composer = PromptComposer()
        strategies = composer.list_strategies()
        # list_strategies() strips _strategy suffix, so "ai_strategy.yaml" becomes "ai"
        assert "ai" in strategies or "ai_strategy" in strategies


class TestLoadPromptConfig:
    """Tests for load_prompt_config function."""

    def test_load_company_overview(self):
        """Should load company_overview config."""
        config = load_prompt_config("company_overview")
        assert isinstance(config, PromptConfig)
        assert config.name == "Strategic Company Overview"

    def test_load_strategic_layer(self):
        """Should load strategic_layer config."""
        config = load_prompt_config("strategic_layer")
        assert isinstance(config, PromptConfig)

    def test_config_has_version(self):
        """Config should have version."""
        config = load_prompt_config("company_overview")
        # Version may be 1.0.0 or 1.1.0 depending on updates
        assert config.version in ["1.0.0", "1.1.0"]

    def test_config_has_sections(self):
        """Config should have sections."""
        config = load_prompt_config("company_overview")
        assert len(config.sections) > 0

    def test_config_has_document_purpose(self):
        """Config should have document purpose."""
        config = load_prompt_config("company_overview")
        assert config.document_purpose
        assert "INTERNAL PREP" in config.document_purpose

    def test_config_has_epistemic_rules(self):
        """Config should have epistemic rules."""
        config = load_prompt_config("company_overview")
        assert config.epistemic_rules
        assert len(config.epistemic_rules) > 0

    def test_nonexistent_config_raises(self):
        """Should raise PromptConfigNotFoundError for nonexistent config."""
        with pytest.raises(PromptConfigNotFoundError):
            load_prompt_config("nonexistent_prompt")


class TestCompanyOverviewSections:
    """Tests for company overview section structure."""

    def test_has_executive_summary(self):
        """Should have executive summary section."""
        config = load_prompt_config("company_overview")
        section_ids = [s.id for s in config.sections]
        assert "executive_summary" in section_ids

    def test_has_products_services(self):
        """Should have products and services section."""
        config = load_prompt_config("company_overview")
        section_ids = [s.id for s in config.sections]
        assert "products_services" in section_ids

    def test_has_swot_analysis(self):
        """Should have SWOT analysis section."""
        config = load_prompt_config("company_overview")
        section_ids = [s.id for s in config.sections]
        assert "swot_analysis" in section_ids

    def test_has_discovery_questions(self):
        """Should have discovery questions section."""
        config = load_prompt_config("company_overview")
        section_ids = [s.id for s in config.sections]
        assert "discovery_questions" in section_ids

    def test_sections_have_parts(self):
        """All sections should have part numbers."""
        config = load_prompt_config("company_overview")
        for section in config.sections:
            assert section.part > 0


class TestAIStrategySections:
    """Tests for AI strategy section structure (loaded from strategies/)."""

    @pytest.fixture
    def ai_strategy_config(self):
        """Load AI strategy config from strategies directory."""
        from pathlib import Path
        import yaml
        
        strategies_dir = Path(__file__).parent.parent.parent / "src" / "primr" / "prompts" / "strategies"
        config_path = strategies_dir / "ai_strategy.yaml"
        
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_has_strategic_thesis(self, ai_strategy_config):
        """Should have strategic thesis section."""
        section_ids = [s.get("id") for s in ai_strategy_config.get("sections", [])]
        assert "strategic_thesis" in section_ids

    def test_has_quick_wins(self, ai_strategy_config):
        """Should have quick wins section."""
        section_ids = [s.get("id") for s in ai_strategy_config.get("sections", [])]
        assert "quick_wins" in section_ids

    def test_has_bigger_bets(self, ai_strategy_config):
        """Should have bigger bets section."""
        section_ids = [s.get("id") for s in ai_strategy_config.get("sections", [])]
        assert "bigger_bets" in section_ids

    def test_has_board_summary(self, ai_strategy_config):
        """Should have board summary section."""
        section_ids = [s.get("id") for s in ai_strategy_config.get("sections", [])]
        assert "board_summary" in section_ids

    def test_has_vendor_guidance(self, ai_strategy_config):
        """Should have vendor guidance in config."""
        assert "vendor_guidance" in ai_strategy_config
        assert "azure" in ai_strategy_config["vendor_guidance"]
        assert "aws" in ai_strategy_config["vendor_guidance"]
        assert "gcp" in ai_strategy_config["vendor_guidance"]

    def test_has_data_sources(self, ai_strategy_config):
        """Should have data sources for vendor research files."""
        assert "data_sources" in ai_strategy_config
        data_sources = ai_strategy_config["data_sources"]
        assert len(data_sources) >= 4  # azure, aws, gcp, agnostic
        
        # Check vendor-specific sources exist
        vendors = [ds.get("vendor") for ds in data_sources]
        assert "azure" in vendors
        assert "aws" in vendors
        assert "gcp" in vendors
        assert "agnostic" in vendors


class TestBuildCompanyOverviewPrompt:
    """Tests for build_company_overview_prompt function."""

    def test_includes_company_name(self):
        """Prompt should include company name."""
        prompt = build_company_overview_prompt("Acme Corp")
        assert "Acme Corp" in prompt

    def test_includes_document_purpose(self):
        """Prompt should include document purpose."""
        prompt = build_company_overview_prompt("Acme Corp")
        assert "INTERNAL PREP" in prompt

    def test_includes_sections(self):
        """Prompt should include section headers."""
        prompt = build_company_overview_prompt("Acme Corp")
        assert "## Executive Summary" in prompt
        assert "## Products and Services" in prompt
        assert "## SWOT Analysis" in prompt

    def test_includes_website_url(self):
        """Prompt should include website URL when provided."""
        prompt = build_company_overview_prompt(
            "Acme Corp",
            website_url="https://acme.com"
        )
        assert "https://acme.com" in prompt
        assert "Priority Source" in prompt

    def test_includes_epistemic_rules(self):
        """Prompt should include epistemic rules."""
        prompt = build_company_overview_prompt("Acme Corp")
        assert "EPISTEMIC RULES" in prompt

    def test_includes_formatting_rules(self):
        """Prompt should include formatting rules."""
        prompt = build_company_overview_prompt("Acme Corp")
        assert "FORMATTING" in prompt


class TestBuildAIStrategyPrompt:
    """Tests for build_ai_strategy_prompt function."""

    def test_includes_company_name(self):
        """Prompt should include company name."""
        prompt = build_ai_strategy_prompt("Acme Corp")
        assert "Acme Corp" in prompt

    def test_includes_azure_services(self):
        """Azure prompt should include Azure services."""
        prompt = build_ai_strategy_prompt("Acme Corp", cloud_vendor="azure")
        assert "Azure" in prompt
        assert "Microsoft 365 Copilot" in prompt

    def test_includes_aws_services(self):
        """AWS prompt should include AWS services."""
        prompt = build_ai_strategy_prompt("Acme Corp", cloud_vendor="aws")
        assert "AWS" in prompt
        assert "Amazon Bedrock" in prompt

    def test_includes_gcp_services(self):
        """GCP prompt should include GCP services."""
        prompt = build_ai_strategy_prompt("Acme Corp", cloud_vendor="gcp")
        assert "GCP" in prompt or "Google Cloud" in prompt
        assert "Vertex AI" in prompt

    def test_includes_strategic_sections(self):
        """Prompt should include strategic sections."""
        prompt = build_ai_strategy_prompt("Acme Corp")
        assert "## AI Strategic Thesis" in prompt
        assert "## Five Quick Wins" in prompt
        assert "## Five Bigger Bets" in prompt

    def test_includes_confidence_labeling(self):
        """Prompt should include confidence labeling rule."""
        prompt = build_ai_strategy_prompt("Acme Corp")
        # Confidence labeling may be in epistemic rules section
        assert "Low-regret" in prompt or "proven pattern" in prompt or "confidence" in prompt.lower()

    def test_includes_epistemic_rules(self):
        """Prompt should include epistemic rules."""
        prompt = build_ai_strategy_prompt("Acme Corp")
        assert "EPISTEMIC RULES" in prompt


class TestPromptLength:
    """Tests for prompt length and completeness."""

    def test_company_overview_substantial(self):
        """Company overview prompt should be substantial."""
        prompt = build_company_overview_prompt("Acme Corp")
        # Should be at least 8000 chars for a comprehensive prompt
        assert len(prompt) > 8000

    def test_ai_strategy_substantial(self):
        """AI strategy prompt should be substantial."""
        prompt = build_ai_strategy_prompt("Acme Corp")
        # Should be at least 10000 chars for a comprehensive prompt
        assert len(prompt) > 10000


class TestMalformedYAMLHandling:
    """Property tests for malformed YAML error handling (Property 17)."""

    def test_nonexistent_config_raises_not_found_error(self):
        """Should raise PromptConfigNotFoundError for nonexistent config."""
        from primr.prompts.exceptions import PromptConfigNotFoundError
        
        with pytest.raises(PromptConfigNotFoundError) as exc_info:
            load_prompt_config("nonexistent_prompt_xyz")
        
        # Should include helpful information
        assert "nonexistent_prompt_xyz" in str(exc_info.value)
        assert exc_info.value.prompt_name == "nonexistent_prompt_xyz"
        assert len(exc_info.value.available_prompts) > 0

    def test_malformed_yaml_raises_validation_error(self, tmp_path):
        """Should raise PromptConfigValidationError for malformed YAML."""
        from primr.prompts.exceptions import PromptConfigValidationError
        from primr.prompts.composer import PromptComposer
        
        # Create a malformed YAML file
        malformed_yaml = tmp_path / "malformed.yaml"
        malformed_yaml.write_text("invalid: yaml: content: [unclosed")
        
        composer = PromptComposer(prompts_dir=tmp_path)
        
        with pytest.raises(PromptConfigValidationError) as exc_info:
            composer._load_config_from_path(malformed_yaml)
        
        assert "malformed.yaml" in str(exc_info.value)
        assert len(exc_info.value.errors) > 0

    def test_empty_yaml_raises_validation_error(self, tmp_path):
        """Should raise PromptConfigValidationError for empty YAML."""
        from primr.prompts.exceptions import PromptConfigValidationError
        from primr.prompts.composer import PromptComposer
        
        # Create an empty YAML file
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")
        
        composer = PromptComposer(prompts_dir=tmp_path)
        
        with pytest.raises(PromptConfigValidationError) as exc_info:
            composer._load_config_from_path(empty_yaml)
        
        assert "empty.yaml" in str(exc_info.value)
        assert "Empty" in str(exc_info.value)

    def test_strategy_not_found_error(self):
        """Should raise PromptConfigNotFoundError for nonexistent strategy."""
        from primr.prompts.exceptions import PromptConfigNotFoundError
        from primr.prompts.composer import PromptComposer
        from primr.prompts.schema import PromptContext
        
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp")
        
        with pytest.raises(PromptConfigNotFoundError) as exc_info:
            composer.compose_strategy("nonexistent_strategy_xyz", context)
        
        assert "nonexistent_strategy_xyz" in str(exc_info.value)
        # Should list available strategies
        assert len(exc_info.value.available_prompts) > 0

    def test_exception_inheritance(self):
        """All prompt exceptions should inherit from PromptConfigError."""
        from primr.prompts.exceptions import (
            PromptConfigError,
            PromptConfigNotFoundError,
            PromptConfigValidationError,
            StrategyModuleNotFoundError,
            DataSourceNotFoundError,
        )
        
        assert issubclass(PromptConfigNotFoundError, PromptConfigError)
        assert issubclass(PromptConfigValidationError, PromptConfigError)
        assert issubclass(StrategyModuleNotFoundError, PromptConfigError)
        assert issubclass(DataSourceNotFoundError, PromptConfigError)


class TestYAMLLoadingRoundTrip:
    """
    Property tests for YAML loading round-trip consistency.
    
    **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
    **Validates: Requirements 1.1**
    
    These tests verify that:
    1. Both build_company_overview_prompt() and ConsultingPromptBuilder produce identical output
    2. The PromptComposer-based implementation maintains backward compatibility
    3. All prompt building paths produce valid, complete prompts
    4. Edge cases are handled correctly
    """

    # =========================================================================
    # EXACT EQUIVALENCE TESTS - These paths MUST produce identical output
    # =========================================================================

    def test_loader_and_builder_produce_semantically_equivalent_output(self):
        """
        Property: build_company_overview_prompt() and ConsultingPromptBuilder.build_comprehensive_prompt()
        produce semantically equivalent output (both delegate to PromptComposer).
        
        Note: Minor differences in date formatting are acceptable since loader uses "%B %Y"
        while builder uses the composer's default "%B %d, %Y" format.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.ai.deep_research import ConsultingPromptBuilder
        
        company_name = "Acme Corp"
        website_url = "https://acme.com"
        
        # Build using loader function
        loader_prompt = build_company_overview_prompt(company_name, website_url=website_url)
        
        # Build using ConsultingPromptBuilder
        builder = ConsultingPromptBuilder()
        builder_prompt = builder.build_comprehensive_prompt(company_name, website_url=website_url)
        
        # Both should contain all the same structural elements
        assert "Acme Corp" in loader_prompt
        assert "Acme Corp" in builder_prompt
        assert "https://acme.com" in loader_prompt
        assert "https://acme.com" in builder_prompt
        
        # Both should have all required sections
        assert "## Executive Summary" in loader_prompt
        assert "## Executive Summary" in builder_prompt
        assert "EPISTEMIC RULES" in loader_prompt
        assert "EPISTEMIC RULES" in builder_prompt
        
        # Length should be within 1% (date format difference is ~4 chars out of 22000+)
        length_diff = abs(len(loader_prompt) - len(builder_prompt))
        max_diff = max(len(loader_prompt), len(builder_prompt)) * 0.01
        assert length_diff < max_diff, (
            f"Outputs differ by more than 1%: {length_diff} chars "
            f"(loader: {len(loader_prompt)}, builder: {len(builder_prompt)})"
        )

    def test_composer_direct_produces_semantically_equivalent_output(self):
        """
        Property: PromptComposer.compose() produces semantically equivalent output as build_company_overview_prompt().
        
        Note: Minor differences in date formatting are acceptable since loader uses "%B %Y"
        while direct composer uses "%B %d, %Y" format by default.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.schema import PromptContext
        from datetime import datetime
        
        company_name = "Test Company"
        website_url = "https://test.com"
        
        # Build using loader function (uses "%B %Y" format)
        loader_prompt = build_company_overview_prompt(company_name, website_url=website_url)
        
        # Build using PromptComposer directly with SAME date format as loader
        composer = PromptComposer()
        current_date = datetime.now().strftime("%B %Y")  # Match loader's format
        context = PromptContext(
            company_name=company_name,
            website_url=website_url,
            current_date=current_date,
            has_stage1_context=False,
        )
        composed = composer.compose("company_overview", context)
        
        # MUST be identical when using same date format
        assert loader_prompt == composed.content, (
            f"Direct composer output differs from loader!\n"
            f"Loader length: {len(loader_prompt)}, Composed length: {len(composed.content)}"
        )

    def test_ai_strategy_loader_and_composer_semantically_equivalent(self):
        """
        Property: build_ai_strategy_prompt() produces semantically equivalent output as PromptComposer.compose_strategy().
        
        Note: Minor differences in date formatting are acceptable.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.schema import PromptContext
        from datetime import datetime
        
        company_name = "Test Corp"
        cloud_vendor = "azure"
        current_date = datetime.now().strftime("%B %Y")  # Match loader's format
        
        # Build using loader function
        loader_prompt = build_ai_strategy_prompt(company_name, cloud_vendor=cloud_vendor, current_date=current_date)
        
        # Build using PromptComposer directly with same date format
        composer = PromptComposer()
        context = PromptContext(
            company_name=company_name,
            cloud_vendor=cloud_vendor,
            current_date=current_date,
            has_stage1_context=True,
        )
        composed = composer.compose_strategy("ai_strategy", context)
        
        # MUST be identical when using same date format
        assert loader_prompt == composed.content, (
            f"AI strategy loader and composer outputs differ!\n"
            f"Loader length: {len(loader_prompt)}, Composed length: {len(composed.content)}"
        )

    # =========================================================================
    # IDEMPOTENCY TESTS - Same inputs MUST produce same outputs
    # =========================================================================

    def test_idempotency_company_overview(self):
        """
        Property: Calling build_company_overview_prompt twice with same inputs produces identical output.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        prompt1 = build_company_overview_prompt("Test Corp", website_url="https://test.com")
        prompt2 = build_company_overview_prompt("Test Corp", website_url="https://test.com")
        
        assert prompt1 == prompt2, "Idempotency violated: same inputs produced different outputs"

    def test_idempotency_ai_strategy(self):
        """
        Property: Calling build_ai_strategy_prompt twice with same inputs produces identical output.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        prompt1 = build_ai_strategy_prompt("Test Corp", cloud_vendor="aws")
        prompt2 = build_ai_strategy_prompt("Test Corp", cloud_vendor="aws")
        
        assert prompt1 == prompt2, "Idempotency violated: same inputs produced different outputs"

    def test_idempotency_multiple_composer_instances(self):
        """
        Property: Different PromptComposer instances produce identical output for same inputs.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.schema import PromptContext
        
        context = PromptContext(company_name="Test Corp", website_url="https://test.com")
        
        composer1 = PromptComposer()
        composer2 = PromptComposer()
        
        result1 = composer1.compose("company_overview", context)
        result2 = composer2.compose("company_overview", context)
        
        assert result1.content == result2.content, "Different composer instances produced different output"

    # =========================================================================
    # COMPLETE YAML CONTENT VERIFICATION
    # =========================================================================

    def test_all_yaml_sections_appear_in_output(self):
        """
        Property: ALL sections defined in company_overview.yaml MUST appear in the output.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        config = load_prompt_config("company_overview")
        prompt = build_company_overview_prompt("Test Corp")
        
        missing_sections = []
        for section in config.sections:
            if section.name not in prompt:
                missing_sections.append(section.name)
        
        assert not missing_sections, f"Missing sections in output: {missing_sections}"

    def test_all_epistemic_rules_appear_in_output(self):
        """
        Property: ALL epistemic rules from shared components MUST appear in the output.
        
        Note: The composer uses shared/epistemic_rules.yaml, not the prompt-specific YAML.
        The composer adds "- " prefix to each rule.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.shared_loader import load_shared_components
        
        shared = load_shared_components()
        prompt = build_company_overview_prompt("Test Corp")
        
        missing_rules = []
        for rule_name, rule_text in shared.epistemic_rules.items():
            # The composer adds "- " prefix to each rule
            formatted_rule = f"- {rule_text.strip()}"
            if formatted_rule not in prompt:
                missing_rules.append(rule_name)
        
        assert not missing_rules, f"Missing epistemic rules in output: {missing_rules}"

    def test_all_formatting_rules_appear_in_output(self):
        """
        Property: ALL formatting rules from shared components MUST appear in the output.
        
        Note: The composer uses shared/formatting.yaml, not the prompt-specific YAML.
        The composer adds "- " prefix to each rule.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.shared_loader import load_shared_components
        
        shared = load_shared_components()
        prompt = build_company_overview_prompt("Test Corp")
        
        missing_rules = []
        for rule_name, rule_text in shared.formatting_rules.items():
            # The composer adds "- " prefix to each rule
            formatted_rule = f"- {rule_text.strip()}"
            if formatted_rule not in prompt:
                missing_rules.append(rule_name)
        
        assert not missing_rules, f"Missing formatting rules in output: {missing_rules}"

    def test_document_purpose_appears_verbatim(self):
        """
        Property: Document purpose from YAML MUST appear verbatim in output.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        config = load_prompt_config("company_overview")
        prompt = build_company_overview_prompt("Test Corp")
        
        assert config.document_purpose in prompt, (
            f"Document purpose not found verbatim in output.\n"
            f"Expected: {config.document_purpose[:100]}..."
        )

    # =========================================================================
    # EDGE CASE TESTS
    # =========================================================================

    def test_company_name_with_special_characters(self):
        """
        Property: Company names with special characters are handled correctly.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        special_names = [
            "Acme & Sons, Inc.",
            "O'Reilly Media",
            'Company "With Quotes"',
            "Société Générale",
            "日本企業株式会社",
            "Company\nWith\nNewlines",
            "Company\tWith\tTabs",
        ]
        
        for name in special_names:
            prompt = build_company_overview_prompt(name)
            assert name in prompt, f"Company name '{name}' not found in output"
            assert len(prompt) > 5000, f"Prompt too short for company '{name}'"

    def test_empty_company_name_handled(self):
        """
        Property: Empty company name produces valid output (with placeholder or error).
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        # Empty string should still produce a valid prompt structure
        prompt = build_company_overview_prompt("")
        
        # Should still have all the structural elements
        assert "## Executive Summary" in prompt
        assert "EPISTEMIC RULES" in prompt
        assert "FORMATTING" in prompt

    def test_very_long_company_name(self):
        """
        Property: Very long company names are handled without truncation or error.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        long_name = "A" * 500 + " Corporation International Holdings Ltd."
        prompt = build_company_overview_prompt(long_name)
        
        assert long_name in prompt, "Long company name was truncated"
        assert len(prompt) > 5000, "Prompt too short"

    def test_website_url_none_vs_not_provided(self):
        """
        Property: website_url=None and not providing website_url produce same output.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        prompt_none = build_company_overview_prompt("Test Corp", website_url=None)
        prompt_default = build_company_overview_prompt("Test Corp")
        
        assert prompt_none == prompt_default, "None and default website_url produce different output"

    def test_empty_website_url(self):
        """
        Property: Empty string website_url is handled gracefully.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        prompt = build_company_overview_prompt("Test Corp", website_url="")
        
        # Should still produce valid output
        assert "## Executive Summary" in prompt
        assert len(prompt) > 5000

    # =========================================================================
    # VENDOR VARIATION TESTS
    # =========================================================================

    def test_all_vendors_produce_valid_ai_strategy(self):
        """
        Property: All supported cloud vendors produce valid AI strategy prompts.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        vendors = ["azure", "aws", "gcp"]
        
        for vendor in vendors:
            prompt = build_ai_strategy_prompt("Test Corp", cloud_vendor=vendor)
            
            # Each vendor prompt should be substantial
            assert len(prompt) > 10000, f"Prompt too short for vendor {vendor}"
            
            # Each should have strategic sections
            assert "## AI Strategic Thesis" in prompt, f"Missing thesis for {vendor}"
            assert "## Five Quick Wins" in prompt, f"Missing quick wins for {vendor}"
            assert "## Five Bigger Bets" in prompt, f"Missing bigger bets for {vendor}"

    def test_vendor_specific_content_differs(self):
        """
        Property: Different vendors produce different vendor-specific content.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        azure_prompt = build_ai_strategy_prompt("Test Corp", cloud_vendor="azure")
        aws_prompt = build_ai_strategy_prompt("Test Corp", cloud_vendor="aws")
        gcp_prompt = build_ai_strategy_prompt("Test Corp", cloud_vendor="gcp")
        
        # Prompts should differ (vendor-specific content)
        assert azure_prompt != aws_prompt, "Azure and AWS prompts are identical"
        assert aws_prompt != gcp_prompt, "AWS and GCP prompts are identical"
        assert azure_prompt != gcp_prompt, "Azure and GCP prompts are identical"
        
        # Each should contain vendor-specific terms
        assert "Azure" in azure_prompt or "Microsoft" in azure_prompt
        assert "AWS" in aws_prompt or "Amazon" in aws_prompt
        assert "GCP" in gcp_prompt or "Google" in gcp_prompt

    # =========================================================================
    # CONTEXT VARIATION TESTS
    # =========================================================================

    def test_stage1_context_affects_output(self):
        """
        Property: has_stage1_context=True vs False produces different output.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.schema import PromptContext
        
        composer = PromptComposer()
        
        context_with = PromptContext(company_name="Test Corp", has_stage1_context=True)
        context_without = PromptContext(company_name="Test Corp", has_stage1_context=False)
        
        result_with = composer.compose("company_overview", context_with)
        result_without = composer.compose("company_overview", context_without)
        
        # Outputs should differ based on context
        assert result_with.content != result_without.content, (
            "has_stage1_context should affect output"
        )

    # =========================================================================
    # BACKWARD COMPATIBILITY TESTS
    # =========================================================================

    def test_backward_compatibility_query_parameter_ignored(self):
        """
        Property: The query parameter is accepted but ignored for backward compatibility.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        prompt_with_query = build_company_overview_prompt(
            "Test Corp",
            query="This custom query should be ignored",
            website_url="https://test.com"
        )
        prompt_without_query = build_company_overview_prompt(
            "Test Corp",
            website_url="https://test.com"
        )
        
        # Query parameter should be ignored - outputs should be identical
        assert prompt_with_query == prompt_without_query, (
            "Query parameter should be ignored but affected output"
        )

    def test_backward_compatibility_all_parameters(self):
        """
        Property: All legacy parameters are accepted without error.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        # Should not raise any errors
        prompt = build_company_overview_prompt(
            "Test Corp",
            query="ignored query",
            website_url="https://test.com",
        )
        
        assert "Test Corp" in prompt
        assert "https://test.com" in prompt

    # =========================================================================
    # STRATEGIC LAYER TESTS
    # =========================================================================

    def test_strategic_layer_round_trip(self):
        """
        Property: strategic_layer prompt also follows round-trip consistency.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        from primr.prompts.schema import PromptContext
        
        config = load_prompt_config("strategic_layer")
        
        composer = PromptComposer()
        context = PromptContext(company_name="Test Corp", has_stage1_context=True)
        composed = composer.compose("strategic_layer", context)
        
        # All sections should appear
        for section in config.sections:
            assert section.name in composed.content, f"Missing section: {section.name}"

    # =========================================================================
    # PROPERTY-BASED TESTS WITH HYPOTHESIS
    # =========================================================================

    @pytest.mark.parametrize("company_name", [
        "Simple Corp",
        "Acme & Sons",
        "O'Reilly",
        "Société Générale",
        "Company, Inc.",
        "Test (Holdings) Ltd",
        "A" * 100,
    ])
    def test_various_company_names_produce_valid_output(self, company_name):
        """
        Property: Various company name formats all produce valid prompts.
        
        **Feature: deep-research-prompt-architecture, Property 1: YAML Loading Round-Trip**
        **Validates: Requirements 1.1**
        """
        prompt = build_company_overview_prompt(company_name)
        
        assert company_name in prompt
        assert "## Executive Summary" in prompt
        assert "EPISTEMIC RULES" in prompt
        assert len(prompt) > 5000
