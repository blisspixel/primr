"""
Comprehensive tests for external source search and validation.

These tests ensure the external source pipeline is bulletproof:
1. Search queries are constructed correctly
2. Low-value sites are filtered out
3. Content is extracted cleanly
4. LLM validation correctly identifies the target company
5. Errors are handled gracefully without silent failures
"""
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Reset circuit breaker before each test."""
    from primr.data.search_utils import _search_circuit
    _search_circuit._failure_count = 0
    _search_circuit._state = "closed"
    _search_circuit._last_failure_time = None
    yield
    # Reset after test too
    _search_circuit._failure_count = 0
    _search_circuit._state = "closed"
    _search_circuit._last_failure_time = None


class TestSearchQueryConstruction:
    """Test that search queries are built correctly (Google provider)."""

    def test_query_includes_company_name(self):
        """Company name should be prepended to query."""
        from primr.data.search_utils import _search_google

        with patch('primr.data.search_utils._google_api_available', True), \
             patch('primr.data.search_utils.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"items": []}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            _search_google("news", "Acme Corp", "https://acme.com")

            # Check the query parameter
            call_args = mock_get.call_args
            params = call_args[1]["params"]
            assert "Acme Corp" in params["q"]
            assert "news" in params["q"]

    def test_site_filter_uses_domain_not_url(self):
        """The -site: filter should use domain, not full URL."""
        from primr.data.search_utils import _search_google

        with patch('primr.data.search_utils._google_api_available', True), \
             patch('primr.data.search_utils.requests.get') as mock_get:
            mock_response = Mock()
            # Return actual items so we don't hit fallback path
            mock_response.json.return_value = {
                "items": [{"link": "https://example.com/article", "title": "Test"}]
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            _search_google("news", "Acme Corp", "https://www.acme.com/path/page")

            # Get the FIRST call's params (before any fallback)
            first_call = mock_get.call_args_list[0]
            params = first_call[1]["params"]
            # Should be -site:acme.com, NOT -site:https://www.acme.com/path/page
            assert "-site:acme.com" in params["q"]
            assert "https://" not in params["q"]
            assert "/path" not in params["q"]

    def test_site_filter_strips_www(self):
        """The -site: filter should strip www prefix."""
        from primr.data.search_utils import _search_google

        with patch('primr.data.search_utils._google_api_available', True), \
             patch('primr.data.search_utils.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "items": [{"link": "https://example.com/article", "title": "Test"}]
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            _search_google("news", "Test Co", "https://www.example.com")

            first_call = mock_get.call_args_list[0]
            params = first_call[1]["params"]
            assert "-site:example.com" in params["q"]
            # Check www is not in the site filter part
            site_part = params["q"].split("-site:")[1] if "-site:" in params["q"] else ""
            assert not site_part.startswith("www.")

    def test_no_site_filter_when_no_website(self):
        """No -site: filter when website is None or empty."""
        from primr.data.search_utils import _search_google

        with patch('primr.data.search_utils._google_api_available', True), \
             patch('primr.data.search_utils.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"items": []}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            _search_google("news", "Test Co", None)

            call_args = mock_get.call_args
            params = call_args[1]["params"]
            assert "-site:" not in params["q"]


class TestExcludedSites:
    """Test that low-value sites are filtered out."""

    def test_social_media_excluded(self):
        """Social media sites should be filtered out."""
        from primr.data.search_utils import EXCLUDED_SITES

        social_sites = ["reddit.com", "facebook.com", "twitter.com", "x.com",
                       "instagram.com", "tiktok.com", "linkedin.com", "youtube.com"]

        for site in social_sites:
            assert site in EXCLUDED_SITES, f"{site} should be in EXCLUDED_SITES"

    def test_job_sites_excluded(self):
        """Job/review sites should be filtered out."""
        from primr.data.search_utils import EXCLUDED_SITES

        job_sites = ["glassdoor.com", "indeed.com"]

        for site in job_sites:
            assert site in EXCLUDED_SITES, f"{site} should be in EXCLUDED_SITES"

    def test_support_patterns_excluded(self):
        """Support/help subdomains should be filtered out."""
        from primr.data.search_utils import EXCLUDED_SITES

        # These are patterns, not full domains
        support_patterns = ["support.", "help.", "community.", "forum."]

        for pattern in support_patterns:
            assert pattern in EXCLUDED_SITES, f"{pattern} should be in EXCLUDED_SITES"

    def test_excluded_sites_filter_works(self):
        """Verify excluded sites are actually filtered from results (Google provider)."""
        from primr.data.search_utils import _search_google

        mock_items = [
            {"link": "https://www.businesswire.com/news/article", "title": "Good"},
            {"link": "https://www.reddit.com/r/company", "title": "Bad"},
            {"link": "https://techcrunch.com/article", "title": "Good"},
            {"link": "https://support.company.com/help", "title": "Bad"},
            {"link": "https://www.youtube.com/watch", "title": "Bad"},
        ]

        with patch('primr.data.search_utils._google_api_available', True), \
             patch('primr.data.search_utils.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"items": mock_items}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            results = _search_google("news", "Test Co", "https://test.com")

            # Should only have businesswire and techcrunch
            urls = [r["url"] for r in results]
            assert len(urls) == 2
            assert any("businesswire.com" in u for u in urls)
            assert any("techcrunch.com" in u for u in urls)


class TestDomainFiltering:
    """Test domain filtering in scrape_external_sources_validated."""

    def test_exact_domain_filtered(self):
        """Exact domain match should be filtered."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://acme.com/news", "title": "Acme News"},
            {"url": "https://www.acme.com/about", "title": "About Acme"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_orch.return_value.scrape_url.return_value = Mock(
                success=True,
                extracted_text="Some content about Acme"
            )

            # Both should be filtered - they're the main site
            result = scrape_external_sources_validated(
                search_results,
                company_name="Acme Corp",
                website="https://www.acme.com",
                max_sources=2
            )

            # No results because all were filtered
            assert len(result) == 0

    def test_subdomains_not_filtered(self):
        """Subdomains like investors.company.com should NOT be filtered."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://investors.acme.com/news", "title": "Investor News"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_result = Mock()
            mock_result.success = True
            # Content must be > 100 chars
            mock_result.extracted_text = "This is about Acme Corp at acme.com with detailed content about their products and services. " * 5
            mock_orch.return_value.scrape_url.return_value = mock_result

            # Call the function - it will fail at LLM validation but we just want to verify
            # the subdomain wasn't filtered out before scraping
            result = scrape_external_sources_validated(
                search_results,
                company_name="Acme Corp",
                website="https://www.acme.com",
                max_sources=2
            )

            # The scrape should have been attempted (subdomain not filtered)
            # This proves the domain filter didn't block investors.acme.com
            mock_orch.return_value.scrape_url.assert_called_once_with("https://investors.acme.com/news")

    def test_third_party_sites_not_filtered(self):
        """Third-party news sites should NOT be filtered."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://businesswire.com/news/acme", "title": "Acme Press Release"},
            {"url": "https://techcrunch.com/acme-funding", "title": "Acme Raises $10M"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_result = Mock()
            mock_result.success = True
            mock_result.extracted_text = "Acme Corp (acme.com) announced today..." + "x" * 200
            mock_orch.return_value.scrape_url.return_value = mock_result

            with patch('primr.ai.llm.llm') as mock_llm:
                mock_llm.return_value = "YES\nMentions acme.com domain"

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="Acme Corp",
                    website="https://www.acme.com",
                    max_sources=2
                )

                assert len(result) == 2


