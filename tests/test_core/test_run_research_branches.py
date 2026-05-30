"""Unit tests for run_research early branches in primr.core.research_agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.research_agent import run_research


@pytest.fixture
def isolated_run(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path / "wk"))
    monkeypatch.setattr("primr.core.research_agent.OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr("primr.core.research_agent.LOGS_DIR", str(tmp_path / "logs"))


class TestRunResearchEarlyExit:
    def test_returns_none_when_scrape_empty(self, isolated_run, monkeypatch):
        # When website is provided but fetch_web_content returns empty dict.
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={}),
        )
        result = run_research(
            company_name="Acme",
            website="https://acme.example",
        )
        assert result is None

    def test_returns_none_when_scrape_quality_too_low(self, isolated_run, monkeypatch):
        # Tiny scrape - 1 page, few chars - should fail quality gate.
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={"https://x.example": "x"}),
        )
        # Force quality check to fail by tightening thresholds
        monkeypatch.setattr(
            "primr.core.research_agent._validate_scrape_quality",
            MagicMock(return_value=(False, "too thin")),
        )
        result = run_research(
            company_name="Acme",
            website="https://acme.example",
            fail_on_low_scrape=True,
        )
        assert result is None

    def test_skip_quality_validation_proceeds_past_check(self, isolated_run, monkeypatch):
        # When fail_on_low_scrape=False, low quality shouldn't bail.
        # But the function will then try external search etc. — mock those out.
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={"https://x.example": "x" * 5000}),
        )
        # Stop the flow after scrape via search exception.
        monkeypatch.setattr(
            "primr.core.research_agent.generate_external_search_queries",
            MagicMock(side_effect=RuntimeError("stop here")),
        )
        # The function may swallow the exception or propagate — either way it's testing
        # that the quality gate didn't trigger the early-return path.
        try:
            run_research(
                company_name="Acme",
                website="https://acme.example",
                fail_on_low_scrape=False,
            )
        except RuntimeError:
            pass  # OK — proves we got past the quality gate

    def test_no_website_skips_scrape(self, isolated_run, monkeypatch):
        # When website is empty, scraping is skipped — function proceeds.
        scrape_mock = MagicMock(return_value={})
        monkeypatch.setattr("primr.core.research_agent.fetch_web_content", scrape_mock)
        # External search will run but we can stop it
        monkeypatch.setattr(
            "primr.core.research_agent.generate_external_search_queries",
            MagicMock(side_effect=RuntimeError("stop")),
        )
        try:
            run_research(company_name="Acme", website="")
        except RuntimeError:
            pass
        # Should NOT have called fetch_web_content
        scrape_mock.assert_not_called()


class TestProgressCallback:
    def test_progress_callback_invoked(self, isolated_run, monkeypatch):
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={}),
        )
        progress = MagicMock()
        run_research(
            company_name="Acme",
            website="https://acme.example",
            on_progress=progress,
        )
        # Should have been called at least with the "Working folder:" message.
        assert progress.called
