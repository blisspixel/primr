"""Website-controlled paths must remain raw artifact names on every platform."""

import ntpath
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from primr.data.scrape import fetch_web_content
from primr.data.scraping import PageAccessState, ScrapeResult
from primr.data.scraping.discovery import DiscoveredLink


@pytest.mark.parametrize(
    "path",
    [r"/..\..\victim", r"/C:\victim", r"/\\server\share\victim", "/victim:stream", "/about/team"],
)
def test_raw_scrape_write_contains_website_path(tmp_path, monkeypatch, path):
    website = "https://example.com"
    page = website + path
    orchestrator = Mock()
    orchestrator._get_host_state.return_value = SimpleNamespace(best_tier=None)
    orchestrator.scrape_url.side_effect = lambda url: ScrapeResult(
        url=url,
        success=True,
        tier="httpx",
        raw_content=f"<main><h1>ExampleCo</h1><p>{url} useful company information</p></main>".encode(),
        extracted_text=f"Company information for {url}",
    )
    monkeypatch.setattr("primr.data.scrape.get_orchestrator", lambda **_: orchestrator)
    monkeypatch.setattr("primr.data.scrape.SCRAPE_PILOT_COUNT", 0)
    from primr.data.scraping.models import PageAccessAssessment

    monkeypatch.setattr(
        "primr.data.scraping.classify_page_access",
        lambda *a, **kw: PageAccessAssessment(state=PageAccessState.SUCCESS, reason="ok"),
    )
    monkeypatch.setattr(
        "primr.data.scraping.discovery.discover_links",
        lambda **_: [DiscoveredLink(url=page, source="html", anchor_text="About our company")],
    )
    monkeypatch.setattr("primr.data.link_selection.select_links_with_llm", lambda *a, **kw: [page])

    fetch_web_content(website, "ExampleCo", max_pages=2, working_folder=str(tmp_path))

    artifacts = list((tmp_path / "_raw_scrapes").glob("page_*.txt"))
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.parent == tmp_path / "_raw_scrapes"
    assert ntpath.basename(artifact.name) == artifact.name
    assert not ntpath.splitdrive(artifact.name)[0]
    assert ":" not in artifact.name
    assert f"URL: {page}" in artifact.read_text(encoding="utf-8")
