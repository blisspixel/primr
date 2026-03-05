"""
Shared parsing helpers for Deep Research interaction responses.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_interaction_content(interaction: Any) -> str:
    """Extract all text output from an interaction."""
    if hasattr(interaction, "outputs") and interaction.outputs:
        text_parts = []
        for output in interaction.outputs:
            if hasattr(output, "text") and output.text:
                text_parts.append(str(output.text))
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
        if hasattr(interaction, "outputs") and interaction.outputs:
            for output in interaction.outputs:
                metadata = None
                if hasattr(output, "grounding_metadata"):
                    metadata = output.grounding_metadata
                elif hasattr(output, "groundingMetadata"):
                    metadata = output.groundingMetadata

                if metadata and hasattr(metadata, "web_search_queries"):
                    queries = metadata.web_search_queries
                    if isinstance(queries, list):
                        return len(queries)

                if hasattr(output, "candidates") and output.candidates:
                    for candidate in output.candidates:
                        candidate_meta = None
                        if hasattr(candidate, "grounding_metadata"):
                            candidate_meta = candidate.grounding_metadata
                        elif hasattr(candidate, "groundingMetadata"):
                            candidate_meta = candidate.groundingMetadata

                        if candidate_meta and hasattr(candidate_meta, "web_search_queries"):
                            queries = candidate_meta.web_search_queries
                            if isinstance(queries, list):
                                return len(queries)
    except Exception as e:
        logger.debug("Failed to count search queries: %s", e)
        return 0

    return 0
