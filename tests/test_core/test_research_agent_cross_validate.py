"""Unit tests for _fast_cross_validate in primr.core.research_agent."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.research_agent import _fast_cross_validate


class TestFastCrossValidate:
    def test_empty_response_returns_empty_lists(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=""),
        )
        result = _fast_cross_validate(
            "Acme", "https://acme.example", "report body", []
        )
        assert result["weak_sections"] == []
        assert result["contradictions"] == []

    def test_llm_exception_returns_failed_marker(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(side_effect=RuntimeError("LLM down")),
        )
        result = _fast_cross_validate(
            "Acme", "https://acme.example", "report body", []
        )
        assert result["weak_sections"] == []
        assert result.get("_failed") is True

    def test_parses_clean_json(self, monkeypatch):
        response = (
            '{"weak_sections": ['
            '{"title": "## Financials", "reason": "no sources", "queries": ["q1"]}'
            '], "contradictions": ["revenue conflicts"]}'
        )
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate(
            "Acme", "https://acme.example", "body", []
        )
        assert len(result["weak_sections"]) == 1
        assert result["weak_sections"][0]["title"] == "## Financials"
        assert result["contradictions"] == ["revenue conflicts"]

    def test_strips_markdown_code_fence(self, monkeypatch):
        response = '```json\n{"weak_sections": [], "contradictions": []}\n```'
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate(
            "Acme", "https://acme.example", "body", []
        )
        assert result["weak_sections"] == []
        assert result["contradictions"] == []

    def test_extracts_json_when_surrounded_by_prose(self, monkeypatch):
        response = (
            'Here is the analysis: {"weak_sections": [], "contradictions": []} '
            "End of analysis."
        )
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate(
            "Acme", "https://acme.example", "body", []
        )
        assert result["weak_sections"] == []

    def test_caps_weak_sections_at_3(self, monkeypatch):
        weak_sections = [
            {"title": f"## S{i}", "reason": "r", "queries": ["q"]} for i in range(10)
        ]
        import json

        response = json.dumps({"weak_sections": weak_sections, "contradictions": []})
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate("Acme", None, "body", [])
        assert len(result["weak_sections"]) == 3

    def test_caps_contradictions_at_3(self, monkeypatch):
        import json

        response = json.dumps(
            {
                "weak_sections": [],
                "contradictions": [f"c{i}" for i in range(10)],
            }
        )
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate("Acme", None, "body", [])
        assert len(result["contradictions"]) == 3

    def test_filters_non_string_contradictions(self, monkeypatch):
        import json

        response = json.dumps(
            {
                "weak_sections": [],
                "contradictions": ["ok", 123, None, "good"],
            }
        )
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate("Acme", None, "body", [])
        assert result["contradictions"] == ["ok", "good"]

    def test_filters_non_dict_weak_sections(self, monkeypatch):
        import json

        response = json.dumps(
            {
                "weak_sections": [{"title": "ok"}, "string", 123, {"title": "good"}],
                "contradictions": [],
            }
        )
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value=response),
        )
        result = _fast_cross_validate("Acme", None, "body", [])
        assert len(result["weak_sections"]) == 2
        assert all(isinstance(w, dict) for w in result["weak_sections"])

    def test_non_dict_top_level_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "primr.ai.grok_client.grok_llm",
            MagicMock(return_value='["array", "not", "dict"]'),
        )
        result = _fast_cross_validate("Acme", None, "body", [])
        assert result["weak_sections"] == []
        assert result["contradictions"] == []
