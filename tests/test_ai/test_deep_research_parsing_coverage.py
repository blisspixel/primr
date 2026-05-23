"""Coverage tests for primr.ai.deep_research_parsing.

Targets the all-sources-sections mode, dedupe path, inline-placeholder
synthesis, interaction content extraction, and search-query counting across
its grounding-metadata shapes.
"""

from __future__ import annotations

from types import SimpleNamespace

from primr.ai import deep_research_parsing as p

# ---------------------------------------------------------------------------
# extract_interaction_content
# ---------------------------------------------------------------------------


def test_extract_interaction_content_joins():
    interaction = SimpleNamespace(
        outputs=[
            SimpleNamespace(text="a"),
            SimpleNamespace(text=""),
            SimpleNamespace(text="b"),
        ]
    )
    assert p.extract_interaction_content(interaction) == "a\nb"


def test_extract_interaction_content_no_outputs():
    assert p.extract_interaction_content(SimpleNamespace(outputs=[])) == ""
    assert p.extract_interaction_content(SimpleNamespace()) == ""


# ---------------------------------------------------------------------------
# extract_citations_from_content
# ---------------------------------------------------------------------------


def test_citations_empty_content():
    assert p.extract_citations_from_content("") == []


def test_citations_trailing_sources_section():
    content = (
        "Body.\n\n**Sources:**\n"
        "1. [Acme](https://acme.example)\n"
        "2. [News](https://news.example)\n"
    )
    cites = p.extract_citations_from_content(content)
    assert len(cites) == 2
    assert cites[0]["url"] == "https://acme.example"


def test_citations_all_sources_sections():
    content = (
        "Ch1.\n**Sources:**\n1. [A](https://a.example)\n\n"
        "Ch2.\n**Sources:**\n1. [B](https://b.example)\n"
    )
    cites = p.extract_citations_from_content(content, all_sources_sections=True)
    urls = {c["url"] for c in cites}
    assert urls == {"https://a.example", "https://b.example"}


def test_citations_all_sources_dedupe():
    content = (
        "**Sources:**\n1. [A](https://dup.example)\n\n"
        "**Sources:**\n1. [A again](https://dup.example)\n"
    )
    cites = p.extract_citations_from_content(
        content, all_sources_sections=True, dedupe_urls=True
    )
    assert len(cites) == 1


def test_citations_trailing_dedupe():
    content = (
        "**Sources:**\n"
        "1. [A](https://dup.example)\n"
        "2. [B](https://dup.example)\n"
    )
    cites = p.extract_citations_from_content(content, dedupe_urls=True)
    assert len(cites) == 1


def test_citations_inline_placeholder_fallback():
    content = "Claim [cite: 2, 1] and [cite: 3]."
    cites = p.extract_citations_from_content(
        content, include_inline_placeholders=True
    )
    assert [c["number"] for c in cites] == ["1", "2", "3"]
    assert all(c["url"] == "" for c in cites)


def test_citations_no_inline_when_flag_off():
    content = "Claim [cite: 1]."
    assert p.extract_citations_from_content(content) == []


# ---------------------------------------------------------------------------
# extract_interaction_citations
# ---------------------------------------------------------------------------


def test_extract_interaction_citations_uses_inline():
    interaction = SimpleNamespace(
        outputs=[SimpleNamespace(text="Body [cite: 5].")]
    )
    cites = p.extract_interaction_citations(interaction)
    assert cites[0]["number"] == "5"


# ---------------------------------------------------------------------------
# extract_search_queries_count
# ---------------------------------------------------------------------------


def test_search_queries_count_output_level():
    meta = SimpleNamespace(web_search_queries=["q1", "q2", "q3"])
    interaction = SimpleNamespace(
        outputs=[SimpleNamespace(grounding_metadata=meta)]
    )
    assert p.extract_search_queries_count(interaction) == 3


def test_search_queries_count_camelcase_metadata():
    meta = SimpleNamespace(web_search_queries=["q1"])
    out = SimpleNamespace(groundingMetadata=meta)
    # Avoid the grounding_metadata attribute entirely.
    interaction = SimpleNamespace(outputs=[out])
    assert p.extract_search_queries_count(interaction) == 1


def test_search_queries_count_candidate_level():
    candidate_meta = SimpleNamespace(web_search_queries=["q1", "q2"])
    candidate = SimpleNamespace(grounding_metadata=candidate_meta)
    out = SimpleNamespace(candidates=[candidate])
    interaction = SimpleNamespace(outputs=[out])
    assert p.extract_search_queries_count(interaction) == 2


def test_search_queries_count_zero_when_no_metadata():
    interaction = SimpleNamespace(outputs=[SimpleNamespace()])
    assert p.extract_search_queries_count(interaction) == 0


def test_search_queries_count_no_outputs():
    assert p.extract_search_queries_count(SimpleNamespace()) == 0


def test_search_queries_count_non_list_ignored():
    meta = SimpleNamespace(web_search_queries="not-a-list")
    interaction = SimpleNamespace(
        outputs=[SimpleNamespace(grounding_metadata=meta)]
    )
    assert p.extract_search_queries_count(interaction) == 0
