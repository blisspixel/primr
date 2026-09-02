"""Unit tests for _run_preflight_checks in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.core import cli_preflight
from primr.core.cli import _run_preflight_checks
from primr.core.cli_preflight import _run_network_preflight_checks


@pytest.fixture(autouse=True)
def _scrub_openrouter_environment(monkeypatch):
    for name in (
        "OPENROUTER_API_KEY",
        "PRIMR_OPENROUTER_ENABLED",
        "PRIMR_OPENROUTER_MODEL",
        "PRIMR_OPENROUTER_INPUT_PRICE",
        "PRIMR_OPENROUTER_OUTPUT_PRICE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli_preflight, "sync_browser_runtime_supported", lambda: True)


def _mock_playwright_ready():
    pw = MagicMock()
    pw.chromium.launch.return_value = MagicMock()
    sync = MagicMock()
    sync.start.return_value = pw
    return sync


class TestPreflightApiKey:
    def test_missing_gemini_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        ok, errors = _run_preflight_checks("deep-research")
        assert ok is False
        assert any("GEMINI_API_KEY" in e for e in errors)

    def test_short_gemini_key_returns_error(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "short")
        ok, errors = _run_preflight_checks("deep-research")
        assert ok is False

    def test_full_mode_accepts_xai_only_without_gemini(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks("complete")
        assert ok is True
        assert errors == []

    def test_full_mode_rejects_openai_only_until_runtime_gap_closes(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-openai-test-key")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks("complete")
        assert ok is False
        assert any("Full report execution currently requires" in e for e in errors)

    def test_premium_mode_requires_gemini_even_with_xai(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks("complete", premium_mode=True)
        assert ok is False
        assert any("GEMINI_API_KEY" in e for e in errors)

    def test_fast_vendor_refresh_requires_both_provider_keys(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks(
                "complete",
                fast_mode=True,
                refresh_vendor_research=True,
                allow_network=False,
            )

        assert ok is False
        assert any("GEMINI_API_KEY" in error for error in errors)
        assert not any("XAI_API_KEY" in error for error in errors)

    def test_fast_vendor_refresh_still_requires_xai(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-gemini-test-key")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks(
                "complete",
                fast_mode=True,
                refresh_vendor_research=True,
                allow_network=False,
            )

        assert ok is False
        assert any("XAI_API_KEY" in error for error in errors)

    def test_fast_mode_detects_missing_optional_client_locally(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        with (
            patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()),
            patch.dict("sys.modules", {"openai": None}),
        ):
            ok, errors = _run_preflight_checks(
                "complete",
                fast_mode=True,
                allow_network=False,
            )

        assert ok is False
        assert any("openai" in error for error in errors)

    def test_openrouter_key_requires_separate_paid_routing_opt_in(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-openrouter-key")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks("complete", allow_network=False)

        assert ok is False
        assert any("routing is disabled" in error for error in errors)

    def test_openrouter_only_full_mode_passes_local_preflight_after_opt_in(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-openrouter-key")
        monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks("complete", allow_network=False)

        assert ok is True
        assert errors == []

    def test_openrouter_does_not_replace_xai_for_max_tier(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-openrouter-key")
        monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks(
                "complete",
                fast_mode=True,
                grok_tier="max",
                allow_network=False,
            )

        assert ok is False
        assert any("XAI_API_KEY" in error for error in errors)

    def test_openrouter_custom_model_requires_valid_prices_before_quote(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-openrouter-key")
        monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
        monkeypatch.setenv("PRIMR_OPENROUTER_MODEL", "vendor/unpriced")
        with patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()):
            ok, errors = _run_preflight_checks("complete", allow_network=False)

        assert ok is False
        assert any("configuration is invalid" in error for error in errors)


class TestPreflightPlaywrightSkip:
    def test_deep_research_mode_skips_playwright_check(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        # deep-research mode shouldn't try to launch Playwright.
        # Even if API connectivity check fails downstream, the playwright path is skipped.
        with patch(
            "playwright.sync_api.sync_playwright",
            side_effect=RuntimeError("should not be called"),
        ):
            ok, errors = _run_preflight_checks("deep-research")
        # Either passes (if API connectivity also passes) or has API errors,
        # but NOT playwright errors.
        assert not any("Playwright" in e for e in errors)


class TestPreflightPlaywrightFailure:
    def test_browsers_not_installed_returns_error(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        with patch(
            "playwright.sync_api.sync_playwright",
            side_effect=RuntimeError("Executable doesn't exist"),
        ):
            ok, errors = _run_preflight_checks("complete")
        assert any(
            "playwright install" in e.lower() or "browsers not installed" in e for e in errors
        )

    def test_unsupported_sync_runtime_uses_safe_fallbacks(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        monkeypatch.setattr(cli_preflight, "sync_browser_runtime_supported", lambda: False)

        with patch(
            "playwright.sync_api.sync_playwright",
            side_effect=RuntimeError("should not be called"),
        ) as sync_playwright:
            ok, errors = _run_preflight_checks("complete", allow_network=False)

        assert ok is True
        assert errors == []
        sync_playwright.assert_not_called()


class TestPreflightApiConnectivity:
    def test_connectivity_uses_model_metadata_without_generation(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "auto")
        fake = MagicMock()
        fake.Client.return_value.models.get.return_value = MagicMock()

        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            ok, errors = _run_preflight_checks("deep-research")

        assert ok is True
        assert errors == []
        fake.Client.return_value.models.get.assert_called_once()
        fake.Client.return_value.models.generate_content.assert_not_called()

    def test_local_only_preflight_skips_provider_and_search_calls(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        with (
            patch("playwright.sync_api.sync_playwright", return_value=_mock_playwright_ready()),
            patch("primr.core.cli_preflight._check_gemini_connectivity") as gemini,
            patch("primr.core.cli_preflight._check_google_search") as search,
        ):
            ok, errors = _run_preflight_checks("complete", allow_network=False)

        assert ok is True
        assert errors == []
        gemini.assert_not_called()
        search.assert_not_called()

    def test_network_preflight_does_not_repeat_local_dependency_checks(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "not-a-real-xai-test-key")
        with (
            patch("primr.core.cli_preflight._check_gemini_connectivity") as gemini,
            patch("primr.core.cli_preflight._check_google_search") as search,
            patch("primr.core.cli_preflight._check_playwright") as playwright,
            patch("primr.core.cli_preflight._check_fast_dependency") as dependency,
        ):
            ok, errors = _run_network_preflight_checks("complete", fast_mode=True)

        assert ok is True
        assert errors == []
        gemini.assert_called_once()
        search.assert_called_once()
        playwright.assert_not_called()
        dependency.assert_not_called()

    def test_openrouter_only_network_preflight_uses_auth_only_probe(self, monkeypatch):
        from primr.ai.providers import CredentialCheck

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-openrouter-key")
        monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
        result = CredentialCheck(provider="openrouter", ok=True, detail="authenticated")
        with (
            patch("primr.ai.providers.validate_provider_credentials", return_value=result) as probe,
            patch("primr.core.cli_preflight._check_google_search"),
        ):
            ok, errors = _run_network_preflight_checks("complete")

        assert ok is True
        assert errors == []
        probe.assert_called_once()

    def test_unselected_openrouter_does_not_block_gemini_route(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-gemini-test-key")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "stale-openrouter-key")
        monkeypatch.setenv("PRIMR_OPENROUTER_ENABLED", "1")
        with (
            patch("primr.core.cli_preflight._check_gemini_connectivity"),
            patch("primr.ai.providers.validate_provider_credentials") as probe,
            patch("primr.core.cli_preflight._check_google_search"),
        ):
            ok, errors = _run_network_preflight_checks("complete")

        assert ok is True
        assert errors == []
        probe.assert_not_called()

    def test_quota_error_returns_specific_message(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        fake = MagicMock()
        fake.Client.return_value.models.get.side_effect = RuntimeError("429 quota exceeded")
        # Skip playwright check by using deep-research mode
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            ok, errors = _run_preflight_checks("deep-research")
        assert any("quota" in e.lower() for e in errors)

    def test_invalid_key_returns_specific_message(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        fake = MagicMock()
        fake.Client.return_value.models.get.side_effect = RuntimeError("invalid api key")
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            ok, errors = _run_preflight_checks("deep-research")
        assert any("invalid" in e.lower() for e in errors)


class TestPreflightSearchProvider:
    def test_google_search_missing_keys_returns_errors(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        monkeypatch.setenv("SEARCH_PROVIDER", "google")
        monkeypatch.delenv("SEARCH_API_KEY", raising=False)
        monkeypatch.delenv("SEARCH_ENGINE_ID", raising=False)

        # Stub API connectivity to skip
        fake = MagicMock()
        fake.Client.return_value.models.get.return_value = MagicMock()
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            ok, errors = _run_preflight_checks("deep-research")
        assert any("SEARCH_API_KEY" in e for e in errors)


@pytest.mark.parametrize("mode", ["deep-research"])
def test_deep_research_doesnt_need_playwright(monkeypatch, mode):
    monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
    fake = MagicMock()
    fake.Client.return_value.models.get.return_value = MagicMock()
    with (
        patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
        patch("google.genai", fake, create=True),
    ):
        _ok, errors = _run_preflight_checks(mode)
    assert not any("Playwright" in e for e in errors)
