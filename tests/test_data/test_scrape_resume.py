"""Regression tests for scrape resume behavior from local checkpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from primr.data.scrape import fetch_web_content, normalize_url


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

    with (
        patch("primr.data.scrape.get_orchestrator", return_value=orchestrator),
        patch(
            "primr.data.scraping.scrape_with_playwright",
            return_value=SimpleNamespace(
                success=False, raw_content=None, error="network error", tier="playwright"
            ),
        ),
    ):
        content = fetch_web_content(
            website="https://example.com",
            company_name="ExampleCo",
            max_pages=10,
            working_folder=str(working_folder),
        )

    assert content[normalize_url(homepage_url)] == "Homepage local content"
    assert content[normalize_url(about_url)] == "About local content"
    # Fallback check for homepage is expected once; resumed sub-page should be skipped.
    assert orchestrator.scrape_url.call_count == 1
