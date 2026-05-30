"""Tests for hiring-signal gathering.

All HTTP and LLM calls are mocked — these run offline and don't depend on
any real company's ATS or careers page. The module's design is fail-open
at every stage, and the tests exercise both the success paths and every
fallback branch.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from primr.data import hiring_signals as hs
from primr.data.hiring_signals import (
    HiringSignals,
    Posting,
    _candidate_slugs,
    _coerce_extraction,
    _deterministic_triage,
    _extract_posting_links,
    _parse_json_blob,
    _slugify,
    _strip_html,
    gather_hiring_signals,
    render_for_prompt,
)

# =============================================================================
# Slug guessing
# =============================================================================


class TestSlugGuessing:
    def test_slugify_basics(self):
        assert _slugify("Acme Corp") == "acme-corp"
        assert _slugify("  Hello_World!  ") == "hello-world"
        assert _slugify("Multi   Spaces") == "multi-spaces"

    def test_website_hostname_first_token_becomes_candidate(self):
        slugs = _candidate_slugs("Acme Corporation", "https://acme-labs.io")
        assert "acme-labs" in slugs

    def test_corporate_suffix_is_stripped(self):
        slugs = _candidate_slugs("Acme Holdings Inc", "https://acme.com")
        # Full hyphenated form and suffix-stripped form both appear
        assert "acme-holdings-inc" in slugs
        assert "acme" in slugs

    def test_recon_hints_take_priority(self):
        slugs = _candidate_slugs(
            "Example Corp",
            "https://example.com",
            recon_hints={"ats_slugs": ["example-hq"]},
        )
        assert slugs[0] == "example-hq"

    def test_cap_is_respected(self):
        slugs = _candidate_slugs(
            "Alpha Beta Gamma Delta Epsilon Zeta",
            "https://alphabet.example.com",
        )
        assert len(slugs) <= hs.MAX_SLUG_CANDIDATES

    def test_empty_inputs_return_empty_list(self):
        assert _candidate_slugs("", "") == []


# =============================================================================
# HTML stripping
# =============================================================================


class TestHtmlStripping:
    def test_removes_script_and_style(self):
        html = "<html><script>alert('x')</script><style>body{}</style><p>Hello</p></html>"
        out = _strip_html(html)
        assert "alert" not in out
        assert "Hello" in out

    def test_decodes_common_entities(self):
        assert _strip_html("Tom &amp; Jerry") == "Tom & Jerry"
        assert _strip_html("&nbsp;spaced&nbsp;") == "spaced"

    def test_collapses_whitespace(self):
        out = _strip_html("<p>one</p>  <p>two</p>")
        tokens = [tok for tok in out.split() if tok]
        assert tokens == ["one", "two"]


# =============================================================================
# JSON parsing robustness
# =============================================================================


class TestJsonParsing:
    def test_raw_json_object(self):
        assert _parse_json_blob('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        text = 'Sure, here is the answer:\n```json\n{"selected": [0, 1]}\n```\nDone.'
        assert _parse_json_blob(text) == {"selected": [0, 1]}

    def test_json_embedded_in_prose(self):
        text = 'The selection is {"selected": [3]} which is optimal.'
        assert _parse_json_blob(text) == {"selected": [3]}

    def test_empty_returns_none(self):
        assert _parse_json_blob("") is None
        assert _parse_json_blob("not json at all") is None


# =============================================================================
# ATS provider parsers
# =============================================================================


# Body must exceed _MIN_USEFUL_BODY_CHARS (200) to survive the extraction guard.
_LONG_ENG_BODY = (
    "<p>Join our data platform team and help us scale Snowflake, dbt, "
    "Airflow, Terraform, and AWS infrastructure. We are building a "
    "self-serve analytics platform that serves every team in the company. "
    "You will own schema design, performance tuning, and incident response. "
    "This is a senior role reporting directly to the Head of Data.</p>"
)
_LONG_RETAIL_BODY = (
    "<p>As a retail associate you will greet customers, operate the register, "
    "restock shelves, and keep the store floor tidy. Evenings and weekends "
    "required. No specific technical experience needed. We provide full "
    "on-the-job training and a competitive employee discount program.</p>"
)

GREENHOUSE_FIXTURE = {
    "jobs": [
        {
            "id": 1,
            "title": "Senior Data Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": {"name": "New York, NY"},
            "departments": [{"id": 11, "name": "Data Platform"}],
            "content": _LONG_ENG_BODY,
            "updated_at": "2026-04-01T00:00:00-04:00",
        },
        {
            "id": 2,
            "title": "Retail Associate",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
            "location": {"name": "Remote"},
            "departments": [{"id": 22, "name": "Stores"}],
            "content": _LONG_RETAIL_BODY,
            "updated_at": "2026-04-02T00:00:00-04:00",
        },
    ]
}


LEVER_FIXTURE = [
    {
        "id": "abc-123",
        "text": "Principal Platform Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
        "categories": {"location": "London, UK", "department": "Engineering"},
        "descriptionPlain": "Help us scale Kubernetes and Terraform.",
        "createdAt": 1_740_000_000_000,  # ms since epoch
        "lists": [{"text": "Responsibilities", "content": "<li>Own the platform</li>"}],
    }
]


ASHBY_FIXTURE = {
    "jobs": [
        {
            "title": "VP, Product Strategy",
            "jobUrl": "https://jobs.ashbyhq.com/acme/vp-product",
            "locationName": "San Francisco, CA",
            "departmentName": "Product",
            "descriptionHtml": "<p>Lead product strategy.</p>",
            "publishedAt": "2026-03-15T12:00:00Z",
        }
    ]
}


SMARTRECRUITERS_FIXTURE = {
    "content": [
        {
            "id": "xyz-789",
            "name": "Staff Security Engineer",
            "location": {"city": "Austin", "country": "US"},
            "department": {"label": "Security"},
            "releasedDate": "2026-02-01T00:00:00Z",
        }
    ]
}


class TestAtsProviders:
    def test_greenhouse_parses_all_fields(self):
        with patch.object(
            hs,
            "_http_get",
            return_value=(200, json.dumps(GREENHOUSE_FIXTURE).encode(), None),
        ):
            postings = hs._fetch_greenhouse("acme")
        assert postings is not None
        assert len(postings) == 2
        first = postings[0]
        assert first.source == "greenhouse"
        assert first.title == "Senior Data Engineer"
        assert first.location == "New York, NY"
        assert first.department == "Data Platform"
        assert first.body is not None
        assert "Snowflake" in first.body
        assert first.updated_at is not None
        assert first.updated_at.startswith("2026-04-01")

    def test_greenhouse_404_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(404, b"", None)):
            assert hs._fetch_greenhouse("missing") is None

    def test_greenhouse_empty_jobs_returns_none(self):
        with patch.object(
            hs, "_http_get", return_value=(200, json.dumps({"jobs": []}).encode(), None)
        ):
            assert hs._fetch_greenhouse("empty") is None

    def test_lever_parses_categories_and_description(self):
        with patch.object(
            hs,
            "_http_get",
            return_value=(200, json.dumps(LEVER_FIXTURE).encode(), None),
        ):
            postings = hs._fetch_lever("acme")
        assert postings is not None
        assert len(postings) == 1
        p = postings[0]
        assert p.source == "lever"
        assert p.location == "London, UK"
        assert p.department == "Engineering"
        assert p.body is not None
        assert "Kubernetes" in p.body
        assert p.apply_url is not None
        assert "apply" in p.apply_url

    def test_lever_non_list_response_returns_none(self):
        with patch.object(
            hs, "_http_get", return_value=(200, json.dumps({"oops": True}).encode(), None)
        ):
            assert hs._fetch_lever("acme") is None

    def test_ashby_parses_fields(self):
        with patch.object(
            hs,
            "_http_get",
            return_value=(200, json.dumps(ASHBY_FIXTURE).encode(), None),
        ):
            postings = hs._fetch_ashby("acme")
        assert postings is not None
        assert len(postings) == 1
        assert postings[0].title.startswith("VP")
        assert postings[0].department == "Product"

    def test_smartrecruiters_builds_canonical_url(self):
        with patch.object(
            hs,
            "_http_get",
            return_value=(200, json.dumps(SMARTRECRUITERS_FIXTURE).encode(), None),
        ):
            postings = hs._fetch_smartrecruiters("acme")
        assert postings is not None
        assert len(postings) == 1
        assert postings[0].url == "https://jobs.smartrecruiters.com/acme/xyz-789"
        assert postings[0].location == "Austin, US"

    def test_malformed_json_returns_none(self):
        with patch.object(hs, "_http_get", return_value=(200, b"not json", None)):
            assert hs._fetch_greenhouse("acme") is None
            assert hs._fetch_lever("acme") is None


# =============================================================================
# HTML fallback — posting link extraction
# =============================================================================


class TestHtmlFallback:
    def test_extracts_posting_links_with_hints(self):
        html = b"""
        <html><body>
            <a href="/careers/senior-data-engineer">Senior Data Engineer</a>
            <a href="/about">About Us</a>
            <a href="https://other.example/jobs/platform-lead">Platform Lead</a>
            <a href="#anchor">Jump</a>
            <a href="mailto:jobs@example.com">Email</a>
        </body></html>
        """
        base = "https://example.com/careers"
        links = _extract_posting_links(html, base)
        urls = [u for u, _ in links]
        assert "https://example.com/careers/senior-data-engineer" in urls
        assert "https://other.example/jobs/platform-lead" in urls
        assert "https://example.com/about" not in urls
        # mailto: and # anchors are filtered
        assert not any(u.startswith("mailto:") or u.endswith("#anchor") for u in urls)

    def test_dedups_links(self):
        html = b"""
        <a href="/careers/role-a">Role A</a>
        <a href="/careers/role-a">Role A (duplicate)</a>
        """
        links = _extract_posting_links(html, "https://example.com/careers")
        urls = [u for u, _ in links]
        assert urls.count("https://example.com/careers/role-a") == 1


# =============================================================================
# Triage
# =============================================================================


def _posting(title, **kwargs) -> Posting:
    return Posting(url=f"https://example.com/jobs/{title}", title=title, **kwargs)


class TestTriage:
    def test_deterministic_triage_prefers_senior_roles(self):
        postings = [
            _posting("Retail Associate"),
            _posting("Senior Data Engineer", department="Engineering"),
            _posting("Intern, Marketing"),
            _posting("VP, Platform"),
            _posting("Customer Support Rep"),
        ]
        selected = _deterministic_triage(postings, k=2)
        titles = {postings[i].title for i in selected}
        # Both senior / leadership picks win over retail/intern/support
        assert "Senior Data Engineer" in titles or "VP, Platform" in titles
        assert "Retail Associate" not in titles
        assert "Intern, Marketing" not in titles

    def test_deterministic_triage_respects_k(self):
        postings = [_posting(f"Role {i}") for i in range(20)]
        assert len(_deterministic_triage(postings, k=5)) == 5


# =============================================================================
# Extraction coercion — LLM output may be messy
# =============================================================================


class TestExtractionCoercion:
    def test_full_shape_passes_through(self):
        parsed = {
            "roles": [{"title": "SRE", "location": "NYC", "department": "Platform"}],
            "tech_stack": {"Kubernetes": 3, "Terraform": 2},
            "strategic_initiatives": ["Build platform"],
            "culture_signals": ["Remote"],
            "locations": ["NYC"],
            "hiring_volume": "moderate",
            "notable_absences": [],
            "summary": "They are hiring platform engineers.",
        }
        out = _coerce_extraction(parsed)
        assert out["tech_stack"]["Kubernetes"] == 3
        assert out["hiring_volume"] == "moderate"
        assert out["roles"][0]["title"] == "SRE"

    def test_bad_tech_stack_values_coerced_to_ints_or_dropped(self):
        parsed = {"tech_stack": {"Snowflake": "four", "dbt": 2}}
        out = _coerce_extraction(parsed)
        # "four" fails int() coercion and is dropped
        assert "Snowflake" not in out["tech_stack"]
        assert out["tech_stack"]["dbt"] == 2

    def test_invalid_hiring_volume_becomes_unknown(self):
        assert _coerce_extraction({"hiring_volume": "ludicrous"})["hiring_volume"] == "unknown"

    def test_missing_fields_default_to_empty(self):
        out = _coerce_extraction({})
        assert out["roles"] == []
        assert out["tech_stack"] == {}
        assert out["hiring_volume"] == "unknown"
        assert out["summary"] == ""


# =============================================================================
# render_for_prompt
# =============================================================================


class TestRenderForPrompt:
    def test_empty_signals_renders_nothing(self):
        empty = HiringSignals(
            company_slug="acme",
            source="none",
            postings_found=0,
            postings_selected=0,
            postings_extracted=0,
        )
        assert render_for_prompt(empty) == ""

    def test_rich_signals_include_every_section(self):
        signals = HiringSignals(
            company_slug="acme",
            source="greenhouse",
            postings_found=20,
            postings_selected=15,
            postings_extracted=12,
            tech_stack={"Snowflake": 4, "dbt": 3},
            strategic_initiatives=["Expanding EMEA"],
            culture_signals=["Remote-first"],
            locations=["London", "NYC"],
            summary="They are doubling down on data platform.",
            hiring_volume="high",
        )
        out = render_for_prompt(signals)
        assert "Snowflake" in out
        assert "Expanding EMEA" in out
        assert "Remote-first" in out
        assert "doubling down" in out
        assert "Hiring volume: high" in out
        assert "greenhouse" in out

    def test_char_budget_is_enforced(self):
        signals = HiringSignals(
            company_slug="acme",
            source="greenhouse",
            postings_found=20,
            postings_selected=15,
            postings_extracted=12,
            summary="a" * 20_000,
        )
        out = render_for_prompt(signals, char_budget=1_000)
        assert len(out) <= 1_000


# =============================================================================
# End-to-end — gather_hiring_signals with everything mocked
# =============================================================================


class TestGatherHiringSignalsE2E:
    def test_ats_hit_runs_full_pipeline(self, tmp_path):
        """Greenhouse hit → triage → extraction → artifact write."""
        fixture_body = json.dumps(GREENHOUSE_FIXTURE).encode()

        # Only Greenhouse returns 200; every other provider 404s.
        def fake_http_get(url, timeout, headers=None, params=None):
            if "boards-api.greenhouse.io" in url:
                return 200, fixture_body, None
            return 404, b"", None

        def fake_grok_llm(prompt, **kwargs):
            # Triage call returns a JSON selection; extraction returns structured output.
            if "Pick up to" in prompt:
                return '{"selected": [0]}'
            return json.dumps(
                {
                    "roles": [
                        {"title": "Senior Data Engineer", "location": "NYC", "department": "Data"}
                    ],
                    "tech_stack": {"Snowflake": 1, "dbt": 1},
                    "strategic_initiatives": ["Building data platform"],
                    "culture_signals": [],
                    "locations": ["New York, NY"],
                    "hiring_volume": "moderate",
                    "notable_absences": [],
                    "summary": "Data platform buildout in progress.",
                }
            )

        with (
            patch.object(hs, "_http_get", side_effect=fake_http_get),
            patch("primr.ai.grok_client.grok_llm", side_effect=fake_grok_llm),
        ):
            signals = gather_hiring_signals(
                "Acme Corp",
                "https://acme.com",
                working_folder=str(tmp_path),
            )

        assert signals is not None
        assert signals.source == "greenhouse"
        assert signals.postings_found == 2
        assert signals.postings_extracted == 1
        assert signals.tech_stack.get("Snowflake") == 1
        assert "data platform" in signals.summary.lower()

        # Artifacts written
        hiring_dir = tmp_path / "_hiring"
        assert (hiring_dir / "hiring_signals.json").exists()
        assert (hiring_dir / "hiring_signals.md").exists()
        assert (hiring_dir / "postings_index.json").exists()

    def test_no_ats_and_no_careers_page_returns_none_source(self, tmp_path):
        """Every provider misses, HTML fallback finds nothing, web-search
        fallback also misses → source='none', signals empty."""
        with (
            patch.object(hs, "_http_get", return_value=(404, b"", None)),
            patch.object(hs, "_discover_via_web_search", return_value=[]),
            patch("primr.ai.grok_client.grok_llm") as grok,
        ):
            signals = gather_hiring_signals(
                "Obscure LLC",
                "https://obscure.example",
                working_folder=str(tmp_path),
            )
            # Zero LLM calls when nothing found anywhere
            grok.assert_not_called()

        assert signals is not None
        assert signals.source == "none"
        assert signals.postings_found == 0
        assert signals.is_empty()

    def test_env_toggle_skips_entirely(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_SKIP_HIRING_SIGNALS", "1")
        with patch.object(hs, "_http_get") as http:
            signals = gather_hiring_signals(
                "Acme Corp",
                "https://acme.com",
                working_folder=str(tmp_path),
            )
            http.assert_not_called()
        assert signals is None

    def test_llm_extraction_failure_yields_skeleton_not_crash(self, tmp_path):
        """When the extraction LLM call returns unparseable output we still
        write an artifact with counts but empty signals."""
        fixture_body = json.dumps(GREENHOUSE_FIXTURE).encode()

        def fake_http_get(url, timeout, headers=None, params=None):
            if "greenhouse" in url:
                return 200, fixture_body, None
            return 404, b"", None

        def fake_grok_llm(prompt, **kwargs):
            if "Pick up to" in prompt:
                return '{"selected": [0]}'
            return "this is not json at all"

        with (
            patch.object(hs, "_http_get", side_effect=fake_http_get),
            patch("primr.ai.grok_client.grok_llm", side_effect=fake_grok_llm),
        ):
            signals = gather_hiring_signals(
                "Acme Corp",
                "https://acme.com",
                working_folder=str(tmp_path),
            )

        assert signals is not None
        # Source still records where postings came from
        assert signals.source == "greenhouse"
        # Bodies were aggregated but extraction couldn't parse — empty structured fields
        assert signals.tech_stack == {}
        assert signals.summary == ""

    def test_recon_hint_slug_tried_first(self, tmp_path):
        """Recon-supplied slug should be tried before name-derived guesses."""
        probed: list[str] = []
        fixture_body = json.dumps(GREENHOUSE_FIXTURE).encode()

        def fake_http_get(url, timeout, headers=None, params=None):
            probed.append(url)
            # Only the recon slug gets a 200; everything else 404
            if "boards-api.greenhouse.io/v1/boards/my-recon-slug/jobs" in url:
                return 200, fixture_body, None
            return 404, b"", None

        def fake_grok_llm(prompt, **kwargs):
            if "Pick up to" in prompt:
                return '{"selected": [0]}'
            return json.dumps({"summary": "ok"})

        with (
            patch.object(hs, "_http_get", side_effect=fake_http_get),
            patch("primr.ai.grok_client.grok_llm", side_effect=fake_grok_llm),
        ):
            signals = gather_hiring_signals(
                "Acme Corp",
                "https://acme.com",
                working_folder=str(tmp_path),
                recon_hints={"ats_slugs": ["my-recon-slug"]},
            )

        assert signals is not None
        assert signals.source == "greenhouse"
        assert any("my-recon-slug" in url for url in probed)


# =============================================================================
# Posting staleness
# =============================================================================


class TestPostingStaleness:
    def test_fresh_posting_is_not_stale(self):
        from datetime import datetime, timezone

        fresh_iso = datetime.now(timezone.utc).isoformat()
        p = Posting(url="u", title="t", updated_at=fresh_iso)
        assert not p.is_stale()
        age = p.age_days()
        assert age is not None
        assert age < 5

    def test_posting_without_date_has_no_age(self):
        p = Posting(url="u", title="t", updated_at=None)
        assert p.age_days() is None
        assert not p.is_stale()

    def test_very_old_posting_is_stale(self):
        p = Posting(url="u", title="t", updated_at="2023-01-01T00:00:00+00:00")
        assert p.is_stale()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
