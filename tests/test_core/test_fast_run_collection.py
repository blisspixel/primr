"""Tests for the extracted data-collection stage (roadmap #23, Batch G).

Pins the adaptive-depth calibration, the candidate filter/dedup rules, pool
seeding, quality-filter application, failure isolation in the validation
pool, and the recovery-executor handoff to later stages.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_collection import DataCollectionResult, collect_research_data


@pytest.fixture
def seams(monkeypatch, tmp_path):
    captured: dict = {}

    fetch = MagicMock(return_value={"https://acme.example/about": "page content"})
    monkeypatch.setattr("primr.core.fast_run_collection.fetch_web_content", fetch)

    summarize = MagicMock(return_value="site summary")
    monkeypatch.setattr("primr.core.fast_run_collection.summarize_scraped_content", summarize)

    gen_queries = MagicMock(return_value=["acme revenue"])
    monkeypatch.setattr(
        "primr.core.fast_run_collection.generate_external_search_queries", gen_queries
    )

    search = MagicMock(return_value=[{"url": "https://evidence.example/news"}])
    monkeypatch.setattr("primr.core.fast_run_collection.search_web", search)

    scrape = MagicMock(
        side_effect=lambda candidates, **k: {c["url"]: "validated content" for c in candidates}
    )
    monkeypatch.setattr("primr.core.fast_run_collection.scrape_external_sources_validated", scrape)

    def fake_update(folder_path, **updates):
        captured.setdefault("run_state", {}).update(updates)

    monkeypatch.setattr("primr.core.fast_run_collection._update_run_state", fake_update)
    monkeypatch.setattr(
        "primr.core.fast_run_collection._build_resilience_event_listener",
        lambda folder: lambda event: None,
    )

    executor_token = object()
    monkeypatch.setattr(
        "primr.pipeline.integration.create_pipeline_executor",
        lambda folder, event_listener=None: executor_token,
    )

    def fake_recovery(executor, wrapped, url, folder):
        try:
            return SimpleNamespace(success=True, output=wrapped(), skipped=False, skip_reason=None)
        except Exception as e:
            return SimpleNamespace(success=False, output=None, skipped=True, skip_reason=str(e))

    monkeypatch.setattr("primr.pipeline.integration.scrape_page_with_recovery", fake_recovery)

    relevance = MagicMock(side_effect=lambda company, data, folder_path=None: data)
    monkeypatch.setattr("primr.core.source_relevance._assess_source_relevance", relevance)

    captured.update(
        {
            "fetch": fetch,
            "summarize": summarize,
            "gen_queries": gen_queries,
            "search": search,
            "scrape": scrape,
            "relevance": relevance,
            "executor_token": executor_token,
            "tmp": tmp_path,
        }
    )
    return captured


def _call(seams, **overrides) -> DataCollectionResult:
    defaults = {
        "company_name": "AcmeCo",
        "website": "https://acme.example",
        "folder_path": str(seams["tmp"]),
        "total_phases": 5,
    }
    defaults.update(overrides)
    return collect_research_data(**defaults)


class TestWebsiteScrape:
    def test_no_website_skips_scrape_and_summary(self, seams):
        result = _call(seams, website=None)
        seams["fetch"].assert_not_called()
        seams["summarize"].assert_not_called()
        assert result.scraped_data == {}
        assert result.pages_scraped == 0
        assert result.raw_corpus == ""

    def test_raw_corpus_built_with_page_markers(self, seams):
        result = _call(seams)
        assert result.raw_corpus.startswith("[Page: https://acme.example/about]")
        assert "page content" in result.raw_corpus

    def test_long_pages_truncated_in_corpus(self, seams):
        seams["fetch"].return_value = {"https://acme.example/big": "x" * 50_000}
        result = _call(seams)
        # 30k truncation per page (plus the page marker line)
        assert len(result.raw_corpus) < 31_000


class TestAdaptiveDepth:
    def test_rich_site_reduces_external_search(self, seams):
        seams["fetch"].return_value = {f"https://acme.example/p{i}": "x" * 7000 for i in range(31)}
        _call(seams)
        assert seams["gen_queries"].call_args.kwargs["max_queries"] == 8
        assert seams["run_state"]["search_depth"] == "rich"

    def test_thin_site_increases_external_search(self, seams):
        seams["fetch"].return_value = {"https://acme.example/only": "tiny"}
        _call(seams)
        assert seams["gen_queries"].call_args.kwargs["max_queries"] == 12
        assert seams["run_state"]["search_depth"] == "thin"

    def test_normal_site_default_depth(self, seams):
        seams["fetch"].return_value = {"https://acme.example/about": "x" * 30_000}
        _call(seams)
        assert seams["gen_queries"].call_args.kwargs["max_queries"] == 10
        assert seams["run_state"]["search_depth"] == "normal"


class TestExternalValidation:
    def test_pools_seeded_with_validated_sources(self, seams):
        result = _call(seams)
        assert result.source_urls == ["https://evidence.example/news"]
        assert "https://evidence.example/news" in result.source_urls_seen
        assert any("validated content" in p for p in result.external_text_parts)
        assert any("validated content" in p for p in result.external_raw_parts)
        assert result.external_query_count == 1

    def test_own_site_results_filtered(self, seams):
        seams["search"].return_value = [{"url": "https://acme.example/self-praise"}]
        result = _call(seams)
        assert result.source_urls == []
        seams["scrape"].assert_not_called()

    def test_duplicate_candidates_deduped(self, seams):
        seams["gen_queries"].return_value = ["q1", "q2"]
        seams["search"].return_value = [{"url": "https://evidence.example/same"}]
        result = _call(seams)
        assert seams["scrape"].call_count == 1
        assert result.source_urls == ["https://evidence.example/same"]

    def test_one_validation_failure_does_not_block_others(self, seams):
        seams["gen_queries"].return_value = ["q1", "q2"]
        seams["search"].side_effect = lambda q, c, w: [{"url": f"https://evidence.example/{q}"}]

        def flaky(candidates, **k):
            if "q1" in candidates[0]["url"]:
                raise RuntimeError("validator died")
            return {c["url"]: "validated content" for c in candidates}

        seams["scrape"].side_effect = flaky
        result = _call(seams)
        assert result.source_urls == ["https://evidence.example/q2"]
        assert seams["run_state"]["failed_scrape_urls"] == ["https://evidence.example/q1"]

    def test_quality_filter_drops_low_relevance(self, seams):
        seams["relevance"].side_effect = lambda company, data, folder_path=None: {}
        result = _call(seams)
        assert result.source_urls == []
        assert result.external_data == {}
        assert result.external_text_parts == []

    def test_search_uses_raw_company_name(self, seams):
        _call(seams, company_name=None)
        assert seams["search"].call_args.args[1] is None


class TestRecoveryExecutorHandoff:
    def test_executor_constructed_here_and_returned(self, seams):
        result = _call(seams)
        assert result.recovery_executor is seams["executor_token"]

    def test_run_state_records_collection_metrics(self, seams):
        _call(seams)
        state = seams["run_state"]
        assert state["pages_scraped"] == 1
        assert state["external_sources_initial"] == 1


class TestCollectionResumeCache:
    def test_resume_reuses_cache_and_skips_paid_collection(self, seams):
        first = _call(seams)
        seams["fetch"].reset_mock()
        seams["summarize"].reset_mock()
        seams["search"].reset_mock()
        seams["scrape"].reset_mock()

        resumed = _call(seams, resume_local=True)

        seams["fetch"].assert_not_called()
        seams["summarize"].assert_not_called()
        seams["search"].assert_not_called()
        seams["scrape"].assert_not_called()
        assert resumed.scraped_data == first.scraped_data
        assert resumed.summarized == first.summarized
        assert resumed.external_data == first.external_data
        assert resumed.source_urls == first.source_urls

    def test_resume_without_cache_runs_collection(self, seams):
        _call(seams, resume_local=True)
        seams["fetch"].assert_called()
        seams["summarize"].assert_called()

    @pytest.mark.parametrize(
        ("metric", "invalid_value"),
        [
            ("pages_scraped", "not-a-number"),
            ("total_scraped_chars", -1),
            ("external_query_count", True),
        ],
    )
    def test_invalid_cache_metrics_trigger_fresh_collection(self, seams, metric, invalid_value):
        _call(seams)
        cache_path = seams["tmp"] / "_collection_cache.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload[metric] = invalid_value
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        seams["fetch"].reset_mock()

        result = _call(seams, resume_local=True)

        seams["fetch"].assert_called_once()
        assert result.pages_scraped == 1
