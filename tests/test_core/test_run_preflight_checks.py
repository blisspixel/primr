"""Unit tests for _run_preflight_checks in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.core.cli import _run_preflight_checks


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
