"""Tests for _assess_source_relevance - LLM-based source filtering."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from primr.core.research_agent import _assess_source_relevance


def _ten_sources():
    return {f"https://s{i}.example": f"content about Acme {i}" * 50 for i in range(10)}


class TestAssessSourceRelevance:
    def test_skips_filter_when_too_few_sources(self):
        small = {f"https://s{i}.example": "body" for i in range(5)}
        result = _assess_source_relevance("Acme", small)
        # 5 sources or fewer -> short circuit, return unchanged
        assert result == small

    def test_empty_input_returns_empty(self):
        assert _assess_source_relevance("Acme", {}) == {}

    def test_llm_filters_to_subset(self, monkeypatch):
        sources = _ten_sources()
        # LLM keeps 1, 3, 5, 7, 9 (1-indexed)
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(return_value="[1, 3, 5, 7, 9]"),
        )
        result = _assess_source_relevance("Acme", sources)
        # 5 kept (>= 3 threshold)
        assert len(result) == 5

    def test_llm_too_aggressive_falls_back_to_all(self, monkeypatch):
        sources = _ten_sources()
        # LLM keeps only 2, which is too aggressive, so fallback returns originals.
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(return_value="[1, 2]"),
        )
        result = _assess_source_relevance("Acme", sources)
        assert result == sources  # fallback

    def test_llm_response_with_markdown_fence_parsed(self, monkeypatch):
        sources = _ten_sources()
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(return_value="```json\n[1, 2, 3, 4, 5]\n```"),
        )
        result = _assess_source_relevance("Acme", sources)
        assert len(result) == 5

    def test_llm_no_brackets_falls_back(self, monkeypatch):
        sources = _ten_sources()
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(return_value="not a list at all"),
        )
        result = _assess_source_relevance("Acme", sources)
        assert result == sources

    def test_llm_exception_falls_back(self, monkeypatch):
        sources = _ten_sources()
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(side_effect=RuntimeError("llm down")),
        )
        result = _assess_source_relevance("Acme", sources)
        assert result == sources

    def test_out_of_range_indices_filtered(self, monkeypatch):
        sources = _ten_sources()  # 10 sources, indices 1-10
        # Mix valid and out-of-range
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(return_value="[1, 2, 3, 50, 100]"),
        )
        result = _assess_source_relevance("Acme", sources)
        # Only indices 1-3 are valid -> 3 sources; >= 3 threshold met
        assert len(result) == 3

    def test_routed_model_is_passed_to_llm(self, monkeypatch):
        sources = _ten_sources()
        route = SimpleNamespace(
            model_name="routed-utility-model",
            log_metadata=lambda: {
                "stage_id": "fast.source_relevance",
                "inference_profile": "hybrid",
                "backend_id": "routed-utility-model",
            },
        )
        resolver = MagicMock(return_value=route)
        llm_mock = MagicMock(return_value="[1, 2, 3]")
        monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", resolver)
        monkeypatch.setattr("primr.core.source_relevance.llm", llm_mock)

        result = _assess_source_relevance("Acme", sources)

        assert len(result) == 3
        resolver.assert_called_once_with("fast.source_relevance", legacy_model_type="fast")
        assert llm_mock.call_args.kwargs["model"] == "routed-utility-model"

    def test_route_usage_metadata_is_recorded(self, monkeypatch, tmp_path):
        sources = _ten_sources()
        route = SimpleNamespace(
            model_name="routed-utility-model",
            log_metadata=lambda: {
                "stage_id": "fast.source_relevance",
                "inference_profile": "hybrid",
                "backend_id": "routed-utility-model",
                "backend_kind": "cloud_api",
                "billing_mode": "api_dollars",
                "routed": True,
                "route_reasons": ["meets_context"],
                "expected_input_tokens": 18_000,
                "expected_output_tokens": 2_000,
            },
        )
        monkeypatch.setattr(
            "primr.ai.stage_routing.resolve_stage_model",
            MagicMock(return_value=route),
        )
        monkeypatch.setattr(
            "primr.core.source_relevance.llm",
            MagicMock(return_value="[1, 2, 3, 4]"),
        )
        monkeypatch.setattr(
            "primr.core.source_relevance.stage_routing.capture_stage_usage",
            MagicMock(return_value={"before": {"input_tokens": 10}}),
        )
        monkeypatch.setattr(
            "primr.core.source_relevance.stage_routing.stage_usage_delta",
            MagicMock(
                return_value={
                    "actual_input_tokens": 120,
                    "actual_output_tokens": 30,
                    "actual_cached_input_tokens": 12,
                    "actual_cost_usd": 0.000045,
                    "actual_usage_by_model": {
                        "routed-utility-model": {
                            "input_tokens": 120,
                            "output_tokens": 30,
                            "cached_input_tokens": 12,
                            "actual_cost_usd": 0.000045,
                        }
                    },
                }
            ),
        )

        result = _assess_source_relevance("Acme", sources, str(tmp_path))

        assert len(result) == 4
        state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
        [record] = state["stage_routes"]
        assert record["outcome"] == "selected"
        assert record["stage_id"] == "fast.source_relevance"
        assert record["input_items"] == 10
        assert record["output_items"] == 4
        assert record["expected_input_tokens"] == 18_000
        assert record["expected_output_tokens"] == 2_000
        assert record["actual_input_tokens"] == 120
        assert record["actual_output_tokens"] == 30
        assert record["actual_cached_input_tokens"] == 12
        assert record["actual_cost_usd"] == 0.000045
        assert record["actual_usage_by_model"]["routed-utility-model"]["input_tokens"] == 120
        assert "prompt" not in record
        assert "response" not in record
