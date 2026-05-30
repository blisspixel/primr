"""Tests for subdomain probing, ATS-redirect detection, and the
broadened posting-link regex.

All HTTP calls mocked — no network required.
"""

from __future__ import annotations

from unittest.mock import patch

from primr.data import hiring_signals as hs
from primr.data.hiring_signals import (
    _CAREERS_SUBDOMAIN_PREFIXES,
    _POSTING_URL_HINTS,
    _WORKDAY_BLIND_DISCOVERY_BUDGET,
    _careers_url_candidates,
    _detect_ats_redirect,
    _discover_via_html,
)

# =============================================================================
# Subdomain candidates
# =============================================================================


class TestCareersUrlCandidates:
    def test_subdomain_probes_included(self):
        urls = _careers_url_candidates("https://acme.example", corpus=None)
        # All six subdomain prefixes should be probed.
        for prefix in _CAREERS_SUBDOMAIN_PREFIXES:
            expected = f"https://{prefix}.acme.example/"
            assert expected in urls, f"missing subdomain candidate: {expected}"

    def test_subdomain_probes_first(self):
        urls = _careers_url_candidates("https://acme.example", corpus=None)
        # Subdomain probes come before on-path probes.
        first_subdomain = next(
            (i for i, u in enumerate(urls) if u.startswith("https://jobs.")),
            None,
        )
        first_on_path = next(
            (i for i, u in enumerate(urls) if "/careers" in u and "://acme" in u),
            None,
        )
        assert first_subdomain is not None
        assert first_on_path is not None
        assert first_subdomain < first_on_path

    def test_www_stripped_before_subdomain(self):
        urls = _careers_url_candidates("https://www.acme.example", corpus=None)
        assert "https://jobs.acme.example/" in urls

    def test_corpus_subdomain_urls_promoted(self):
        corpus = {
            "https://jobs.acme.example/listing/123": "...",
            "https://acme.example/about": "...",
        }
        urls = _careers_url_candidates("https://acme.example", corpus=corpus)
        assert "https://jobs.acme.example/listing/123" in urls
        assert "https://acme.example/about" not in urls

    def test_cap_respected(self):
        urls = _careers_url_candidates("https://acme.example", corpus=None)
        assert len(urls) <= 14


# =============================================================================
# Broadened posting-link regex
# =============================================================================


class TestPostingUrlHints:
    def test_matches_existing_patterns(self):
        # Original patterns still match.
        for path in ["/jobs/abc", "/careers/sr-eng", "/positions/123", "/openings/data"]:
            assert _POSTING_URL_HINTS.search(path), f"missed: {path}"

    def test_matches_new_patterns(self):
        # Broadened patterns.
        for path in [
            "/apply/abc-123",
            "/role/senior-eng",
            "/open-roles/data-engineer",
            "/open_roles/data-engineer",
            "/talent/123",
            "/listing/sr",
            "/listings/sr-eng",
            "/open-positions/123",
        ]:
            assert _POSTING_URL_HINTS.search(path), f"new pattern missed: {path}"

    def test_does_not_match_non_posting_paths(self):
        for path in ["/about", "/", "/blog/post"]:
            assert not _POSTING_URL_HINTS.search(path), f"false positive: {path}"


# =============================================================================
# ATS-redirect detection
# =============================================================================


