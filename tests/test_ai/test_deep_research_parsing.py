"""Tests for shared Deep Research parsing helpers."""

from types import SimpleNamespace
from unittest.mock import Mock

from primr.ai.deep_research_parsing import (
    extract_citations_from_content,
    extract_interaction_citations,
    extract_interaction_content,
    extract_search_queries_count,
)


def test_extract_interaction_content_reads_current_model_output_steps():
    interaction = SimpleNamespace(
        steps=[
            SimpleNamespace(type="thought", content=[]),
            SimpleNamespace(
                type="model_output",
                content=[
                    SimpleNamespace(type="text", text="Part one "),
                    SimpleNamespace(type="text", text="and part two"),
                ],
            ),
        ]
    )

    assert extract_interaction_content(interaction) == "Part one and part two"


def test_extract_interaction_content_reads_mapping_steps():
    interaction = {
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": "Current response"}],
            }
        ]
    }

    assert extract_interaction_content(interaction) == "Current response"


def test_extract_interaction_content_prefers_current_steps_over_legacy_outputs():
    interaction = SimpleNamespace(
        steps=[
            SimpleNamespace(
                type="model_output",
                content=[SimpleNamespace(type="text", text="Current response")],
            )
        ],
        outputs=[SimpleNamespace(text="Legacy response")],
    )

    assert extract_interaction_content(interaction) == "Current response"


def test_extract_interaction_content_concatenates_outputs():
    output1 = Mock()
    output1.text = "Part one"
    output2 = Mock()
    output2.text = "Part two"
    interaction = Mock()
    interaction.outputs = [output1, output2]

    content = extract_interaction_content(interaction)
    assert content == "Part one\nPart two"


def test_extract_search_query_count_reads_current_google_search_steps():
    interaction = SimpleNamespace(
        steps=[
            SimpleNamespace(
                type="google_search_call",
                arguments=SimpleNamespace(queries=["one", "two"]),
            ),
            SimpleNamespace(
                type="google_search_call",
                arguments=SimpleNamespace(queries=["three"]),
            ),
        ]
    )

    assert extract_search_queries_count(interaction) == 3


def test_extract_interaction_citations_with_inline_fallback():
    output = Mock()
    output.text = "Finding [cite: 3, 1]"
    interaction = Mock()
    interaction.outputs = [output]

    citations = extract_interaction_citations(interaction)
    assert [c["number"] for c in citations] == ["1", "3"]


def test_extract_citations_from_content_all_sections_dedupes_urls():
    content = (
        "**Sources:**\n"
        "1. [A](https://example.com/a)\n"
        "2. [B](https://example.com/b)\n\n"
        "More text\n\n"
        "**Sources:**\n"
        "1. [A2](https://example.com/a)\n"
        "2. [C](https://example.com/c)\n"
    )

    citations = extract_citations_from_content(
        content,
        all_sources_sections=True,
        dedupe_urls=True,
    )
    urls = [c["url"] for c in citations]
    assert urls == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]
