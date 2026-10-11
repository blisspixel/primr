"""Company identity checks for guessed ATS boards and search discoveries."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Protocol, TypeVar
from urllib.parse import urljoin, urlsplit, urlunsplit

from primr.data.first_party_url import belongs_to_website
from primr.utils.logging_config import get_logger
from primr.utils.url_helpers import normalized_hostname, public_web_url

logger = get_logger(__name__)
HttpGet = Callable[..., tuple[int | None, bytes | None, str | None]]


class IdentityPosting(Protocol):
    url: str
    body: str | None
    identity: str
    identity_evidence: str


TPosting = TypeVar("TPosting", bound=IdentityPosting)


def associate_postings(postings: list[TPosting], evidence: str) -> list[TPosting]:
    """Record the identity evidence before postings reach counts or synthesis."""
    for posting in postings:
        posting.identity = "verified"
        posting.identity_evidence = evidence
    return postings


def _board_url(url: str) -> str:
    parsed = urlsplit(public_web_url(url))
    parts = parsed.path.strip("/").split("/")
    if parts and parts[0].lower() in {"en-us", "en-gb"}:
        parts = parts[1:]
    path = "/" + parts[0] if parts and parts[0] else "/"
    if normalized_hostname(url).endswith((".icims.com", ".bamboohr.com")):
        path = "/jobs/search" if ".icims.com" in parsed.netloc else "/careers"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


class _EmployerMetadata(HTMLParser):
    """Read employer schema and explicit homepage links from hosted boards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.homepages: list[str] = []
        self._schema: list[str] | None = None
        self._regions: list[str] = []
        self._anchor: tuple[str, bool, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self._schema = []
        if tag in {"header", "footer", "nav"}:
            self._regions.append(tag)
        if tag == "a" and (href := attributes.get("href")):
            label = (attributes.get("aria-label") or attributes.get("title") or "").lower()
            self._anchor = (href, bool(self._regions), [label])

    def handle_data(self, data: str) -> None:
        if self._schema is not None:
            self._schema.append(data)
        elif self._anchor is not None:
            self._anchor[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._schema is not None:
            self.json_ld.append("".join(self._schema))
            self._schema = None
        if tag == "a" and self._anchor is not None:
            href, eligible, labels = self._anchor
            label = " ".join(" ".join(labels).lower().split())
            if eligible and any(
                phrase in label
                for phrase in (
                    "company website",
                    "company homepage",
                    "visit our website",
                    "back to website",
                )
            ):
                self.homepages.append(href)
            self._anchor = None
        if tag in self._regions:
            self._regions.remove(tag)


def _employer_metadata(content: str) -> _EmployerMetadata:
    parser = _EmployerMetadata()
    parser.feed(content[:1_000_000])
    return parser


def _schema_nodes(parser: _EmployerMetadata) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for raw in parser.json_ld[:20]:
        try:
            pending = [json.loads(raw)]
        except (ValueError, RecursionError):
            continue
        while pending and len(nodes) < 1000:
            value = pending.pop()
            if isinstance(value, dict):
                nodes.append(value)
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value[:1000])
    return nodes


def _posting_key(url: str) -> tuple[str, str, str] | None:
    canonical = public_web_url(url)
    if not canonical:
        return None
    parsed = urlsplit(canonical)
    return normalized_hostname(canonical, strip_www=True), parsed.path.rstrip("/"), parsed.query


def employer_website(content: str, website: str, posting_url: str) -> str | None:
    """Match the employer of this posting, excluding tools, customers and peers."""
    expected_key = _posting_key(posting_url)
    if expected_key is None:
        return None
    nodes = _schema_nodes(_employer_metadata(content))
    by_id = {
        node["@id"]: node
        for node in nodes
        if isinstance(node.get("@id"), str) and (node.get("url") or node.get("sameAs"))
    }
    jobs = []
    for node in nodes:
        types = node.get("@type")
        if any(
            isinstance(kind, str) and kind.rsplit("/", 1)[-1] == "JobPosting"
            for kind in (types if isinstance(types, list) else [types])
        ):
            jobs.append(node)
    for job in jobs:
        job_url = job.get("url") or job.get("@id")
        if isinstance(job_url, str):
            if _posting_key(urljoin(posting_url, job_url)) != expected_key:
                continue
        elif len(jobs) != 1:
            continue
        organizations = job.get("hiringOrganization")
        for organization in organizations if isinstance(organizations, list) else [organizations]:
            if not isinstance(organization, dict):
                continue
            reference = organization.get("@id")
            if isinstance(reference, str):
                organization = by_id.get(reference, organization)
            for field in ("url", "sameAs"):
                raw_urls = organization.get(field)
                for url in raw_urls if isinstance(raw_urls, list) else [raw_urls]:
                    if isinstance(url, str) and belongs_to_website(url, website):
                        return public_web_url(url)
    return None


def verify_guessed_board(
    postings: list[TPosting],
    website: str,
    *,
    http_get: HttpGet,
    timeout: float,
    include_board_page: bool = True,
) -> list[TPosting]:
    """Require explicit employer identity, never arbitrary description backlinks.

    A board homepage can link its tenant. JobPosting employer metadata links
    only the specific role it describes, without promoting a mixed board.
    All network fetches retain the existing SSRF-safe HTTP boundary.
    """
    if not postings or not normalized_hostname(website):
        return []
    if include_board_page:
        board_url = _board_url(postings[0].url)
        if public_web_url(board_url):
            status, body, resolved = http_get(board_url, timeout=timeout)
            if status == 200 and body:
                final_url = resolved or board_url
                parser = _employer_metadata(body.decode("utf-8", errors="replace"))
                for homepage in parser.homepages:
                    try:
                        link = public_web_url(urljoin(final_url, homepage))
                    except ValueError:
                        continue
                    if belongs_to_website(link, website):
                        return associate_postings(postings, f"board_company_homepage:{link}")
    verified: list[TPosting] = []
    for posting in postings:
        if belongs_to_website(posting.url, website):
            verified.extend(
                associate_postings([posting], f"posting_url:{public_web_url(posting.url)}")
            )
    for posting in postings[:2]:
        if posting in verified:
            continue
        employer = employer_website(posting.body or "", website, posting.url)
        if not employer and public_web_url(posting.url):
            status, body, resolved = http_get(posting.url, timeout=timeout)
            if status == 200 and body:
                employer = employer_website(
                    body.decode("utf-8", errors="replace"), website, resolved or posting.url
                )
        if employer:
            verified.extend(
                associate_postings([posting], f"jobposting_hiring_organization:{employer}")
            )
    if not verified:
        logger.info("Hiring identity: rejected unverified board %s", postings[0].url)
    return verified


def verify_search_postings(
    postings: list[TPosting],
    website: str,
    *,
    http_get: HttpGet,
    timeout: float,
    budget_seconds: float = 20.0,
) -> list[TPosting]:
    """Check individual search hits within a shared network time budget.

    Search hosts may aggregate unrelated employers. A generic board index
    backlink cannot establish the identity of an individual search result.
    """
    verified: list[TPosting] = []
    deadline = time.monotonic() + budget_seconds
    for posting in postings[:20]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            verified.extend(
                verify_guessed_board(
                    [posting],
                    website,
                    http_get=http_get,
                    timeout=min(timeout, remaining),
                    include_board_page=False,
                )
            )
        except Exception as exc:
            logger.debug("Search identity check failed for %s: %s", posting.url, exc)
    return verified


def discover_verified_ats(
    slugs: list[str],
    website: str,
    *,
    providers: Sequence[tuple[str, Callable[[str], list[TPosting] | None]]],
    http_get: HttpGet,
    timeout: float,
    max_workers: int,
) -> tuple[list[TPosting], str | None]:
    """Probe candidates independently and rank only identity-linked boards."""
    if not normalized_hostname(website):
        return [], None

    def probe(
        provider: str, fetcher: Callable[[str], list[TPosting] | None], slug: str
    ) -> tuple[str, str, list[TPosting]]:
        try:
            postings = verify_guessed_board(
                fetcher(slug) or [], website, http_get=http_get, timeout=timeout
            )
        except Exception as exc:
            logger.debug("ATS identity probe %s/%s failed: %s", provider, slug, exc)
            postings = []
        return provider, slug, postings

    results: list[tuple[str, str, list[TPosting]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(probe, provider, fetcher, slug)
            for provider, fetcher in providers
            for slug in slugs
        ]
        for future in as_completed(futures):
            result = future.result()
            if result[2]:
                results.append(result)
    if not results:
        return [], None
    provider, _, postings = min(results, key=lambda result: (-len(result[2]), result[0], result[1]))
    return postings, provider
