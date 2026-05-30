"""Unit tests for _repair_fast_report_citation_integrity."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _repair_fast_report_citation_integrity


class TestRepairCitations:
    def test_empty_content_returns_unchanged(self):
        result = _repair_fast_report_citation_integrity("Acme", None, "", ["https://s1"])
        assert result == ""

    def test_no_sources_returns_unchanged(self):
        original = "## Section\n\nbody"
        result = _repair_fast_report_citation_integrity(
            "Acme", "https://acme.example", original, []
        )
        assert result == original

    def test_llm_exception_returns_original(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(side_effect=RuntimeError("grok down")),
        )
        original = "## Section\n\nbody"
        result = _repair_fast_report_citation_integrity(
            "Acme", "https://acme.example", original, ["https://s1.example"]
        )
        assert result == original

    def test_empty_llm_response_returns_original(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=""),
        )
        original = "## Section\n\nbody"
        result = _repair_fast_report_citation_integrity(
            "Acme", "https://acme.example", original, ["https://s1.example"]
        )
        assert result == original

    def test_structure_broken_returns_original(self, monkeypatch):
        original = (
            "## Executive Summary\n\n"
            + ("word " * 500)
            + "\n\n## SWOT\n\n"
            + ("word " * 500)
            + "\n\nWhat to validate: ask"
        )
        # Polished response only has ONE section -> structure broken
        polished = "## Executive Summary\n\n" + ("word " * 100)
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=polished),
        )
        result = _repair_fast_report_citation_integrity(
            "Acme",
            "https://acme.example",
            original,
            ["https://s1.example", "https://s2.example"],
        )
        assert result == original