class TestContentExtraction:
    """Test that content is extracted cleanly."""

    def test_html_noise_removed(self):
        """Script, style, and nav tags should be removed."""
        from primr.data.scraping.content import extract_clean_text

        html = b"""
        <html>
        <head>
            <script>var x = 1;</script>
            <style>.foo { color: red; }</style>
        </head>
        <body>
            <nav>Home | About | Contact</nav>
            <main>
                <h1>Important Article</h1>
                <p>This is the actual content we want.</p>
            </main>
            <footer>Copyright 2024</footer>
        </body>
        </html>
        """

        text = extract_clean_text(html, mode="aggressive")

        assert "var x = 1" not in text
        assert "color: red" not in text
        assert "Important Article" in text
        assert "actual content" in text

    def test_consecutive_duplicates_removed(self):
        """Consecutive duplicate lines should be deduplicated."""
        from primr.data.scraping.content import extract_clean_text

        html = b"""
        <html><body>
            <p>Line one</p>
            <p>Line one</p>
            <p>Line one</p>
            <p>Line two</p>
        </body></html>
        """

        text = extract_clean_text(html)
        lines = [l for l in text.split("\n") if l.strip()]

        # Should only have 2 unique lines
        assert lines.count("Line one") == 1
        assert lines.count("Line two") == 1

    def test_empty_html_returns_empty_string(self):
        """Empty or None HTML should return empty string."""
        from primr.data.scraping.content import extract_clean_text

        assert extract_clean_text(b"") == ""
        assert extract_clean_text(None) == ""


