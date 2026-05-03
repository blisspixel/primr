"""
Tests for the routing layer (`primr.ai.routing`).

These pin the policy that previously lived scattered across `llm.py` and
`grok_client.py`: utility-tier calls prefer Grok 4.1-NR when ``XAI_API_KEY``
is set, fall back to Gemini Flash otherwise; pro-tier always uses Gemini Pro.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.ai.providers import OpenAICompatibleProvider, Provider
from primr.ai.routing import (
    Role,
    get_provider_for_model,
    pick_model_for_legacy_type,
    pick_model_for_role,
)
from primr.config.models import PrimrModels


class TestPickModelForRole:
    def test_utility_picks_grok_when_xai_key_set(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert pick_model_for_role(Role.UTILITY) == PrimrModels.GROK_MODEL_WRITING

    def test_utility_falls_back_to_gemini_without_xai_key(self) -> None:
        env = {k: v for k, v in __import__("os").environ.items() if k != "XAI_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.UTILITY) == PrimrModels.FLASH_MODEL

    def test_pro_always_picks_gemini_pro(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert pick_model_for_role(Role.PRO) == PrimrModels.PRO_MODEL

        env = {k: v for k, v in __import__("os").environ.items() if k != "XAI_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.PRO) == PrimrModels.PRO_MODEL

    def test_role_accepts_string_alias(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert pick_model_for_role("utility") == PrimrModels.GROK_MODEL_WRITING


class TestLegacyTypeMapping:
    def test_legacy_utility_types_map_to_role(self) -> None:
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            for legacy_type in (
                "scraping",
                "link_selection",
                "filtering",
                "fast",
                "research",
                "summarization",
            ):
                assert (
                    pick_model_for_legacy_type(legacy_type)
                    == PrimrModels.GROK_MODEL_WRITING
                )

    def test_legacy_pro_types_map_to_pro_model(self) -> None:
        for legacy_type in ("section_writing", "analysis", "reasoning", "report"):
            assert pick_model_for_legacy_type(legacy_type) == PrimrModels.PRO_MODEL

    def test_unknown_type_defaults_to_utility(self) -> None:
        # Unknown legacy strings should not crash; they map to utility role
        # so the call lands on a cheap model instead of an expensive Pro one.
        with patch.dict("os.environ", {"XAI_API_KEY": "test-key"}, clear=False):
            assert (
                pick_model_for_legacy_type("never-seen-before")
                == PrimrModels.GROK_MODEL_WRITING
            )


class TestGetProviderForModel:
    def test_xai_model_returns_openai_compatible_provider(self) -> None:
        provider = get_provider_for_model(PrimrModels.GROK_MODEL_WRITING)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.name == "xai"

    def test_gemini_model_returns_provider_with_gemini_name(self) -> None:
        provider = get_provider_for_model(PrimrModels.PRO_MODEL)
        assert isinstance(provider, Provider)
        assert provider.name == "gemini"

    def test_unknown_model_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            get_provider_for_model("definitely-not-a-real-model")
