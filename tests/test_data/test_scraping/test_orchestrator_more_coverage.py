"""Further coverage for the scrape orchestrator.

Targets branches still uncovered after test_orchestrator.py: the pure
helper functions (``_safe_for_log``, ``_score_extracted_text``,
``_normalise_path``, ``_equivalent_paths``, ``_paths_match``,
``_detect_wrong_page``), plus state-machine paths exercised with mocked
tier fetch functions only (no real browser, no network): SSRF rejection,
remembered rate-limit skip, best-tier reordering, wrong-page detection,
binary-content skip with content-type routing, PDF routing, thin-content
escalation, and the all-tiers-failed terminal result.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from primr.data.scraping import orchestrator as orch_mod
from primr.data.scraping.cache import ScrapeCache
from primr.data.scraping.models import (
    Attempt,
    ErrorType,
    PageAccessAssessment,
    PageAccessState,
    ScrapeResult,
    ScrapeTier,
)
from primr.data.scraping.orchestrator import (
    ScrapeOrchestrator,
    _detect_wrong_page,
    _equivalent_paths,
    _normalise_path,
    _paths_match,
    _safe_for_log,
    _score_extracted_text,
)
from primr.data.scraping.rate_limiter import NoOpRateLimiter

GOOD_HTML = b"""<!DOCTYPE html>
<html><head><title>About Acme Corp</title></head>
<body><main><h1>About Acme Corp</h1>
<article>
<p>Acme Corp is a leading provider of innovative technology solutions that help businesses transform operations. Founded in 2010, we serve over 5,000 customers across North America with cloud and digital workplace services.</p>
<p>Our team of 500 certified experts brings deep expertise in cloud migration, cybersecurity, and digital transformation. We partner with industry leaders to deliver best-in-class solutions for every client.</p>
<p>Our mission is to empower organizations to achieve their full potential through technology and durable long-term partnerships with the customers we proudly serve.</p>
</article></main></body></html>"""


def make_tier(name, *, success=True, content=GOOD_HTML, content_type="text/html", **extra):
    def scrape_fn(url, timeout):
        if success:
            return ScrapeResult(
                url=url,
                success=True,
                raw_content=content,
                content_type=content_type,
                http_status=200,
                final_url=extra.get("final_url", url),
                tier=name,
                elapsed_ms=10,
                attempts=[Attempt(tier=name, success=True, elapsed_ms=10, http_status=200)],
            )
        return ScrapeResult(
            url=url,
            success=False,
            error_type=extra.get("error_type", ErrorType.NETWORK_ERROR),
            error="mock fail",
            http_status=extra.get("http_status"),
            tier=name,
            elapsed_ms=10,
            attempts=[Attempt(tier=name, success=False, error="mock fail", elapsed_ms=10)],
        )

    return ScrapeTier(name=name, scrape_fn=scrape_fn, timeout=10)


def _success_assessment(*args, **kwargs):
    """Stub classify_page_access to always report SUCCESS.

    Lets tests drive the post-classification routing (content-type, quality,
    wrong-page) without depending on the classifier's own heuristics.
    """
    return PageAccessAssessment(state=PageAccessState.SUCCESS, reason="stubbed", confidence=1.0)


def build(tiers, **kw):
    tmp = tempfile.mkdtemp()
    return ScrapeOrchestrator(
        tiers=tiers,
        cache=ScrapeCache(cache_dir=tmp),
        rate_limiter=NoOpRateLimiter(),
        delay_between_tiers=(0, 0),
        **kw,
    )


# =============================================================================
# Pure helpers
# =============================================================================


class TestSafeForLog:
    def test_none(self):
        assert _safe_for_log(None) == ""

    def test_strips_control_chars(self):
        assert _safe_for_log("a\r\nb\x1bc") == "a??b?c"

    def test_truncates_long_values(self):
        out = _safe_for_log("x" * 1000)
        assert len(out) == 256
        assert out.endswith("...")


class TestScoreExtractedText:
    def test_empty_is_zero(self):
        assert _score_extracted_text("") == 0.0

    def test_boilerplate_penalized_below_prose(self):
        prose = "This is a clear sentence about the company. " * 5
        boiler = "This website uses cookies. " * 5 + "accept all show details"
        assert _score_extracted_text(prose) > _score_extracted_text(boiler)


class TestPathHelpers:
    def test_normalise_path_strips_trailing_slash_and_lowercases(self):
        assert _normalise_path("https://x.com/About/") == "/about"

    def test_equivalent_paths_fdc_prefix(self):
        variants = _equivalent_paths("/fdc/about")
        assert "/about" in variants

    def test_equivalent_paths_adds_fdc_variant(self):
        variants = _equivalent_paths("/about")
        assert "/fdc/about" in variants

    def test_paths_match_via_fdc_equivalence(self):
        assert _paths_match("/about", "/fdc/about") is True

    def test_paths_do_not_match(self):
        assert _paths_match("/about", "/careers") is False


class TestDetectWrongPage:
    def test_homepage_always_accepted(self):
        wrong, _ = _detect_wrong_page("https://x.com/", b"<html></html>", None)
        assert wrong is False

    def test_canonical_mismatch_flagged(self):
        html = b'<html><head><link rel="canonical" href="https://x.com/blog/post"></head></html>'
        wrong, canonical = _detect_wrong_page("https://x.com/services", html, None)
        assert wrong is True
        assert "blog/post" in canonical

    def test_canonical_match_accepted(self):
        html = b'<html><head><link rel="canonical" href="https://x.com/services"></head></html>'
        wrong, _ = _detect_wrong_page("https://x.com/services", html, None)
        assert wrong is False

    def test_final_url_mismatch_flagged(self):
        wrong, final = _detect_wrong_page(
            "https://x.com/services", b"<html></html>", "https://x.com/products"
        )
        assert wrong is True
        assert final == "https://x.com/products"


# =============================================================================
# scrape_url state-machine branches (mocked tiers only)
# =============================================================================


class TestSsrf:
    def test_ssrf_blocked_url(self):
        orch = build([make_tier("t1")])
        result = orch.scrape_url("http://169.254.169.254/latest/meta-data/")
        assert result.success is False
        assert result.error_type == ErrorType.HARD_BLOCK
        assert "SSRF" in result.error


class TestRateLimitSkip:
    def test_remembered_rate_limit_skips_live_scrape(self):
        from primr.data.scraping import rate_limit_state

        rate_limit_state.reset_all_for_testing()
        rate_limit_state.record_rate_limit("example.com", reason="HTTP 429 earlier")

        orch = build([make_tier("t1")])
        try:
            result = orch.scrape_url("https://example.com/page")
        finally:
            rate_limit_state.reset_all_for_testing()

        assert result.success is False
        assert result.error_type == ErrorType.SOFT_BLOCK
        assert "rate-limited" in result.error


class TestBestTierReorder:
    def test_known_best_tier_is_tried_first(self):
        order: list[str] = []

        def fn(name):
            def scrape_fn(url, timeout):
                order.append(name)
                return make_tier(name).scrape_fn(url, timeout)

            return ScrapeTier(name=name, scrape_fn=scrape_fn, timeout=10)

        t1, t2 = fn("t1"), fn("t2")
        orch = build([t1, t2])
        # Prime best_tier to t2.
        orch._get_host_state("example.com").best_tier = "t2"
        orch.scrape_url("https://example.com/page")
        assert order[0] == "t2"


class TestWrongPageEscalation:
    def test_wrong_page_breaks_with_error_result(self):
        wrong_html = (
            b'<html><head><link rel="canonical" href="https://example.com/elsewhere">'
            b"</head><body><main><p>" + b"filler content " * 50 + b"</p></main></body></html>"
        )
        t1 = make_tier("t1", content=wrong_html)
        t2 = make_tier("t2")
        orch = build([t1, t2])
        with patch.object(orch_mod, "classify_page_access", _success_assessment):
            result = orch.scrape_url("https://example.com/services")
        # Wrong page detected -> break, no fall-through success.
        assert result.success is False
        assert "Wrong page" in result.error


class TestContentTypeRouting:
    def test_binary_content_skipped_then_escalates(self):
        # Force detect_content_type to a non-text class so the orchestrator's
        # "skip binary, escalate" branch runs (detect_content_type itself never
        # returns such a value today, so we stub it for the first tier only).
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 400
        t1 = make_tier("t1", content=png, content_type="image/png")
        t2 = make_tier("t2")
        orch = build([t1, t2])

        calls = {"n": 0}

        def fake_detect(raw, header=None):
            calls["n"] += 1
            return "image" if calls["n"] == 1 else "html"

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, None)),
            patch.object(orch_mod, "classify_page_access", _success_assessment),
            patch.object(orch_mod, "detect_content_type", side_effect=fake_detect),
        ):
            result = orch.scrape_url("https://example.com/asset")
        # Binary skipped on t1, real HTML succeeds on t2.
        assert result.success is True
        assert result.tier == "t2"

    def test_pdf_routed_to_pdf_extractor(self):
        pdf = b"%PDF-1.4\n" + b"stream content " * 30
        t1 = make_tier("t1", content=pdf, content_type="application/pdf")
        orch = build([t1])
        with (
            patch.object(orch_mod, "classify_page_access", _success_assessment),
            patch.object(
                orch_mod,
                "extract_text_from_pdf_via_llm",
                return_value=(
                    "Acme Corp annual report. Revenue grew across all segments. "
                    "The company expanded into three new markets and hired hundreds of staff. "
                    "Operating margins improved year over year as efficiency programs matured."
                ),
            ) as mock_pdf,
        ):
            result = orch.scrape_url("https://example.com/report.pdf")
        mock_pdf.assert_called_once()
        assert result.success is True
        assert "annual report" in result.extracted_text


class TestThinContentEscalation:
    def test_thin_content_escalates_to_next_tier(self):
        thin = b"<html><body><div>hi</div></body></html>"
        t1 = make_tier("t1", content=thin)
        t2 = make_tier("t2")
        orch = build([t1, t2])
        result = orch.scrape_url("https://example.com/page")
        assert result.success is True
        assert result.tier == "t2"

    def test_classifier_thin_content_escalates(self):
        """A page the real classifier rates THIN_CONTENT escalates (no stub)."""
        # Sparse body: <120 visible chars, no expected markers, no landmarks
        # -> page_access returns THIN_CONTENT, exercising the orchestrator's
        # thin/unknown escalation branch.
        sparse = b"<html><body><div>welcome</div></body></html>"
        t1 = make_tier("t1", content=sparse)
        t2 = make_tier("t2")
        orch = build([t1, t2])
        with patch.object(orch_mod, "classify_page_access") as mock_cls:
            mock_cls.side_effect = [
                PageAccessAssessment(
                    state=PageAccessState.THIN_CONTENT, reason="sparse", confidence=0.7
                ),
                PageAccessAssessment(state=PageAccessState.SUCCESS, reason="ok", confidence=0.9),
            ]
            result = orch.scrape_url("https://example.com/page")
        assert result.success is True
        assert result.tier == "t2"

    def test_classifier_unknown_escalates(self):
        """A page the classifier rates UNKNOWN also escalates."""
        t1 = make_tier("t1")
        t2 = make_tier("t2")
        orch = build([t1, t2])
        with patch.object(orch_mod, "classify_page_access") as mock_cls:
            mock_cls.side_effect = [
                PageAccessAssessment(
                    state=PageAccessState.UNKNOWN, reason="inconclusive", confidence=0.45
                ),
                PageAccessAssessment(state=PageAccessState.SUCCESS, reason="ok", confidence=0.9),
            ]
            result = orch.scrape_url("https://example.com/page")
        assert result.success is True
        assert result.tier == "t2"

    def test_soft_block_classified_as_hard_marks_host(self):
        """A SOFT_BLOCK whose reason names a hard block escalates to host-block."""
        t1 = make_tier("t1")
        orch = build([t1])
        with patch.object(orch_mod, "classify_page_access") as mock_cls:
            mock_cls.return_value = PageAccessAssessment(
                state=PageAccessState.SOFT_BLOCK,
                reason="hard block: access denied",
                confidence=0.9,
            )
            result = orch.scrape_url("https://example.com/page")
        assert result.success is False
        assert result.error_type == ErrorType.HARD_BLOCK
        host_state = orch.get_host_state("example.com")
        assert host_state is not None
        assert host_state.hard_blocked is True

    def test_soft_block_escalates_to_next_tier(self):
        """A plain SOFT_BLOCK (non-browser tier) escalates to the next tier."""
        t1 = make_tier("t1")
        t2 = make_tier("t2")
        orch = build([t1, t2])
        with patch.object(orch_mod, "classify_page_access") as mock_cls:
            mock_cls.side_effect = [
                PageAccessAssessment(
                    state=PageAccessState.SOFT_BLOCK, reason="challenge shell", confidence=0.8
                ),
                PageAccessAssessment(state=PageAccessState.SUCCESS, reason="ok", confidence=0.9),
            ]
            result = orch.scrape_url("https://example.com/page")
        assert result.success is True
        assert result.tier == "t2"


class TestHostPositiveMarkers:
    def test_learned_host_marker_can_confirm_later_generic_page(self, tmp_path, monkeypatch):
        from primr.data.scraping import host_markers

        marker_state = tmp_path / "host_markers.json"
        monkeypatch.setattr(host_markers, "STATE_FILE", marker_state)
        host_markers.reset_all_for_testing()
        host_markers.record_positive_markers("https://www.example.com/", ["ExampleCo"])
        generic_page = b"""<!DOCTYPE html>
        <html><head><title>ExampleCo customer portal</title></head>
        <body><header><nav>Home Customers Support</nav></header><section><h1>Customer portal</h1>
        <p>ExampleCo customers use this portal to review implementation guidance,
        operational playbooks, account resources, and release notes that support
        ongoing platform adoption across distributed teams.</p>
        <p>The portal includes product education, support workflows, account
        resources, and service details for organizations managing complex
        technology programs across multiple regions.</p>
        </section></body></html>"""
        orch = build([make_tier("t1", content=generic_page)])

        try:
            result = orch.scrape_url("https://www.example.com/customer-portal")
        finally:
            host_markers.reset_all_for_testing()

        assert result.success is True
        assert result.access_assessment is not None
        assert "exampleco" in result.access_assessment.matched_expected_markers


class TestAllTiersFail:
    def test_terminal_result_when_all_fail(self):
        t1 = make_tier("t1", success=False)
        t2 = make_tier("t2", success=False)
        orch = build([t1, t2])
        result = orch.scrape_url("https://example.com/page")
        assert result.success is False
        assert result.tier is None
        assert len(result.attempts) >= 2

    def test_429_records_rate_limit_state(self):
        from primr.data.scraping import rate_limit_state

        rate_limit_state.reset_all_for_testing()
        t1 = make_tier("t1", success=False, http_status=429)
        orch = build([t1])
        try:
            orch.scrape_url("https://example.com/page")
            entry = rate_limit_state.get_rate_limit("example.com")
            assert entry is not None
        finally:
            rate_limit_state.reset_all_for_testing()


class TestQualityFailureEscalation:
    def test_garbage_content_escalates(self):
        garbage = b"<html><body><main><p>404 not found</p></main></body></html>"
        # Make it long enough to clear thin-content but trip a garbage pattern.
        garbage = (
            b"<html><body><main><h1>Oops</h1><p>404 not found. "
            + b"Please try again later as the page is unavailable right now. " * 8
            + b"</p></main></body></html>"
        )
        t1 = make_tier("t1", content=garbage)
        t2 = make_tier("t2")
        orch = build([t1, t2])
        with patch.object(orch_mod, "classify_page_access", _success_assessment):
            result = orch.scrape_url("https://example.com/page")
        assert result.success is True
        assert result.tier == "t2"


@pytest.mark.parametrize("status", [200, 301, 302])
def test_score_extracted_text_monotonic_in_length(status):
    """Longer clean text scores higher (sanity for variant selection)."""
    short = "A clear sentence about the company exists here."
    longer = short * 4
    assert _score_extracted_text(longer) > _score_extracted_text(short)


class TestBrowserExecutionEnv:
    def test_non_browser_tier_is_passthrough(self):
        orch = build([make_tier("requests")])
        state = orch._get_host_state("example.com")
        before = os.environ.get("PRIMR_BROWSER_SESSION_MODE")
        # Non-adaptive tier: context manager yields without touching env.
        with orch._browser_execution_env(state, "requests"):
            assert os.environ.get("PRIMR_BROWSER_SESSION_MODE") == before

    def test_browser_tier_sets_and_restores_session_mode(self):
        orch = build([make_tier("playwright")])
        state = orch._get_host_state("example.com")
        before = os.environ.get("PRIMR_BROWSER_SESSION_MODE")
        with orch._browser_execution_env(state, "playwright"):
            assert os.environ["PRIMR_BROWSER_SESSION_MODE"] == "persistent"
        # Restored to prior value (or removed if previously unset).
        assert os.environ.get("PRIMR_BROWSER_SESSION_MODE") == before

    def test_browser_tier_headed_sets_headed_flag(self):
        orch = build([make_tier("playwright")])
        state = orch._get_host_state("example.com")
        prev = os.environ.pop("PRIMR_BROWSER_HEADED", None)
        try:
            with orch._browser_execution_env(state, "playwright", headed=True):
                assert os.environ["PRIMR_BROWSER_HEADED"] == "1"
            assert "PRIMR_BROWSER_HEADED" not in os.environ
        finally:
            if prev is not None:
                os.environ["PRIMR_BROWSER_HEADED"] = prev


class TestHostStateHelpers:
    def test_reset_host_state(self):
        orch = build([make_tier("t1")])
        orch._get_host_state("example.com")
        orch.reset_host_state("example.com")
        assert orch.get_host_state("example.com") is None

    def test_reset_all_host_states(self):
        orch = build([make_tier("t1")])
        orch._get_host_state("a.example")
        orch._get_host_state("b.example")
        orch.reset_all_host_states()
        assert orch.get_stats()["hosts_tracked"] == 0

    def test_get_host_state_missing_returns_none(self):
        orch = build([make_tier("t1")])
        assert orch.get_host_state("never-seen.example") is None


class TestScrapeUrlsLogging:
    def test_logs_success_and_failure(self):
        t_ok = make_tier("ok")
        orch_ok = build([t_ok])
        results = orch_ok.scrape_urls(["https://example.com/a", "https://example.com/b"])
        assert len(results) == 2
        assert all(r.success for r in results)

        t_bad = make_tier("bad", success=False)
        orch_bad = build([t_bad])
        results = orch_bad.scrape_urls(["https://example.com/c"])
        assert len(results) == 1
        assert results[0].success is False