class TestLLMValidation:
    """Test LLM validation logic for company identification."""

    def test_validation_uses_domain_as_identifier(self):
        """LLM prompt should use domain as definitive identifier."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://news.com/article", "title": "Article"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_result = Mock()
            mock_result.success = True
            mock_result.extracted_text = "Content about some company" + "x" * 200
            mock_orch.return_value.scrape_url.return_value = mock_result

            with patch('primr.ai.llm.llm') as mock_llm:
                mock_llm.return_value = "NO\nDifferent company"

                scrape_external_sources_validated(
                    search_results,
                    company_name="Acme Corp",
                    website="https://www.acme.com",
                    max_sources=1
                )

                # Check the prompt includes domain
                call_args = mock_llm.call_args[0][0]
                assert "acme.com" in call_args

    def test_validation_rejects_wrong_company(self):
        """Articles about different companies should be rejected."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://news.com/article", "title": "EverTrue Senior Living"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_result = Mock()
            mock_result.success = True
            mock_result.extracted_text = "EverTrue Senior Living at evertrue-living.com announced..." + "x" * 200
            mock_orch.return_value.scrape_url.return_value = mock_result

            with patch('primr.ai.llm.llm') as mock_llm:
                # LLM says NO - different company
                mock_llm.return_value = "NO\nThis is about EverTrue Senior Living, not EverTrue fundraising software"

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="EverTrue",
                    website="https://www.evertrue.com",
                    max_sources=1
                )

                assert len(result) == 0

    def test_validation_accepts_correct_company(self):
        """Articles about the target company should be accepted."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://businesswire.com/article", "title": "Acme Corp Funding"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_result = Mock()
            mock_result.success = True
            mock_result.extracted_text = "Acme Corp (www.acme.com) today announced $10M in funding..." + "x" * 200
            mock_orch.return_value.scrape_url.return_value = mock_result

            with patch('primr.ai.llm.llm') as mock_llm:
                mock_llm.return_value = "YES\nMentions www.acme.com domain directly"

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="Acme Corp",
                    website="https://www.acme.com",
                    max_sources=1
                )

                assert len(result) == 1
                assert "businesswire.com" in list(result.keys())[0]


class TestErrorHandling:
    """Test graceful error handling."""

    def test_scrape_failure_skipped_gracefully(self):
        """Failed scrapes should be skipped, not crash."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://failing-site.com/article", "title": "Will Fail"},
            {"url": "https://working-site.com/article", "title": "Will Work"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            def scrape_side_effect(url):
                if "failing" in url:
                    return Mock(success=False, extracted_text=None)
                return Mock(success=True, extracted_text="Good content about Acme at acme.com" + "x" * 200)

            mock_orch.return_value.scrape_url.side_effect = scrape_side_effect

            with patch('primr.ai.llm.llm') as mock_llm:
                mock_llm.return_value = "YES\nCorrect company"

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="Acme",
                    website="https://acme.com",
                    max_sources=2
                )

                # Should have 1 result (the working one)
                assert len(result) == 1
                assert "working-site.com" in list(result.keys())[0]

    def test_llm_failure_skipped_gracefully(self):
        """LLM validation failures should skip the source, not crash."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://site1.com/article", "title": "Article 1"},
            {"url": "https://site2.com/article", "title": "Article 2"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_orch.return_value.scrape_url.return_value = Mock(
                success=True,
                extracted_text="Content about Acme at acme.com" + "x" * 200
            )

            with patch('primr.ai.llm.llm') as mock_llm:
                call_count = [0]
                def llm_side_effect(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        raise Exception("LLM API error")
                    return "YES\nCorrect company"

                mock_llm.side_effect = llm_side_effect

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="Acme",
                    website="https://acme.com",
                    max_sources=2
                )

                # Should have 1 result (the second one that didn't fail)
                assert len(result) == 1

    def test_short_content_skipped(self):
        """Content under 100 chars should be skipped."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": "https://site.com/short", "title": "Short"},
            {"url": "https://site.com/long", "title": "Long"},
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            def scrape_side_effect(url):
                if "short" in url:
                    return Mock(success=True, extracted_text="Too short")
                return Mock(success=True, extracted_text="A" * 200 + " about Acme at acme.com")

            mock_orch.return_value.scrape_url.side_effect = scrape_side_effect

            with patch('primr.ai.llm.llm') as mock_llm:
                mock_llm.return_value = "YES\nCorrect"

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="Acme",
                    website="https://acme.com",
                    max_sources=2
                )

                # Only the long content should pass
                assert len(result) == 1
                assert "long" in list(result.keys())[0]

    def test_empty_search_results_returns_empty(self):
        """Empty search results should return empty dict."""
        from primr.data.scrape import scrape_external_sources_validated

        result = scrape_external_sources_validated(
            [],
            company_name="Acme",
            website="https://acme.com",
            max_sources=2
        )

        assert result == {}

    def test_max_sources_respected(self):
        """Should stop after max_sources validated."""
        from primr.data.scrape import scrape_external_sources_validated

        search_results = [
            {"url": f"https://site{i}.com/article", "title": f"Article {i}"}
            for i in range(10)
        ]

        with patch('primr.data.scrape.get_orchestrator') as mock_orch:
            mock_orch.return_value.scrape_url.return_value = Mock(
                success=True,
                extracted_text="Good content about Acme at acme.com " * 20
            )

            with patch('primr.ai.llm.llm') as mock_llm:
                mock_llm.return_value = "YES\nCorrect"

                result = scrape_external_sources_validated(
                    search_results,
                    company_name="Acme",
                    website="https://acme.com",
                    max_sources=3
                )

                assert len(result) == 3


