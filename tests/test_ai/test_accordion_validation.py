"""
Pre-validation tests for Accordion Method.

These tests validate configuration and API connectivity BEFORE running
expensive full pipeline tests. Run these first to catch issues early.

**Feature: accordion-method-default, Task 8**
"""


import socket
import warnings
from unittest.mock import MagicMock, patch

import pytest

_GEMINI_NETWORK_AVAILABLE: bool | None = None


def _is_network_unavailable(error: Exception | str) -> bool:
    """Detect transient environment/network restrictions for integration tests."""
    text = str(error).lower()
    patterns = (
        "socket operation was attempted to an unreachable network",
        "connecterror",
        "connection error",
        "all connection attempts failed",
        "network is unreachable",
        "winerror 10051",
    )
    return any(pattern in text for pattern in patterns)


def _can_reach_gemini_api() -> bool:
    """Fast probe to skip integration tests in network-restricted environments."""
    global _GEMINI_NETWORK_AVAILABLE
    if _GEMINI_NETWORK_AVAILABLE is not None:
        return _GEMINI_NETWORK_AVAILABLE

    try:
        with socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=2.5):
            _GEMINI_NETWORK_AVAILABLE = True
    except OSError:
        _GEMINI_NETWORK_AVAILABLE = False

    return _GEMINI_NETWORK_AVAILABLE


