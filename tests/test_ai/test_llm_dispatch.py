"""
Tests for the role-aware dispatch in `primr.ai.llm`.

v1.24.0 split the legacy PRO role into WRITING and REASONING:

- WRITING (section_writing, report): prefers Grok 4.20-NR when XAI_API_KEY is
  set, else Pro model.
- REASONING (analysis, reasoning): prefers Grok 4.3 when XAI_API_KEY is set,
  else Pro model.
- UTILITY (scraping, link_selection, fast): prefers Grok 4.20-NR when
  XAI_API_KEY is set, else Gemini Flash.

The legacy assumption that "PRO tier always = Gemini" no longer holds. When
XAI is configured, primr's reasoning and writing stages run on Grok, which
matches v1.22.0+ production behavior in research_agent. This file pins the
new role-based dispatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import primr.ai.llm as llm_module
from primr.ai.providers import QuotaExhaustedError
from primr.config.models import PrimrModels

_PROVIDER_API_KEY_VARS = (
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "PRIMR_OPENROUTER_ENABLED",
    "PRIMR_OPENROUTER_MODEL",
    "PRIMR_OPENROUTER_INPUT_PRICE",
    "PRIMR_OPENROUTER_OUTPUT_PRICE",
)


def _scrubbed_env(**overrides: str) -> dict[str, str]:
    base = {k: v for k, v in __import__("os").environ.items() if k not in _PROVIDER_API_KEY_VARS}
    base.update(overrides)
    return base


class TestUtilityTierResolution:
    """`_get_model_for_type` for utility-tier model types under v1.24.0 routing.

    Gemini key wins for utility-tier; XAI-only falls back to grok-4.20-NR.
    """

    def test_scraping_xai_only_path(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("scraping") == PrimrModels.GROK_MODEL_WRITING

    def test_scraping_gemini_wins(self) -> None:
        """v1.24.0 default: Gemini Flash for utility when Gemini key set."""
        env = _scrubbed_env(XAI_API_KEY="test-xai", GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("scraping") == PrimrModels.FLASH_MODEL

    def test_link_selection_xai_only_path(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                llm_module._get_model_for_type("link_selection") == PrimrModels.GROK_MODEL_WRITING
            )

    def test_fast_xai_only_path(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("fast") == PrimrModels.GROK_MODEL_WRITING

    def test_legacy_aliases_xai_only_path(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("filtering") == PrimrModels.GROK_MODEL_WRITING
            assert llm_module._get_model_for_type("research") == PrimrModels.GROK_MODEL_WRITING
            assert llm_module._get_model_for_type("summarization") == PrimrModels.GROK_MODEL_WRITING

    def test_utility_falls_back_to_gemini_without_xai_key(self) -> None:
        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("scraping") == PrimrModels.FLASH_MODEL
            assert llm_module._get_model_for_type("link_selection") == PrimrModels.FLASH_MODEL
            assert llm_module._get_model_for_type("fast") == PrimrModels.FLASH_MODEL


class TestWritingTierResolution:
    """Writing tier resolution under v1.24.0 routing.

    Gemini key wins (Flash-Lite is v1.24.0 winner); XAI-only stays on grok-4.20-NR.
    """

    def test_section_writing_xai_only_path(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                llm_module._get_model_for_type("section_writing") == PrimrModels.GROK_MODEL_WRITING
            )

    def test_section_writing_gemini_wins(self) -> None:
        """v1.24.0 default: gemini-3.1-flash-lite for section writing when Gemini key set."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(XAI_API_KEY="test-xai", GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert (
                llm_module._get_model_for_type("section_writing")
                == ModelRegistry.GEMINI_3_1_FLASH_LITE.name
            )

    def test_report_xai_only_path(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("report") == PrimrModels.GROK_MODEL_WRITING

    def test_writing_falls_back_to_pro_model_without_keys(self) -> None:
        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("section_writing") == PrimrModels.PRO_MODEL


class TestReasoningTierResolution:
    """Reasoning tier (analysis, reasoning) -> Grok 4.3 with XAI key (unchanged from v1.23)."""

    def test_analysis_routes_to_grok_43_with_xai_key(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("analysis") == PrimrModels.GROK_MODEL_43

    def test_reasoning_routes_to_grok_43_with_xai_key(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("reasoning") == PrimrModels.GROK_MODEL_43

    def test_reasoning_falls_back_to_pro_model_without_xai_key(self) -> None:
        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            assert llm_module._get_model_for_type("analysis") == PrimrModels.PRO_MODEL


class TestLLMDispatch:
    """`llm()` dispatches to grok_llm when the resolved model is xAI-provider."""

    def test_llm_calls_grok_for_utility_tier_xai_only(self) -> None:
        """XAI-only path: utility tier routes through grok_llm with grok-4.20-NR."""
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with (
            patch.dict("os.environ", env, clear=True),
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

    def test_llm_uses_gemini_for_pro_tier_when_no_xai_key(self) -> None:
        """Without XAI key, analysis falls back to Pro and the provider stays Gemini."""
        from primr.ai.providers import ChatResponse

        env = {k: v for k, v in __import__("os").environ.items() if k != "XAI_API_KEY"}
        with (
            patch.dict("os.environ", env, clear=True),
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

    def test_llm_uses_grok_for_reasoning_tier_with_xai_key(self) -> None:
        """With XAI key, analysis routes to Grok 4.3 via grok_llm."""
        with (
            patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False),
            patch("primr.ai.grok_client.grok_llm", return_value="grok response") as mock_grok,
            patch("primr.ai.llm._get_client") as mock_gemini_client,
        ):
            result = llm_module.llm("test prompt", model_type="analysis")

        assert result == "grok response"
        mock_grok.assert_called_once()
        kwargs = mock_grok.call_args.kwargs
        assert kwargs["model"] == PrimrModels.GROK_MODEL_43
        mock_gemini_client.assert_not_called()

    def test_explicit_model_override_wins_over_legacy_model_type(self) -> None:
        with (
            patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False),
            patch("primr.ai.grok_client.grok_llm", return_value="routed response") as mock_grok,
            patch("primr.ai.llm._get_client") as mock_gemini_client,
        ):
            result = llm_module.llm(
                "test prompt",
                model_type="analysis",
                model=PrimrModels.GROK_MODEL_WRITING,
            )

        assert result == "routed response"
        assert mock_grok.call_args.kwargs["model"] == PrimrModels.GROK_MODEL_WRITING
        mock_gemini_client.assert_not_called()

    def test_zero_retry_xai_route_bypasses_failover(self) -> None:
        with (
            patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False),
            patch("primr.ai.grok_client.grok_llm", return_value="one response") as mock_grok,
            patch("primr.pipeline.llm_failover.call_with_failover") as failover,
        ):
            result = llm_module.llm(
                "test prompt",
                model=PrimrModels.GROK_MODEL_WRITING,
                retries=0,
                allow_failover=False,
                max_tokens=256,
            )

        assert result == "one response"
        failover.assert_not_called()
        mock_grok.assert_called_once_with(
            "test prompt",
            model=PrimrModels.GROK_MODEL_WRITING,
            temperature=1.0,
            max_tokens=256,
            retries=0,
        )

    def test_zero_retry_gemini_route_reaches_provider(self) -> None:
        from primr.ai.providers import ChatResponse

        provider = MagicMock()
        provider.chat.return_value = ChatResponse(
            text="one response",
            input_tokens=1,
            output_tokens=1,
        )
        with patch.object(llm_module, "_get_gemini_provider", return_value=provider):
            result = llm_module.llm(
                "test prompt",
                model=PrimrModels.FLASH_MODEL,
                retries=0,
                allow_failover=False,
                max_tokens=256,
            )

        assert result == "one response"
        assert provider.chat.call_args.kwargs["retries"] == 0
        assert provider.chat.call_args.kwargs["max_tokens"] == 256

    @pytest.mark.parametrize("model_name", ["gpt-5.4-mini", "claude-haiku-4-5"])
    def test_zero_retry_cross_provider_route_reaches_provider(self, model_name) -> None:
        from primr.ai.providers import ChatResponse

        provider = MagicMock()
        provider.chat.return_value = ChatResponse(
            text="one response",
            input_tokens=1,
            output_tokens=1,
            actual_cost_usd=0.00125,
        )
        mirror_usage = MagicMock()
        with (
            patch("primr.ai.routing.get_provider_for_model", return_value=provider),
            patch("primr.ai.grok_client._mirror_session_usage", mirror_usage),
        ):
            result = llm_module.llm(
                "test prompt",
                model=model_name,
                retries=0,
                allow_failover=False,
                max_tokens=256,
            )

        assert result == "one response"
        assert provider.chat.call_args.kwargs["retries"] == 0
        assert provider.chat.call_args.kwargs["max_tokens"] == 256
        mirror_usage.assert_called_once_with(
            model_name,
            1,
            1,
            cached_input_tokens=0,
            actual_cost_usd=0.00125,
        )

    def test_llm_renders_provider_owned_gemini_quota_guidance(self, capsys) -> None:
        """Gemini quota copy comes from the provider, while llm() only renders it."""
        from primr.ai.providers.gemini import GeminiProvider

        env = _scrubbed_env()
        provider = GeminiProvider()
        provider.chat = MagicMock(side_effect=QuotaExhaustedError("quota"))

        with (
            patch.dict("os.environ", env, clear=True),
            patch.object(llm_module, "_get_gemini_provider", return_value=provider),
            patch.object(llm_module, "log_chat_interaction"),
            pytest.raises(RuntimeError, match="Daily API quota exhausted"),
        ):
            llm_module.llm("test prompt", model_type="analysis")

        output = capsys.readouterr().out
        assert "[QUOTA EXHAUSTED] Daily API limit reached." in output
        assert "Upgrade your API plan at https://ai.google.dev" in output
        assert "Check quota: primr --check-quota" in output
