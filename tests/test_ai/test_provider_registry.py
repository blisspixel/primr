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
    registry,
)
from primr.config.models import PrimrModels


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


# Providers like Ollama have a default key (no env var required) and so are
# always reported as available. The tests below scope assertions to the
# env-keyed providers we are actually toggling.
_ENV_KEYED_PROVIDER_NAMES = {"xai", "gemini", "openai", "anthropic"}


def _env_keyed_available() -> set[str]:
    return {p.name for p in get_available_providers() if p.name in _ENV_KEYED_PROVIDER_NAMES}


# All env-keyed provider keys — must be scrubbed from the test environment so
# the user's real .env doesn't contaminate availability assertions.
_ENV_KEYED_API_KEYS = {
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
}


def _scrubbed_env() -> dict[str, str]:
    """Return the current env with all provider API key vars removed."""
    return {k: v for k, v in __import__("os").environ.items() if k not in _ENV_KEYED_API_KEYS}


class TestAvailableProviders:
    def test_xai_only(self) -> None:
        env = _scrubbed_env()
        env["XAI_API_KEY"] = "test-xai"
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == {"xai"}

    def test_gemini_only(self) -> None:
        env = _scrubbed_env()
        env["GEMINI_API_KEY"] = "test-gemini"
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == {"gemini"}

    def test_both_keys(self) -> None:
        env = _scrubbed_env()
        env["XAI_API_KEY"] = "test-xai"
        env["GEMINI_API_KEY"] = "test-gemini"
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == {"xai", "gemini"}

    def test_no_keys(self) -> None:
        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == set()

    def test_openai_only(self) -> None:
        """OPENAI_API_KEY alone surfaces openai as the only env-keyed provider."""
        env = _scrubbed_env()
        env["OPENAI_API_KEY"] = "test-openai"
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == {"openai"}

    def test_anthropic_only(self) -> None:
        """ANTHROPIC_API_KEY alone surfaces anthropic as the only env-keyed provider."""
        env = _scrubbed_env()
        env["ANTHROPIC_API_KEY"] = "test-anthropic"
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == {"anthropic"}

    def test_all_four_keys(self) -> None:
        """All four env-keyed providers surface when their keys are set."""
        env = _scrubbed_env()
        env["XAI_API_KEY"] = "test-xai"
        env["GEMINI_API_KEY"] = "test-gemini"
        env["OPENAI_API_KEY"] = "test-openai"
        env["ANTHROPIC_API_KEY"] = "test-anthropic"
        with patch.dict("os.environ", env, clear=True):
            available = _env_keyed_available()
        assert available == {"xai", "gemini", "openai", "anthropic"}


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

    def test_openai_entry_uses_responses_api(self) -> None:
        openai_entry = next(p for p in KNOWN_PROVIDERS if p.name == "openai")
        provider = build_provider(openai_entry)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._api_style == "responses"

    def test_model_provider_resolution_is_cached_without_routing_import(self, monkeypatch) -> None:
        monkeypatch.setattr(registry, "_PROVIDER_INSTANCES", {})
        first = registry.get_registered_provider_for_model(PrimrModels.PRO_MODEL)
        second = registry.get_registered_provider_for_model(PrimrModels.PRO_MODEL)

        assert isinstance(first, GeminiProvider)
        assert second is first


def test_validate_provider_credentials_captures_build_failure():
    """A provider whose construction/probe raises is reported, not raised."""
    from primr.ai.providers import ProviderEntry, validate_provider_credentials

    entry = ProviderEntry(name="xai", api_key_env="XAI_API_KEY", description="x")
    with patch(
        "primr.ai.providers.registry.build_provider",
        side_effect=RuntimeError("boom"),
    ):
        result = validate_provider_credentials(entry)
    assert result.ok is False
    assert result.provider == "xai"
    assert "RuntimeError" in result.detail


def test_validate_provider_credentials_delegates_to_provider():
    from unittest.mock import MagicMock

    from primr.ai.providers import CredentialCheck, ProviderEntry, validate_provider_credentials

    entry = ProviderEntry(name="gemini", api_key_env="GEMINI_API_KEY", description="g")
    provider = MagicMock()
    provider.validate_credentials.return_value = CredentialCheck(
        provider="gemini", ok=True, detail="ok"
    )
    with patch("primr.ai.providers.registry.build_provider", return_value=provider):
        result = validate_provider_credentials(entry)
    assert result.ok is True
    provider.validate_credentials.assert_called_once()
