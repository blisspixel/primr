from unittest.mock import patch

from primr.core.research_agent import select_links_with_llm
from primr.data.scraping.discovery import DiscoveredLink


def test_select_links_with_llm_drops_invented_urls():
    links = [
        DiscoveredLink(url="https://example.com/about", source="homepage", anchor_text="About"),
        DiscoveredLink(url="https://example.com/news", source="homepage", anchor_text="News"),
    ]

    response = "\n".join(
        [
            "https://example.com/about",
            "https://example.com/pricing",
            "https://example.com/news",
        ]
    )

    with patch("primr.core.research_agent.llm", return_value=response):
        selected = select_links_with_llm(
            links,
            company_name="Example",
            website="https://example.com",
            organization_type="government",
        )

    assert selected == ["https://example.com/about", "https://example.com/news"]


from primr.data.scrape import _filter_selected_urls


def test_filter_selected_urls_drops_homepage_and_wrapper_urls():
    urls = [
        "https://www.fdc.myflorida.com/",
        "https://www.fdc.myflorida.com/fdc",
        "https://fdc.myflorida.com/programs",
    ]

    filtered = _filter_selected_urls(urls, "https://www.fdc.myflorida.com/")

    assert filtered == ["https://fdc.myflorida.com/programs"]
