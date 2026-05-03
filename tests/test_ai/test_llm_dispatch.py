"""
Tests for the utility-tier dispatch in `primr.ai.llm`.

When XAI_API_KEY is set, scraping / link-selection / generic "fast" calls
route to Grok 4.1 fast non-reasoning instead of Gemini Flash. Pro-tier calls
(analysis, section writing) stay on Gemini regardless. This file pins that
behaviour so a future refactor can't silently re-Geminify the utility tier.
"""

from __future__ import annotations

from unittest.mock import patch

import primr.ai.llm as llm_module
from primr.config.models import PrimrModels


class TestUtilityTierResolution:
    """`_get_model_for_type` honours XAI_API_KEY for utility model types."""

    def test_scraping_routes_to_grok_when_xai_key_present(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert llm_module._get_model_for_type("scraping") == PrimrModels.GROK_MODEL_WRITING

    def test_link_selection_routes_to_grok_when_xai_key_present(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert (
                llm_module._get_model_for_type("link_selection") == PrimrModels.GROK_MODEL_WRITING
            )

    def test_fast_routes_to_grok_when_xai_key_present(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert llm_module._get_model_for_type("fast") == PrimrModels.GROK_MODEL_WRITING

    def test_legacy_aliases_route_to_grok_when_xai_key_present(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert llm_module._get_model_for_type("filtering") == PrimrModels.GROK_MODEL_WRITING
            assert llm_module._get_model_for_type("research") == PrimrModels.GROK_MODEL_WRITING
            assert (
                llm_module._get_model_for_type("summarization") == PrimrModels.GROK_MODEL_WRITING
            )

    def test_utility_falls_back_to_gemini_without_xai_key(self) -> None:
        env = {k: v for k, v in __import__("os").environ.items() if k != "XAI_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("scraping") == PrimrModels.FLASH_MODEL
            assert llm_module._get_model_for_type("link_selection") == PrimrModels.FLASH_MODEL
            assert llm_module._get_model_for_type("fast") == PrimrModels.FLASH_MODEL


class TestProTierUnchanged:
    """Pro tier always resolves to Gemini Pro — XAI_API_KEY must not affect it."""

    def test_section_writing_stays_on_gemini_pro_with_xai_key(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert llm_module._get_model_for_type("section_writing") == PrimrModels.PRO_MODEL

    def test_analysis_stays_on_gemini_pro_with_xai_key(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert llm_module._get_model_for_type("analysis") == PrimrModels.PRO_MODEL

    def test_reasoning_stays_on_gemini_pro_with_xai_key(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert llm_module._get_model_for_type("reasoning") == PrimrModels.PRO_MODEL


class TestLLMDispatch:
    """`llm()` dispatches to grok_llm when the resolved model is xAI-provider."""

    def test_llm_calls_grok_for_utility_tier_when_xai_key_present(self) -> None:
        with (
            patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False),
            patch("primr.ai.grok_client.grok_llm", return_value="grok response") as mock_grok,
            patch("primr.ai.llm._get_client") as mock_gemini_client,
        ):
            result = llm_module.llm("test prompt", model_type="scraping")

        assert result == "grok response"
        mock_grok.assert_called_once()
        kwargs = mock_grok.call_args.kwargs
        assert kwargs["model"] == PrimrModels.GROK_MODEL_WRITING
        # Gemini client must not have been touched
        mock_gemini_client.assert_not_called()

    def test_llm_uses_gemini_for_pro_tier_even_with_xai_key(self) -> None:
        # Pro-tier is provider-specific. XAI_API_KEY must not redirect it.
        from primr.ai.providers import ChatResponse

        with (
            patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False),
            patch("primr.ai.grok_client.grok_llm") as mock_grok,
            patch.object(
                llm_module,
                "_get_gemini_provider",
            ) as mock_get_provider,
        ):
            mock_provider = mock_get_provider.return_value
            mock_provider.chat.return_value = ChatResponse(
                text="gemini response", input_tokens=1, output_tokens=1
            )

            result = llm_module.llm("test prompt", model_type="analysis")

        assert result == "gemini response"
        mock_grok.assert_not_called()
        # Confirm the call routed through the Gemini provider, not Grok
        mock_provider.chat.assert_called_once()
        kwargs = mock_provider.chat.call_args.kwargs
        assert kwargs["model"] == llm_module.PrimrModels.PRO_MODEL
