"""First-party JSON-LD recovery for blocked-origin fallback runs."""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from primr.data.first_party_url import same_site

logger = logging.getLogger(__name__)

HttpGet = Callable[..., tuple[int | None, bytes | None, str | None]]

_HTML_MAX_BYTES = 1_000_000
_JSON_LD_BLOCK_MAX_CHARS = 500_000
_CONTENT_CHAR_CAP = 8_000
_MIN_CONTENT_CHARS = 120
_DEFAULT_MAX_PAGES = 3
_DEFAULT_MAX_ENTITIES = 12
_DEFAULT_MAX_PROBE_URLS = 10

_STRUCTURED_DATA_PATHS = (
    "/",
    "/about",
    "/about-us",
    "/company",
    "/news",
    "/newsroom",
    "/press",
    "/investors",
    "/investor-relations",
    "/leadership",
    "/help",
    "/support",
)

_INTERESTING_TYPES = {
    "Article",
    "BlogPosting",
    "Corporation",
    "Event",
    "JobPosting",
    "LocalBusiness",
    "NewsArticle",
    "Organization",
    "Person",
    "Product",
    "WebPage",
}


@dataclass
class StructuredDataPage:
    """Structured facts recovered from JSON-LD on a first-party page."""

    url: str
    content: str
    raw_html: bytes | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class _JsonLdCollector(HTMLParser):
    """Collect bounded ``application/ld+json`` script bodies from HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._capturing = False
        self._parts: list[str] = []
        self._chars = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script" or self._capturing:
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        script_type = attr_map.get("type", "").lower()
        if "ld+json" not in script_type:
            return
        self._capturing = True
        self._parts = []
        self._chars = 0

    def handle_data(self, data: str) -> None:
        if not self._capturing or self._chars >= _JSON_LD_BLOCK_MAX_CHARS:
            return
        remaining = _JSON_LD_BLOCK_MAX_CHARS - self._chars
        chunk = data[:remaining]
        self._parts.append(chunk)
        self._chars += len(chunk)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self._capturing:
            return
        block = "".join(self._parts).strip()
        if block:
            self.blocks.append(block)
        self._capturing = False
        self._parts = []
        self._chars = 0


def fetch_structured_data_pages(
    base_host: str,
    *,
    http_get: HttpGet,
    per_request_timeout: float = 10.0,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_entities: int = _DEFAULT_MAX_ENTITIES,
    max_probe_urls: int = _DEFAULT_MAX_PROBE_URLS,
) -> list[StructuredDataPage]:
    """Recover bounded, same-site JSON-LD facts from priority first-party pages."""

    normalized_host = base_host.lower().removeprefix("www.").strip()
    if not normalized_host:
        return []

    pages: list[StructuredDataPage] = []
    seen_entities: set[tuple[str, ...]] = set()
    for url in _candidate_urls(normalized_host, max_probe_urls=max_probe_urls):
        if len(pages) >= max_pages or len(seen_entities) >= max_entities:
            break
        status, body, final_url = http_get(url, timeout=per_request_timeout)
        if status != 200 or not body:
            continue
        page = _structured_page_from_html(
            final_url or url,
            body,
            normalized_host,
            seen_entities=seen_entities,
            max_entities=max_entities,
        )
        if page is not None:
            pages.append(page)

    if pages:
        logger.info(
            "Structured-data fallback: recovered %d page(s) for %s",
            len(pages),
            normalized_host,
        )
    return pages


def fetch_structured_data_content(
    base_host: str,
    *,
    http_get: HttpGet | None = None,
    per_request_timeout: float = 10.0,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_entities: int = _DEFAULT_MAX_ENTITIES,
    max_probe_urls: int = _DEFAULT_MAX_PROBE_URLS,
) -> list[Any]:
    """Return fallback-page objects for JSON-LD facts without growing fan-out code."""

    from primr.data.fallback_sources import FallbackPage, _http_get

    resolved_http_get = http_get or _http_get
    pages = fetch_structured_data_pages(
        base_host,
        http_get=resolved_http_get,
        per_request_timeout=per_request_timeout,
        max_pages=max_pages,
        max_entities=max_entities,
        max_probe_urls=max_probe_urls,
    )
    return [
        FallbackPage(
            url=page.url,
            source="structured_data",
            content=page.content,
            raw_html=page.raw_html,
            title=page.title,
            metadata=page.metadata,
        )
        for page in pages
    ]


def _candidate_urls(base_host: str, *, max_probe_urls: int) -> list[str]:
    hosts = [base_host]
    if not base_host.startswith("www."):
        hosts.append(f"www.{base_host}")

    candidates: list[str] = []
    for path in _STRUCTURED_DATA_PATHS:
        for host in hosts if path == "/" else hosts[:1]:
            candidates.append(urljoin(f"https://{host}/", path.lstrip("/")))

    seen: set[str] = set()
    ordered: list[str] = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
        if len(ordered) >= max_probe_urls:
            break
    return ordered


def _structured_page_from_html(
    url: str,
    body: bytes,
    base_host: str,
    *,
    seen_entities: set[tuple[str, ...]],
    max_entities: int,
) -> StructuredDataPage | None:
    blocks = _extract_json_ld_blocks(body)
    if not blocks:
        return None

    summaries: list[str] = []
    local_seen: set[tuple[str, ...]] = set()
    for block in blocks:
        for entity in _iter_json_ld_entities(block):
            if len(seen_entities) >= max_entities:
                break
            summary = _summarize_entity(entity, base_host)
            if summary is None:
                continue
            key = _entity_key(entity, base_host)
            if key in seen_entities or key in local_seen:
                continue
            local_seen.add(key)
            seen_entities.add(key)
            summaries.append(summary)
        if len(seen_entities) >= max_entities:
            break

    content = "\n\n".join(summaries)
    if len(content) < _MIN_CONTENT_CHARS:
        return None

    if len(content) > _CONTENT_CHAR_CAP:
        content = content[: _CONTENT_CHAR_CAP - 24].rstrip() + "\n\n[truncated]"

    return StructuredDataPage(
        url=url,
        content=content,
        raw_html=body[:_HTML_MAX_BYTES],
        title="First-party structured data",
        metadata={
            "entity_count": len(summaries),
            "json_ld_blocks": len(blocks),
            "path": urlparse(url).path or "/",
        },
    )


def _extract_json_ld_blocks(body: bytes) -> list[str]:
    parser = _JsonLdCollector()
    parser.feed(body[:_HTML_MAX_BYTES].decode("utf-8", errors="ignore"))
    parser.close()
    return parser.blocks


def _iter_json_ld_entities(block: str) -> Iterable[Mapping[str, Any]]:
    try:
        payload = json.loads(block)
    except json.JSONDecodeError:
        return []

    return _walk_json_ld(payload)


def _walk_json_ld(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_json_ld(item)
        return

    if not isinstance(value, Mapping):
        return

    if _is_interesting_entity(value):
        yield value

    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _walk_json_ld(item)


def _is_interesting_entity(entity: Mapping[str, Any]) -> bool:
    return bool(set(_entity_types(entity)) & _INTERESTING_TYPES)


def _entity_types(entity: Mapping[str, Any]) -> list[str]:
    raw_types = entity.get("@type") or entity.get("type")
    if isinstance(raw_types, str):
        values: Sequence[Any] = [raw_types]
    elif isinstance(raw_types, Sequence) and not isinstance(raw_types, (bytes, bytearray)):
        values = raw_types
    else:
        values = []

    types: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        local = raw.rsplit("/", 1)[-1].rsplit("#", 1)[-1].strip()
        if local:
            types.append(local)
    return types


def _summarize_entity(entity: Mapping[str, Any], base_host: str) -> str | None:
    types = _entity_types(entity)
    if not types:
        return None

    lines = [f"Structured data type: {', '.join(types)}"]
    title = _first_text(entity, ("name", "legalName", "headline", "alternateName"), limit=220)
    if title:
        lines.append(f"Name: {title}")

    description = _first_text(entity, ("description", "abstract"), limit=700)
    if description:
        lines.append(f"Description: {description}")

    same_site_url = _same_site_url(entity, base_host)
    if same_site_url:
        lines.append(f"URL: {same_site_url}")

    for name in ("datePublished", "dateModified", "dateCreated"):
        value = _text(entity.get(name), limit=80)
        if value:
            lines.append(f"{name}: {value}")

    author = _named_value(entity.get("author"), limit=160)
    if author:
        lines.append(f"Author: {author}")

    publisher = _named_value(entity.get("publisher"), limit=160)
    if publisher:
        lines.append(f"Publisher: {publisher}")

    address = _address_value(entity.get("address"))
    if address:
        lines.append(f"Address: {address}")

    if len(lines) <= 1:
        return None
    return "\n".join(lines)


def _entity_key(entity: Mapping[str, Any], base_host: str) -> tuple[str, ...]:
    return (
        "|".join(_entity_types(entity)),
        _first_text(entity, ("name", "legalName", "headline"), limit=220).lower(),
        (_same_site_url(entity, base_host) or "").lower(),
    )


def _first_text(entity: Mapping[str, Any], fields: Sequence[str], *, limit: int) -> str:
    for name in fields:
        value = _text(entity.get(name), limit=limit)
        if value:
            return value
    return ""


def _text(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return _first_text(value, ("name", "headline", "text", "@id", "url"), limit=limit)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_text(item, limit=limit) for item in value]
        collapsed = "; ".join(part for part in parts if part)
    else:
        collapsed = str(value)
    collapsed = re.sub(r"\s+", " ", html.unescape(collapsed)).strip()
    return collapsed[:limit]


def _named_value(value: Any, *, limit: int) -> str:
    if isinstance(value, Mapping):
        return _first_text(value, ("name", "legalName", "headline"), limit=limit)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_named_value(item, limit=limit) for item in value]
        return "; ".join(part for part in parts if part)[:limit]
    return _text(value, limit=limit)


def _address_value(value: Any) -> str:
    if isinstance(value, Mapping):
        fields = (
            "streetAddress",
            "addressLocality",
            "addressRegion",
            "postalCode",
            "addressCountry",
        )
        parts = [_text(value.get(field), limit=120) for field in fields]
        return ", ".join(part for part in parts if part)[:300]
    return _text(value, limit=300)


def _same_site_url(entity: Mapping[str, Any], base_host: str) -> str:
    for name in ("url", "mainEntityOfPage", "@id"):
        url = _url_value(entity.get(name))
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and same_site(parsed.hostname or "", base_host):
            return url
    return ""


def _url_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("@id", "url"):
            nested = value.get(key)
            if isinstance(nested, str):
                return nested
    return ""