class TestDetectAtsRedirect:
    def test_workday_url_extracts_triple(self):
        with patch.object(hs, "_workday_fetch_one") as mock_fetch:
            mock_fetch.return_value = [
                hs.Posting(url="https://x", title="Eng", source="workday")
            ]
            result = _detect_ats_redirect(
                "https://acmecorp.wd5.myworkdayjobs.com/External_Careers"
            )
        assert result is not None
        provider, postings = result
        assert provider == "workday"
        assert len(postings) == 1
        # Verify the extracted triple matches what we expect.
        mock_fetch.assert_called_once_with(("acmecorp", "wd5", "External_Careers"))

    def test_workday_locale_prefix(self):
        with patch.object(hs, "_workday_fetch_one") as mock_fetch:
            mock_fetch.return_value = [
                hs.Posting(url="https://x", title="Eng", source="workday")
            ]
            _detect_ats_redirect(
                "https://acmecorp.wd1.myworkdayjobs.com/en-US/External"
            )
        mock_fetch.assert_called_once_with(("acmecorp", "wd1", "External"))

    def test_greenhouse_redirect(self):
        with patch.object(hs, "_fetch_greenhouse") as mock_fetch:
            mock_fetch.return_value = [
                hs.Posting(url="https://x", title="Eng", source="greenhouse")
            ]
            result = _detect_ats_redirect("https://boards.greenhouse.io/acmecorp")
        assert result is not None
        provider, postings = result
        assert provider == "greenhouse"
        mock_fetch.assert_called_once_with("acmecorp")

    def test_recruitee_redirect_extracts_subdomain_slug(self):
        with patch.object(hs, "_fetch_recruitee") as mock_fetch:
            mock_fetch.return_value = [
                hs.Posting(url="https://x", title="Eng", source="recruitee")
            ]
            result = _detect_ats_redirect("https://acmecorp.recruitee.com/offers")
        assert result is not None
        provider, _ = result
        assert provider == "recruitee"
        mock_fetch.assert_called_once_with("acmecorp")

    def test_non_ats_url_returns_none(self):
        result = _detect_ats_redirect("https://acme.example/careers/123")
        assert result is None

    def test_empty_url_returns_none(self):
        assert _detect_ats_redirect("") is None

    def test_workday_with_no_provider_response_returns_none(self):
        with patch.object(hs, "_workday_fetch_one", return_value=None):
            result = _detect_ats_redirect(
                "https://acmecorp.wd5.myworkdayjobs.com/External"
            )
        assert result is None


# =============================================================================
# _discover_via_html with redirect short-circuit
# =============================================================================


class TestDiscoverViaHtmlRedirectShortCircuit:
    def test_redirect_to_workday_short_circuits(self):
        # Subdomain probe lands at an httpx final-URL that's a Workday board.
        def _http_get_stub(url, timeout, headers=None, params=None):
            if "jobs.acme.example" in url:
                # Redirect chain to Workday final URL.
                return (
                    200,
                    b"<html></html>",
                    "https://acmecorp.wd5.myworkdayjobs.com/External",
                )
            return (404, None, None)

        with (
            patch.object(hs, "_http_get", side_effect=_http_get_stub),
            patch.object(hs, "_workday_fetch_one") as mock_fetch,
        ):
            mock_fetch.return_value = [
                hs.Posting(
                    url="https://acmecorp.wd5.myworkdayjobs.com/job/1",
                    title="Eng",
                    source="workday",
                )
            ]
            postings, source = _discover_via_html(
                "https://acme.example", corpus=None
            )

        assert source == "workday"
        assert len(postings) == 1
        # We short-circuited on the very first matching probe — confirm
        # by checking the Workday handler was called exactly once.
        assert mock_fetch.call_count == 1

    def test_no_redirect_falls_through_to_html(self):
        html = (
            b"<a href='/jobs/role-1'>Engineer</a>"
            b"<a href='/jobs/role-2'>PM</a>"
        )

        def _http_get_stub(url, timeout, headers=None, params=None):
            # jobs.acme returns html, no redirect (final URL == request URL).
            if "jobs.acme.example" in url:
                return 200, html, "https://jobs.acme.example/"
            return 404, None, None

        with patch.object(hs, "_http_get", side_effect=_http_get_stub):
            postings, source = _discover_via_html(
                "https://acme.example", corpus=None
            )
        assert source == "html"
        assert len(postings) == 2

    def test_all_misses_returns_empty(self):
        with patch.object(hs, "_http_get", return_value=(404, None, None)):
            postings, source = _discover_via_html(
                "https://acme.example", corpus=None
            )
        assert postings == []
        assert source is None


# =============================================================================
# Workday blind discovery probe budget
# =============================================================================


class TestWorkdayProbeBudget:
    def test_blind_discovery_caps_at_budget(self):
        # When every probe misses, we should stop after the budget,
        # not the full 20-triple cross product.
        with patch.object(hs, "_workday_fetch_one", return_value=None) as mock:
            result = hs._fetch_workday("acmecorp")
        assert result is None
        # Probe count never exceeds the documented budget.
        assert mock.call_count <= _WORKDAY_BLIND_DISCOVERY_BUDGET
