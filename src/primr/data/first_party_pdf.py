"""First-party PDF recovery for blocked-origin fallback runs."""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from primr.data.first_party_url import same_site

logger = logging.getLogger(__name__)

HttpGet = Callable[..., tuple[int | None, bytes | None, str | None]]

_HTML_MAX_BYTES = 1_000_000
_PDF_MAX_BYTES = 8 * 1024 * 1024
_PDF_CONTENT_CHAR_CAP = 25_000
_MIN_PDF_TEXT_CHARS = 400
_DEFAULT_MAX_PAGES = 2
_DEFAULT_MAX_LANDING_PAGES = 12
_DEFAULT_MAX_PDF_CANDIDATES = 12

_LANDING_PATHS = (
    "/",
    "/investors",
    "/investor-relations",
    "/about",
    "/about-us",
    "/company",
    "/news",
    "/newsroom",
    "/press",
    "/media",
    "/help",
    "/support",
)

_SUBDOMAIN_PREFIXES = (
    "investors",
    "investor",
    "ir",
    "news",
    "newsroom",
    "press",
    "media",
    "help",
    "support",
)

_DIRECT_PDF_PATHS = (
    "/annual-report.pdf",
    "/investors/annual-report.pdf",
    "/investor-relations/annual-report.pdf",
    "/investor-relations/annual-reports.pdf",
    "/investors/company-overview.pdf",
    "/investors/fact-sheet.pdf",
    "/company-overview.pdf",
    "/about/company-overview.pdf",
    "/press/media-kit.pdf",
    "/news/media-kit.pdf",
    "/help/guide.pdf",
    "/support/user-guide.pdf",
)

_PRIORITY_TERMS = (
    ("annual", 35),
    ("10-k", 35),
    ("report", 30),
    ("investor", 25),
    ("fact-sheet", 22),
    ("fact sheet", 22),
    ("overview", 20),
    ("company", 20),
    ("presentation", 16),
    ("press", 12),
    ("news", 12),
    ("media-kit", 10),
    ("media kit", 10),
    ("help", 6),
    ("support", 6),
    ("guide", 6),
)


@dataclass(frozen=True)
class PdfCandidate:
    """A same-site PDF URL candidate with ranking context."""

    url: str
    title: str
    score: int
    discovered_from: str


