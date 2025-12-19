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
