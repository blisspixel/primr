"""Model-assisted selection of discovered first-party links."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from primr.data.scraping.org_profile import get_focus_areas_for_org_type
from primr.utils.logging_config import get_logger
from primr.utils.model_policy import model_calls_disabled

logger = get_logger("link_selection")


def build_link_selection_prompt(
    company_name: str,
    website: str,
    links_text: str,
    max_links: int,
    organization_type: str,
    *,
    focus_areas: Iterable[str] | None = None,
) -> str:
    """Build the bounded prompt used to select discovered links."""

    resolved_focus_areas = (
        focus_areas if focus_areas is not None else get_focus_areas_for_org_type(organization_type)
    )
    focus_area_text = "\n".join(f"- {focus}" for focus in resolved_focus_areas)
    return (
        f"You are selecting pages for intelligence gathering on {company_name} ({website}).\n\n"
        f"Organization type: {organization_type}.\n"
        "Choose only from the discovered URLs below. Do not invent, normalize, or rewrite URLs.\n\n"
        "Prioritize pages that help explain the organization through these focus areas:\n"
        f"{focus_area_text}\n\n"
        "Discovered URLs:\n"
        f"{links_text}\n\n"
        f"Return only URLs from the discovered list, up to {max_links}, one per line."
    )


def _heuristic_selected_urls(
    links: list[Any],
    max_links: int,
    organization_type: str,
) -> list[str]:
    """Prefer research-valuable pages when a model cannot choose."""

    try:
        from primr.data.scraping.discovery import score_links_heuristically

        scored = score_links_heuristically(list(links), organization_type=organization_type)
        return [link.url for link in scored[:max_links]]
    except Exception:
        return [link.url for link in links[:max_links]]


def select_links_with_llm(
    links: list[Any],
    company_name: str,
    website: str,
    max_links: int = 50,
    organization_type: str = "commercial",
    *,
    model_call: Callable[..., str] | None = None,
) -> list[str]:
    """Select valuable discovered links, with a bounded heuristic fallback."""

    if not links:
        return []
    if len(links) <= max_links:
        return [link.url for link in links[:max_links]]
    if model_calls_disabled():
        return _heuristic_selected_urls(links, max_links, organization_type)

    link_list = []
    for link in links[:200]:
        if hasattr(link, "anchor_text") and link.anchor_text:
            link_list.append(f"{link.url} ({link.anchor_text})")
        else:
            link_list.append(link.url)

    try:
        prompt = build_link_selection_prompt(
            company_name=company_name,
            website=website,
            links_text="\n".join(link_list),
            max_links=max_links,
            organization_type=organization_type,
        )
        if model_call is None:
            from primr.ai.llm import llm

            model_call = llm
        response = model_call(prompt, model_type="link_selection")

        discovered_urls = {link.url for link in links}
        selected_urls = []
        dropped_urls = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("http"):
                continue
            if line in discovered_urls and line not in selected_urls:
                selected_urls.append(line)
            else:
                dropped_urls.append(line)

        if dropped_urls:
            logger.info(
                "Dropped %s LLM-selected URLs that were not in the discovered set",
                len(dropped_urls),
            )
        if selected_urls:
            logger.info("LLM selected %s links from %s", len(selected_urls), len(links))
            return selected_urls
    except Exception as exc:
        logger.warning("LLM link selection failed: %s, falling back to heuristic scoring", exc)

    return _heuristic_selected_urls(links, max_links, organization_type)


__all__ = ["build_link_selection_prompt", "select_links_with_llm"]