@dataclass
class FirstPartyPdfPage:
    """Extracted text from a first-party PDF."""

    url: str
    content: str
    raw_pdf: bytes | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class _PdfLinkCollector(HTMLParser):
    """Collect PDF anchors and anchor text from bounded HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href", "").strip()
        if not href or ".pdf" not in href.lower():
            return
        self._href = href
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append((self._href, _clean_text(" ".join(self._text), limit=180)))
        self._href = None
        self._text = []


def fetch_first_party_pdf_pages(
    base_host: str,
    *,
    http_get: HttpGet,
    per_request_timeout: float = 12.0,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_landing_pages: int = _DEFAULT_MAX_LANDING_PAGES,
    max_pdf_candidates: int = _DEFAULT_MAX_PDF_CANDIDATES,
    max_pdf_bytes: int = _PDF_MAX_BYTES,
    min_text_chars: int = _MIN_PDF_TEXT_CHARS,
) -> list[FirstPartyPdfPage]:
    """Recover text from prioritized first-party PDFs with local extraction only."""

    normalized_host = base_host.lower().removeprefix("www.").strip()
    if not normalized_host:
        return []

    candidates = _discover_pdf_candidates(
        normalized_host,
        http_get=http_get,
        per_request_timeout=per_request_timeout,
        max_landing_pages=max_landing_pages,
    )
    if not candidates:
        return []

    from primr.data.scraping.content import extract_text_from_pdf

    pages: list[FirstPartyPdfPage] = []
    seen_text_hashes: set[int] = set()
    for candidate in candidates[:max_pdf_candidates]:
        if len(pages) >= max_pages:
            break

        status, body, final_url = http_get(candidate.url, timeout=per_request_timeout)
        if status != 200 or not body:
            continue
        if len(body) > max_pdf_bytes or not _looks_like_pdf(body):
            continue

        text = (extract_text_from_pdf(body) or "").strip()
        if len(text) < min_text_chars:
            continue

        text_hash = hash(text[:1_000])
        if text_hash in seen_text_hashes:
            continue
        seen_text_hashes.add(text_hash)

        content = text
        truncated = False
        if len(content) > _PDF_CONTENT_CHAR_CAP:
            content = content[: _PDF_CONTENT_CHAR_CAP - 24].rstrip() + "\n\n[truncated]"
            truncated = True

        pages.append(
            FirstPartyPdfPage(
                url=final_url or candidate.url,
                content=content,
                raw_pdf=None,
                title=candidate.title or _title_from_url(candidate.url),
                metadata={
                    "discovered_from": candidate.discovered_from,
                    "pdf_bytes": len(body),
                    "text_chars": len(text),
                    "truncated": truncated,
                },
            )
        )

    if pages:
        logger.info("First-party PDF fallback: recovered %d page(s) for %s", len(pages), base_host)
    return pages


def fetch_first_party_pdf_content(
    base_host: str,
    *,
    http_get: HttpGet | None = None,
    per_request_timeout: float = 12.0,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_landing_pages: int = _DEFAULT_MAX_LANDING_PAGES,
    max_pdf_candidates: int = _DEFAULT_MAX_PDF_CANDIDATES,
) -> list[Any]:
    """Return fallback-page objects for first-party PDFs."""

    from primr.data.fallback_sources import FallbackPage, _http_get

    pages = fetch_first_party_pdf_pages(
        base_host,
        http_get=http_get or _http_get,
        per_request_timeout=per_request_timeout,
        max_pages=max_pages,
        max_landing_pages=max_landing_pages,
        max_pdf_candidates=max_pdf_candidates,
    )
    return [
        FallbackPage(
            url=page.url,
            source="first_party_pdf",
            content=page.content,
            raw_html=page.raw_pdf,
            title=page.title,
            metadata=page.metadata,
        )
        for page in pages
    ]


def _discover_pdf_candidates(
    base_host: str,
    *,
    http_get: HttpGet,
    per_request_timeout: float,
    max_landing_pages: int,
) -> list[PdfCandidate]:
    candidates: list[PdfCandidate] = []
    for landing_url in _landing_urls(base_host)[:max_landing_pages]:
        status, body, final_url = http_get(landing_url, timeout=per_request_timeout)
        if status != 200 or not body:
            continue
        resolved_landing = final_url or landing_url
        for href, title in _extract_pdf_links(body):
            resolved = urljoin(resolved_landing, href)
            if not _is_same_site_pdf_url(resolved, base_host):
                continue
            candidates.append(
                PdfCandidate(
                    url=resolved,
                    title=title or _title_from_url(resolved),
                    score=_score_pdf_candidate(resolved, title, discovered=True),
                    discovered_from=resolved_landing,
                )
            )

    for path in _DIRECT_PDF_PATHS:
        url = urljoin(f"https://{base_host}/", path.lstrip("/"))
        candidates.append(
            PdfCandidate(
                url=url,
                title=_title_from_url(url),
                score=_score_pdf_candidate(url, "", discovered=False),
                discovered_from="direct-probe",
            )
        )

    return _dedupe_ranked_candidates(candidates)


def _landing_urls(base_host: str) -> list[str]:
    urls: list[str] = []
    for path in _LANDING_PATHS:
        urls.append(urljoin(f"https://{base_host}/", path.lstrip("/")))
    for prefix in _SUBDOMAIN_PREFIXES:
        urls.append(f"https://{prefix}.{base_host}/")
    return list(dict.fromkeys(urls))


def _extract_pdf_links(body: bytes) -> list[tuple[str, str]]:
    parser = _PdfLinkCollector()
    parser.feed(body[:_HTML_MAX_BYTES].decode("utf-8", errors="ignore"))
    parser.close()
    return parser.links


def _is_same_site_pdf_url(url: str, base_host: str) -> bool:
    parsed = urlparse(url)
    path_and_query = f"{parsed.path}?{parsed.query}".lower()
    return (
        parsed.scheme in {"http", "https"}
        and same_site(parsed.hostname or "", base_host)
        and ".pdf" in path_and_query
    )


def _looks_like_pdf(body: bytes) -> bool:
    return b"%PDF" in body[:1024]


def _dedupe_ranked_candidates(candidates: list[PdfCandidate]) -> list[PdfCandidate]:
    best_by_url: dict[str, PdfCandidate] = {}
    for candidate in candidates:
        key = candidate.url.split("#", 1)[0]
        previous = best_by_url.get(key)
        if previous is None or candidate.score > previous.score:
            best_by_url[key] = candidate
    return sorted(best_by_url.values(), key=lambda c: (-c.score, c.url))


def _score_pdf_candidate(url: str, title: str, *, discovered: bool) -> int:
    parsed = urlparse(url)
    text = f"{parsed.netloc} {parsed.path} {title}".lower().replace("_", "-")
    score = 10 if discovered else 0
    host_prefix = parsed.hostname.split(".", 1)[0] if parsed.hostname else ""
    if host_prefix in {"investor", "investors", "ir"}:
        score += 35
    if host_prefix in {"news", "newsroom", "press", "media"}:
        score += 12
    for term, value in _PRIORITY_TERMS:
        if term in text:
            score += value
    return score


def _title_from_url(url: str) -> str:
    path = urlparse(url).path.rsplit("/", 1)[-1]
    stem = path.rsplit(".", 1)[0]
    return _clean_text(stem.replace("-", " ").replace("_", " "), limit=180) or "First-party PDF"


def _clean_text(value: str, *, limit: int) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()[:limit]
