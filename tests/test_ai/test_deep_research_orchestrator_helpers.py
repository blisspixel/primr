"""Supplemental unit tests for DeepResearchOrchestrator helpers.

These cover the small mockable methods not exercised by the existing
test_deep_research_orchestrator.py: _calculate_backoff_delay,
_get_phase_name, _get_poll_interval, _extract_* delegators,
_load_accordion_prompts (+ default fallback), and
_build_research_dossier_prompt.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.ai.deep_research import DeepResearchOrchestrator


@pytest.fixture
def orchestrator(monkeypatch):
    """A DeepResearchOrchestrator with genai.Client mocked out."""
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    # Reset class-level caches so each test sees fresh load behavior.
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", None)
    monkeypatch.setattr(DeepResearchOrchestrator, "_accordion_prompts_cache", None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


class TestCalculateBackoffDelay:
    def test_attempt_zero_is_base_delay(self, orchestrator):
        delay = orchestrator._calculate_backoff_delay(0)
        assert delay == orchestrator.BASE_RETRY_DELAY

    def test_doubles_per_attempt(self, orchestrator):
        assert (
            orchestrator._calculate_backoff_delay(1)
            == orchestrator.BASE_RETRY_DELAY * 2
        )
        assert (
            orchestrator._calculate_backoff_delay(2)
            == orchestrator.BASE_RETRY_DELAY * 4
        )
        assert (
            orchestrator._calculate_backoff_delay(3)
            == orchestrator.BASE_RETRY_DELAY * 8
        )


class TestPhaseAndPollInterval:
    def test_phase_name_returns_string(self, orchestrator):
        name = orchestrator._get_phase_name(30)
        assert isinstance(name, str)

    def test_poll_interval_5s_early(self, orchestrator):
        assert orchestrator._get_poll_interval(10) == 5.0
        assert orchestrator._get_poll_interval(59) == 5.0

    def test_poll_interval_10s_at_middle(self, orchestrator):
        assert orchestrator._get_poll_interval(120) == 10.0

    def test_poll_interval_20s_after_middle(self, orchestrator):
        assert orchestrator._get_poll_interval(250) == 20.0

    def test_poll_interval_30s_after_long_run(self, orchestrator):
        assert orchestrator._get_poll_interval(400) == 30.0


class TestExtractDelegators:
    def test_extract_content_returns_string(self, orchestrator):
        with patch(
            "primr.ai.deep_research.extract_interaction_content",
            return_value="content body",
        ):
            assert orchestrator._extract_content(MagicMock()) == "content body"

    def test_extract_citations_returns_list(self, orchestrator):
        with patch(
            "primr.ai.deep_research.extract_interaction_citations",
            return_value=[{"url": "https://x"}],
        ):
            assert orchestrator._extract_citations(MagicMock()) == [{"url": "https://x"}]

    def test_extract_search_queries_count_returns_int(self, orchestrator):
        with patch(
            "primr.ai.deep_research.extract_search_queries_count",
            return_value=7,
        ):
            assert orchestrator._extract_search_queries_count(MagicMock()) == 7


class TestLoadAccordionPrompts:
    def test_default_prompts_contain_expected_keys(self):
        defaults = DeepResearchOrchestrator._get_default_accordion_prompts()
        assert "research_dossier_prompt" in defaults
        assert "section_writing_prompt" in defaults
        assert "position_guidance" in defaults

    def test_falls_back_to_defaults_on_load_error(self, monkeypatch):
        monkeypatch.setattr(
            DeepResearchOrchestrator, "_accordion_prompts_cache", None
        )
        with patch(
            "primr.prompts.composer.PromptComposer",
            side_effect=RuntimeError("yaml broken"),
        ):
            result = DeepResearchOrchestrator._load_accordion_prompts()
        assert "research_dossier_prompt" in result

    def test_load_caches_result(self, monkeypatch):
        monkeypatch.setattr(
            DeepResearchOrchestrator, "_accordion_prompts_cache", None
        )

        composer = MagicMock()
        config = MagicMock()
        config.raw_config = {
            "accordion_method": {
                "research_dossier_prompt": "DOSSIER {company_name}",
                "section_writing_prompt": "SECTION {section_title}",
                "position_guidance": {"opening": "open"},
            }
        }
        composer._load_config.return_value = config
        with patch("primr.prompts.composer.PromptComposer", return_value=composer):
            result = DeepResearchOrchestrator._load_accordion_prompts()
        assert result["research_dossier_prompt"] == "DOSSIER {company_name}"

        # Second call should hit the cache, not the composer.
        with patch("primr.prompts.composer.PromptComposer") as composer_mock:
            DeepResearchOrchestrator._load_accordion_prompts()
            composer_mock.assert_not_called()


class TestBuildResearchDossierPrompt:
    def test_includes_company_name(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Compile dossier for {company_name}{website_context}.",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme Corp", None)
        assert "Acme Corp" in result

    def test_includes_website_when_provided(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Compile dossier for {company_name}{website_context}.",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt(
                "Acme", "https://acme.example"
            )
        assert "https://acme.example" in result

    def test_omits_website_when_missing(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Compile dossier for {company_name}{website_context}.",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme", None)
        assert "website" not in result

    def test_uses_default_when_yaml_template_empty(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme", None)
        # Falls back to default which references "Lead Researcher".
        assert "Lead Researcher" in result
