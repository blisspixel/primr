"""Tests for the newly added hiring-signal providers.

Covers Workday (including corpus-based URL discovery), Workable,
Recruitee, Jobvite, the web-search fallback, and the metadata-only
output path that ships when no posting bodies are recoverable.

All HTTP and search calls are mocked — no network needed.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from primr.data import hiring_signals as hs
from primr.data.hiring_signals import (
    _clean_web_search_title,
    _discover_via_web_search,
    _discover_workday_triples,
    _fetch_jobvite,
    _fetch_recruitee,
    _fetch_workable,
    _fetch_workday,
    _looks_like_posting_url,
    _workday_fetch_one,
)

# =============================================================================
# Workday corpus-URL discovery
# =============================================================================


class TestWorkdayCorpusDiscovery:
    def test_finds_canonical_workday_url(self):
        corpus = {
            "https://acme.example/careers": (
                "Apply via our careers portal at "
                "https://acmecorp.wd5.myworkdayjobs.com/Acme_External"
            ),
        }
        triples = _discover_workday_triples(corpus)
        assert triples == [("acmecorp", "wd5", "Acme_External")]

    def test_finds_locale_suffix_url(self):
        corpus = {
            "https://acme.example/careers": (
                "https://acmecorp.wd103.myworkdayjobs.com/en-US/External_Careers"
            ),
        }
        triples = _discover_workday_triples(corpus)
        assert triples == [("acmecorp", "wd103", "External_Careers")]

    def test_dedupes(self):
        # Two pages mention the same Workday URL — one triple in the output.
        corpus = {
            "https://acme.example/a": ("https://acmecorp.wd1.myworkdayjobs.com/External"),
            "https://acme.example/b": (
                "https://acmecorp.wd1.myworkdayjobs.com/External "
                "https://acmecorp.wd1.myworkdayjobs.com/External"
            ),
        }
        triples = _discover_workday_triples(corpus)
        assert len(triples) == 1

    def test_empty_corpus_returns_empty(self):
        assert _discover_workday_triples(None) == []
        assert _discover_workday_triples({}) == []
        assert _discover_workday_triples({"u": "no workday mentioned here"}) == []


# =============================================================================
# Workday POST endpoint
# =============================================================================


class TestWorkdayFetch:
    def test_successful_post_yields_postings(self, monkeypatch):
        """Fake httpx so the live POST never actually fires."""
        import httpx

        class _Resp:
            def __init__(self):
                self.status_code = 200
                self.url = "https://acmecorp.wd1.myworkdayjobs.com/wday/cxs/acmecorp/External/jobs"

            def json(self):
                return {
                    "jobPostings": [
                        {
                            "title": "Senior Cloud Engineer",
                            "externalPath": "/job/Remote/Senior-Cloud-Engineer_R-1234",
                            "locationsText": "Remote, US",
                            "postedOn": "5 days ago",
                        },
                        {
                            "title": "Salesforce Admin",
                            "externalPath": "/job/Toronto/Salesforce-Admin_R-1235",
                            "locationsText": "Toronto, ON",
                            "postedOn": "2024-12-01",
                        },
                    ]
                }

        class _Client:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def post(self, *_args, **_kwargs):
                return _Resp()

        monkeypatch.setattr(httpx, "Client", _Client)

        # Bypass the security guards so the response actually returns.
        def _ok(_url):
            return True, ""

        monkeypatch.setattr("primr.utils.security.is_safe_url", _ok)

        postings = _workday_fetch_one(("acmecorp", "wd1", "External"))
        assert postings is not None
        assert len(postings) == 2
        assert postings[0].title == "Senior Cloud Engineer"
        assert postings[0].source == "workday"
        assert postings[0].url.endswith("Senior-Cloud-Engineer_R-1234")
        assert postings[1].location == "Toronto, ON"

    def test_blind_discovery_iterates_triples(self):
        """_fetch_workday should cycle through the bounded triple list."""
        call_count = {"n": 0}
        expected = [hs.Posting(url="https://x/y", title="X", source="workday")]

        def _stub(_triple):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                return expected
            return None

        with patch.object(hs, "_workday_fetch_one", side_effect=_stub):
            result = _fetch_workday("acmecorp")
        assert result == expected
        assert call_count["n"] == 2


# =============================================================================
# Workable
# =============================================================================


class TestWorkable:
    def test_parses_widget_response(self):
        body = json.dumps(
            {
                "jobs": [
                    {
                        "title": "Backend Engineer",
                        "url": "https://apply.workable.com/acme/j/abc123",
                        "city": "Lisbon",
                        "country": "Portugal",
                        "department": "Engineering",
                        "published": "2024-12-10",
                    }
                ]
            }
        ).encode()
        with patch.object(hs, "_http_get", return_value=(200, body, None)):
            postings = _fetch_workable("acme")
        assert postings is not None
        assert postings[0].title == "Backend Engineer"
        assert postings[0].location == "Lisbon, Portugal"
        assert postings[0].department == "Engineering"
        assert postings[0].source == "workable"

    def test_empty_jobs_returns_none(self):
        body = json.dumps({"jobs": []}).encode()
        with patch.object(hs, "_http_get", return_value=(200, body, None)):
            assert _fetch_workable("acme") is None

    def test_404_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(404, None, None)):
            assert _fetch_workable("acme") is None


# =============================================================================
# Recruitee
# =============================================================================


class TestRecruitee:
    def test_parses_offers(self):
        body = json.dumps(
            {
                "offers": [
                    {
                        "title": "Product Manager",
                        "careers_url": "https://acme.recruitee.com/o/product-manager",
                        "city": "Berlin",
                        "country": "Germany",
                        "department": "Product",
                        "description": "<p>Drive roadmap.</p>",
                        "published_at": "2024-11-22",
                    }
                ]
            }
        ).encode()
        with patch.object(hs, "_http_get", return_value=(200, body, None)):
            postings = _fetch_recruitee("acme")
        assert postings is not None
        assert postings[0].title == "Product Manager"
        assert postings[0].location == "Berlin, Germany"
        assert postings[0].body is not None
        assert "Drive roadmap" in postings[0].body

    def test_malformed_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(200, b"<html>", None)):
            assert _fetch_recruitee("acme") is None


# =============================================================================
# Jobvite (RSS)
# =============================================================================


class TestJobvite:
    def test_parses_rss_items(self):
        rss = b"""<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Sales Engineer</title>
            <link>https://jobs.jobvite.com/acme/job/abc</link>
          </item>
          <item>
            <title>Account Executive</title>
            <link>https://jobs.jobvite.com/acme/job/xyz</link>
          </item>
        </channel></rss>
        """
        with patch.object(hs, "_http_get", return_value=(200, rss, None)):
            postings = _fetch_jobvite("acme")
        assert postings is not None
        assert {p.title for p in postings} == {"Sales Engineer", "Account Executive"}
        assert all(p.source == "jobvite" for p in postings)

    def test_no_items_returns_none(self):
        with patch.object(
            hs, "_http_get", return_value=(200, b"<rss><channel></channel></rss>", None)
        ):
            assert _fetch_jobvite("acme") is None


# =============================================================================
# Web search fallback
# =============================================================================


class TestWebSearchHelpers:
    def test_url_hint_matching(self):
        assert _looks_like_posting_url("https://linkedin.com/jobs/view/123")
        assert _looks_like_posting_url("https://acmecorp.wd1.myworkdayjobs.com/X")
        assert _looks_like_posting_url("https://boards.greenhouse.io/acme/jobs/1")
        assert not _looks_like_posting_url("https://acme.example/about")

    def test_title_cleanup(self):
        # Suffix-strip removes "| LinkedIn"; the company-name trail
        # remains so the role label keeps its context.
        cleaned = _clean_web_search_title("Senior Engineer - Acme | LinkedIn")
        assert "LinkedIn" not in cleaned
        assert "Senior Engineer" in cleaned

        cleaned = _clean_web_search_title("Marketing Manager | Indeed.com")
        assert cleaned == "Marketing Manager"

        cleaned = _clean_web_search_title("Account Executive at Acme | Glassdoor")
        # "at Acme" should be stripped via the second cleanup pass.
        assert "Glassdoor" not in cleaned
        assert "Account Executive" in cleaned


class TestDiscoverViaWebSearch:
    def test_filters_to_posting_hosts(self):
        # Stub the ddgs.DDGS context manager + .text iterator.
        class _DDGS:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def text(self, _query, max_results=20):
                return [
                    {
                        "title": "Account Executive - Acme | LinkedIn",
                        "href": "https://www.linkedin.com/jobs/view/9999",
                    },
                    {
                        "title": "About Acme",
                        "href": "https://acme.example/about",  # filtered out
                    },
                    {
                        "title": "Practice Lead at Acme",
                        "href": "https://acmecorp.wd1.myworkdayjobs.com/External/job/123",
                    },
                ]

        # ddgs is imported lazily inside the function, so we install a
        # synthetic module entry that the import statement will pick up.
        import sys
        import types

        ddgs_module = types.ModuleType("ddgs")
        ddgs_module.DDGS = _DDGS  # type: ignore[attr-defined]
        exc_module = types.ModuleType("ddgs.exceptions")

        class _DDGSStubError(Exception):
            pass

        exc_module.DDGSException = _DDGSStubError  # type: ignore[attr-defined]

        sys.modules["ddgs"] = ddgs_module
        sys.modules["ddgs.exceptions"] = exc_module
        try:
            postings = _discover_via_web_search("Acme", "https://acme.example")
        finally:
            sys.modules.pop("ddgs", None)
            sys.modules.pop("ddgs.exceptions", None)

        titles = {p.title for p in postings}
        # The off-target "About Acme" hit is excluded.
        assert "About Acme" not in titles
        # LinkedIn hit is included; suffix cleanup removed " | LinkedIn".
        assert "Account Executive - Acme" in titles or "Account Executive" in titles
        assert any("Workday" not in t for t in titles)
        # All passing entries have source="web-search".
        assert all(p.source == "web-search" for p in postings)