class TestContentValidation:
    """Test content validation functions."""

    def test_validate_content_rejects_short(self):
        """Short content should be invalid."""
        from primr.data.scraping.validation import validate_content

        result = validate_content("Short", "https://example.com")
        assert not result.valid

    def test_validate_content_accepts_good_content(self):
        """Good content should be valid."""
        from primr.data.scraping.validation import validate_content

        good_content = """
        This is a substantial article about a company.
        It contains multiple paragraphs with real information.
        The content discusses products, services, and business strategy.
        There are details about leadership and market position.
        """ * 5  # Make it long enough

        result = validate_content(good_content, "https://example.com")
        assert result.valid

    def test_nav_only_detection(self):
        """Navigation-only pages should be detected."""
        from primr.data.scraping.validation import is_nav_only_page

        nav_content = "Home About Contact Products Services Login"
        assert is_nav_only_page(nav_content)

        real_content = """
        This is a real article with substantial content.
        It discusses important business topics in detail.
        The company announced new products and services.
        """ * 3
        assert not is_nav_only_page(real_content)


class TestCircuitBreaker:
    """Test circuit breaker behavior for search API."""

    def test_circuit_breaker_records_failures(self):
        """Circuit breaker should record failures from API errors (Google provider)."""
        from requests.exceptions import RequestException

        from primr.data.search_utils import _search_circuit, _search_google

        initial_failures = _search_circuit._failure_count

        with patch('primr.data.search_utils._google_api_available', True), \
             patch('primr.data.search_utils.requests.get') as mock_get:
            # Simulate request exception (the type that triggers circuit breaker)
            mock_get.side_effect = RequestException("API Error")

            # Make a failing call
            result = _search_google("test", "Test Co", "https://test.com")

            # Should return empty
            assert result == []
            # Failure count should have increased
            assert _search_circuit._failure_count > initial_failures or _search_circuit._state == "open"


