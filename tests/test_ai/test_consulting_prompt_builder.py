"""Unit tests for ConsultingPromptBuilder in primr.ai.deep_research.

These cover the static-content helpers (_get_formatting_rules,
_get_purpose_section, etc.) and the build_comprehensive_prompt
delegator, which composes the full company-overview prompt via the
shared PromptComposer.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.ai.deep_research import ConsultingPromptBuilder


@pytest.fixture
def builder():
    return ConsultingPromptBuilder()


class TestStaticPromptSections:
    def test_formatting_rules_contains_key_phrases(self, builder):
        text = builder._get_formatting_rules()
        assert "FORMATTING RULES" in text
        assert "single-level" in text
        assert "[cite: X, Y, Z]" in text

    def test_purpose_section_has_subject_positive_intent(self, builder):
        text = builder._get_purpose_section()
        assert "PURPOSE" in text
        assert "Subject-Positive Intent" in text

    def test_epistemic_contract_lists_three_categories(self, builder):
        text = builder._get_epistemic_contract()
        assert "verified fact" in text
        assert "inference" in text
        assert "hypothesis" in text.lower()

    def test_tone_guidelines_include_humility_signals(self, builder):
        text = builder._get_tone_guidelines()
        assert "appears to" in text
        assert "epistemic humility" in text.lower()
        assert "absolutist" in text.lower()

    def test_key_metrics_format_includes_extraction_patterns(self, builder):
        text = builder._get_key_metrics_format()
        assert "Employees:" in text
        assert "Revenue:" in text
        assert "Founded:" in text
        assert "Headquarters:" in text

    def test_chapter_specs_interpolate_company_name(self, builder):
        text = builder._get_chapter_specifications("Acme Corp")
        # Sample chapter names that must appear in the spec
        for chapter in (
            "Executive Summary",
            "Detailed Products and Services",
            "Mission and Vision",
            "Company History",
            "SWOT Analysis",
        ):
            assert chapter in text

    def test_downstream_note_present(self, builder):
        text = builder._get_downstream_note()
        # Just a sanity check that the method returns something
        assert isinstance(text, str)
        assert len(text) > 0


class TestKnownChapters:
    def test_class_attribute_lists_canonical_chapters(self):
        assert "Executive Summary" in ConsultingPromptBuilder.CHAPTERS
        assert "SWOT Analysis" in ConsultingPromptBuilder.CHAPTERS
        assert "Porter's Five Forces Assessment" in ConsultingPromptBuilder.CHAPTERS

    def test_chapters_are_unique(self):
        chapters = ConsultingPromptBuilder.CHAPTERS
        assert len(chapters) == len(set(chapters))


class TestBuildComprehensivePrompt:
    def test_delegates_to_prompt_composer(self, builder):
        composed = MagicMock()
        composed.content = "FULL PROMPT FOR Acme Corp"
        composer = MagicMock()
        composer.compose.return_value = composed
        with patch(
            "primr.prompts.composer.PromptComposer", return_value=composer
        ):
            result = builder.build_comprehensive_prompt("Acme Corp")
            assert result == "FULL PROMPT FOR Acme Corp"
            # Composer was called with "company_overview"
            composer.compose.assert_called_once()
            assert composer.compose.call_args.args[0] == "company_overview"

    def test_passes_website_url_to_context(self, builder):
        composed = MagicMock()
        composed.content = "PROMPT"
        composer = MagicMock()
        composer.compose.return_value = composed
        with patch(
            "primr.prompts.composer.PromptComposer", return_value=composer
        ):
            builder.build_comprehensive_prompt(
                "Acme", website_url="https://acme.example"
            )
        context = composer.compose.call_args.args[1]
        assert context.website_url == "https://acme.example"

    def test_handles_missing_website_url(self, builder):
        composed = MagicMock()
        composed.content = "PROMPT"
        composer = MagicMock()
        composer.compose.return_value = composed
        with patch(
            "primr.prompts.composer.PromptComposer", return_value=composer
        ):
            builder.build_comprehensive_prompt("Acme")
        context = composer.compose.call_args.args[1]
        assert context.website_url is None
