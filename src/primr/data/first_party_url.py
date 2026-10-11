"""First-party URL helpers shared by public-data recovery paths."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from primr.utils.url_helpers import normalized_hostname, public_web_url


def same_site(host: str, base_host: str) -> bool:
    """Return True when ``host`` is the base host, its www form, or a subdomain."""

    host = (host or "").lower().removeprefix("www.")
    base_host = (base_host or "").lower().removeprefix("www.")
    if not host or not base_host:
        return False
    return host == base_host or host.endswith("." + base_host)


def belongs_to_website(url: str, website: str) -> bool:
    """Match normalized HTTP(S) hosts within the supplied company's site tree.

    Keep the complete host rather than guessing a registrable domain from its
    last two labels, which would confuse unrelated tenants and public suffixes.
    """
    return url.lower().startswith(("http://", "https://")) and same_site(
        normalized_hostname(url), normalized_hostname(website)
    )


class _WebsiteLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored += 1
        if not self._ignored:
            key = "src" if tag == "iframe" else "href" if tag == "a" else ""
            self.links.extend(value for name, value in attrs if key and name == key and value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._ignored = max(0, self._ignored - 1)

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.links.extend(re.findall(r"(?<![\w=/?:&])https?://[^\s<>\"']+", data))


def website_links(content: str, base_url: str, *, limit: int = 60) -> list[str]:
    """Read bounded links from HTML or extracted text, ignoring scripts/comments."""
    parser = _WebsiteLinks()
    parser.feed(content[:1_000_000])
    links: list[str] = []
    for raw_url in parser.links:
        try:
            url = public_web_url(urljoin(base_url, raw_url))
        except ValueError:
            continue
        if url and url not in links:
            links.append(url)
            if len(links) >= limit:
                break
    return links
