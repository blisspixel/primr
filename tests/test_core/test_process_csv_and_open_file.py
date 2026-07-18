"""Unit tests for process_csv (legacy single-loop helper) and open_file."""

from __future__ import annotations

import csv
from unittest.mock import MagicMock

import pytest

from primr.core.cli import open_file, process_csv
from primr.core.research_agent import process_csv as legacy_process_csv


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "companies.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "website"])
        writer.writeheader()
        writer.writerow({"company_name": "ExampleCo", "website": "https://a.example"})
        writer.writerow({"company_name": "AcmeCorp", "website": "https://b.example"})
    return path


class TestProcessCsv:
    def test_processes_every_row(self, sample_csv, monkeypatch):
        perform_mock = MagicMock(return_value="/output/report.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        process_csv(str(sample_csv))
        assert perform_mock.call_count == 2
        assert perform_mock.call_args.kwargs["platforms"] is None

    def test_public_legacy_helper_keeps_platform_auto_detection(self, sample_csv, monkeypatch):
        perform_mock = MagicMock(return_value="/output/report.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)

        legacy_process_csv(str(sample_csv))

        assert perform_mock.call_count == 2
        assert perform_mock.call_args.kwargs["platforms"] is None

    def test_swallows_per_row_exceptions(self, sample_csv, monkeypatch):
        # The first raises and the second succeeds, so the loop must continue.
        perform_mock = MagicMock(side_effect=[RuntimeError("boom"), "/output/report.docx"])
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        process_csv(str(sample_csv))
        assert perform_mock.call_count == 2

    def test_skips_blank_rows(self, tmp_path, monkeypatch):
        path = tmp_path / "blank.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["company_name", "website"])
            writer.writeheader()
            writer.writerow({"company_name": "", "website": ""})
        perform_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        process_csv(str(path))
        perform_mock.assert_not_called()

    def test_passes_mode_and_platforms(self, sample_csv, monkeypatch):
        perform_mock = MagicMock(return_value="/output/report.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        process_csv(
            str(sample_csv),
            mode="scrape",
            citation_style="footnoted",
            ai_strategy=False,
            platforms=("aws", "gcp"),
        )
        kwargs = perform_mock.call_args.kwargs
        assert kwargs["mode"] == "scrape"
        assert kwargs["citation_style"] == "footnoted"
        assert kwargs["ai_strategy"] is False
        assert kwargs["platforms"] == ("aws", "gcp")

    def test_website_only_row_processed(self, tmp_path, monkeypatch):
        path = tmp_path / "website_only.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["company_name", "website"])
            writer.writeheader()
            writer.writerow({"company_name": "", "website": "https://x.example"})
        perform_mock = MagicMock(return_value="/output/report.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        process_csv(str(path))
        perform_mock.assert_called_once()


class TestOpenFile:
    def test_invokes_default_opener(self, monkeypatch):
        opener_mock = MagicMock()
        monkeypatch.setattr("primr.utils.files.open_with_default_app", opener_mock)
        open_file("/path/to/x.docx")
        opener_mock.assert_called_once_with("/path/to/x.docx")

    def test_warns_on_opener_failure(self, monkeypatch):
        monkeypatch.setattr(
            "primr.utils.files.open_with_default_app",
            MagicMock(side_effect=RuntimeError("no opener")),
        )
        # Should NOT raise
        open_file("/path/to/x.docx")
