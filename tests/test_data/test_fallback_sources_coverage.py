"""Additional coverage for public-data fallback sources.

Covers the _http_get SSRF gate, subdomain discovery/fetch, EDGAR filing
fetch, Wikipedia article fetch, Grok surrogate path, and the Wayback bridge.
All HTTP, DNS, and LLM access is mocked — no network.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from primr.data.fallback_sources import (
    _http_get,
    discover_live_subdomains,
    fetch_edgar_content,
    fetch_grok_surrogates,
    fetch_latest_edgar_filing,
    fetch_subdomain_content,
    fetch_wikipedia_content,
    find_wikipedia_title,
)

# =============================================================================
# _http_get — SSRF gate + redirect validation
# =============================================================================


class TestHttpGet:
    def test_blocks_unsafe_initial_url(self):
        with patch(
            "primr.utils.security.is_safe_url", return_value=(False, "loopback")
        ):
            status, body, final = _http_get("http://127.0.0.1/")
        assert status is None
        assert body is None
        assert final is None

    def test_blocks_unsafe_final_url_after_redirect(self):
        mock_resp = MagicMock()
        mock_resp.url = "http://169.254.169.254/latest/meta-data"
        mock_resp.status_code = 200
        mock_resp.content = b"secret"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "metadata endpoint"),
            ),
            patch("httpx.Client", return_value=mock_client),
        ):
            status, body, final = _http_get("https://example.com/")
        assert status is None
        assert body is None
        assert final is None

    def test_success_returns_status_body_final(self):
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/page"
        mock_resp.status_code = 200
        mock_resp.content = b"<html>ok</html>"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, ""),
            ),
            patch("httpx.Client", return_value=mock_client),
        ):
            status, body, final = _http_get("https://example.com/")
        assert status == 200
        assert body == b"<html>ok</html>"
        assert final == "https://example.com/page"

    def test_custom_headers_merged(self):
        captured = {}

        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/"
        mock_resp.status_code = 200
        mock_resp.content = b"x"
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client

        def fake_client(**kwargs):
            captured.update(kwargs)
            return mock_client

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, ""),
            ),
            patch("httpx.Client", side_effect=fake_client),
        ):
            _http_get("https://example.com/", headers={"X-Custom": "1"})
        assert captured["headers"]["X-Custom"] == "1"
        # base User-Agent preserved
        assert "User-Agent" in captured["headers"]

    def test_exception_returns_none_tuple(self):
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch("httpx.Client", side_effect=RuntimeError("boom")),
        ):
            status, body, final = _http_get("https://example.com/")
        assert (status, body, final) == (None, None, None)


# =============================================================================
# Subdomain discovery & fetch
# =============================================================================


class TestSubdomainDiscovery:
    def test_discover_live_subdomains_filters_by_resolution(self):
        def fake_resolve(host):
            return host.startswith("investor.")

        with patch("primr.data.fallback_sources._resolve_subdomain", side_effect=fake_resolve):
            live = discover_live_subdomains("example.com")
        assert "investor.example.com" in live
        assert all(h.startswith("investor.") for h in live)

    def test_discover_strips_www_prefix(self):
        with patch("primr.data.fallback_sources._resolve_subdomain", return_value=False):
            live = discover_live_subdomains("www.example.com")
        assert live == []

    def test_fetch_subdomain_content_no_live_subdomains(self):
        with patch(
            "primr.data.fallback_sources.discover_live_subdomains", return_value=[]
        ):
            assert fetch_subdomain_content("example.com") == []

    def test_fetch_subdomain_content_success(self):
        big_body = b"<html><body>" + b"Real corporate content. " * 200 + b"</body></html>"

        with (
            patch(
                "primr.data.fallback_sources.discover_live_subdomains",
                return_value=["investor.example.com"],
            ),
            patch(
                "primr.data.fallback_sources._http_get",
                return_value=(200, big_body, "https://investor.example.com/"),
            ),
            patch(
                "primr.data.scraping.content.extract_main_content",
                return_value="Extracted corporate content " * 50,
            ),
            patch(
                "primr.data.scraping.content.get_page_title",
                return_value="Investor Relations",
            ),
        ):
            pages = fetch_subdomain_content("example.com", max_pages=1)
        assert len(pages) == 1
        assert pages[0].source == "subdomain"
        assert pages[0].title == "Investor Relations"

    def test_fetch_subdomain_skips_small_bodies(self):
        with (
            patch(
                "primr.data.fallback_sources.discover_live_subdomains",
                return_value=["ir.example.com"],
            ),
            patch(
                "primr.data.fallback_sources._http_get",
                return_value=(200, b"tiny", "https://ir.example.com/"),
            ),
        ):
            pages = fetch_subdomain_content("example.com", max_pages=1)
        assert pages == []

    def test_fetch_subdomain_skips_challenge_shell(self):
        # Body large enough to pass size gate but contains a challenge marker.
        body = b"<html>kpsdk " + b"x" * 3000 + b"</html>"
        with (
            patch(
                "primr.data.fallback_sources.discover_live_subdomains",
                return_value=["ir.example.com"],
            ),
            patch(
                "primr.data.fallback_sources._http_get",
                return_value=(200, body, "https://ir.example.com/"),
            ),
        ):
            pages = fetch_subdomain_content("example.com", max_pages=1)
        assert pages == []


# =============================================================================
# EDGAR filing fetch
# =============================================================================


class TestEdgarFiling:
    def test_fetch_latest_filing_returns_matching_form(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K"],
                    "accessionNumber": ["0000-00-000000", "0001-23-456789"],
                    "primaryDocument": ["doc1.htm", "doc2.htm"],
                }
            }
        }

        def fake_http_get(url, **kwargs):
            if "submissions" in url:
                return 200, json.dumps(submissions).encode(), url
            # the archives filing fetch
            return 200, b"<html>filing body</html>", url

        with patch("primr.data.fallback_sources._http_get", side_effect=fake_http_get):
            result = fetch_latest_edgar_filing("0001234567")
        assert result is not None
        filing_url, body = result
        assert "doc2.htm" in filing_url
        assert body == b"<html>filing body</html>"

    def test_fetch_latest_filing_no_submissions(self):
        with patch(
            "primr.data.fallback_sources._http_get", return_value=(404, None, None)
        ):
            assert fetch_latest_edgar_filing("0001234567") is None

    def test_fetch_latest_filing_bad_json(self):
        with patch(
            "primr.data.fallback_sources._http_get",
            return_value=(200, b"not json", None),
        ):
            assert fetch_latest_edgar_filing("0001234567") is None

    def test_fetch_latest_filing_no_matching_form(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["8-K", "DEF 14A"],
                    "accessionNumber": ["0000-00-000000", "0001-23-456789"],
                    "primaryDocument": ["doc1.htm", "doc2.htm"],
                }
            }
        }
        with patch(
            "primr.data.fallback_sources._http_get",
            return_value=(200, json.dumps(submissions).encode(), None),
        ):
            assert fetch_latest_edgar_filing("0001234567") is None

    def test_fetch_edgar_content_no_cik(self):
        with patch("primr.data.fallback_sources.find_edgar_cik", return_value=None):
            assert fetch_edgar_content("Nonexistent Co") == []

    def test_fetch_edgar_content_no_filing(self):
        with (
            patch(
                "primr.data.fallback_sources.find_edgar_cik",
                return_value=("0001234567", "EXMP", "Example Inc"),
            ),
            patch(
                "primr.data.fallback_sources.fetch_latest_edgar_filing", return_value=None
            ),
        ):
            assert fetch_edgar_content("Example Inc") == []

    def test_fetch_edgar_content_thin_filing_skipped(self):
        with (
            patch(
                "primr.data.fallback_sources.find_edgar_cik",
                return_value=("0001234567", "EXMP", "Example Inc"),
            ),
            patch(
                "primr.data.fallback_sources.fetch_latest_edgar_filing",
                return_value=("https://sec.gov/filing", b"<html>x</html>"),
            ),
            patch(
                "primr.data.scraping.content.extract_main_content",
                return_value="too short",
            ),
        ):
            assert fetch_edgar_content("Example Inc") == []

    def test_fetch_edgar_content_truncates_long_filing(self):
        long_text = "Annual report content. " * 5000  # well over 50k chars
        with (
            patch(
                "primr.data.fallback_sources.find_edgar_cik",
                return_value=("0001234567", "EXMP", "Example Inc"),
            ),
            patch(
                "primr.data.fallback_sources.fetch_latest_edgar_filing",
                return_value=("https://sec.gov/filing", b"<html>x</html>"),
            ),
            patch(
                "primr.data.scraping.content.extract_main_content",
                return_value=long_text,
            ),
        ):
            pages = fetch_edgar_content("Example Inc")
        assert len(pages) == 1
        assert pages[0].source == "edgar"
        assert "truncated" in pages[0].content
        assert len(pages[0].content) <= 50_100


# =============================================================================
# Wikipedia
# =============================================================================


class TestWikipedia:
    def test_find_title_search_failure_returns_none(self):
        with patch(
            "primr.data.fallback_sources._http_get", return_value=(500, None, None)
        ):
            assert find_wikipedia_title("Acme") is None

    def test_find_title_bad_json_returns_none(self):
        with patch(
            "primr.data.fallback_sources._http_get",
            return_value=(200, b"not json", None),
        ):
            assert find_wikipedia_title("Acme") is None

    def test_fetch_content_no_title(self):
        with patch(
            "primr.data.fallback_sources.find_wikipedia_title", return_value=None
        ):
            assert fetch_wikipedia_content("Acme") == []

    def test_fetch_content_success(self):
        extract_body = json.dumps(
            {
                "query": {
                    "pages": {
                        "123": {
                            "pageid": 123,
                            "extract": "Acme Inc is a fictional company. " * 50,
                        }
                    }
                }
            }
        ).encode()

        with (
            patch(
                "primr.data.fallback_sources.find_wikipedia_title",
                return_value="Acme Inc",
            ),
            patch(
                "primr.data.fallback_sources._http_get",
                return_value=(200, extract_body, None),
            ),
        ):
            pages = fetch_wikipedia_content("Acme")
        assert len(pages) == 1
        assert pages[0].source == "wikipedia"
        assert "acme_inc" in pages[0].url.lower()

    def test_fetch_content_short_extract_skipped(self):
        extract_body = json.dumps(
            {"query": {"pages": {"1": {"pageid": 1, "extract": "short"}}}}
        ).encode()
        with (
            patch(
                "primr.data.fallback_sources.find_wikipedia_title",
                return_value="Acme",
            ),
            patch(
                "primr.data.fallback_sources._http_get",
                return_value=(200, extract_body, None),
            ),
        ):
            assert fetch_wikipedia_content("Acme") == []

    def test_fetch_content_extract_fetch_failure(self):
        with (
            patch(
                "primr.data.fallback_sources.find_wikipedia_title",
                return_value="Acme",
            ),
            patch(
                "primr.data.fallback_sources._http_get",
                return_value=(503, None, None),
            ),
        ):
            assert fetch_wikipedia_content("Acme") == []


# =============================================================================
# Grok surrogate
# =============================================================================


class TestGrokSurrogates:
    def test_empty_urls_returns_empty(self):
        assert fetch_grok_surrogates([], "Acme") == []

    def test_collects_summaries(self):
        def fake_browse(url, context=None, timeout=None):
            return {"text": "Synthesized summary of the page. " * 20, "citations": ["a"]}

        with patch("primr.ai.grok_client.grok_browse_and_summarize", side_effect=fake_browse):
            pages = fetch_grok_surrogates(["https://example.com/a"], "Acme")
        assert len(pages) == 1
        assert pages[0].source == "grok"
        assert pages[0].metadata["synthesis"] is True

    def test_skips_short_results(self):
        with patch(
            "primr.ai.grok_client.grok_browse_and_summarize",
            return_value={"text": "tiny"},
        ):
            assert fetch_grok_surrogates(["https://example.com/a"], "Acme") == []

    def test_browse_exception_skips_url(self):
        with patch(
            "primr.ai.grok_client.grok_browse_and_summarize",
            side_effect=RuntimeError("boom"),
        ):
            assert fetch_grok_surrogates(["https://example.com/a"], "Acme") == []

    def test_respects_max_pages(self):
        def fake_browse(url, context=None, timeout=None):
            return {"text": "Synthesized summary content here. " * 20}

        urls = [f"https://example.com/{i}" for i in range(5)]
        with patch("primr.ai.grok_client.grok_browse_and_summarize", side_effect=fake_browse):
            pages = fetch_grok_surrogates(urls, "Acme", max_pages=2)
        assert len(pages) == 2
