"""Additional coverage for search_utils.

Targets the LLM-backed query generators, the Google Custom Search retry /
fallback branches, and lookup_company_website — paths not exercised by
test_external_sources.py. All LLM, DDG, and HTTP calls are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _fast_and_clean(monkeypatch):
    """No real sleeps, reset circuit breaker, zero retry delay."""
    from primr.data import search_utils

    monkeypatch.setattr(search_utils.time, "sleep", lambda _s: None)
    monkeypatch.setattr(search_utils, "INITIAL_RETRY_DELAY", 0)
    cb = search_utils._search_circuit
    cb._failure_count = 0
    cb._state = "closed"
    cb._last_failure_time = None
    return


# =============================================================================
# generate_search_queries
# =============================================================================


class TestGenerateSearchQueries:
    def test_parses_numbered_list_and_caps_at_three(self):
        from primr.data.search_utils import generate_search_queries

        llm_out = "1. acme funding\n2. acme leadership\n3. acme products\n4. acme extra"
        with patch("primr.data.search_utils.llm", return_value=llm_out):
            queries = generate_search_queries("Acme", "https://acme.com", "Overview")
        assert len(queries) == 3
        assert "acme funding" in queries

    def test_appends_news_query_when_absent(self):
        from primr.data.search_utils import generate_search_queries

        with patch("primr.data.search_utils.llm", return_value="acme products"):
            queries = generate_search_queries("Acme", "https://acme.com", "Products")
        assert any("news" in q.lower() for q in queries)

    def test_splits_or_statements(self):
        from primr.data.search_utils import generate_search_queries

        with patch("primr.data.search_utils.llm", return_value="acme funding OR acme revenue"):
            queries = generate_search_queries("Acme", "https://acme.com", "Finance")
        # OR-split produces two parts
        assert "acme funding" in queries
        assert "acme revenue" in queries

    def test_strips_quotes(self):
        from primr.data.search_utils import generate_search_queries

        with patch("primr.data.search_utils.llm", return_value='"acme news"'):
            queries = generate_search_queries("Acme", "https://acme.com", "News")
        assert all('"' not in q for q in queries)


# =============================================================================
# generate_external_search_queries
# =============================================================================


class TestGenerateExternalSearchQueries:
    def test_includes_recency_lane(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", return_value="Acme tech stack"):
            queries = generate_external_search_queries("Acme", "https://acme.com", max_queries=10)
        assert any("latest news" in q.lower() for q in queries)
        assert all("acme" in q.lower() for q in queries)

    def test_prompt_uses_hostname_without_port_or_embedded_www_corruption(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", return_value="Acme news") as mock_llm:
            generate_external_search_queries(
                "Acme", "https://notwww.example.com:8443/path", max_queries=10
            )

        prompt = mock_llm.call_args.args[0]
        assert "Their website is: notwww.example.com" in prompt
        assert ":8443" not in prompt

    def test_handles_none_company_name(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", return_value="some query"):
            queries = generate_external_search_queries(None, None, max_queries=5)
        assert isinstance(queries, list)
        assert len(queries) <= 5

    def test_llm_failure_falls_back_to_static(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", side_effect=RuntimeError("api down")):
            queries = generate_external_search_queries("Acme", "https://acme.com", max_queries=8)
        # Recency + coverage fallbacks still produce queries even without LLM
        assert len(queries) > 0
        assert all("acme" in q.lower() for q in queries)

    def test_max_queries_clamped_to_at_least_one(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", return_value="q"):
            queries = generate_external_search_queries("Acme", None, max_queries=0)
        assert len(queries) >= 1

    def test_company_name_prepended_when_missing(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", return_value="quarterly earnings outlook"):
            queries = generate_external_search_queries("Acme", "https://acme.com", max_queries=12)
        # All queries should contain the company name
        assert all("acme" in q.lower() for q in queries)

    def test_dedupes_queries(self):
        from primr.data.search_utils import generate_external_search_queries

        with patch("primr.data.search_utils.llm", return_value="Acme news\nAcme news\nAcme news"):
            queries = generate_external_search_queries("Acme", "https://acme.com", max_queries=12)
        lowered = [q.lower() for q in queries]
        assert len(lowered) == len(set(lowered))


# =============================================================================
# Google Custom Search retry / fallback
# =============================================================================


class TestGoogleSearch:
    def test_unavailable_without_keys(self):
        from primr.data.search_utils import _search_google

        with patch("primr.data.search_utils._google_api_available", False):
            assert _search_google("q", "Acme", "https://acme.com") == []

    def test_returns_filtered_results(self):
        from primr.data import search_utils

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {"title": "Good", "link": "https://news.com/acme"},
                {"title": "Bad", "link": "https://reddit.com/r/acme"},
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with (
            patch.object(search_utils, "_google_api_available", True),
            patch.object(search_utils, "SEARCH_API_KEY", "key"),
            patch.object(search_utils, "SEARCH_ENGINE_ID", "cx"),
            patch("requests.get", return_value=mock_resp),
        ):
            results = search_utils._search_google("news", "Acme", "https://acme.com")
        assert len(results) == 1
        assert "news.com" in results[0]["url"]

    def test_empty_items_triggers_retry_then_gives_up(self):
        from primr.data import search_utils

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status.return_value = None

        with (
            patch.object(search_utils, "_google_api_available", True),
            patch.object(search_utils, "SEARCH_API_KEY", "key"),
            patch.object(search_utils, "SEARCH_ENGINE_ID", "cx"),
            patch.object(search_utils, "MAX_RETRIES", 2),
            patch("requests.get", return_value=mock_resp) as mock_get,
        ):
            results = search_utils._search_google("news", "Acme", "https://acme.com")
        assert results == []
        # Retries happened (more than one call)
        assert mock_get.call_count >= 2

    def test_request_exception_handled(self):
        import requests

        from primr.data import search_utils

        with (
            patch.object(search_utils, "_google_api_available", True),
            patch.object(search_utils, "SEARCH_API_KEY", "key"),
            patch.object(search_utils, "SEARCH_ENGINE_ID", "cx"),
            patch.object(search_utils, "MAX_RETRIES", 2),
            patch(
                "requests.get",
                side_effect=requests.exceptions.RequestException("network"),
            ),
        ):
            results = search_utils._search_google("news", "Acme", "https://acme.com")
        assert results == []

    def test_circuit_open_returns_empty(self):
        from primr.data import search_utils

        with (
            patch.object(search_utils, "_google_api_available", True),
            patch.object(search_utils, "SEARCH_API_KEY", "key"),
            patch.object(search_utils, "SEARCH_ENGINE_ID", "cx"),
            patch.object(search_utils._search_circuit, "can_execute", return_value=False),
        ):
            assert search_utils._search_google("q", "Acme", "https://acme.com") == []


# =============================================================================
# _search_ddg circuit breaker open
# =============================================================================


class TestDdgCircuitOpen:
    def test_open_circuit_returns_empty(self):
        from primr.data import search_utils

        with patch.object(search_utils._search_circuit, "can_execute", return_value=False):
            assert search_utils._search_ddg("q", "Acme", "https://acme.com") == []

    def test_ddgs_generic_exception(self):
        from ddgs.exceptions import DDGSException

        from primr.data.search_utils import _search_ddg

        with patch("ddgs.DDGS") as MockDDGS:
            MockDDGS.return_value.text.side_effect = DDGSException("generic error")
            assert _search_ddg("q", "Acme", "https://acme.com") == []


# =============================================================================
# lookup_company_website
# =============================================================================


class TestLookupCompanyWebsite:
    def test_returns_normalized_root_domain(self):
        from primr.data import search_utils

        with (
            patch("ddgs.DDGS") as MockDDGS,
            patch.object(search_utils, "llm", return_value="https://acme.com/about"),
        ):
            MockDDGS.return_value.text.return_value = [
                {"title": "Acme", "href": "https://acme.com"}
            ]
            url = search_utils.lookup_company_website("Acme")
        assert url == "https://acme.com/"

    def test_llm_returns_none_string(self):
        from primr.data import search_utils

        with (
            patch("ddgs.DDGS") as MockDDGS,
            patch.object(search_utils, "llm", return_value="NONE"),
        ):
            MockDDGS.return_value.text.return_value = []
            assert search_utils.lookup_company_website("Obscure Co") is None

    def test_llm_non_url_response_returns_none(self):
        from primr.data import search_utils

        with (
            patch("ddgs.DDGS") as MockDDGS,
            patch.object(search_utils, "llm", return_value="I am not sure"),
        ):
            MockDDGS.return_value.text.return_value = []
            assert search_utils.lookup_company_website("Obscure Co") is None

    def test_context_builds_query_and_hint(self):
        from primr.data import search_utils

        captured_query = {}

        def fake_text(query, max_results=10):
            captured_query["q"] = query
            return [{"title": "Acme", "href": "https://acme.com"}]

        with (
            patch("ddgs.DDGS") as MockDDGS,
            patch.object(search_utils, "llm", return_value="https://acme.com/"),
        ):
            MockDDGS.return_value.text.side_effect = fake_text
            url = search_utils.lookup_company_website(
                "Acme", context={"industry": "Utilities", "Annual Revenue": "$2B"}
            )
        assert url == "https://acme.com/"
        # industry keyword pushed into the query string
        assert "Utilities" in captured_query["q"]

    def test_ignores_nan_context_values(self):
        from primr.data import search_utils

        with (
            patch("ddgs.DDGS") as MockDDGS,
            patch.object(search_utils, "llm", return_value="https://acme.com/"),
        ):
            MockDDGS.return_value.text.return_value = [
                {"title": "Acme", "href": "https://acme.com"}
            ]
            url = search_utils.lookup_company_website(
                "Acme", context={"region": "nan", "sector": ""}
            )
        assert url == "https://acme.com/"

    def test_ddgs_exception_returns_none(self):
        from ddgs.exceptions import DDGSException

        from primr.data import search_utils

        with patch("ddgs.DDGS") as MockDDGS:
            MockDDGS.return_value.text.side_effect = DDGSException("rate limited")
            assert search_utils.lookup_company_website("Acme") is None

    def test_generic_exception_returns_none(self):
        from primr.data import search_utils

        with patch("ddgs.DDGS") as MockDDGS:
            MockDDGS.return_value.text.side_effect = RuntimeError("boom")
            assert search_utils.lookup_company_website("Acme") is None


class TestActiveSearchCostPerQuery:
    """Provider-aware search pricing (bug-hunt finding: free DDG searches were
    recorded at the paid grounding rate, inflating usage history)."""

    def test_ddg_is_free(self, monkeypatch):
        from primr.data import search_utils

        monkeypatch.setattr(search_utils, "SEARCH_PROVIDER", "auto")
        assert search_utils.active_search_cost_per_query() == 0.0

    def test_google_bills_at_configured_rate(self, monkeypatch):
        from primr.config.models import SEARCH_COST_PER_QUERY
        from primr.data import search_utils

        monkeypatch.setattr(search_utils, "SEARCH_PROVIDER", "google")
        monkeypatch.setattr(search_utils, "_google_api_available", True)
        assert search_utils.active_search_cost_per_query() == SEARCH_COST_PER_QUERY

    def test_google_without_keys_falls_back_to_free_ddg(self, monkeypatch):
        from primr.data import search_utils

        monkeypatch.setattr(search_utils, "SEARCH_PROVIDER", "google")
        monkeypatch.setattr(search_utils, "_google_api_available", False)
        assert search_utils.active_search_cost_per_query() == 0.0
