"""Resolve Wikipedia candidates through current Wikidata official websites."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from primr.data.first_party_url import belongs_to_website
from primr.utils.url_helpers import normalized_hostname

HttpGet = Callable[..., tuple[int | None, bytes | None, str | None]]
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _query(http_get: HttpGet, url: str, timeout: float, **params: Any) -> dict[str, Any]:
    status, body, _ = http_get(
        url, timeout=timeout, params={"format": "json", "maxlag": 5, **params}
    )
    if status != 200 or not body:
        return {}
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _official_websites(entity: dict[str, Any]) -> list[str]:
    claims = entity.get("claims") or {}
    statements = claims.get("P856") if isinstance(claims, dict) else None
    if not isinstance(statements, list):
        return []
    current = [
        statement
        for statement in statements
        if isinstance(statement, dict)
        and statement.get("rank", "normal") in {"normal", "preferred"}
        and isinstance(statement.get("qualifiers", {}), dict)
        and not _mapping(statement.get("qualifiers")).get("P582")
    ]
    preferred = [statement for statement in current if statement.get("rank") == "preferred"]
    urls: list[str] = []
    for statement in preferred or current:
        snak = _mapping(statement.get("mainsnak"))
        if snak.get("snaktype", "value") != "value":
            continue
        value = _mapping(snak.get("datavalue")).get("value")
        if isinstance(value, str):
            urls.append(value)
    return urls


def find_verified_wikipedia_title(
    company_name: str,
    website: str,
    *,
    http_get: HttpGet,
    timeout: float,
) -> str | None:
    """Return a bounded search candidate only when its P856 matches the site.

    Page properties resolve redirects to the actual article's Wikidata item.
    Missing, malformed, historic, and mismatched website claims fail closed.
    """
    if not company_name.strip() or not normalized_hostname(website):
        return None
    search = _query(
        http_get,
        WIKIPEDIA_API,
        timeout,
        action="query",
        list="search",
        srsearch=f"{company_name} company",
        srlimit=5,
    )
    query = search.get("query") or {}
    hits = query.get("search") if isinstance(query, dict) else None
    if not isinstance(hits, list):
        return None
    titles = [
        hit["title"]
        for hit in hits[:5]
        if isinstance(hit, dict) and isinstance(hit.get("title"), str)
    ]
    if not titles:
        return None
    properties = _query(
        http_get,
        WIKIPEDIA_API,
        timeout,
        action="query",
        prop="pageprops",
        ppprop="wikibase_item",
        titles="|".join(titles),
        redirects=1,
    )
    pages = _mapping(properties.get("query")).get("pages") or {}
    if not isinstance(pages, dict):
        return None
    candidates: list[tuple[str, str]] = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        title = page.get("title")
        item = _mapping(page.get("pageprops")).get("wikibase_item")
        if isinstance(title, str) and isinstance(item, str) and re.fullmatch(r"Q[1-9]\d*", item):
            candidates.append((title, item))
    if not candidates:
        return None
    query_properties = _mapping(properties.get("query"))
    aliases: dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for alias in query_properties.get(key) or []:
            if (
                isinstance(alias, dict)
                and isinstance(alias.get("from"), str)
                and isinstance(alias.get("to"), str)
            ):
                aliases[alias["from"]] = alias["to"]
    by_title = dict(candidates)
    ordered_candidates: list[tuple[str, str]] = []
    for title in titles:
        for _ in range(10):
            if title not in aliases:
                break
            title = aliases[title]
        if title in by_title and (title, by_title[title]) not in ordered_candidates:
            ordered_candidates.append((title, by_title[title]))
    candidates = ordered_candidates
    if not candidates:
        return None
    entities = (
        _query(
            http_get,
            WIKIDATA_API,
            timeout,
            action="wbgetentities",
            ids="|".join(dict.fromkeys(item for _, item in candidates)),
            props="claims",
        ).get("entities")
        or {}
    )
    if not isinstance(entities, dict):
        return None
    for title, item in candidates:
        entity = entities.get(item)
        if isinstance(entity, dict) and any(
            belongs_to_website(url, website) for url in _official_websites(entity)
        ):
            return title
    return None
