"""Additional coverage for hiring-signal gathering.

Complements ``test_hiring_signals.py`` by exercising the ATS providers and
fallback branches that file does not reach: Workday (corpus discovery, blind
discovery, direct fetch), Workable, Recruitee, Jobvite RSS, the HTML
careers-page crawl + ATS-redirect short-circuit, the DuckDuckGo web-search
fallback, the ``_http_get`` SSRF boundary, the no-bodies metadata-roles
branch, and the markdown/persist rendering paths.

Every HTTP and LLM call is mocked. ``_http_get`` is the single HTTP boundary
(mirrors the pattern in ``test_hiring_signals.py``); Workday issues a direct
``httpx`` POST so that one provider mocks ``httpx`` instead. The LLM is mocked
at ``primr.ai.grok_client.grok_llm``. No real company names appear — only
``Acme`` / ``ExampleCo`` placeholders.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from primr.data import hiring_signals as hs
from primr.data.hiring_signals import (
    Posting,
    _candidate_workday_triples,
    _careers_url_candidates,
    _clean_web_search_title,
    _detect_ats_redirect,
    _discover_via_html,
    _discover_via_web_search,
    _discover_workday_triples,
    _extract_signals,
    _fetch_html_posting_bodies,
    _fetch_jobvite,
    _fetch_recruitee,
    _fetch_workable,
    _fetch_workday,
    _http_get,
    _llm_triage,
    _looks_like_posting_url,
    _persist,
    _workday_endpoints,
    _workday_fetch_one,
    gather_hiring_signals,
)

# A body long enough to clear the _MIN_USEFUL_BODY_CHARS (200) guard.
_LONG_BODY_HTML = (
    "<p>Join the platform team. We run Kubernetes, Terraform, Snowflake, and "
    "dbt at scale across multiple regions. You will own reliability, schema "
    "design, and incident response while mentoring engineers and shaping the "
    "next phase of our data platform roadmap. This is a senior individual "
    "contributor role reporting to the Head of Platform Engineering.</p>"
)


# =============================================================================
# _http_get — the single HTTP boundary (SSRF + happy/redirect/error paths)
# =============================================================================


class TestHttpGet:
    def test_blocked_initial_url_returns_none_triple(self):
        with patch("primr.utils.security.is_safe_url", return_value=(False, "loopback")):
            assert _http_get("http://127.0.0.1/jobs", timeout=1.0) == (None, None, None)

    def test_happy_path_returns_status_body_final_url(self):
        resp = MagicMock()
        resp.url = "https://acme.example/jobs"
        resp.status_code = 200
        resp.content = b"hello"
        client = MagicMock()
        client.get.return_value = resp
        client_cm = MagicMock()
        client_cm.__enter__.return_value = client
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, None),
            ),
            patch("httpx.Client", return_value=client_cm),
        ):
            status, body, final = _http_get(
                "https://acme.example/jobs", timeout=1.0, headers={"X-Test": "1"}
            )
        assert status == 200
        assert body == b"hello"
        assert final == "https://acme.example/jobs"

    def test_final_url_blocked_after_redirect_drops_response(self):
        resp = MagicMock()
        resp.url = "http://169.254.169.254/latest/meta-data"
        resp.status_code = 200
        resp.content = b"secrets"
        client = MagicMock()
        client.get.return_value = resp
        client_cm = MagicMock()
        client_cm.__enter__.return_value = client
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "metadata"),
            ),
            patch("httpx.Client", return_value=client_cm),
        ):
            assert _http_get("https://acme.example/jobs", timeout=1.0) == (
                None,
                None,
                None,
            )

    def test_request_exception_returns_none_triple(self):
        client_cm = MagicMock()
        client_cm.__enter__.side_effect = RuntimeError("boom")
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch("httpx.Client", return_value=client_cm),
        ):
            assert _http_get("https://acme.example/jobs", timeout=1.0) == (
                None,
                None,
                None,
            )


# =============================================================================
# Workday — endpoints, triple discovery, direct POST fetch, blind discovery
# =============================================================================


class TestWorkday:
    def test_endpoints_construction(self):
        jobs_url, base_url = _workday_endpoints(("acmecorp", "wd5", "External"))
        assert jobs_url == (
            "https://acmecorp.wd5.myworkdayjobs.com/wday/cxs/acmecorp/External/jobs"
        )
        assert base_url == "https://acmecorp.wd5.myworkdayjobs.com/en-US/External"

    def test_discover_triples_from_corpus(self):
        corpus = {
            "https://acme.com/careers": (
                "See open roles at https://acmecorp.wd5.myworkdayjobs.com/en-US/External/job/123"
            ),
            "https://acme.com/about": "nothing relevant here",
        }
        triples = _discover_workday_triples(corpus)
        assert ("acmecorp", "wd5", "External") in triples

    def test_discover_triples_empty_corpus(self):
        assert _discover_workday_triples(None) == []
        assert _discover_workday_triples({"u": "no workday here"}) == []

    def test_candidate_triples_cross_product(self):
        triples = _candidate_workday_triples("acme")
        # 4 datacenters x 5 sites
        assert len(triples) == 20
        assert ("acme", "wd1", "External") in triples

    def _make_workday_post(self, postings_payload, *, status=200, final_url=None):
        resp = MagicMock()
        resp.url = final_url or "https://acmecorp.wd5.myworkdayjobs.com/x"
        resp.status_code = status
        resp.json.return_value = postings_payload
        client = MagicMock()
        client.post.return_value = resp
        client_cm = MagicMock()
        client_cm.__enter__.return_value = client
        return client_cm

    def test_workday_fetch_one_parses_postings(self):
        payload = {
            "jobPostings": [
                {
                    "title": "Staff Platform Engineer",
                    "externalPath": "/job/Staff-Platform-Engineer_R123",
                    "locationsText": "Remote - US",
                    "postedOn": "Posted 3 Days Ago",
                },
                {"title": "", "externalPath": "/job/skip"},  # dropped: no title
            ]
        }
        cm = self._make_workday_post(payload)
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, None),
            ),
            patch("httpx.Client", return_value=cm),
        ):
            postings = _workday_fetch_one(("acmecorp", "wd5", "External"))
        assert postings is not None
        assert len(postings) == 1
        p = postings[0]
        assert p.source == "workday"
        assert p.title == "Staff Platform Engineer"
        assert p.location == "Remote - US"
        assert p.url.startswith("https://acmecorp.wd5.myworkdayjobs.com/en-US/External/")

    def test_workday_fetch_one_blocked_initial_url(self):
        with patch("primr.utils.security.is_safe_url", return_value=(False, "blocked")):
            assert _workday_fetch_one(("acme", "wd5", "External")) is None

    def test_workday_fetch_one_post_exception(self):
        client_cm = MagicMock()
        client_cm.__enter__.side_effect = RuntimeError("net down")
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch("httpx.Client", return_value=client_cm),
        ):
            assert _workday_fetch_one(("acme", "wd5", "External")) is None

    def test_workday_fetch_one_non_200(self):
        cm = self._make_workday_post({}, status=404)
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, None),
            ),
            patch("httpx.Client", return_value=cm),
        ):
            assert _workday_fetch_one(("acme", "wd5", "External")) is None

    def test_workday_fetch_one_final_url_blocked(self):
        cm = self._make_workday_post({"jobPostings": [{"title": "x"}]})
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "redirected-internal"),
            ),
            patch("httpx.Client", return_value=cm),
        ):
            assert _workday_fetch_one(("acme", "wd5", "External")) is None

    def test_workday_fetch_one_bad_shape_returns_none(self):
        cm = self._make_workday_post({"notJobPostings": []})
        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(True, None),
            ),
            patch("httpx.Client", return_value=cm),
        ):
            assert _workday_fetch_one(("acme", "wd5", "External")) is None

    def test_fetch_workday_stops_after_budget(self):
        """Blind discovery must not exceed the per-call probe budget."""
        calls: list = []

        def fake_fetch_one(triple):
            calls.append(triple)
            return None

        with patch.object(hs, "_workday_fetch_one", side_effect=fake_fetch_one):
            assert _fetch_workday("acme") is None
        assert len(calls) == hs._WORKDAY_BLIND_DISCOVERY_BUDGET

    def test_fetch_workday_returns_first_hit(self):
        hit = [Posting(url="u", title="Engineer", source="workday")]

        def fake_fetch_one(triple):
            return hit if triple[1] == "wd1" else None

        with patch.object(hs, "_workday_fetch_one", side_effect=fake_fetch_one):
            assert _fetch_workday("acme") == hit


# =============================================================================
# Workable / Recruitee / Jobvite providers
# =============================================================================


class TestWorkableProvider:
    def test_parses_jobs(self):
        payload = {
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://apply.workable.com/acme/j/ABC123/",
                    "city": "Berlin",
                    "country": "Germany",
                    "department": "Engineering",
                    "published": "2026-04-01",
                },
                {"title": "", "url": "skip"},  # dropped
            ]
        }
        with patch.object(hs, "_http_get", return_value=(200, json.dumps(payload).encode(), None)):
            postings = _fetch_workable("acme")
        assert postings is not None
        assert len(postings) == 1
        p = postings[0]
        assert p.source == "workable"
        assert p.location == "Berlin, Germany"
        assert p.department == "Engineering"

    def test_404_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(404, b"", None)):
            assert _fetch_workable("acme") is None

    def test_non_dict_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(200, json.dumps([1, 2]).encode(), None)):
            assert _fetch_workable("acme") is None

    def test_malformed_json_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(200, b"<<<", None)):
            assert _fetch_workable("acme") is None


class TestRecruiteeProvider:
    def test_parses_offers_with_body(self):
        payload = {
            "offers": [
                {
                    "title": "Data Engineer",
                    "careers_url": "https://acme.recruitee.com/o/data-engineer",
                    "city": "Amsterdam",
                    "country": "NL",
                    "department": "Data",
                    "description": "<p>Build the data platform with dbt.</p>",
                    "published_at": "2026-03-01",
                }
            ]
        }
        with patch.object(hs, "_http_get", return_value=(200, json.dumps(payload).encode(), None)):
            postings = _fetch_recruitee("acme")
        assert postings is not None
        assert len(postings) == 1
        p = postings[0]
        assert p.source == "recruitee"
        assert p.location == "Amsterdam, NL"
        assert p.body is not None
        assert "dbt" in p.body

    def test_falls_back_to_apply_url(self):
        payload = {
            "offers": [
                {
                    "title": "Role",
                    "careers_apply_url": "https://acme.recruitee.com/o/role/apply",
                }
            ]
        }
        with patch.object(hs, "_http_get", return_value=(200, json.dumps(payload).encode(), None)):
            postings = _fetch_recruitee("acme")
        assert postings is not None
        assert postings[0].url.endswith("/apply")

    def test_empty_offers_returns_none(self):
        with patch.object(
            hs, "_http_get", return_value=(200, json.dumps({"offers": []}).encode(), None)
        ):
            assert _fetch_recruitee("acme") is None


class TestJobviteProvider:
    def test_parses_rss_items(self):
        rss = b"""<?xml version="1.0"?><rss><channel>
        <item><title><![CDATA[Senior SRE]]></title>
        <link>https://jobs.jobvite.com/acme/job/sre</link></item>
        <item><title>Product Manager</title>
        <link>https://jobs.jobvite.com/acme/job/pm</link></item>
        <item><title>No Link Role</title></item>
        </channel></rss>"""
        with patch.object(hs, "_http_get", return_value=(200, rss, None)):
            postings = _fetch_jobvite("acme")
        assert postings is not None
        titles = [p.title for p in postings]
        assert "Senior SRE" in titles
        assert "Product Manager" in titles
        assert all(p.source == "jobvite" for p in postings)

    def test_no_items_returns_none(self):
        with patch.object(
            hs, "_http_get", return_value=(200, b"<rss><channel></channel></rss>", None)
        ):
            assert _fetch_jobvite("acme") is None

    def test_404_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(404, b"", None)):
            assert _fetch_jobvite("acme") is None


# =============================================================================
# Web-search fallback (DuckDuckGo)
# =============================================================================


class TestWebSearchFallback:
    def test_looks_like_posting_url(self):
        assert _looks_like_posting_url("https://www.linkedin.com/jobs/view/123")
        assert _looks_like_posting_url("https://acme.wd5.myworkdayjobs.com/x")
        assert not _looks_like_posting_url("https://acme.com/about")

    def test_clean_web_search_title_strips_board_suffixes(self):
        assert _clean_web_search_title("Senior Engineer | LinkedIn") == "Senior Engineer"
        assert _clean_web_search_title("Data Engineer - Indeed.com") == "Data Engineer"
        assert _clean_web_search_title("SRE at Acme") == "SRE"

    def test_discover_via_web_search_filters_and_cleans(self):
        fake_results = [
            {"href": "https://www.linkedin.com/jobs/view/1", "title": "Staff Engineer | LinkedIn"},
            {
                "href": "https://acme.com/blog/post",
                "title": "Not a job",
            },  # filtered: not posting url
            {"href": "https://www.indeed.com/job/2", "title": "Data Scientist - Indeed"},
            {"href": "https://www.linkedin.com/jobs/view/1", "title": "dup"},  # dup url
            {"not": "a dict"},
        ]
        fake_ddgs = MagicMock()
        fake_ddgs.__enter__.return_value.text.return_value = iter(fake_results)
        with patch.dict("sys.modules"):
            import sys
            from types import ModuleType

            mod = ModuleType("ddgs")
            mod.DDGS = MagicMock(return_value=fake_ddgs)
            exc_mod = ModuleType("ddgs.exceptions")

            class _FakeDDGSError(Exception):
                pass

            exc_mod.DDGSException = _FakeDDGSError
            mod.exceptions = exc_mod
            sys.modules["ddgs"] = mod
            sys.modules["ddgs.exceptions"] = exc_mod
            postings = _discover_via_web_search("Acme Corp", "https://acme.com")
        urls = [p.url for p in postings]
        assert "https://www.linkedin.com/jobs/view/1" in urls
        assert "https://www.indeed.com/job/2" in urls
        assert "https://acme.com/blog/post" not in urls
        assert urls.count("https://www.linkedin.com/jobs/view/1") == 1
        assert all(p.source == "web-search" for p in postings)

    def test_discover_via_web_search_handles_ddgs_exception(self):
        import sys
        from types import ModuleType

        class _FakeDDGSError(Exception):
            pass

        fake_ddgs = MagicMock()
        fake_ddgs.__enter__.return_value.text.side_effect = _FakeDDGSError("rate limited")
        mod = ModuleType("ddgs")
        mod.DDGS = MagicMock(return_value=fake_ddgs)
        exc_mod = ModuleType("ddgs.exceptions")
        exc_mod.DDGSException = _FakeDDGSError
        with patch.dict(sys.modules, {"ddgs": mod, "ddgs.exceptions": exc_mod}):
            assert _discover_via_web_search("Acme", "https://acme.com") == []

    def test_discover_via_web_search_no_ddgs_module(self):
        import sys

        with patch.dict(sys.modules, {"ddgs": None, "ddgs.exceptions": None}):
            assert _discover_via_web_search("Acme", "https://acme.com") == []


# =============================================================================
# Careers-URL candidates + HTML discovery + ATS-redirect short-circuit
# =============================================================================


class TestCareersUrlCandidates:
    def test_includes_subdomain_and_onpath_probes(self):
        urls = _careers_url_candidates("https://acme.com", corpus=None)
        assert any(u.startswith("https://jobs.acme.com") for u in urls)
        assert any(u.startswith("https://careers.acme.com") for u in urls)
        assert any(u.endswith("/careers") for u in urls)
        assert len(urls) <= 14

    def test_pulls_careers_pages_from_corpus(self):
        corpus = {
            "https://acme.com/careers/open-roles": "html",
            "https://jobs.acme.com/listing": "html",
            "https://acme.com/about": "html",
        }
        urls = _careers_url_candidates("https://acme.com", corpus=corpus)
        assert "https://acme.com/careers/open-roles" in urls
        assert "https://jobs.acme.com/listing" in urls


class TestDetectAtsRedirect:
    def test_workday_redirect_dispatches_to_fetch_one(self):
        hit = [Posting(url="u", title="Eng", source="workday")]
        with patch.object(hs, "_workday_fetch_one", return_value=hit) as m:
            result = _detect_ats_redirect("https://acmecorp.wd5.myworkdayjobs.com/en-US/External")
        assert result == ("workday", hit)
        m.assert_called_once_with(("acmecorp", "wd5", "External"))

    def test_greenhouse_redirect_dispatches_by_name(self):
        hit = [Posting(url="u", title="Eng", source="greenhouse")]
        with patch.object(hs, "_fetch_greenhouse", return_value=hit):
            result = _detect_ats_redirect("https://boards.greenhouse.io/acmeco/jobs/1")
        assert result == ("greenhouse", hit)

    def test_recruitee_slug_from_subdomain(self):
        hit = [Posting(url="u", title="Eng", source="recruitee")]
        captured = {}

        def fake_recruitee(slug):
            captured["slug"] = slug
            return hit

        with patch.object(hs, "_fetch_recruitee", side_effect=fake_recruitee):
            result = _detect_ats_redirect("https://acmeco.recruitee.com/o/role")
        assert result == ("recruitee", hit)
        assert captured["slug"] == "acmeco"

    def test_non_ats_host_returns_none(self):
        assert _detect_ats_redirect("https://acme.com/careers") is None

    def test_empty_host_returns_none(self):
        assert _detect_ats_redirect("/relative/path") is None

    def test_fetcher_exception_swallowed(self):
        with patch.object(hs, "_fetch_lever", side_effect=RuntimeError("boom")):
            assert _detect_ats_redirect("https://jobs.lever.co/acme/abc") is None


class TestDiscoverViaHtml:
    def test_extracts_links_from_careers_html(self):
        html = (
            b"<html><body>"
            b'<a href="/careers/senior-data-engineer">Senior Data Engineer</a>'
            b'<a href="/careers/platform-lead">Platform Lead</a>'
            b'<a href="/about">About</a>'
            b"</body></html>"
        )

        def fake_http_get(url, timeout, headers=None, params=None):
            if url == "https://acme.com/careers":
                return 200, html, "https://acme.com/careers"
            return 404, b"", None

        with (
            patch.object(hs, "_http_get", side_effect=fake_http_get),
            patch.object(hs, "_detect_ats_redirect", return_value=None),
        ):
            postings, source = _discover_via_html("https://acme.com", corpus=None)
        assert source == "html"
        titles = {p.title for p in postings}
        assert "Senior Data Engineer" in titles
        assert all(p.source == "html" for p in postings)

    def test_ats_redirect_short_circuits(self):
        hit = [
            Posting(url="https://acmecorp.wd5.myworkdayjobs.com/j", title="Eng", source="workday")
        ]

        def fake_http_get(url, timeout, headers=None, params=None):
            return 200, b"<html></html>", "https://acmecorp.wd5.myworkdayjobs.com/en-US/External"

        with (
            patch.object(hs, "_http_get", side_effect=fake_http_get),
            patch.object(hs, "_detect_ats_redirect", return_value=("workday", hit)),
        ):
            postings, source = _discover_via_html("https://acme.com", corpus=None)
        assert source == "workday"
        assert postings == hit

    def test_reuses_corpus_html_without_http(self):
        corpus = {"https://acme.com/careers": ('<a href="/careers/role-x">Role X</a>')}
        http_urls: list[str] = []

        def fake_http_get(url, timeout, headers=None, params=None):
            http_urls.append(url)
            return 404, b"", None

        with (
            patch.object(hs, "_http_get", side_effect=fake_http_get),
            patch.object(hs, "_detect_ats_redirect", return_value=None),
        ):
            postings, source = _discover_via_html("https://acme.com", corpus=corpus)
        # The corpus careers URL was served without an HTTP call for that URL.
        assert source == "html"
        assert any(p.title == "Role X" for p in postings)
        assert "https://acme.com/careers" not in http_urls

    def test_total_miss_returns_empty(self):
        with (
            patch.object(hs, "_http_get", return_value=(404, b"", None)),
            patch.object(hs, "_detect_ats_redirect", return_value=None),
        ):
            postings, source = _discover_via_html("https://acme.com", corpus=None)
        assert postings == []
        assert source is None


# =============================================================================
# HTML posting body fetch
# =============================================================================


class TestFetchHtmlPostingBodies:
    def test_populates_body_for_html_postings(self):
        p = Posting(url="https://acme.com/careers/role", title="Role", source="html")
        big_html = ("<p>" + "Build the data platform. " * 40 + "</p>").encode()
        with patch.object(hs, "_http_get", return_value=(200, big_html, None)):
            _fetch_html_posting_bodies([p])
        assert p.body is not None
        assert len(p.body) >= hs._MIN_USEFUL_BODY_CHARS

    def test_short_body_is_rejected(self):
        p = Posting(url="https://acme.com/careers/role", title="Role", source="html")
        with patch.object(hs, "_http_get", return_value=(200, b"<p>tiny</p>", None)):
            _fetch_html_posting_bodies([p])
        assert p.body is None

    def test_no_targets_is_noop(self):
        ats = Posting(url="u", title="t", source="greenhouse", body="already here")
        with patch.object(hs, "_http_get") as http:
            _fetch_html_posting_bodies([ats])
            http.assert_not_called()

    def test_fetch_exception_is_swallowed(self):
        p = Posting(url="https://acme.com/careers/role", title="Role", source="html")
        with patch.object(hs, "_http_get", side_effect=RuntimeError("net")):
            _fetch_html_posting_bodies([p])  # must not raise
        assert p.body is None


# =============================================================================
# LLM triage paths
# =============================================================================


def _posting(title, **kw):
    return Posting(url=f"https://acme.com/jobs/{title}", title=title, **kw)


class TestLlmTriage:
    def test_llm_selection_is_used(self):
        postings = [_posting("A"), _posting("B"), _posting("C")]
        with patch("primr.ai.grok_client.grok_llm", return_value='{"selected": [2, 0]}'):
            assert _llm_triage(postings, "Acme", k=5) == [2, 0]

    def test_llm_failure_falls_back_to_deterministic(self):
        postings = [_posting("Retail Associate"), _posting("Senior Engineer")]
        with patch("primr.ai.grok_client.grok_llm", side_effect=RuntimeError("api down")):
            result = _llm_triage(postings, "Acme", k=1)
        # Deterministic ranker should pick the senior role, not retail.
        assert result == [1]

    def test_llm_non_dict_falls_back(self):
        postings = [_posting("Senior Engineer"), _posting("Intern")]
        with patch("primr.ai.grok_client.grok_llm", return_value="[1, 2, 3]"):
            result = _llm_triage(postings, "Acme", k=1)
        assert result == [0]

    def test_llm_selected_not_list_falls_back(self):
        postings = [_posting("Senior Engineer")]
        with patch("primr.ai.grok_client.grok_llm", return_value='{"selected": "nope"}'):
            assert _llm_triage(postings, "Acme", k=1) == [0]

    def test_llm_out_of_range_indices_filtered_then_fallback(self):
        postings = [_posting("Senior Engineer")]
        # index 9 is out of range -> no valid -> deterministic fallback
        with patch("primr.ai.grok_client.grok_llm", return_value='{"selected": [9]}'):
            assert _llm_triage(postings, "Acme", k=1) == [0]


# =============================================================================
# Extraction LLM failure path
# =============================================================================


class TestExtractSignals:
    def test_no_bodies_returns_none(self):
        postings = [Posting(url="u", title="t", source="html", body=None)]
        with patch("primr.ai.grok_client.grok_llm") as grok:
            assert _extract_signals(postings, "Acme") is None
            grok.assert_not_called()

    def test_llm_exception_returns_none(self):
        postings = [Posting(url="u", title="t", source="html", body="x" * 300)]
        with patch("primr.ai.grok_client.grok_llm", side_effect=RuntimeError("boom")):
            assert _extract_signals(postings, "Acme") is None

    def test_unparseable_output_returns_none(self):
        postings = [Posting(url="u", title="t", source="html", body="x" * 300)]
        with patch("primr.ai.grok_client.grok_llm", return_value="totally not json"):
            assert _extract_signals(postings, "Acme") is None

    def test_parsed_dict_returned(self):
        postings = [Posting(url="u", title="t", source="html", body="x" * 300)]
        with patch("primr.ai.grok_client.grok_llm", return_value='{"summary": "ok"}'):
            assert _extract_signals(postings, "Acme") == {"summary": "ok"}


# =============================================================================
# Persist / markdown rendering
# =============================================================================


class TestPersist:
    def test_writes_all_artifacts_including_raw_jd(self, tmp_path):
        signals = hs.HiringSignals(
            company_slug="acme",
            source="greenhouse",
            postings_found=3,
            postings_selected=2,
            postings_extracted=1,
            tech_stack={"Snowflake": 4, "dbt": 2},
            strategic_initiatives=["Build platform"],
            culture_signals=["Remote-first"],
            locations=["NYC"],
            notable_absences=["No security roles"],
            summary="Platform buildout.",
            stale_fraction=0.25,
        )
        all_postings = [
            Posting(url="https://acme.com/j/1", title="Eng", source="greenhouse"),
        ]
        selected = [
            Posting(
                url="https://acme.com/j/1",
                title="Senior/Data Engineer",
                location="NYC",
                department="Data",
                source="greenhouse",
                updated_at="2026-04-01T00:00:00Z",
                body="A long job description body. " * 20,
            )
        ]
        _persist(str(tmp_path), signals, all_postings, selected)
        hiring = tmp_path / "_hiring"
        assert (hiring / "hiring_signals.json").exists()
        md = (hiring / "hiring_signals.md").read_text(encoding="utf-8")
        assert "Snowflake" in md
        assert "Build platform" in md
        assert "Remote-first" in md
        assert "No security roles" in md
        assert "25% stale" in md
        assert (hiring / "postings_index.json").exists()
        raw_files = list((hiring / "raw").glob("jd_*.txt"))
        assert len(raw_files) == 1
        raw_text = raw_files[0].read_text(encoding="utf-8")
        assert "URL: https://acme.com/j/1" in raw_text

    def test_persist_directory_creation_failure_is_swallowed(self, tmp_path):
        signals = hs.HiringSignals(
            company_slug="acme",
            source="none",
            postings_found=0,
            postings_selected=0,
            postings_extracted=0,
        )
        with patch.object(hs.os, "makedirs", side_effect=OSError("denied")):
            # Must not raise.
            _persist(str(tmp_path), signals, [], [])


# =============================================================================
# End-to-end branches not covered by the base test file
# =============================================================================


class TestGatherE2EBranches:
    def test_corpus_workday_triple_fetched_directly(self, tmp_path):
        """A Workday board URL in the corpus skips slug fan-out entirely."""
        corpus = {
            "https://acme.com/careers": (
                "Apply at https://acmecorp.wd5.myworkdayjobs.com/en-US/External/job/1"
            )
        }
        workday_postings = [
            Posting(
                url="https://acmecorp.wd5.myworkdayjobs.com/en-US/External/job/1",
                title="Senior Platform Engineer",
                source="workday",
                # Workday listings already carry a body, so extraction runs
                # without an HTML body fetch.
                body="Build the data platform with Kubernetes. " * 10,
            )
        ]

        def fake_grok(prompt, **kw):
            if "Pick up to" in prompt:
                return '{"selected": [0]}'
            return json.dumps({"summary": "Platform buildout.", "tech_stack": {"Kubernetes": 1}})

        with (
            patch.object(hs, "_workday_fetch_one", return_value=workday_postings),
            patch.object(hs, "_http_get", return_value=(404, b"", None)),
            patch("primr.ai.grok_client.grok_llm", side_effect=fake_grok),
        ):
            signals = gather_hiring_signals(
                "Acme Corp",
                "https://acme.com",
                corpus=corpus,
                working_folder=str(tmp_path),
            )
        assert signals is not None
        assert signals.source == "workday"
        assert signals.tech_stack.get("Kubernetes") == 1

    def test_web_search_fallback_no_bodies_populates_roles_from_titles(self, tmp_path):
        """ATS + HTML miss, web-search hits, bodies unrecoverable → roles from titles."""
        web_postings = [
            Posting(
                url="https://www.linkedin.com/jobs/view/1",
                title="Staff Data Engineer",
                source="web-search",
            ),
            Posting(
                url="https://www.linkedin.com/jobs/view/2",
                title="Security Lead",
                source="web-search",
            ),
        ]

        with (
            patch.object(hs, "_http_get", return_value=(404, b"", None)),
            patch.object(hs, "_discover_via_web_search", return_value=web_postings),
            patch("primr.ai.grok_client.grok_llm", return_value='{"selected": [0, 1]}'),
        ):
            signals = gather_hiring_signals(
                "Acme Corp",
                "https://acme.com",
                working_folder=str(tmp_path),
            )
        assert signals is not None
        assert signals.source == "web-search"
        # Bodies never fetched (web-search source != html), so the no-bodies
        # branch fires and roles come straight from titles.
        assert signals.postings_extracted == 2
        role_titles = {r["title"] for r in signals.roles}
        assert "Staff Data Engineer" in role_titles
        assert "Security Lead" in role_titles
        # Skeleton artifact still persisted.
        assert (tmp_path / "_hiring" / "hiring_signals.json").exists()

    def test_no_slug_candidates_returns_none(self):
        assert gather_hiring_signals("", "") is None


# =============================================================================
# render_for_prompt — roles / absences / stale branches
# =============================================================================


class TestRenderForPromptExtra:
    def test_roles_absences_and_stale_sections(self):
        signals = hs.HiringSignals(
            company_slug="acme",
            source="workday",
            postings_found=10,
            postings_selected=8,
            postings_extracted=6,
            roles=[
                {"title": "SRE", "location": "NYC", "department": "Platform"},
                {"title": "", "location": "", "department": ""},  # empty -> skipped
            ],
            notable_absences=["No data engineering"],
            stale_fraction=0.5,
        )
        out = hs.render_for_prompt(signals)
        assert "Representative roles" in out
        assert "SRE [Platform] — NYC" in out
        assert "Notable absences" in out
        assert "Stale fraction" in out


# =============================================================================
# Web-search title length filter
# =============================================================================


class TestWebSearchTitleLength:
    def test_overlong_title_is_dropped(self):
        import sys
        from types import ModuleType

        long_title = "x" * 250  # exceeds the 200-char cap
        fake_results = [
            {"href": "https://www.linkedin.com/jobs/view/1", "title": long_title},
            {"href": "", "title": "no url"},  # empty url -> skipped
        ]
        fake_ddgs = MagicMock()
        fake_ddgs.__enter__.return_value.text.return_value = iter(fake_results)

        class _FakeDDGSError(Exception):
            pass

        mod = ModuleType("ddgs")
        mod.DDGS = MagicMock(return_value=fake_ddgs)
        exc_mod = ModuleType("ddgs.exceptions")
        exc_mod.DDGSException = _FakeDDGSError
        with patch.dict(sys.modules, {"ddgs": mod, "ddgs.exceptions": exc_mod}):
            assert _discover_via_web_search("Acme", "https://acme.com") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
