"""Unit tests for _run_preflight_checks in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.core.cli import _run_preflight_checks


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


class TestPreflightApiConnectivity:
    def test_quota_error_returns_specific_message(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AI" + "x" * 30)
        fake = MagicMock()
        fake.Client.return_value.models.generate_content.side_effect = RuntimeError(
            "429 quota exceeded"
        )
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
        fake.Client.return_value.models.generate_content.side_effect = RuntimeError(
            "invalid api key"
        )
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
        fake.Client.return_value.models.generate_content.return_value = MagicMock()
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
    fake.Client.return_value.models.generate_content.return_value = MagicMock()
    with (
        patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
        patch("google.genai", fake, create=True),
    ):
        _ok, errors = _run_preflight_checks(mode)
    assert not any("Playwright" in e for e in errors)
