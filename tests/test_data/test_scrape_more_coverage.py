"""Additional coverage for primr.data.scrape focusing on the branches the
existing suites leave untouched: the fallback-content helper, the external /
validated source scrapers, the rate-limit skip + zero-page-supplement paths
through fetch_web_content, the orchestrator factory branches, and the legacy
compatibility wrappers.

All network / LLM / orchestrator boundaries are mocked. No real browser or
HTTP traffic. Placeholder company names only.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import primr.data.scrape as scrape
from primr.data.scrape import (
    _collect_fallback_content,
    _filter_selected_urls,
    _looks_like_low_signal_wrapper_url,
    cache_content,
    clear_cache,
    detect_waf_block,
    extract_links_from_homepage,
    extract_links_from_html,
    fetch_sitemap_links,
    fetch_web_content,
    get_external_orchestrator,
    get_orchestrator,
    guess_common_urls,
    normalize_url,
    scrape_external_sources,
    scrape_external_sources_validated,
    scrape_page,
    verify_urls_exist,
)


def _fb_page(url, source, content, title=None):
    return SimpleNamespace(url=url, source=source, content=content, title=title)


def _reset_orchestrators():
    scrape._orchestrator = None
    scrape._external_orchestrator = None


# ============================================================================
# Low-signal wrapper URL + selected-URL filtering
# ============================================================================
class TestLowSignalWrapperFilter:
    def test_bare_host_label_path_is_low_signal(self):
        # /acme mirrors the host label "acme" -> dropped
        assert (
            _looks_like_low_signal_wrapper_url("https://acme.example/acme", "https://acme.example")
            is True
        )

    def test_useful_single_segment_path_is_kept(self):
        assert (
            _looks_like_low_signal_wrapper_url("https://acme.example/about", "https://acme.example")
            is False
        )

    def test_hyphenated_segment_is_kept(self):
        assert (
            _looks_like_low_signal_wrapper_url(
                "https://acme.example/acme-corp", "https://acme.example"
            )
            is False
        )

    def test_multi_segment_path_is_kept(self):
        assert (
            _looks_like_low_signal_wrapper_url(
                "https://acme.example/acme/team", "https://acme.example"
            )
            is False
        )

    def test_segment_not_in_host_is_kept(self):
        assert (
            _looks_like_low_signal_wrapper_url(
                "https://acme.example/widgets", "https://acme.example"
            )
            is False
        )


class TestFilterSelectedUrls:
    def test_drops_homepage_self_link(self):
        urls = ["https://acme.example", "https://acme.example/about"]
        filtered = _filter_selected_urls(urls, "https://acme.example")
        assert "https://acme.example/about" in filtered
        # Homepage normalized away
        assert normalize_url("https://acme.example") not in [normalize_url(u) for u in filtered]

    def test_drops_low_signal_wrapper(self):
        urls = ["https://acme.example/acme", "https://acme.example/products"]
        filtered = _filter_selected_urls(urls, "https://acme.example")
        assert filtered == ["https://acme.example/products"]

    def test_drops_non_content_url(self):
        with patch(
            "primr.data.scrape.is_probably_content_url",
            side_effect=lambda u: "good" in u,
        ):
            filtered = _filter_selected_urls(
                ["https://acme.example/good", "https://acme.example/bad"],
                "https://acme.example",
            )
        assert filtered == ["https://acme.example/good"]


# ============================================================================
# _collect_fallback_content
# ============================================================================
class TestCollectFallbackContent:
    def test_returns_empty_dict_when_no_pages(self):
        with patch(
            "primr.data.fallback_sources.gather_fallback_content", return_value=[]
        ) as gather:
            result = _collect_fallback_content("Acme Corp", "https://acme.example")
        assert result == {}
        gather.assert_called_once()

    def test_builds_url_text_dict_and_skips_empty_pages(self):
        pages = [
            _fb_page("https://web.archive.org/acme", "wayback", "Real recovered content"),
            _fb_page("https://en.wikipedia.org/Acme", "wikipedia", "   "),  # empty after strip
        ]
        with patch("primr.data.fallback_sources.gather_fallback_content", return_value=pages):
            result = _collect_fallback_content("Acme Corp", "https://acme.example")
        assert result == {"https://web.archive.org/acme": "Real recovered content"}

    def test_grok_surrogate_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("PRIMR_DISABLE_GROK_SURROGATE", "1")
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return []

        with patch("primr.data.fallback_sources.gather_fallback_content", side_effect=_capture):
            _collect_fallback_content("Acme Corp", "https://acme.example")
        assert captured["grok_surrogate_urls"] is None
        # Wayback candidates are always built regardless of grok toggle.
        assert any(u.endswith("/about") for u in captured["wayback_urls"])

    def test_grok_surrogate_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("PRIMR_DISABLE_GROK_SURROGATE", raising=False)
        monkeypatch.delenv("PRIMR_ENABLE_GROK_SURROGATE", raising=False)
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return []

        with patch("primr.data.fallback_sources.gather_fallback_content", side_effect=_capture):
            _collect_fallback_content("Acme Corp", "https://acme.example")
        assert captured["grok_surrogate_urls"] is None

    def test_grok_surrogate_requires_explicit_enable(self, monkeypatch):
        monkeypatch.setenv("PRIMR_ENABLE_GROK_SURROGATE", "1")
        monkeypatch.delenv("PRIMR_DISABLE_GROK_SURROGATE", raising=False)
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return []

        with patch("primr.data.fallback_sources.gather_fallback_content", side_effect=_capture):
            _collect_fallback_content("Acme Corp", "https://acme.example")
        assert captured["grok_surrogate_urls"] == [
            "https://acme.example/about",
            "https://acme.example/our-story",
            "https://acme.example/leadership",
        ]

    def test_writes_raw_files_and_calls_trace(self, tmp_path):
        raw_folder = tmp_path / "_raw_scrapes"
        raw_folder.mkdir()
        traces = []
        pages = [
            _fb_page("https://web.archive.org/acme", "wayback", "Recovered body", title="Acme"),
        ]
        with patch("primr.data.fallback_sources.gather_fallback_content", return_value=pages):
            result = _collect_fallback_content(
                "Acme Corp",
                "https://acme.example",
                raw_folder=str(raw_folder),
                append_trace=lambda *a: traces.append(a),
            )
        assert result
        written = list(raw_folder.glob("fb_*_wayback.txt"))
        assert len(written) == 1
        assert "Recovered body" in written[0].read_text(encoding="utf-8")
        assert traces
        assert traces[0][0] == "FALLBACK_OK"

    def test_source_with_slash_is_sanitized_in_filename(self, tmp_path):
        raw_folder = tmp_path / "_raw_scrapes"
        raw_folder.mkdir()
        pages = [_fb_page("https://x/y", "grok/web_search", "Body text here")]
        with patch("primr.data.fallback_sources.gather_fallback_content", return_value=pages):
            _collect_fallback_content(
                "Acme Corp", "https://acme.example", raw_folder=str(raw_folder)
            )
        assert list(raw_folder.glob("fb_01_grok_web_search.txt"))


# ============================================================================
# Orchestrator factories
# ============================================================================
class TestOrchestratorFactories:
    def setup_method(self):
        _reset_orchestrators()

    def teardown_method(self):
        _reset_orchestrators()

    def test_get_external_orchestrator_excludes_patchright_and_drission(self, monkeypatch):
        monkeypatch.delenv("PRIMR_ENABLE_DRISSION", raising=False)
        orch = get_external_orchestrator()
        names = {t.name for t in orch.tiers}
        assert "patchright" not in names
        assert "drissionpage" not in names
        assert "drissionpage_stealth" not in names
        # Cached on second call
        assert get_external_orchestrator() is orch

    def test_get_external_orchestrator_keeps_drission_when_enabled(self, monkeypatch):
        monkeypatch.setenv("PRIMR_ENABLE_DRISSION", "1")
        orch = get_external_orchestrator()
        names = {t.name for t in orch.tiers}
        assert "patchright" not in names
        # Drission tiers retained when explicitly enabled
        assert {"drissionpage", "drissionpage_stealth"} & names

    def test_get_orchestrator_drops_drission_by_default(self, monkeypatch):
        monkeypatch.delenv("PRIMR_ENABLE_DRISSION", raising=False)
        orch = get_orchestrator()
        names = {t.name for t in orch.tiers}
        assert "drissionpage" not in names
        assert "drissionpage_stealth" not in names
        assert get_orchestrator() is orch


# ============================================================================
# scrape_page
# ============================================================================
class TestScrapePage:
    def test_returns_text_and_tier_on_success(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(
            success=True, extracted_text="page text", tier="httpx", error=None
        )
        with patch("primr.data.scrape.get_orchestrator", return_value=orch):
            text, tier = scrape_page("https://acme.example")
        assert text == "page text"
        assert tier == "httpx"

    def test_returns_none_and_error_on_failure(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(
            success=False, extracted_text=None, tier=None, error="blocked"
        )
        with patch("primr.data.scrape.get_orchestrator", return_value=orch):
            text, err = scrape_page("https://acme.example")
        assert text is None
        assert err == "blocked"


# ============================================================================
# scrape_external_sources
# ============================================================================
class TestScrapeExternalSources:
    def test_collects_up_to_max_sources(self):
        orch = Mock()
        orch.scrape_url.side_effect = [
            SimpleNamespace(success=True, extracted_text="x" * 200),
            SimpleNamespace(success=True, extracted_text="y" * 200),
            SimpleNamespace(success=True, extracted_text="z" * 200),
        ]
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources(
                [
                    {"url": "https://a.example"},
                    {"url": "https://b.example"},
                    {"url": "https://c.example"},
                ],
                max_sources=2,
            )
        assert len(result) == 2

    def test_skips_entries_without_url(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=True, extracted_text="x" * 200)
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources([{"title": "no url"}, {"url": "https://a.example"}])
        assert list(result) == ["https://a.example"]

    def test_allowed_domains_filter(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=True, extracted_text="x" * 200)
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources(
                [{"url": "https://keep.example/a"}, {"url": "https://drop.other/b"}],
                allowed_domains=["keep.example"],
            )
        assert list(result) == ["https://keep.example/a"]

    def test_allowed_domains_use_hostname_boundaries_and_strip_userinfo(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=True, extracted_text="x" * 200)
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources(
                [
                    {"url": "https://keep.example@evil.example/bypass"},
                    {"url": "https://user:secret@news.keep.example/story"},
                    {"url": "https://notkeep.example/lookalike"},
                ],
                max_sources=3,
                allowed_domains=["keep.example"],
            )

        assert list(result) == ["https://news.keep.example/story"]
        orch.scrape_url.assert_called_once_with("https://news.keep.example/story")

    def test_www_specific_allowlist_does_not_authorize_sibling_subdomains(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=True, extracted_text="x" * 200)
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources(
                [
                    {"url": "https://news.keep.example/story"},
                    {"url": "https://docs.www.keep.example/guide"},
                ],
                max_sources=2,
                allowed_domains=["www.keep.example"],
            )

        assert list(result) == ["https://docs.www.keep.example/guide"]
        orch.scrape_url.assert_called_once_with("https://docs.www.keep.example/guide")

    def test_skips_short_content(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=True, extracted_text="short")
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources([{"url": "https://a.example"}])
        assert result == {}

    def test_skips_failed_scrape(self):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=False, extracted_text=None)
        with patch("primr.data.scrape.get_external_orchestrator", return_value=orch):
            result = scrape_external_sources([{"url": "https://a.example"}])
        assert result == {}


# ============================================================================
# scrape_external_sources_validated
# ============================================================================
class TestScrapeExternalSourcesValidated:
    def _orch(self, text="A" * 500):
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(success=True, extracted_text=text)
        return orch

    def test_validated_source_accepted_on_yes(self):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", return_value="YES\nmentions acme.example"),
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://news.example/story", "title": "Acme deal"}],
                company_name="Acme Corp",
                website="https://acme.example",
            )
        assert "https://news.example/story" in result

    def test_rejected_source_on_no(self):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", return_value="NO\nwrong company"),
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://news.example/story", "title": "Other"}],
                company_name="Acme Corp",
                website="https://acme.example",
            )
        assert result == {}

    def test_skips_exact_main_site_domain(self):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", return_value="YES\nok") as llm_mock,
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://www.acme.example/", "title": "home"}],
                company_name="Acme Corp",
                website="https://acme.example",
            )
        assert result == {}
        # Main-site entry skipped before scraping/validation.
        llm_mock.assert_not_called()
        orch.scrape_url.assert_not_called()

    def test_skips_main_site_when_configured_url_has_port(self):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm") as llm_mock,
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://www.acme.example/news", "title": "home"}],
                company_name="Acme Corp",
                website="https://acme.example:8443",
            )

        assert result == {}
        llm_mock.assert_not_called()
        orch.scrape_url.assert_not_called()

    def test_validation_exception_skips_source(self):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", side_effect=RuntimeError("llm down")),
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://news.example/story", "title": "x"}],
                company_name="Acme Corp",
                website="https://acme.example",
            )
        assert result == {}

    def test_skips_failed_or_short_scrape(self):
        orch = Mock()
        orch.scrape_url.side_effect = [
            SimpleNamespace(success=False, extracted_text=None),
            SimpleNamespace(success=True, extracted_text="short"),
        ]
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", return_value="YES\nok") as llm_mock,
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://a.example"}, {"url": "https://b.example"}],
                company_name="Acme Corp",
                website="https://acme.example",
            )
        assert result == {}
        llm_mock.assert_not_called()

    def test_writes_raw_file_when_working_folder(self, tmp_path):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", return_value="YES\nok"),
        ):
            scrape_external_sources_validated(
                [{"url": "https://news.example/story", "title": "Acme deal"}],
                company_name="Acme Corp",
                website="https://acme.example",
                working_folder=str(tmp_path),
            )
        raw = tmp_path / "_raw_scrapes"
        assert list(raw.glob("ext_*_news.example.txt"))

    def test_none_company_and_website_tolerated(self):
        orch = self._orch()
        with (
            patch("primr.data.scrape.get_external_orchestrator", return_value=orch),
            patch("primr.ai.llm.llm", return_value="YES\nok"),
        ):
            result = scrape_external_sources_validated(
                [{"url": "https://news.example/story", "title": "x"}],
                company_name=None,
                website=None,
            )
        assert "https://news.example/story" in result


# ============================================================================
# fetch_web_content — rate-limit skip + zero-page supplement
# ============================================================================
class TestFetchWebContentFallbackPaths:
    def test_blocked_origin_prints_evidence_summary_before_public_fallback(self):
        class FakeConsole:
            _arrow = "->"

            def __init__(self):
                self.events = []

            def status(self, msg):
                self.events.append(("status", msg))

            def clear_line(self):
                self.events.append(("clear", ""))

            def found(self, msg):
                self.events.append(("found", msg))

            def fail(self, msg):
                self.events.append(("fail", msg))

            def muted(self, msg):
                self.events.append(("muted", msg))

            def done(self, msg):
                self.events.append(("done", msg))

        fake_console = FakeConsole()
        assessment = SimpleNamespace(
            reason="challenge shell",
            evidence=["soft_block_detector: challenge", "visible_text_length:12"],
        )
        orch = Mock()
        orch.scrape_url.return_value = SimpleNamespace(
            success=False,
            raw_content=None,
            error="challenge shell",
            tier="requests",
            access_assessment=assessment,
        )
        with (
            patch("primr.data.scrape.console", fake_console),
            patch("primr.data.scrape.get_orchestrator", return_value=orch),
            patch("primr.data.scraping.rate_limit_state.get_rate_limit", return_value=None),
            patch(
                "primr.data.scrape.classify_organization_type",
                return_value=SimpleNamespace(
                    organization_type="commercial", confidence=0.8, signals=[]
                ),
            ),
            patch("primr.data.scraping.discovery.discover_links", return_value=[]),
            patch("primr.data.scrape._collect_fallback_content", return_value={}),
        ):
            result = fetch_web_content("https://acme.example", "Acme Corp")

        messages = "\n".join(msg for _, msg in fake_console.events)
        assert result == {}
        assert "Could not access acme.example" in messages
        assert "Evidence: challenge shell" in messages
        assert "visible_text_length:12" in messages
        assert "0 same-site candidate page(s)" in messages
        assert "--mode deep" in messages

    def test_rate_limit_skip_goes_straight_to_fallbacks(self):
        rl_entry = SimpleNamespace(
            remaining_seconds=lambda: 125,
            reason="HTTP 429",
        )
        orch = Mock()
        with (
            patch("primr.data.scrape.get_orchestrator", return_value=orch),
            patch(
                "primr.data.scraping.rate_limit_state.get_rate_limit",
                return_value=rl_entry,
            ),
            patch(
                "primr.data.scrape._collect_fallback_content",
                return_value={"https://web.archive.org/acme": "recovered"},
            ) as collect,
        ):
            result = fetch_web_content("https://acme.example", "Acme Corp")
        assert result == {"https://web.archive.org/acme": "recovered"}
        # Never touched the live orchestrator when rate-limited.
        orch.scrape_url.assert_not_called()
        collect.assert_called_once()

    def test_rate_limit_skip_returns_empty_when_no_fallback(self):
        rl_entry = SimpleNamespace(remaining_seconds=lambda: 30, reason="HTTP 429")
        orch = Mock()
        with (
            patch("primr.data.scrape.get_orchestrator", return_value=orch),
            patch(
                "primr.data.scraping.rate_limit_state.get_rate_limit",
                return_value=rl_entry,
            ),
            patch("primr.data.scrape._collect_fallback_content", return_value={}),
        ):
            result = fetch_web_content("https://acme.example", "Acme Corp")
        assert result == {}

    def test_zero_page_origin_supplements_with_fallback(self):
        """Homepage 'succeeds' but yields no usable text -> zero-page supplement."""
        homepage_html = b"<html><body><main><h1>Acme</h1></main></body></html>"
        orch = Mock()
        orch._get_host_state.return_value = SimpleNamespace(best_tier=None)
        orch.scrape_url.return_value = SimpleNamespace(
            success=True,
            raw_content=homepage_html,
            error=None,
            tier="httpx",
            final_url="https://acme.example",
            http_status=200,
            content_type="text/html",
            access_assessment=None,
        )
        empty_structured = SimpleNamespace(
            title="Acme",
            text="",
            raw_text="",
            quality=SimpleNamespace(score=0.9, flags=[]),
            metrics=SimpleNamespace(
                char_count=0,
                heading_count=0,
                paragraph_count=0,
                link_density=0.0,
                boilerplate_ratio=0.0,
            ),
            to_plain_text=lambda include_cta=False: "",
        )
        with (
            patch("primr.data.scrape.get_orchestrator", return_value=orch),
            patch(
                "primr.data.scraping.rate_limit_state.get_rate_limit",
                return_value=None,
            ),
            patch(
                "primr.data.scrape.classify_organization_type",
                return_value=SimpleNamespace(
                    organization_type="commercial", confidence=0.9, signals=["homepage"]
                ),
            ),
            patch("primr.data.scraping.discovery.discover_links", return_value=[]),
            patch(
                "primr.data.scraping.extract_structured_content",
                return_value=empty_structured,
            ),
            # First call (homepage classify) returns content so homepage_access_ok;
            # later block-recovery falls back to "" so scraped_content stays empty.
            patch(
                "primr.data.scraping.extract_main_content",
                return_value="",
            ),
            patch(
                "primr.data.scrape._collect_fallback_content",
                return_value={"https://web.archive.org/acme": "supplemented body"},
            ) as collect,
        ):
            result = fetch_web_content("https://acme.example", "Acme Corp")
        assert result == {"https://web.archive.org/acme": "supplemented body"}
        collect.assert_called_once()


# ============================================================================
# Legacy compatibility wrappers
# ============================================================================
class TestLegacyWrappers:
    def setup_method(self):
        _reset_orchestrators()

    def teardown_method(self):
        _reset_orchestrators()

    def test_detect_waf_block_empty(self):
        blocked, reason = detect_waf_block("")
        assert blocked is True
        assert reason == "Empty response"

    def test_detect_waf_block_clean_content(self):
        # Exercise the non-empty branch; mock the underlying detector so the
        # test asserts the wrapper's pass-through, not detection heuristics.
        with patch(
            "primr.data.scrape._detect_soft_block_new",
            return_value=(False, None),
        ):
            blocked, reason = detect_waf_block("<html><body>real content</body></html>")
        assert blocked is False
        # Wrapper normalizes None reason to "".
        assert reason == ""

    def test_wrap_tier_function_extracts_text(self):
        fake_tier = Mock(
            return_value=SimpleNamespace(
                success=True, raw_content=b"<html><body>hi</body></html>", extracted_text=None
            )
        )
        wrapped = scrape._wrap_tier_function(fake_tier)
        with patch("primr.data.scrape._extract_text", return_value="extracted body"):
            text, err = wrapped("https://acme.example")
        assert text == "extracted body"
        assert err is None

    def test_wrap_tier_function_extract_failure(self):
        fake_tier = Mock(
            return_value=SimpleNamespace(
                success=True, raw_content=b"<html></html>", extracted_text=None
            )
        )
        wrapped = scrape._wrap_tier_function(fake_tier)
        with patch("primr.data.scrape._extract_text", return_value=""):
            text, err = wrapped("https://acme.example")
        assert text is None
        assert err == "Failed to extract text"

    def test_wrap_tier_function_vision_extracted_text(self):
        fake_tier = Mock(
            return_value=SimpleNamespace(
                success=True, raw_content=None, extracted_text="vision text"
            )
        )
        wrapped = scrape._wrap_tier_function(fake_tier)
        text, err = wrapped("https://acme.example")
        assert text == "vision text"
        assert err is None

    def test_wrap_tier_function_failure(self):
        fake_tier = Mock(
            return_value=SimpleNamespace(
                success=False, raw_content=None, extracted_text=None, error="dead"
            )
        )
        wrapped = scrape._wrap_tier_function(fake_tier)
        text, err = wrapped("https://acme.example")
        assert text is None
        assert err == "dead"

    def test_fetch_sitemap_links_returns_url_set(self):
        with patch(
            "primr.data.scrape._fetch_sitemap_links_new",
            return_value=[SimpleNamespace(url="https://acme.example/a")],
        ):
            assert fetch_sitemap_links("https://acme.example") == {"https://acme.example/a"}

    def test_guess_common_urls_returns_url_set(self):
        with patch(
            "primr.data.scrape._guess_common_urls_new",
            return_value=[SimpleNamespace(url="https://acme.example/about")],
        ):
            assert guess_common_urls("https://acme.example") == {"https://acme.example/about"}

    def test_verify_urls_exist_returns_url_set(self):
        with patch(
            "primr.data.scrape._verify_urls_exist_new",
            return_value=[SimpleNamespace(url="https://acme.example/live")],
        ):
            result = verify_urls_exist({"https://acme.example/live", "https://acme.example/dead"})
        assert result == {"https://acme.example/live"}

    def test_extract_links_from_html_accepts_str(self):
        with patch(
            "primr.data.scrape._extract_links_from_html_new",
            return_value=[SimpleNamespace(url="https://acme.example/x")],
        ) as new_fn:
            result = extract_links_from_html("<a href='/x'>x</a>", "https://acme.example")
        assert result == {"https://acme.example/x"}
        # str input converted to bytes before delegating
        assert isinstance(new_fn.call_args[0][0], bytes)

    def test_extract_links_from_homepage_returns_list(self):
        with patch(
            "primr.data.scrape._extract_links_from_homepage_new",
            return_value=[
                SimpleNamespace(url="https://acme.example/a"),
                SimpleNamespace(url="https://acme.example/b"),
            ],
        ):
            assert extract_links_from_homepage("https://acme.example") == [
                "https://acme.example/a",
                "https://acme.example/b",
            ]


# ============================================================================
# Cache wrappers + cleanup
# ============================================================================
class TestCacheAndCleanup:
    def setup_method(self):
        _reset_orchestrators()

    def teardown_method(self):
        _reset_orchestrators()

    def test_clear_cache_with_initialized_orchestrator(self):
        orch = get_orchestrator()
        orch.cache.set_extracted("https://acme.example/x", "cached")
        clear_cache()
        assert orch.cache.get_extracted("https://acme.example/x") is None

    def test_clear_cache_without_orchestrator(self):
        # No orchestrator initialized: should clear disk cache without error.
        assert scrape._orchestrator is None
        clear_cache()

    def test_cache_roundtrip_via_wrappers(self):
        cache_content("https://acme.example/round", "trip")
        from primr.data.scrape import get_cached_content

        assert get_cached_content("https://acme.example/round") == "trip"

    def test_cleanup_browser_swallows_errors(self):
        with patch(
            "primr.data.scraping.browsers.SharedBrowser.get",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise even when close path explodes.
            scrape.cleanup_browser()