class TestDDGSearch:
    """Test DuckDuckGo search provider."""

    def test_ddg_returns_structured_results(self):
        """DDG results should have title and url keys."""
        from primr.data.search_utils import _search_ddg

        mock_ddg_results = [
            {"title": "Acme Corp News", "href": "https://news.com/acme", "body": "..."},
            {"title": "Acme Funding", "href": "https://techcrunch.com/acme", "body": "..."},
        ]

        with patch('ddgs.DDGS') as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_ddg_results

            results = _search_ddg("news", "Acme Corp", "https://acme.com")

            assert len(results) == 2
            assert results[0]["title"] == "Acme Corp News"
            assert results[0]["url"] == "https://news.com/acme"
            assert results[1]["url"] == "https://techcrunch.com/acme"

    def test_ddg_excludes_low_value_sites(self):
        """DDG should filter excluded sites."""
        from primr.data.search_utils import _search_ddg

        mock_ddg_results = [
            {"title": "Good", "href": "https://businesswire.com/article", "body": "..."},
            {"title": "Bad", "href": "https://reddit.com/r/company", "body": "..."},
            {"title": "Bad", "href": "https://youtube.com/watch", "body": "..."},
        ]

        with patch('ddgs.DDGS') as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_ddg_results

            results = _search_ddg("news", "Test Co", "https://test.com")

            assert len(results) == 1
            assert "businesswire.com" in results[0]["url"]

    def test_ddg_excludes_company_domain(self):
        """DDG should filter out company's own domain."""
        from primr.data.search_utils import _search_ddg

        mock_ddg_results = [
            {"title": "Own Site", "href": "https://acme.com/about", "body": "..."},
            {"title": "News", "href": "https://news.com/acme-article", "body": "..."},
        ]

        with patch('ddgs.DDGS') as MockDDGS:
            MockDDGS.return_value.text.return_value = mock_ddg_results

            results = _search_ddg("news", "Acme Corp", "https://www.acme.com")

            assert len(results) == 1
            assert "news.com" in results[0]["url"]

    def test_ddg_handles_rate_limit(self):
        """DDG rate limit should return empty and record failure."""
        from ddgs.exceptions import RatelimitException

        from primr.data.search_utils import _search_circuit, _search_ddg

        initial_failures = _search_circuit._failure_count

        with patch('ddgs.DDGS') as MockDDGS:
            MockDDGS.return_value.text.side_effect = RatelimitException("rate limited")

            results = _search_ddg("test", "Test Co", "https://test.com")

            assert results == []
            assert _search_circuit._failure_count > initial_failures or _search_circuit._state == "open"

    def test_ddg_handles_timeout(self):
        """DDG timeout should return empty."""
        from ddgs.exceptions import TimeoutException

        from primr.data.search_utils import _search_ddg

        with patch('ddgs.DDGS') as MockDDGS:
            MockDDGS.return_value.text.side_effect = TimeoutException("timeout")

            results = _search_ddg("test", "Test Co", "https://test.com")

            assert results == []


class TestSearchProviderDispatch:
    """Test search_web dispatches to correct provider."""

    def test_default_uses_ddg(self):
        """Default provider should be DDG."""
        from primr.data.search_utils import _get_active_provider

        with patch('primr.data.search_utils.SEARCH_PROVIDER', 'auto'):
            assert _get_active_provider() == "ddg"

    def test_google_with_keys_uses_google(self):
        """SEARCH_PROVIDER=google with keys should use Google."""
        from primr.data.search_utils import _get_active_provider

        with patch('primr.data.search_utils.SEARCH_PROVIDER', 'google'), \
             patch('primr.data.search_utils._google_api_available', True):
            assert _get_active_provider() == "google"

    def test_google_without_keys_falls_back_to_ddg(self):
        """SEARCH_PROVIDER=google without keys should fall back to DDG."""
        from primr.data.search_utils import _get_active_provider

        with patch('primr.data.search_utils.SEARCH_PROVIDER', 'google'), \
             patch('primr.data.search_utils._google_api_available', False):
            assert _get_active_provider() == "ddg"

    def test_search_web_dispatches_to_ddg(self):
        """search_web should call _search_ddg when provider is DDG."""
        from primr.data.search_utils import search_web

        with patch('primr.data.search_utils._get_active_provider', return_value='ddg'), \
             patch('primr.data.search_utils._search_ddg', return_value=[{"title": "T", "url": "U"}]) as mock_ddg:
            results = search_web("test", "Test Co", "https://test.com")
            mock_ddg.assert_called_once()
            assert len(results) == 1

    def test_search_web_dispatches_to_google(self):
        """search_web should call _search_google when provider is Google."""
        from primr.data.search_utils import search_web

        with patch('primr.data.search_utils._get_active_provider', return_value='google'), \
             patch('primr.data.search_utils._search_google', return_value=[{"title": "T", "url": "U"}]) as mock_google:
            results = search_web("test", "Test Co", "https://test.com")
            mock_google.assert_called_once()
            assert len(results) == 1

    def test_search_google_alias_works(self):
        """search_google backward compatibility alias should work."""
        from primr.data.search_utils import search_google, search_web
        assert search_google is search_web
