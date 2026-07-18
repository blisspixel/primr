"""Unit tests for process_csv (legacy single-loop helper) and open_file."""

from __future__ import annotations

import csv
from unittest.mock import MagicMock

import pytest

from primr.core.cli import open_file, process_csv
from primr.core.research_agent import (
    perform_research as legacy_perform_research,
)
from primr.core.research_agent import (
    process_csv as legacy_process_csv,
)


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "companies.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "website"])
        writer.writeheader()
        writer.writerow({"company_name": "ExampleCo", "website": "https://a.example"})
        writer.writerow({"company_name": "AcmeCorp", "website": "https://b.example"})
    return path


@pytest.fixture
def website_only_csv(tmp_path):
    path = tmp_path / "website_only.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "website"])
        writer.writeheader()
        writer.writerow(
            {
                "company_name": "",
                "website": "https://website-only.invalid",
            }
        )
    return path


class TestProcessCsv:
    def test_public_helper_delegates_to_governed_batch(self, sample_csv, monkeypatch):
        governed = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli_batch_runtime.process_batch", governed)
        process_csv(
            str(sample_csv),
            mode="scrape",
            citation_style="footnoted",
            ai_strategy=False,
            platforms=("aws", "gcp"),
        )

        governed.assert_called_once_with(
            str(sample_csv),
            mode="scrape",
            citation_style="footnoted",
            ai_strategy=False,
            platforms=("aws", "gcp"),
            skip_confirm=False,
            research_runner=legacy_perform_research,
        )

    def test_research_agent_export_delegates_to_governed_batch(self, sample_csv, monkeypatch):
        governed = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli_batch_runtime.process_batch", governed)

        legacy_process_csv(
            str(sample_csv),
            mode="deep",
            citation_style="footnoted",
            ai_strategy=False,
            platforms=("gcp",),
            no_qa=True,
        )

        governed.assert_called_once_with(
            str(sample_csv),
            mode="deep",
            citation_style="footnoted",
            ai_strategy=False,
            platforms=("gcp",),
            skip_confirm=False,
            no_qa=True,
            research_runner=legacy_perform_research,
        )

    @pytest.mark.parametrize("helper", [process_csv, legacy_process_csv])
    def test_decline_starts_no_research(self, helper, sample_csv, monkeypatch):
        research = MagicMock()
        monkeypatch.setattr("primr.core.research_agent.perform_research", research)
        monkeypatch.setattr("builtins.input", MagicMock(return_value="n"))

        helper(str(sample_csv), ai_strategy=False)

        research.assert_not_called()

    @pytest.mark.parametrize("helper", [process_csv, legacy_process_csv])
    def test_website_only_row_uses_validated_hostname(
        self,
        helper,
        website_only_csv,
        tmp_path,
        monkeypatch,
    ):
        report = tmp_path / "report.md"
        report.write_text("report " * 1_000, encoding="utf-8")
        research = MagicMock(return_value=str(report))
        monkeypatch.setattr("primr.core.research_agent.perform_research", research)
        monkeypatch.setattr("builtins.input", MagicMock(return_value="y"))
        monkeypatch.delenv("PRIMR_ALLOW_VENDOR_REFRESH", raising=False)

        helper(str(website_only_csv), ai_strategy=False)

        research.assert_called_once()
        assert research.call_args.args[:2] == (
            "website-only.invalid",
            "https://website-only.invalid",
        )


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
