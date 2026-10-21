"""Bounded sitemap expansion, incremental XML parsing and recursive work."""

from __future__ import annotations

import io
import math
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from defusedxml.ElementTree import iterparse

from primr.data.http_body import read_bounded_chunks
from primr.utils.logging_config import get_logger

from .config import SitemapConfig
from .models import DiscoveredLink
from .net import extract_host
from .rate_limiter import NoOpRateLimiter, RateLimiter

logger = get_logger(__name__)
_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class _Budget:
    remaining_documents: int
    remaining_bytes: int
    deadline: float


def _records(
    content: bytes, config: SitemapConfig, deadline: float
) -> Iterator[tuple[bool, ET.Element]]:
    """Yield complete records and detach them before advancing the parser."""
    stack: list[ET.Element] = []
    count = 0
    record_depth = 0
    index = False
    for event, element in iterparse(io.BytesIO(content), events=("start", "end"), forbid_dtd=True):
        if time.monotonic() >= deadline:
            raise TimeoutError("Sitemap deadline exceeded")
        if event == "start":
            stack.append(element)
            count += 1
            if count > config.max_sitemap_elements or len(stack) > config.max_sitemap_xml_depth:
                raise ValueError("Sitemap XML structure exceeds its budget")
            if len(stack) == 1:
                index = element.tag == _NS + "sitemapindex"
            if not record_depth and element.tag == _NS + ("sitemap" if index else "url"):
                record_depth = len(stack)
        else:
            if len(stack) == record_depth:
                yield index, element
                record_depth = 0
            if not record_depth:
                element.clear()
                if len(stack) > 1:
                    stack[-2].remove(element)
            stack.pop()


def collect_sitemap_links(
    base_url: str,
    config: SitemapConfig | None,
    rate_limiter: RateLimiter | None,
    *,
    fetch: Callable[..., Any],
) -> list[DiscoveredLink]:
    """Share one attempt, byte and elapsed-work budget across every root/child."""
    config = config or SitemapConfig()
    limiter = rate_limiter or NoOpRateLimiter()
    values = (
        config.max_sitemap_size_mb,
        config.max_total_sitemap_size_mb,
        config.max_sitemap_seconds,
        config.max_sitemap_documents,
        config.max_sitemap_elements,
        config.max_sitemap_xml_depth,
    )
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Sitemap budgets must be positive and finite")
    budget = _Budget(
        config.max_sitemap_documents,
        int(config.max_total_sitemap_size_mb * 1024 * 1024),
        time.monotonic() + config.max_sitemap_seconds,
    )
    visited: set[str] = set()
    links: list[DiscoveredLink] = []

    def walk(url: str, depth: int) -> None:
        if (
            url in visited
            or depth > config.max_sitemap_depth
            or len(links) >= config.max_urls_per_sitemap
            or budget.remaining_documents <= 0
            or budget.remaining_bytes <= 0
            or time.monotonic() >= budget.deadline
        ):
            return
        visited.add(url)
        budget.remaining_documents -= 1
        host = extract_host(url)
        initial_links = len(links)
        try:
            limit = min(int(config.max_sitemap_size_mb * 1024 * 1024), budget.remaining_bytes)
            # Reserve before I/O: failed reads/expansions retain their allowance.
            # Only known, bounded representations can refund unused capacity.
            budget.remaining_bytes -= limit
            limiter.acquire(host)
            try:
                remaining = budget.deadline - time.monotonic()
                if remaining <= 0:
                    return
                response = fetch(
                    url,
                    timeout=min(30, remaining),
                    max_body_bytes=limit,
                    max_total_body_bytes=limit,
                )
                content = response.content
                used = max(len(content), response.__dict__.get("primr_body_bytes", len(content)))
                if used > limit:
                    raise ValueError("Aggregate sitemap byte budget exceeded")
                if response.status_code != 200:
                    budget.remaining_bytes += limit - used
                    return
            finally:
                limiter.release(host)
            encoding = "gzip" if content.startswith(b"\x1f\x8b") else "identity"
            expanded = read_bounded_chunks(
                [content],
                {"content-encoding": encoding},
                limit - used + len(content),
                budget.deadline,
            )
            used += max(0, len(expanded) - len(content))
            budget.remaining_bytes += limit - used
            for index, element in _records(expanded, config, budget.deadline):
                loc = element.find(_NS + "loc")
                if loc is None or not loc.text or not loc.text.strip():
                    continue
                target = loc.text.strip()
                if index:
                    walk(target, depth + 1)
                else:
                    priority_element = element.find(_NS + "priority")
                    try:
                        priority = (
                            float(priority_element.text) if priority_element is not None else None
                        )
                        if priority is not None and not math.isfinite(priority):
                            priority = None
                    except (ValueError, TypeError):
                        priority = None
                    modified = element.find(_NS + "lastmod")
                    links.append(
                        DiscoveredLink(
                            url=target,
                            source="sitemap",
                            sitemap_priority=priority,
                            sitemap_lastmod=modified.text.strip()
                            if modified is not None and modified.text
                            else None,
                        )
                    )
                if len(links) >= config.max_urls_per_sitemap:
                    break
                if index and budget.remaining_documents <= 0:
                    break
        except Exception as exc:
            del links[initial_links:]
            logger.debug("Skipping sitemap outside its parsing/work budget: %s", exc)

    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap.xml.gz", "/sitemaps/sitemap.xml"):
        walk(base + path, 0)
        if links:
            break
    return links
