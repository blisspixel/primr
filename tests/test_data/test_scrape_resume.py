"""Regression tests for scrape resume behavior from local checkpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from primr.data.scrape import fetch_web_content, normalize_url
from primr.data.scraping.discovery import DiscoveredLink


def _write_raw_scrape(path, url: str, body: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"URL: {url}",
                "Tier: playwright",
                "Title: N/A",
                "Quality: 0.90 []",
                "Metrics: 100 chars, 1 headings, 1 paragraphs, link_density=0.00, boilerplate_ratio=0.00",
                "-" * 60,
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def test_scrape_website_uses_local_resume_when_homepage_fetch_fails(tmp_path):
    working_folder = tmp_path / "run"
    raw = working_folder / "_raw_scrapes"
    raw.mkdir(parents=True)

    homepage_url = "https://example.com/"
    about_url = "https://example.com/about"

    (raw / "_selected_links.txt").write_text(
        f"# Selected links\n001. {about_url}\n",
        encoding="utf-8",
    )
    _write_raw_scrape(raw / "homepage.txt", homepage_url, "Homepage local content")
    _write_raw_scrape(raw / "about.txt", about_url, "About local content")

    orchestrator = Mock()
    orchestrator.scrape_url.return_value = SimpleNamespace(
        success=False,
        raw_content=None,
        error="network error",
        tier="playwright",
        attempts=[],
        error_type="network",
    )
    orchestrator._get_host_state.return_value = SimpleNamespace(best_tier=None)

    with patch("primr.data.scrape.get_orchestrator", return_value=orchestrator):
        content = fetch_web_content(
            website="https://example.com",
            company_name="ExampleCo",
            max_pages=10,
            working_folder=str(working_folder),
        )

    assert content[normalize_url(homepage_url)] == "Homepage local content"
    assert content[normalize_url(about_url)] == "About local content"
    # Homepage fetch is expected once; resumed sub-page should be skipped.
    assert orchestrator.scrape_url.call_count == 1


def test_scrape_website_keeps_homepage_when_structured_blocks_are_empty(tmp_path):
    working_folder = tmp_path / "run"
    working_folder.mkdir(parents=True)

    homepage_url = "https://example.com"
    homepage_html = (
        b"<html><head><title>ExampleCo</title></head><body><main><h1>ExampleCo</h1>"
        b"<p>Visible homepage body with enough real content to pass homepage validation.</p>"
        b"</main></body></html>"
    )

    orchestrator = Mock()
    orchestrator._get_host_state.return_value = SimpleNamespace(best_tier=None)

    empty_structured = SimpleNamespace(
        title="Example",
        text="",
        raw_text="",
        quality=SimpleNamespace(score=0.95, flags=[]),
        metrics=SimpleNamespace(
            char_count=0,
            heading_count=0,
            paragraph_count=0,
            link_density=0.0,
            boilerplate_ratio=0.0,
        ),
        to_plain_text=lambda include_cta=False: "",
    )

    orchestrator.scrape_url.return_value = SimpleNamespace(
        success=True,
        raw_content=homepage_html,
        error=None,
        tier="playwright",
        final_url=homepage_url,
        http_status=200,
        content_type="text/html",
        access_assessment=None,
    )

    with (
        patch("primr.data.scrape.get_orchestrator", return_value=orchestrator),
        patch(
            "primr.data.scraping.org_profile.classify_organization_type",
            return_value=SimpleNamespace(
                organization_type="commercial",
                confidence=0.9,
                signals=["homepage"],
            ),
        ),
        patch(
            "primr.data.scraping.discovery.discover_links",
            return_value=[],
        ),
        patch(
            "primr.data.scraping.extract_structured_content",
            return_value=empty_structured,
        ),
        patch(
            "primr.data.scraping.extract_main_content",
            return_value="Visible homepage body",
        ),
    ):
        content = fetch_web_content(
            website=homepage_url,
            company_name="ExampleCo",
            max_pages=10,
            working_folder=str(working_folder),
        )

    assert content == {normalize_url(homepage_url): "Visible homepage body"}


def test_scrape_website_retries_homepage_when_playwright_hits_soft_block(tmp_path):
    working_folder = tmp_path / "run"
    working_folder.mkdir(parents=True)

    homepage_url = "https://example.com"
    recovered_html = (
        b"<html><head><title>ExampleCo</title></head><body><main><h1>ExampleCo</h1>"
        b"<p>Recovered content describing ExampleCo, its mission, and its products in a real homepage layout.</p>"
        b"<p>ExampleCo builds durable products for customers around the world and documents its history clearly.</p>"
        b"<p>The homepage includes company overview text, navigation landmarks, and brand-specific content.</p>"
        b"<p>Customers rely on ExampleCo for product quality, dependable support, and clear corporate information."
        b" The site also includes overview sections about leadership, heritage, and sustainability priorities.</p>"
        b"<p>Additional homepage content explains the brand promise, operating footprint, service model, and how "
        b"visitors can navigate deeper into the company story, investor materials, and support resources.</p>"
        b"<p>ExampleCo's homepage also summarizes product categories, regional operations, customer commitments, "
        b"corporate values, innovation programs, manufacturing standards, distribution capabilities, and long-term "
        b"strategy so that first-time visitors can immediately understand the business.</p>"
        b"<p>That overview content is intentionally substantial because the adaptive homepage validator should treat "
        b"this page as obviously real site content rather than a thin placeholder response.</p>"
        b"<p>ExampleCo provides additional homepage detail about its operating model, customer experience standards, "
        b"design philosophy, supply chain discipline, regional presence, quality controls, digital channels, "
        b"service capabilities, and long-term strategic investments across the business.</p>"
        b"<p>The homepage further explains how visitors can move into corporate overview pages, product collections, "
        b"support resources, sustainability information, newsroom items, investor materials, and contact paths "
        b"without any ambiguity about the site's identity or purpose.</p>"
        b"<p>There is enough substantive content here to resemble a genuine company homepage with visible text, "
        b"multiple descriptive paragraphs, clear branding, and enough body copy to eliminate false positives from "
        b"the short-shell detector used by the page access classifier.</p>"
        b"</main></body></html>"
    )

    orchestrator = Mock()
    orchestrator._get_host_state.return_value = SimpleNamespace(best_tier=None)
    orchestrator.scrape_url.return_value = SimpleNamespace(
        success=True,
        raw_content=recovered_html,
        error=None,
        tier="playwright",
        final_url=homepage_url,
        http_status=200,
        content_type="text/html",
        access_assessment=None,
    )

    recovered_structured = SimpleNamespace(
        title="History",
        text="Recovered content",
        raw_text="Recovered content",
        quality=SimpleNamespace(score=0.95, flags=[]),
        metrics=SimpleNamespace(
            char_count=17,
            heading_count=1,
            paragraph_count=1,
            link_density=0.0,
            boilerplate_ratio=0.0,
        ),
        to_plain_text=lambda include_cta=False: "Recovered content",
    )

    with (
        patch("primr.data.scrape.get_orchestrator", return_value=orchestrator),
        patch(
            "primr.data.scrape.classify_organization_type",
            return_value=SimpleNamespace(
                organization_type="commercial",
                confidence=0.9,
                signals=["homepage"],
            ),
        ),
        patch(
            "primr.data.scraping.discovery.discover_links",
            return_value=[],
        ),
        patch(
            "primr.data.scraping.extract_structured_content",
            return_value=recovered_structured,
        ),
        patch(
            "primr.data.scraping.extract_main_content",
            return_value="Recovered content",
        ),
    ):
        content = fetch_web_content(
            website=homepage_url,
            company_name="ExampleCo",
            max_pages=10,
            working_folder=str(working_folder),
        )

    assert content == {normalize_url(homepage_url): "Recovered content"}
    orchestrator.scrape_url.assert_called_once_with(homepage_url)


def test_scrape_website_recovers_first_party_page_when_homepage_is_blocked(tmp_path):
    working_folder = tmp_path / "run"
    working_folder.mkdir(parents=True)

    homepage_url = "https://example.com"
    about_url = "https://example.com/about"
    about_html = (
        b"<html><body><main><h1>About ExampleCo</h1>"
        b"<p>ExampleCo builds durable products for global customers.</p>"
        b"<p>Its history and mission are documented on this page.</p>"
        b"</main></body></html>"
    )

    orchestrator = Mock()
    orchestrator._get_host_state.return_value = SimpleNamespace(best_tier=None)
    orchestrator.scrape_url.side_effect = [
        SimpleNamespace(
            success=False,
            raw_content=None,
            error="Soft block detected",
            tier="curl_cffi",
            attempts=[],
            error_type="soft_block",
            access_assessment=SimpleNamespace(reason="Challenge shell detected"),
        ),
        SimpleNamespace(
            success=True,
            raw_content=about_html,
            extracted_text="About ExampleCo\nExampleCo builds durable products for global customers.",
            error=None,
            tier="curl_cffi",
            attempts=[],
            error_type=None,
        ),
    ]

    structured = SimpleNamespace(
        title="About ExampleCo",
        text="About ExampleCo\nExampleCo builds durable products for global customers.",
        raw_text="About ExampleCo\nExampleCo builds durable products for global customers.",
        quality=SimpleNamespace(score=0.95, flags=[]),
        metrics=SimpleNamespace(
            char_count=72,
            heading_count=1,
            paragraph_count=2,
            link_density=0.0,
            boilerplate_ratio=0.0,
        ),
        to_plain_text=lambda include_cta=False: (
            "About ExampleCo\nExampleCo builds durable products for global customers."
        ),
    )

    with (
        patch("primr.data.scrape.get_orchestrator", return_value=orchestrator),
        patch(
            "primr.data.scrape.classify_organization_type",
            return_value=SimpleNamespace(
                organization_type="commercial",
                confidence=0.9,
                signals=["domain"],
            ),
        ),
        patch(
            "primr.data.scraping.discovery.discover_links",
            return_value=[DiscoveredLink(url=about_url, source="guess")],
        ),
        patch(
            "primr.data.scraping.extract_structured_content",
            return_value=structured,
        ),
        patch(
            "primr.data.scraping.extract_main_content",
            return_value="About ExampleCo\nExampleCo builds durable products for global customers.",
        ),
    ):
        content = fetch_web_content(
            website=homepage_url,
            company_name="ExampleCo",
            max_pages=10,
            working_folder=str(working_folder),
        )

    assert content == {
        normalize_url(
            about_url
        ): "About ExampleCo\nExampleCo builds durable products for global customers."
    }
    assert orchestrator.scrape_url.call_count == 2


def test_scrape_website_returns_empty_when_homepage_and_first_party_recovery_fail(tmp_path):
    working_folder = tmp_path / "run"
    working_folder.mkdir(parents=True)

    homepage_url = "https://example.com"
    orchestrator = Mock()
    orchestrator._get_host_state.return_value = SimpleNamespace(best_tier=None)
    orchestrator.scrape_url.return_value = SimpleNamespace(
        success=False,
        raw_content=None,
        error="Soft block detected",
        tier="curl_cffi",
        attempts=[],
        error_type="soft_block",
        access_assessment=SimpleNamespace(reason="Challenge shell detected"),
    )

    with (
        patch("primr.data.scrape.get_orchestrator", return_value=orchestrator),
        patch(
            "primr.data.scrape.classify_organization_type",
            return_value=SimpleNamespace(
                organization_type="commercial",
                confidence=0.9,
                signals=["domain"],
            ),
        ),
        patch(
            "primr.data.scraping.discovery.discover_links",
            return_value=[],
        ),
    ):
        content = fetch_web_content(
            website=homepage_url,
            company_name="ExampleCo",
            max_pages=10,
            working_folder=str(working_folder),
        )

    assert content == {}
    orchestrator.scrape_url.assert_called_once_with(homepage_url)
