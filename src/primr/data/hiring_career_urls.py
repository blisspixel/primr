"""Explicit career-site URL helpers for hiring-signal discovery.

These helpers stay side-effect-light: URL normalization is structural only,
and outbound SSRF protection remains in the caller's HTTP boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar
from urllib.parse import urlparse

MAX_CAREER_URLS = 12
MAX_CAREER_URL_LENGTH = 2048

_ALLOWED_SCHEMES = {"http", "https"}
_CONTROL_CHARS = frozenset({"\x00", "\r", "\n"})

TPosting = TypeVar("TPosting")


def normalize_career_urls(raw_urls: Iterable[str] | None) -> list[str]:
    """Trim, validate, dedupe, and cap operator-supplied career URLs."""
    if not raw_urls:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls:
        url = str(raw).strip()
        if not url:
            continue
        if len(url) > MAX_CAREER_URL_LENGTH:
            raise ValueError(
                f"career_urls entry exceeds {MAX_CAREER_URL_LENGTH} characters: {url[:80]!r}"
            )
        if any(char in url for char in _CONTROL_CHARS):
            raise ValueError("career_urls entries may not contain control characters")

        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
            raise ValueError("career_urls entries must be absolute HTTP(S) URLs")

        canonical = parsed._replace(scheme=scheme).geturl()
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(canonical)
        if len(normalized) > MAX_CAREER_URLS:
            raise ValueError(f"career_urls accepts at most {MAX_CAREER_URLS} URLs")

    return normalized


def discover_career_url_postings(
    career_urls: Iterable[str],
    *,
    corpus: dict[str, str] | None,
    http_get: Callable[..., tuple[int | None, bytes | None, str | None]],
    detect_ats_redirect: Callable[[str], tuple[str, list[TPosting]] | None],
    extract_posting_links: Callable[[bytes, str], list[tuple[str, str]]],
    make_html_posting: Callable[[str, str], TPosting],
    html_timeout_s: float,
    max_discovered: int,
) -> tuple[list[TPosting], str | None]:
    """Discover postings from exact career/ATS URLs and merge valid slices.

    Unlike slug fan-out, explicit operator URLs are intentionally merged:
    enterprise career sites often split corporate, field, and subsidiary
    boards across different ATS tenants. Each URL may be a direct ATS board,
    a vanity page that redirects to an ATS, or a plain HTML listing.
    """
    postings: list[TPosting] = []
    seen_urls: set[str] = set()
    source_labels: list[str] = []
    source_seen: set[str] = set()

    def _record_source(label: str) -> None:
        if label not in source_seen:
            source_seen.add(label)
            source_labels.append(label)

    def _add_posts(label: str, found: list[TPosting]) -> None:
        for posting in found:
            url = str(getattr(posting, "url", "")).strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            postings.append(posting)
            _record_source(label)
            if len(postings) >= max_discovered:
                return

    for career_url in career_urls:
        direct_hit = detect_ats_redirect(career_url)
        if direct_hit is not None:
            provider, found = direct_hit
            _add_posts(provider, found)
            if len(postings) >= max_discovered:
                break
            continue

        html_bytes: bytes | None = None
        final_url: str | None = None
        if corpus and career_url in corpus:
            html_bytes = corpus[career_url].encode("utf-8", errors="ignore")
            final_url = career_url
        else:
            status, body, resolved = http_get(career_url, timeout=html_timeout_s)
            if status == 200 and body:
                html_bytes = body
                final_url = resolved or career_url

        if not html_bytes or not final_url:
            continue

        redirect_hit = detect_ats_redirect(final_url)
        if redirect_hit is not None:
            provider, found = redirect_hit
            _add_posts(provider, found)
            if len(postings) >= max_discovered:
                break
            continue

        html_posts = [
            make_html_posting(url, label)
            for url, label in extract_posting_links(html_bytes, final_url)
        ]
        _add_posts("html", html_posts)
        if len(postings) >= max_discovered:
            break

    if not postings:
        return [], None
    return postings[:max_discovered], "career-url:" + "+".join(source_labels)
