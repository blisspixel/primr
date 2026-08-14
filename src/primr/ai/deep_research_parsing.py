"""
Shared parsing helpers for Deep Research interaction responses.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)


def _field(value: Any, name: str, default: Any = None) -> Any:
    """Read one SDK-model or mapping field without assuming a concrete SDK type."""
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _items(value: Any) -> Sequence[Any]:
    """Return list-like SDK fields while rejecting strings and mock sentinels."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _current_interaction_text(interaction: Any) -> str:
    """Extract the final model text from the current Interactions `steps` schema."""
    output_text = _field(interaction, "output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    parts: list[str] = []
    collecting = False
    for step in reversed(_items(_field(interaction, "steps"))):
        step_type = _field(step, "type")
        if step_type == "user_input":
            break
        if step_type != "model_output":
            if collecting:
                break
            continue

        content_items = _items(_field(step, "content"))
        if not content_items:
            if collecting:
                break
            continue
        for content in reversed(content_items):
            text = _field(content, "text")
            if isinstance(text, str):
                collecting = True
                parts.append(text)
            elif collecting:
                parts.reverse()
                return "".join(parts)

    parts.reverse()
    return "".join(parts)


def extract_interaction_content(interaction: Any) -> str:
    """Extract model text from current interactions, then the legacy schema."""
    current_text = _current_interaction_text(interaction)
    if current_text:
        return current_text

    # Deliberate compatibility fallback for persisted pre-June 2026 responses.
    outputs = _items(_field(interaction, "outputs"))
    if outputs:
        text_parts = []
        for output in outputs:
            text = _field(output, "text")
            if isinstance(text, str) and text:
                text_parts.append(text)
        return "\n".join(text_parts) if text_parts else ""
    return ""


def extract_interaction_citations(interaction: Any) -> list[dict[str, str]]:
    """Extract citations from the interaction output text."""
    return extract_citations_from_content(
        extract_interaction_content(interaction),
        include_inline_placeholders=True,
    )


def extract_citations_from_content(
    content: str,
    *,
    all_sources_sections: bool = False,
    include_inline_placeholders: bool = False,
    dedupe_urls: bool = False,
) -> list[dict[str, str]]:
    """
    Extract markdown citations from text content.

    Args:
        content: Full markdown content.
        all_sources_sections: If True, parse all `**Sources:**` blocks.
            Otherwise parse only the trailing `**Sources:**` block.
        include_inline_placeholders: If True and no explicit markdown citations
            are found, synthesize placeholder entries from `[cite: ...]`.
        dedupe_urls: If True, deduplicate extracted citations by URL.
    """
    citations: list[dict[str, str]] = []
    if not content:
        return citations

    citation_pattern = r"(\d+)\.\s*\[([^\]]+)\]\(([^)]+)\)"
    seen_urls: set[str] = set()

    if all_sources_sections:
        sources_pattern = r"\*\*Sources:\*\*\s*((?:\d+\.\s*\[[^\]]+\]\([^)]+\)\s*)+)"
        sources_iter = re.finditer(sources_pattern, content)
        for sources_match in sources_iter:
            sources_text = sources_match.group(1)
            for match in re.finditer(citation_pattern, sources_text):
                url = match.group(3)
                if dedupe_urls and url in seen_urls:
                    continue
                if dedupe_urls:
                    seen_urls.add(url)
                citations.append(
                    {
                        "number": match.group(1),
                        "title": match.group(2),
                        "url": url,
                    }
                )
    else:
        sources_match = re.search(r"\*\*Sources:\*\*\s*([\s\S]*?)$", content)
        if sources_match:
            sources_text = sources_match.group(1)
            for match in re.finditer(citation_pattern, sources_text):
                url = match.group(3)
                if dedupe_urls and url in seen_urls:
                    continue
                if dedupe_urls:
                    seen_urls.add(url)
                citations.append(
                    {
                        "number": match.group(1),
                        "title": match.group(2),
                        "url": url,
                    }
                )

    if not citations and include_inline_placeholders:
        inline_pattern = r"\[cite:\s*([\d,\s]+)\]"
        all_nums = set()
        for match in re.finditer(inline_pattern, content):
            nums = [n.strip() for n in match.group(1).split(",")]
            all_nums.update(nums)
        for num in sorted(all_nums, key=lambda x: int(x) if x.isdigit() else 0):
            citations.append({"number": num, "title": f"Source {num}", "url": ""})

    return citations


def extract_search_queries_count(interaction: Any) -> int:
    """Extract actual search query count from grounding metadata."""
    try:
        query_count = 0
        for step in _items(_field(interaction, "steps")):
            if _field(step, "type") != "google_search_call":
                continue
            queries = _field(_field(step, "arguments"), "queries")
            query_count += len(_items(queries))
        if query_count:
            return query_count

        outputs = _items(_field(interaction, "outputs"))
        if outputs:
            for output in outputs:
                metadata = None
                if _field(output, "grounding_metadata") is not None:
                    metadata = _field(output, "grounding_metadata")
                elif _field(output, "groundingMetadata") is not None:
                    metadata = _field(output, "groundingMetadata")

                if metadata:
                    queries = _field(metadata, "web_search_queries")
                    if isinstance(queries, list):
                        return len(queries)

                candidates = _items(_field(output, "candidates"))
                if candidates:
                    for candidate in candidates:
                        candidate_meta = None
                        if _field(candidate, "grounding_metadata") is not None:
                            candidate_meta = _field(candidate, "grounding_metadata")
                        elif _field(candidate, "groundingMetadata") is not None:
                            candidate_meta = _field(candidate, "groundingMetadata")

                        if candidate_meta:
                            queries = _field(candidate_meta, "web_search_queries")
                            if isinstance(queries, list):
                                return len(queries)
    except Exception as e:
        logger.warning("Failed to count search queries: %s", e)
        return 0

    return 0
