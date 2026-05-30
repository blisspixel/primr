"""Unit tests for perform_scrape_only in primr.core.research_agent."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from primr.core.research_agent import perform_scrape_only


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path / "wk"))
    monkeypatch.setattr("primr.core.research_agent.OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr("primr.core.research_agent.LOGS_DIR", str(tmp_path / "logs"))


class TestPerformScrapeOnly:
    def test_no_website_returns_none(self, isolated):
        assert (
            perform_scrape_only(
                company_name="Acme",
                website=None,
                start_time=time.time(),
            )
            is None
        )

    def test_empty_scrape_returns_none(self, isolated, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={}),
        )
        result = perform_scrape_only(
            company_name="Acme",
            website="https://acme.example",
            start_time=time.time(),
            folder_path=str(tmp_path / "work"),
        )
        assert result is None

    def test_low_quality_scrape_returns_none_when_validation_enabled(
        self, isolated, monkeypatch, tmp_path
    ):
        # 1 page with 1 char - fails quality gate
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={"url": "x"}),
        )
        monkeypatch.setattr(
            "primr.core.research_agent._validate_scrape_quality",
            MagicMock(return_value=(False, "too thin")),
        )
        result = perform_scrape_only(
            company_name="Acme",
            website="https://acme.example",
            start_time=time.time(),
            fail_on_low_scrape=True,
            folder_path=str(tmp_path / "work"),
        )
        assert result is None

    def test_skip_validation_proceeds_to_summarize(self, isolated, monkeypatch, tmp_path):
        folder = tmp_path / "work"
        folder.mkdir()
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value={"url1": "content " * 100}),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.summarize_scraped_content",
            MagicMock(return_value="summary body"),
        )
        result = perform_scrape_only(
            company_name="Acme",
            website="https://acme.example",
            start_time=time.time(),
            fail_on_low_scrape=False,
            folder_path=str(folder),
        )
        # Returns the folder path on success
        assert result == str(folder)
        # Output files should exist
        assert (folder / "scraped_content.txt").exists()
        assert (folder / "insights.txt").exists()

    def test_happy_path_with_quality_validation_pass(self, isolated, monkeypatch, tmp_path):
        folder = tmp_path / "work"
        folder.mkdir()
        # Big enough corpus to pass default quality thresholds.
        corpus = {f"url{i}": "content " * 1000 for i in range(10)}
        monkeypatch.setattr(
            "primr.core.research_agent.fetch_web_content",
            MagicMock(return_value=corpus),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.summarize_scraped_content",
            MagicMock(return_value="summary"),
        )
        result = perform_scrape_only(
            company_name="Acme",
            website="https://acme.example",
            start_time=time.time(),
            fail_on_low_scrape=True,
            folder_path=str(folder),
        )
        assert result == str(folder)
