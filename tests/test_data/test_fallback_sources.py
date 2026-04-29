"""Tests for the public-data fallback sources.

These tests use mocked HTTP responses so they run without network and don't
depend on any real company's website, Wikipedia article, or EDGAR filing.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from primr.data.fallback_sources import (
    FallbackPage,
    _normalize_company_name,
    find_edgar_cik,
    find_wikipedia_title,
    gather_fallback_content,
)

# =============================================================================
# Normalization
# =============================================================================


def test_normalize_company_name_strips_trailing_suffix():
    assert _normalize_company_name("Example Inc.") == "example"
    assert _normalize_company_name("Global Corp.") == "global"
    assert _normalize_company_name("WidgetCo LLC") == "widgetco"
    assert _normalize_company_name("Example PLC") == "example"
    # One suffix stripped per call (last-suffix-wins); chained stripping
    # would risk mangling legitimate trailing words.
    assert _normalize_company_name("Acme Holdings Inc") == "acme holdings"


def test_normalize_company_name_preserves_core_name():
    assert _normalize_company_name("Example International") == "example international"
    assert _normalize_company_name("Alpha Beta Gamma") == "alpha beta gamma"


# =============================================================================
# EDGAR CIK resolution
# =============================================================================


def test_find_edgar_cik_exact_match():
    fake_index_body = json.dumps(
        {
            "0": {"cik_str": 1234567, "ticker": "EXMP", "title": "Example Holdings Inc."},
            "1": {"cik_str": 7654321, "ticker": "WGT", "title": "Widget Corp"},
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, fake_index_body, None),
    ):
        # Clear the module-level cache
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        result = find_edgar_cik("Example Holdings Inc.")
        assert result is not None
        cik, ticker, canonical = result
        assert cik == "0001234567"
        assert ticker == "EXMP"
        assert canonical == "Example Holdings Inc."


def test_find_edgar_cik_fuzzy_substring_match():
    fake_index_body = json.dumps(
        {
            "0": {"cik_str": 1234567, "ticker": "EXMP", "title": "Example Holdings Inc."},
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, fake_index_body, None),
    ):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        # Lookup with just "Example" should match "Example Holdings Inc."
        result = find_edgar_cik("Example")
        assert result is not None
        cik, ticker, _ = result
        assert ticker == "EXMP"


def test_find_edgar_cik_no_match_returns_none():
    fake_index_body = json.dumps(
        {
            "0": {"cik_str": 1234567, "ticker": "EXMP", "title": "Example Holdings Inc."},
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, fake_index_body, None),
    ):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        result = find_edgar_cik("Nonexistent Widget Company LLC")
        assert result is None


def test_find_edgar_cik_handles_index_fetch_failure():
    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(403, None, None),
    ):
        import primr.data.fallback_sources as fb

        fb._ticker_index_cache = None

        result = find_edgar_cik("Example Inc.")
        assert result is None


# =============================================================================
# Wikipedia lookup
# =============================================================================


def test_find_wikipedia_title_prefers_matching_title():
    search_response = json.dumps(
        {
            "query": {
                "search": [
                    {"title": "Unrelated Article", "snippet": "..."},
                    {"title": "Example Holdings", "snippet": "..."},
                ]
            }
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, search_response, None),
    ):
        title = find_wikipedia_title("Example Holdings Inc.")
        assert title == "Example Holdings"


def test_find_wikipedia_title_falls_back_to_top_hit():
    search_response = json.dumps(
        {
            "query": {
                "search": [
                    {"title": "Some Other Article", "snippet": "..."},
                ]
            }
        }
    ).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, search_response, None),
    ):
        title = find_wikipedia_title("Completely Unrelated Name")
        assert title == "Some Other Article"


def test_find_wikipedia_title_empty_results():
    search_response = json.dumps({"query": {"search": []}}).encode()

    with patch(
        "primr.data.fallback_sources._http_get",
        return_value=(200, search_response, None),
    ):
        title = find_wikipedia_title("Anything")
        assert title is None


# =============================================================================
# Parallel fan-out contract
# =============================================================================


def test_gather_fallback_content_merges_all_sources():
    """Fan-out collects pages from every source that returns something."""
    fake_pages_by_source = {
        "wikipedia": [FallbackPage(url="https://w", source="wikipedia", content="wiki text " * 60)],
        "edgar": [FallbackPage(url="https://e", source="edgar", content="10-K text " * 300)],
        "subdomain": [FallbackPage(url="https://s", source="subdomain", content="IR text " * 80)],
        "wayback": [FallbackPage(url="https://y", source="wayback", content="archive text " * 100)],
        "grok": [FallbackPage(url="https://g", source="grok", content="grok synth text " * 50)],
    }

    def fake_subdomain(base_host, **_kwargs):
        return fake_pages_by_source["subdomain"]

    def fake_edgar(name, **_kwargs):
        return fake_pages_by_source["edgar"]

    def fake_wikipedia(name, **_kwargs):
        return fake_pages_by_source["wikipedia"]

    def fake_wayback(urls, **_kwargs):
        return fake_pages_by_source["wayback"]

    def fake_grok(urls, name, **_kwargs):
        return fake_pages_by_source["grok"]

    with (
        patch("primr.data.fallback_sources.fetch_subdomain_content", side_effect=fake_subdomain),
        patch("primr.data.fallback_sources.fetch_edgar_content", side_effect=fake_edgar),
        patch("primr.data.fallback_sources.fetch_wikipedia_content", side_effect=fake_wikipedia),
        patch("primr.data.fallback_sources.fetch_wayback_pages", side_effect=fake_wayback),
        patch("primr.data.fallback_sources.fetch_grok_surrogates", side_effect=fake_grok),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=["https://example.com/about"],
            grok_surrogate_urls=["https://example.com/about"],
        )

    sources = sorted(p.source for p in pages)
    assert sources == ["edgar", "grok", "subdomain", "wayback", "wikipedia"]


def test_gather_fallback_content_tolerates_individual_source_failure():
    """A raising source does not prevent others from contributing."""
    good_page = FallbackPage(url="https://w", source="wikipedia", content="wiki text " * 60)

    def raises(*_args, **_kwargs):
        raise RuntimeError("simulated outage")

    with (
        patch("primr.data.fallback_sources.fetch_subdomain_content", side_effect=raises),
        patch("primr.data.fallback_sources.fetch_edgar_content", side_effect=raises),
        patch("primr.data.fallback_sources.fetch_wikipedia_content", return_value=[good_page]),
        patch("primr.data.fallback_sources.fetch_wayback_pages", side_effect=raises),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=[],
        )

    assert len(pages) == 1
    assert pages[0].source == "wikipedia"


def test_gather_fallback_content_returns_empty_when_all_sources_empty():
    with (
        patch("primr.data.fallback_sources.fetch_subdomain_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_edgar_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_wikipedia_content", return_value=[]),
        patch("primr.data.fallback_sources.fetch_wayback_pages", return_value=[]),
    ):
        pages = gather_fallback_content(
            company_name="Example Inc.",
            website="https://example.com/",
            wayback_urls=["https://example.com/about"],
        )

    assert pages == []
