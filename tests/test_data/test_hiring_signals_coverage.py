"""Additional coverage for hiring-signal gathering.

Targets branches not covered by test_hiring_signals.py: careers-URL
candidate generation, corpus reuse in HTML discovery, posting-body fetch,
the ATS fan-out merge/tiebreak, LLM triage parse fallbacks, extraction
LLM call, render_markdown, and the persist path. All HTTP and LLM access
is mocked; filesystem uses tmp_path.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from primr.data import hiring_signals as hs
from primr.data.hiring_signals import (
    HiringSignals,
    Posting,
    _careers_url_candidates,
    _discover_via_ats,
    _discover_via_html,
    _extract_signals,
    _fetch_html_posting_bodies,
    _llm_triage,
    _persist,
    _render_markdown,
)

# =============================================================================
# careers URL candidates
# =============================================================================


class TestCareersUrlCandidates:
    def test_static_paths_off_root(self):
        urls = _careers_url_candidates("https://acme.com", None)
        assert any(u.endswith("/careers") for u in urls)
        assert any(u.endswith("/jobs") for u in urls)

    def test_corpus_careers_url_preferred(self):
        corpus = {
            "https://acme.com/about/careers": "<html>jobs</html>",
            "https://acme.com/products": "<html>products</html>",
        }
        urls = _careers_url_candidates("https://acme.com", corpus)
        assert "https://acme.com/about/careers" in urls

    def test_caps_at_documented_budget(self):
        # Cap raised from 6 to 14 in the subdomain-probing change so the
        # six subdomain probes plus the four on-path probes plus corpus
        # carryovers all fit. Verify we still cap.
        corpus = {f"https://acme.com/careers/{i}": "x" for i in range(40)}
        urls = _careers_url_candidates("https://acme.com", corpus)
        assert len(urls) <= 14


# =============================================================================
# HTML discovery via careers page
# =============================================================================


class TestDiscoverViaHtml:
    def test_uses_corpus_content_without_http(self):
        careers_html = (
            '<a href="/careers/staff-engineer">Staff Engineer</a>'
            '<a href="/careers/product-lead">Product Lead</a>'
        )
        corpus = {"https://acme.com/careers": careers_html}
        # Any non-corpus careers candidate misses; the corpus hit needs no HTTP.
        with patch.object(hs, "_http_get", return_value=(404, b"", None)):
            postings, _source = _discover_via_html("https://acme.com", corpus)
        titles = {p.title for p in postings}
        assert "Staff Engineer" in titles
        assert "Product Lead" in titles

    def test_fetches_when_not_in_corpus(self):
        careers_html = b'<a href="/jobs/data-engineer">Data Engineer</a>'

        def fake_http_get(url, timeout, headers=None, params=None):
            if url.endswith("/careers"):
                return 200, careers_html, None
            return 404, b"", None

        with patch.object(hs, "_http_get", side_effect=fake_http_get):
            postings, _source = _discover_via_html("https://acme.com", None)
        assert any("data-engineer" in p.url for p in postings)

    def test_returns_empty_when_nothing_found(self):
        with patch.object(hs, "_http_get", return_value=(404, b"", None)):
            postings, source = _discover_via_html("https://acme.com", None)
        assert postings == []
        assert source is None


# =============================================================================
# Posting body fetch
# =============================================================================


class TestFetchHtmlPostingBodies:
    def test_populates_body_for_html_postings(self):
        long_body = b"<p>" + b"Detailed job description content. " * 30 + b"</p>"
        posting = Posting(url="https://acme.com/jobs/1", title="Eng", source="html")

        with patch.object(hs, "_http_get", return_value=(200, long_body, None)):
            _fetch_html_posting_bodies([posting])
        assert posting.body is not None
        assert "Detailed job description" in posting.body

    def test_skips_ats_postings_with_body(self):
        posting = Posting(
            url="https://acme.com/jobs/1", title="Eng", source="greenhouse", body="already here"
        )
        with patch.object(hs, "_http_get") as http:
            _fetch_html_posting_bodies([posting])
            http.assert_not_called()

    def test_short_body_not_set(self):
        posting = Posting(url="https://acme.com/jobs/1", title="Eng", source="html")
        with patch.object(hs, "_http_get", return_value=(200, b"<p>tiny</p>", None)):
            _fetch_html_posting_bodies([posting])
        assert posting.body is None

    def test_no_targets_returns_early(self):
        # All postings already have bodies -> no work, no exception
        postings = [Posting(url="u", title="t", source="html", body="x" * 300)]
        with patch.object(hs, "_http_get") as http:
            _fetch_html_posting_bodies(postings)
            http.assert_not_called()


# =============================================================================
# ATS fan-out merge / tiebreak
# =============================================================================


class TestDiscoverViaAts:
    """_ATS_PROVIDERS captures function references at import time, so we patch
    the provider list itself rather than the module-level fetcher names."""

    def test_total_miss_returns_empty(self):
        providers = [
            ("greenhouse", lambda slug: None),
            ("lever", lambda slug: None),
        ]
        with patch.object(hs, "_ATS_PROVIDERS", providers):
            postings, provider = _discover_via_ats(["acme"])
        assert postings == []
        assert provider is None

    def test_picks_provider_with_most_postings(self):
        few = [Posting(url="u1", title="A", source="lever")]
        many = [Posting(url=f"u{i}", title=str(i), source="greenhouse") for i in range(5)]
        providers = [
            ("greenhouse", lambda slug: many),
            ("lever", lambda slug: few),
        ]
        with patch.object(hs, "_ATS_PROVIDERS", providers):
            postings, provider = _discover_via_ats(["acme"])
        assert provider == "greenhouse"
        assert len(postings) == 5

    def test_provider_exception_swallowed(self):
        good = [Posting(url="u", title="A", source="ashby")]

        def _raise(slug):
            raise RuntimeError("boom")

        providers = [
            ("greenhouse", _raise),
            ("ashby", lambda slug: good),
        ]
        with patch.object(hs, "_ATS_PROVIDERS", providers):
            postings, provider = _discover_via_ats(["acme"])
        assert provider == "ashby"


# =============================================================================
# LLM triage parse fallbacks
# =============================================================================


def _postings(n: int) -> list[Posting]:
    return [Posting(url=f"u{i}", title=f"Role {i}") for i in range(n)]


class TestLlmTriage:
    def test_valid_selection(self):
        with patch("primr.ai.grok_client.grok_llm", return_value='{"selected": [0, 2]}'):
            idx = _llm_triage(_postings(4), "Acme", k=3)
        assert idx == [0, 2]

    def test_llm_exception_falls_back_to_deterministic(self):
        postings = [
            Posting(url="u0", title="Retail Associate"),
            Posting(url="u1", title="Senior Data Engineer", department="Engineering"),
        ]
        with patch("primr.ai.grok_client.grok_llm", side_effect=RuntimeError("api")):
            idx = _llm_triage(postings, "Acme", k=1)
        # deterministic ranker should prefer the senior engineering role
        assert idx == [1]

    def test_non_dict_json_falls_back(self):
        with patch("primr.ai.grok_client.grok_llm", return_value="[1, 2, 3]"):
            idx = _llm_triage(_postings(4), "Acme", k=2)
        assert isinstance(idx, list)
        assert len(idx) == 2

    def test_missing_selected_key_falls_back(self):
        with patch("primr.ai.grok_client.grok_llm", return_value='{"other": [0]}'):
            idx = _llm_triage(_postings(3), "Acme", k=2)
        assert len(idx) == 2

    def test_out_of_range_indices_filtered_then_fallback(self):
        # All indices invalid -> empty valid list -> deterministic fallback
        with patch("primr.ai.grok_client.grok_llm", return_value='{"selected": [99, 100]}'):
            idx = _llm_triage(_postings(3), "Acme", k=2)
        assert all(0 <= i < 3 for i in idx)

    def test_overshoot_capped_to_k(self):
        with patch(
            "primr.ai.grok_client.grok_llm", return_value='{"selected": [0, 1, 2, 3, 4]}'
        ):
            idx = _llm_triage(_postings(6), "Acme", k=2)
        assert len(idx) == 2


# =============================================================================
# Extraction LLM call
# =============================================================================


class TestExtractSignals:
    def test_no_bodies_returns_none(self):
        postings = [Posting(url="u", title="t", body=None)]
        with patch("primr.ai.grok_client.grok_llm") as grok:
            result = _extract_signals(postings, "Acme")
            grok.assert_not_called()
        assert result is None

    def test_success_returns_parsed_dict(self):
        postings = [Posting(url="u", title="Eng", body="Snowflake dbt " * 50)]
        payload = json.dumps({"summary": "data platform buildout", "tech_stack": {"dbt": 1}})
        with patch("primr.ai.grok_client.grok_llm", return_value=payload):
            result = _extract_signals(postings, "Acme")
        assert result is not None
        assert result["summary"] == "data platform buildout"

    def test_llm_exception_returns_none(self):
        postings = [Posting(url="u", title="Eng", body="x" * 300)]
        with patch("primr.ai.grok_client.grok_llm", side_effect=RuntimeError("down")):
            assert _extract_signals(postings, "Acme") is None

    def test_unparseable_output_returns_none(self):
        postings = [Posting(url="u", title="Eng", body="x" * 300)]
        with patch("primr.ai.grok_client.grok_llm", return_value="not json at all"):
            assert _extract_signals(postings, "Acme") is None


# =============================================================================
# Markdown rendering
# =============================================================================


class TestRenderMarkdown:
    def test_full_signal_renders_all_sections(self):
        signals = HiringSignals(
            company_slug="acme",
            source="greenhouse",
            postings_found=20,
            postings_selected=15,
            postings_extracted=12,
            tech_stack={"Snowflake": 4},
            strategic_initiatives=["Build platform"],
            culture_signals=["Remote-first"],
            notable_absences=["No security roles"],
            locations=["NYC"],
            summary="Strategic synthesis.",
            hiring_volume="high",
            stale_fraction=0.25,
        )
        selected = [Posting(url="u", title="Engineer", location="NYC", department="Eng")]
        md = _render_markdown(signals, selected)
        assert "# Hiring Signals" in md
        assert "Snowflake" in md
        assert "Build platform" in md
        assert "Remote-first" in md
        assert "No security roles" in md
        assert "Strategic synthesis." in md
        assert "high" in md
        assert "25% stale" in md
        assert "[Engineer" in md

    def test_minimal_signal_still_renders(self):
        signals = HiringSignals(
            company_slug="acme",
            source="none",
            postings_found=0,
            postings_selected=0,
            postings_extracted=0,
        )
        md = _render_markdown(signals, [])
        assert "Hiring Signals" in md


# =============================================================================
# Persist artifacts
# =============================================================================


class TestPersist:
    def test_writes_all_artifacts(self, tmp_path):
        signals = HiringSignals(
            company_slug="acme",
            source="greenhouse",
            postings_found=2,
            postings_selected=1,
            postings_extracted=1,
            summary="ok",
        )
        all_postings = [Posting(url="https://acme.com/1", title="Engineer", source="greenhouse")]
        selected = [
            Posting(
                url="https://acme.com/1",
                title="Engineer",
                source="greenhouse",
                body="Detailed JD body content. " * 20,
                updated_at="2026-01-01T00:00:00Z",
            )
        ]
        _persist(str(tmp_path), signals, all_postings, selected)
        hiring = tmp_path / "_hiring"
        assert (hiring / "hiring_signals.json").exists()
        assert (hiring / "hiring_signals.md").exists()
        assert (hiring / "postings_index.json").exists()
        raw_files = list((hiring / "raw").glob("jd_*.txt"))
        assert len(raw_files) == 1
        content = raw_files[0].read_text(encoding="utf-8")
        assert "Detailed JD body content" in content

    def test_skips_raw_for_bodyless_selected(self, tmp_path):
        signals = HiringSignals(
            company_slug="acme",
            source="html",
            postings_found=1,
            postings_selected=1,
            postings_extracted=0,
        )
        selected = [Posting(url="u", title="Engineer", source="html", body=None)]
        _persist(str(tmp_path), signals, selected, selected)
        raw_files = list((tmp_path / "_hiring" / "raw").glob("jd_*.txt"))
        assert raw_files == []

    def test_unwritable_dir_fails_open(self):
        signals = HiringSignals(
            company_slug="acme",
            source="none",
            postings_found=0,
            postings_selected=0,
            postings_extracted=0,
        )
        # makedirs failure should be swallowed (no exception propagates)
        with patch("primr.data.hiring_signals.os.makedirs", side_effect=OSError("denied")):
            _persist("/nonexistent/path", signals, [], [])