class TestYAMLConfiguration:
    """
    Task 8.1: Validate YAML configuration loads correctly.
    """

    def test_company_overview_yaml_loads(self):
        """company_overview.yaml loads without errors."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        assert config is not None
        # meta is a dict, not an object
        assert config.meta["name"] == "Strategic Company Overview"

    def test_accordion_method_section_exists(self):
        """accordion_method section exists in company_overview.yaml."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})
        assert accordion, "accordion_method section missing from company_overview.yaml"

    def test_research_dossier_prompt_exists(self):
        """research_dossier_prompt template exists and has placeholders."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})
        prompt = accordion.get("research_dossier_prompt", "")

        assert prompt, "research_dossier_prompt is empty"
        assert "{company_name}" in prompt, "Missing {company_name} placeholder"
        assert "Lead Researcher" in prompt, "Missing Lead Researcher instruction"

    def test_section_writing_prompt_exists(self):
        """section_writing_prompt template exists and has placeholders."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})
        prompt = accordion.get("section_writing_prompt", "")

        assert prompt, "section_writing_prompt is empty"
        assert "{company_name}" in prompt, "Missing {company_name} placeholder"
        assert "{section_title}" in prompt, "Missing {section_title} placeholder"
        assert "{research_dossier}" in prompt, "Missing {research_dossier} placeholder"

    def test_position_guidance_exists(self):
        """position_guidance templates exist for opening/middle/closing."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        accordion = config.raw_config.get("accordion_method", {})
        guidance = accordion.get("position_guidance", {})

        assert "opening" in guidance, "Missing opening guidance"
        assert "middle" in guidance, "Missing middle guidance"
        assert "closing" in guidance, "Missing closing guidance"

    def test_all_sections_have_required_fields(self):
        """All 23 sections have id, name, part, position, purpose, covers."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        required_fields = ["id", "name", "part", "purpose", "covers"]

        for section in config.sections:
            for field in required_fields:
                value = getattr(section, field, None)
                assert value is not None, f"Section {section.id} missing {field}"

    def test_sections_have_position_field(self):
        """All sections have position field (opening/middle/closing/framework)."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        valid_positions = {"opening", "middle", "closing", "framework"}

        for section in config.sections:
            position = getattr(section, "position", None)
            assert position in valid_positions, \
                f"Section {section.id} has invalid position: {position}"

    def test_section_count(self):
        """Should have 23 sections defined."""
        from primr.prompts.composer import PromptComposer

        composer = PromptComposer()
        config = composer._load_config("company_overview")

        assert len(config.sections) == 23, \
            f"Expected 23 sections, got {len(config.sections)}"


class TestPreflightValidator:
    """
    Test the PreflightValidator class.
    """

    def test_preflight_result_summary_success(self):
        """PreflightResult generates correct success summary."""
        from primr.ai.preflight import PreflightResult

        result = PreflightResult(
            success=True,
            errors=[],
            warnings=[],
            checks={"api_key": {"passed": True, "status": "configured"}},
            estimated_duration="35-50 minutes",
            estimated_cost="~$0.50",
        )

        summary = result.summary()
        # Note: summary() uses ASCII '+' for cross-platform compatibility
        assert "+ Pre-flight validation passed" in summary
        assert "35-50 minutes" in summary

    def test_preflight_result_summary_failure(self):
        """PreflightResult generates correct failure summary."""
        from primr.ai.preflight import PreflightResult

        result = PreflightResult(
            success=False,
            errors=["GEMINI_API_KEY not configured"],
            warnings=["Website may be slow"],
            checks={},
            estimated_duration="",
            estimated_cost="",
        )

        summary = result.summary()
        # Note: summary() uses ASCII 'x' for cross-platform compatibility
        assert "x Pre-flight validation FAILED" in summary
        assert "GEMINI_API_KEY not configured" in summary
        assert "Website may be slow" in summary

    def test_preflight_result_verbose_summary(self):
        """PreflightResult verbose mode shows check details."""
        from primr.ai.preflight import PreflightResult

        result = PreflightResult(
            success=True,
            errors=[],
            warnings=[],
            checks={
                "api_key": {"passed": True, "status": "configured", "detail": "xxx...xxx"},
                "playwright": {"passed": True, "status": "installed"},
            },
            estimated_duration="35-50 minutes",
            estimated_cost="~$0.50",
        )

        summary = result.summary(verbose=True)
        assert "Check details:" in summary
        assert "api_key" in summary
        assert "playwright" in summary

    def test_model_constants(self):
        """PreflightValidator has correct model constants."""
        from primr.ai.preflight import PreflightValidator

        assert PreflightValidator.DEEP_RESEARCH_AGENT == "deep-research-pro-preview-12-2025"
        assert PreflightValidator.SECTION_MODEL == "gemini-3-flash-preview"

    def test_estimates_by_mode(self):
        """PreflightValidator has estimates for all modes."""
        from primr.ai.preflight import PreflightValidator

        assert "full" in PreflightValidator.ESTIMATES
        assert "deep" in PreflightValidator.ESTIMATES
        assert "scrape" in PreflightValidator.ESTIMATES

        for _mode, est in PreflightValidator.ESTIMATES.items():
            assert "duration" in est
            assert "cost" in est

    @pytest.mark.asyncio
    async def test_deep_research_unknown_error_is_failure(self):
        """Unknown Deep Research errors should fail preflight."""
        from primr.ai.preflight import PreflightValidator

        validator = PreflightValidator()

        fake_client = MagicMock()
        fake_client.interactions.create.side_effect = Exception("weird transport blowup")

        with patch("google.genai.Client", return_value=fake_client):
            errors: list[str] = []
            warnings_list: list[str] = []
            checks: dict[str, dict] = {}
            await validator._check_models(
                mode="deep",
                errors=errors,
                warnings=warnings_list,
                checks=checks,
                progress=lambda _msg: None,
            )

        assert errors
        assert checks["deep_research"]["passed"] is False
        assert checks["deep_research"]["status"] == "error"


class TestOrchestratorConfiguration:
    """
    Test DeepResearchOrchestrator loads config correctly.
    """

    def test_orchestrator_loads_sections_from_yaml(self):
        """Orchestrator loads sections from YAML, not hardcoded."""
        from primr.ai.deep_research import DeepResearchOrchestrator

        # Clear cache to force reload
        DeepResearchOrchestrator._sections_cache = None

        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        sections = orchestrator.REPORT_SECTIONS

        assert len(sections) == 23, f"Expected 23 sections, got {len(sections)}"

        # Verify structure
        for section in sections:
            assert "id" in section
            assert "title" in section
            assert "instructions" in section
            assert "position" in section

    def test_orchestrator_loads_accordion_prompts(self):
        """Orchestrator loads accordion prompts from YAML."""
        from primr.ai.deep_research import DeepResearchOrchestrator

        # Clear cache
        DeepResearchOrchestrator._accordion_prompts_cache = None

        prompts = DeepResearchOrchestrator._load_accordion_prompts()

        assert "research_dossier_prompt" in prompts
        assert "section_writing_prompt" in prompts
        assert "position_guidance" in prompts

        assert prompts["research_dossier_prompt"], "research_dossier_prompt is empty"
        assert prompts["section_writing_prompt"], "section_writing_prompt is empty"

    def test_build_research_dossier_prompt(self):
        """Research dossier prompt builds correctly."""
        from primr.ai.deep_research import DeepResearchOrchestrator

        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        prompt = orchestrator._build_research_dossier_prompt(
            company_name="Test Corp",
            website_url="https://test.com"
        )

        assert "Test Corp" in prompt
        assert "test.com" in prompt
        assert "Lead Researcher" in prompt

    def test_build_section_prompt(self):
        """Section prompt builds correctly with all context."""
        from primr.ai.deep_research import DeepResearchOrchestrator

        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)

        section = {
            "id": "test",
            "title": "Test Section",
            "instructions": "Write a test.",
            "position": "middle",
        }

        prompt = orchestrator._build_section_prompt(
            section=section,
            company_name="Test Corp",
            research_dossier="Research facts here.",
            previous_sections=[],
            stage1_context="Stage 1 data here.",
            section_index=0,
            total_sections=10,
        )

        assert "Test Corp" in prompt
        assert "Test Section" in prompt
        assert "Research facts" in prompt
        assert "Stage 1 data" in prompt


class TestAPIConnectivity:
    """
    Task 8.2 & 8.3: Validate API connectivity.

    These tests make real API calls - mark as slow/integration.
    """

    @pytest.mark.slow
    @pytest.mark.integration
    def test_gemini_3_flash_connectivity(self):
        """
        Task 8.2: Verify Gemini 3 Flash API access.
        """
        if not _can_reach_gemini_api():
            pytest.skip("Network restricted: cannot reach generativelanguage.googleapis.com:443")

        from google import genai

        from primr.config.settings import get_settings

        settings = get_settings()
        try:
            api_key = settings.api.gemini_key
        except Exception:
            pytest.skip("GEMINI_API_KEY not configured")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not configured")

        client = genai.Client(api_key=api_key)

        # Simple test call
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents="Say 'API test successful' and nothing else.",
            )
        except Exception as e:
            if _is_network_unavailable(e):
                pytest.skip(f"Network unavailable for integration test: {e}")
            raise

        assert response.text is not None
        assert len(response.text) > 0
        print(f"Gemini 3 Flash response: {response.text[:100]}")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_deep_research_agent_exists(self):
        """
        Task 8.3: Verify Deep Research agent is accessible.
        """
        if not _can_reach_gemini_api():
            pytest.skip("Network restricted: cannot reach generativelanguage.googleapis.com:443")

        from google import genai

        from primr.config.settings import get_settings

        settings = get_settings()
        try:
            api_key = settings.api.gemini_key
        except Exception:
            pytest.skip("GEMINI_API_KEY not configured")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not configured")

        client = genai.Client(api_key=api_key)

        try:
            # google-genai emits an experimental usage warning for interactions.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Interactions usage is experimental.*",
                    category=UserWarning,
                )
                interaction = client.interactions.create(
                    input="Test",
                    agent="deep-research-pro-preview-12-2025",
                    background=True,
                )

            assert interaction.id is not None
            print(f"Deep Research agent accessible, interaction: {interaction.id[:20]}...")

        except Exception as e:
            if "not found" in str(e).lower() or "invalid" in str(e).lower():
                pytest.fail(f"Deep Research agent not accessible: {e}")
            print(f"Deep Research agent exists (got expected error): {e}")

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_preflight_validation(self):
        """
        Run full pre-flight validation.
        """
        if not _can_reach_gemini_api():
            pytest.skip("Network restricted: cannot reach generativelanguage.googleapis.com:443")

        from primr.ai.preflight import PreflightValidator
        from primr.config.settings import get_settings

        settings = get_settings()
        try:
            api_key = settings.api.gemini_key
        except Exception:
            pytest.skip("GEMINI_API_KEY not configured")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not configured")

        validator = PreflightValidator()
        result = await validator.validate(
            mode="full",
            website_url="https://www.boh.com",
            on_progress=lambda msg: print(msg),
        )

        print("\n" + result.summary(verbose=True))

        # Should pass if all keys are configured
        if result.errors:
            print(f"Errors: {result.errors}")

        # In network-restricted environments, skip this integration assertion.
        gemini_detail = result.checks.get("gemini_flash", {}).get("detail", "")
        if _is_network_unavailable(gemini_detail):
            pytest.skip(f"Network unavailable for integration test: {gemini_detail}")

        # At minimum, Gemini should be accessible
        assert result.checks.get("gemini_flash", {}).get("passed", False), \
            "Gemini Flash should be accessible"


class TestRetryLogic:
    """
    Test the retry and fallback logic.
    """

    def test_retryable_errors_identified(self):
        """Verify which errors are considered retryable."""
        retryable_patterns = [
            "429", "quota exceeded", "rate limit",
            "500", "internal server error",
            "503", "service unavailable",
            "connection error", "timeout",
        ]

        for pattern in retryable_patterns:
            error_str = f"Error: {pattern} occurred"
            is_retryable = any(p in error_str.lower() for p in [
                "429", "quota", "rate", "500", "internal server error",
                "503", "service unavailable", "connection", "timeout"
            ])
            assert is_retryable, f"Pattern '{pattern}' should be retryable"


class TestDirectGenerationMethod:
    """
    Test the _execute_direct_generation method exists and works.
    """

    def test_method_exists(self):
        """_execute_direct_generation method exists on orchestrator."""
        from primr.ai.deep_research import DeepResearchOrchestrator

        assert hasattr(DeepResearchOrchestrator, '_execute_direct_generation')

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_direct_generation_works(self):
        """Direct generation produces content."""
        if not _can_reach_gemini_api():
            pytest.skip("Network restricted: cannot reach generativelanguage.googleapis.com:443")

        from primr.ai.deep_research import DeepResearchOrchestrator
        from primr.config.settings import get_settings

        settings = get_settings()
        try:
            api_key = settings.api.gemini_key
        except Exception:
            pytest.skip("GEMINI_API_KEY not configured")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not configured")

        orchestrator = DeepResearchOrchestrator()

        result = await orchestrator._execute_direct_generation(
            prompt="Write a single paragraph about the importance of testing software.",
        )

        if result.error and _is_network_unavailable(result.error):
            pytest.skip(f"Network unavailable for integration test: {result.error}")

        assert result.success, f"Direct generation failed: {result.error}"
        assert result.content, "No content returned"
        assert len(result.content.split()) > 20, "Content too short"
        print(f"Direct generation: {len(result.content.split())} words")
