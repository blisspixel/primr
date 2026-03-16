from primr.core.research_agent import _clean_fast_report_output, _normalize_fast_citations


def test_normalize_fast_citations_converts_inline_source_tags():
    content = (
        "## Executive Summary\n\n"
        "Claim one [Source: https://example.com/a].\n"
        "Claim two [Source: https://example.com/b].\n"
        "Claim repeat [Source: https://example.com/a].\n"
    )

    normalized = _normalize_fast_citations(content)

    assert "[Source:" not in normalized
    body = normalized.split("## Sources", 1)[0]
    assert body.count("[cite: 1]") == 2
    assert body.count("[cite: 2]") == 1
    assert "## Sources" in normalized
    assert "[cite: 1] https://example.com/a" in normalized
    assert "[cite: 2] https://example.com/b" in normalized


def test_normalize_fast_citations_replaces_existing_sources_appendix():
    content = (
        "## Findings\n\n"
        "Details [Source: https://example.com/a].\n\n"
        "## Sources\n\n"
        "[cite: 99] https://old.example\n"
    )

    normalized = _normalize_fast_citations(content)
    assert "[cite: 99]" not in normalized
    assert normalized.count("## Sources") == 1
    assert "[cite: 1] https://example.com/a" in normalized


def test_normalize_fast_citations_preserves_existing_defs_and_drops_orphans():
    content = (
        "## Findings\n\n"
        "Known reference [cite: 3]. Unknown reference [cite: 9].\n\n"
        "## Sources\n\n"
        "[cite: 3] https://example.com/known\n"
    )

    normalized = _normalize_fast_citations(content)
    body = normalized.split("## Sources", 1)[0]
    assert "[cite: 9]" not in body
    assert "[cite: 1]" in body
    assert "[cite: 1] https://example.com/known" in normalized


def test_normalize_fast_citations_strips_multiword_source_tags():
    """Multi-word [Source: ...] tags (not URLs) should be stripped entirely."""
    content = (
        "## Strategy\n\n"
        "Azure is the leader [Source: Microsoft Azure].\n"
        "Also see [Source: Company Website].\n"
        "URL cite [Source: https://example.com/a].\n"
    )

    normalized = _normalize_fast_citations(content)

    assert "[Source:" not in normalized
    assert "Microsoft Azure" not in normalized or "[Source: Microsoft Azure]" not in normalized
    assert "[cite: 1] https://example.com/a" in normalized


def test_clean_fast_report_output_rewrites_nested_confidence_urls():
    content = (
        "## Findings\n\n"
        "Sticky integration [Confirmed: Dec 2022 [cite:6 from https://example.com/a]].\n"
    )

    cleaned = _clean_fast_report_output(content)

    assert "[cite:6 from" not in cleaned
    assert "(Confirmed: Dec 2022)" in cleaned
    assert "[Source: https://example.com/a]" in cleaned


def test_normalize_fast_citations_repairs_malformed_inline_citations():
    content = (
        "## Findings\n\n"
        "Sticky integration (Confirmed: Dec 2022) [Source: https://example.com/a].\n"
        "Another source [cite: 5; Tracxn].\n\n"
        "## Sources\n\n"
        "[cite: 5] https://example.com/b\n"
    )

    normalized = _normalize_fast_citations(content)
    body = normalized.split("## Sources", 1)[0]

    assert "[cite: 5; Tracxn]" not in normalized
    assert "[cite: 1]" in body
    assert "[cite: 2]" in body
    assert "[cite: 1] https://example.com/a" in normalized
    assert "[cite: 2] https://example.com/b" in normalized
