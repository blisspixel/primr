"""
Tests for the provider registry (`primr.ai.providers.registry`).

The registry knows which providers primr supports, which env keys configure
them, and which capability roles each can serve. Pinning this in tests means
adding a provider in the future is a small, traceable change.
"""

from __future__ import annotations

from unittest.mock import patch

from primr.ai.providers import (
    KNOWN_PROVIDERS,
    GeminiProvider,
    OpenAICompatibleProvider,
    build_provider,
    get_available_providers,
    list_known_providers,
)


class TestRegistry:
    def test_known_providers_includes_xai_and_gemini(self) -> None:
        names = {p.name for p in KNOWN_PROVIDERS}
        assert "xai" in names
        assert "gemini" in names

    def test_each_known_provider_has_api_key_env(self) -> None:
        for p in KNOWN_PROVIDERS:
            assert p.api_key_env, f"{p.name!r} entry must declare an api_key_env"

    def test_list_known_providers_returns_tuple(self) -> None:
        result = list_known_providers()
        assert isinstance(result, tuple)
        assert len(result) >= 2


class TestAvailableProviders:
    def test_xai_only(self) -> None:
        env = {k: v for k, v in __import__("os").environ.items() if k != "GEMINI_API_KEY"}
        env["XAI_API_KEY"] = "test-xai"
        with patch.dict("os.environ", env, clear=True):
            available = {p.name for p in get_available_providers()}
        assert available == {"xai"}

    def test_gemini_only(self) -> None:
        env = {k: v for k, v in __import__("os").environ.items() if k != "XAI_API_KEY"}
        env["GEMINI_API_KEY"] = "test-gemini"
        with patch.dict("os.environ", env, clear=True):
            available = {p.name for p in get_available_providers()}
        assert available == {"gemini"}

    def test_both_keys(self) -> None:
        env = {
            "XAI_API_KEY": "test-xai",
            "GEMINI_API_KEY": "test-gemini",
        }
        with patch.dict("os.environ", env, clear=True):
            available = {p.name for p in get_available_providers()}
        assert available == {"xai", "gemini"}

    def test_no_keys(self) -> None:
        env = {
            k: v
            for k, v in __import__("os").environ.items()
            if k not in {"XAI_API_KEY", "GEMINI_API_KEY"}
        }
        with patch.dict("os.environ", env, clear=True):
            available = get_available_providers()
        assert available == []


class TestBuildProvider:
    def test_xai_entry_builds_openai_compatible(self) -> None:
        xai_entry = next(p for p in KNOWN_PROVIDERS if p.name == "xai")
        provider = build_provider(xai_entry)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.name == "xai"

    def test_gemini_entry_builds_gemini_provider(self) -> None:
        gemini_entry = next(p for p in KNOWN_PROVIDERS if p.name == "gemini")
        provider = build_provider(gemini_entry)
        assert isinstance(provider, GeminiProvider)
        assert provider.name == "gemini"
