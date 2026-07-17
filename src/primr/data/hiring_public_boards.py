"""Public HTML job-board helpers for hiring-signal discovery.

Some ATSs expose official job APIs only to authenticated customers or partners,
while their hosted career portals remain public. These helpers provide bounded
HTML listing extraction for those public boards without adding credentials or a
new egress path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from primr.utils.url_helpers import normalized_hostname


@dataclass(frozen=True)
class PublicBoardPosting:
    """A posting link parsed from a public hosted career board."""

    url: str
    title: str
    source: str


_POSTING_URL_HINTS = re.compile(
    r"/(?:jobs?|careers?|positions?|openings?|roles?|opportunities?|"
    r"apply|role|open[\-_]roles?|open[\-_]positions?|talent|listings?)/"
    r"(?:[a-z0-9][a-z0-9\-_]+)",
    re.IGNORECASE,
)


def _clean_slug(slug: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "", slug.lower()).strip("-")


def _strip_html_fragment(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    for key, val in {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
    }.items():
        text = text.replace(key, val)
    return re.sub(r"\s+", " ", text).strip()


def extract_posting_links(
    html: bytes,
    base_url: str,
    *,
    max_links: int,
) -> list[tuple[str, str]]:
    """Return posting-like ``(absolute_url, anchor_text)`` links from HTML."""
    try:
        text = html.decode("utf-8", errors="ignore")
    except Exception:
        return []

    pattern = re.compile(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        href, label_html = match.group(1), match.group(2)
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if not _POSTING_URL_HINTS.search(href):
            continue
        absolute = urljoin(base_url, href.split("#")[0])
        if absolute in seen:
            continue
        label = _strip_html_fragment(label_html)
        if not label or len(label) > 200:
            continue
        seen.add(absolute)
        out.append((absolute, label))
        if len(out) >= max_links:
            break
    return out


def _host_matches(url: str, suffixes: tuple[str, ...]) -> bool:
    host = normalized_hostname(url, strip_www=True)
    return any(host.endswith(suffix) for suffix in suffixes)


def _postings_from_html(
    html: bytes,
    base_url: str,
    *,
    source: str,
    host_suffixes: tuple[str, ...],
    max_links: int,
) -> list[PublicBoardPosting]:
    out: list[PublicBoardPosting] = []
    for url, title in extract_posting_links(html, base_url, max_links=max_links):
        if _host_matches(url, host_suffixes):
            out.append(PublicBoardPosting(url=url, title=title, source=source))
    return out


def _fetch_public_html_board(
    urls: tuple[str, ...],
    *,
    source: str,
    host_suffixes: tuple[str, ...],
    http_get,
    timeout_s: float,
    max_links: int,
    max_discovered: int,
) -> list[PublicBoardPosting] | None:
    out: list[PublicBoardPosting] = []
    seen: set[str] = set()
    for url in urls:
        status, body, resolved = http_get(url, timeout=timeout_s)
        if status != 200 or not body:
            continue
        base_url = resolved or url
        for posting in _postings_from_html(
            body,
            base_url,
            source=source,
            host_suffixes=host_suffixes,
            max_links=max_links,
        ):
            if posting.url in seen:
                continue
            seen.add(posting.url)
            out.append(posting)
            if len(out) >= max_discovered:
                return out
    return out or None


def fetch_icims_public_board(
    slug: str,
    *,
    http_get,
    timeout_s: float,
    max_links: int,
    max_discovered: int,
) -> list[PublicBoardPosting] | None:
    """Fetch public iCIMS portal HTML for a tenant slug."""
    clean = _clean_slug(slug)
    if not clean:
        return None
    urls = (
        f"https://careers-{clean}.icims.com/jobs/search",
        f"https://jobs-{clean}.icims.com/jobs/search",
        f"https://{clean}.icims.com/jobs/search",
        f"https://careers-{clean}.icims.com/jobs/intro",
        f"https://jobs-{clean}.icims.com/jobs/intro",
    )
    return _fetch_public_html_board(
        urls,
        source="icims",
        host_suffixes=(".icims.com",),
        http_get=http_get,
        timeout_s=timeout_s,
        max_links=max_links,
        max_discovered=max_discovered,
    )


def fetch_bamboohr_public_board(
    slug: str,
    *,
    http_get,
    timeout_s: float,
    max_links: int,
    max_discovered: int,
) -> list[PublicBoardPosting] | None:
    """Fetch public BambooHR hosted career HTML for a tenant slug."""
    clean = _clean_slug(slug)
    if not clean:
        return None
    urls = (
        f"https://{clean}.bamboohr.com/careers",
        f"https://{clean}.bamboohr.com/careers/list",
        f"https://{clean}.bamboohr.com/jobs",
    )
    return _fetch_public_html_board(
        urls,
        source="bamboohr",
        host_suffixes=(".bamboohr.com",),
        http_get=http_get,
        timeout_s=timeout_s,
        max_links=max_links,
        max_discovered=max_discovered,
    )
