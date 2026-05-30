"""Unit tests for ReportFormatter and FormattedReport in primr.ai.deep_research.

These cover the public format_report orchestrator plus each internal
helper: prohibited-pattern removal, header normalization, chapter
extraction, TOC generation, citation rendering, KEY METRICS relocation,
and the failure/memo/debug content guard checks.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.ai.deep_research import FormattedReport, ReportFormatter

# ---------------------------------------------------------------------------
# FormattedReport
# ---------------------------------------------------------------------------


class TestFormattedReport:
    def test_estimated_pages_floor_at_one(self):
        fr = FormattedReport(
            markdown="x",
            table_of_contents="",
            chapters=[],
            citations=[],
            company_name="Acme",
            word_count=0,
        )
        assert fr.estimated_pages == 1

    def test_estimated_pages_500_words_per_page(self):
        fr = FormattedReport(
            markdown="",
            table_of_contents="",
            chapters=[],
            citations=[],
            company_name="Acme",
            word_count=2500,
        )
        assert fr.estimated_pages == 5


# ---------------------------------------------------------------------------
# ReportFormatter — guard predicates
# ---------------------------------------------------------------------------


class TestGuardPredicates:
    def setup_method(self):
        self.f = ReportFormatter()

    def test_has_failure_markers_detects_check(self):
        assert self.f.has_failure_markers("good ✓ result") is True

    def test_has_failure_markers_detects_x(self):
        assert self.f.has_failure_markers("bad ✗ result") is True

    def test_has_failure_markers_clean_text(self):
        assert self.f.has_failure_markers("just text") is False

    def test_has_memo_headers_detects_research_request(self):
        assert self.f.has_memo_headers("RESEARCH REQUEST: foo") is True

    def test_has_memo_headers_detects_to_field(self):
        assert self.f.has_memo_headers("TO: someone") is True

    def test_has_memo_headers_clean_text(self):
        assert self.f.has_memo_headers("Plain prose with no memo.") is False

    def test_has_debug_artifacts_detects_debug_tag(self):
        assert self.f.has_debug_artifacts("[DEBUG] info") is True

    def test_has_debug_artifacts_detects_traceback(self):
        assert self.f.has_debug_artifacts("Traceback (most recent call last):\n  ...") is True

    def test_has_debug_artifacts_clean_text(self):
        assert self.f.has_debug_artifacts("clean prose") is False


# ---------------------------------------------------------------------------
# ReportFormatter — internal helpers
# ---------------------------------------------------------------------------


class TestRemoveProhibitedPatterns:
    def test_strips_research_request(self):
        f = ReportFormatter()
        result = f._remove_prohibited_patterns("RESEARCH REQUEST: top secret")
        assert "RESEARCH REQUEST" not in result

    def test_strips_status_markers(self):
        f = ReportFormatter()
        result = f._remove_prohibited_patterns("✓ done ✗ failed")
        assert "✓" not in result
        assert "✗" not in result

    def test_strips_debug_tags(self):
        f = ReportFormatter()
        assert "[DEBUG]" not in f._remove_prohibited_patterns("[DEBUG] noisy")
        assert "[ERROR]" not in f._remove_prohibited_patterns("[ERROR] noisy")


class TestEnsureCleanHeader:
    def test_preserves_existing_strategic_overview_header(self):
        f = ReportFormatter()
        content = "# Strategic Company Overview: Acme\n\nbody"
        assert f._ensure_clean_header(content, "Acme") == content

    def test_preserves_generic_strategic_overview_header(self):
        f = ReportFormatter()
        content = "# Strategic Company Overview\n\nbody"
        assert f._ensure_clean_header(content, "Acme") == content

    def test_preserves_ai_strategy_header(self):
        f = ReportFormatter()
        content = "# AI Strategy: Acme\n\nbody"
        assert f._ensure_clean_header(content, "Acme") == content

    def test_strips_memo_lines_when_no_clean_header(self):
        f = ReportFormatter()
        content = (
            "RESEARCH REQUEST: Acme\n"
            "TO: someone\n"
            "FROM: research\n"
            "SUBJECT: deep dive\n"
            "DATE: January 2025\n"
            "\n"
            "real body content"
        )
        result = f._ensure_clean_header(content, "Acme")
        for marker in ("RESEARCH REQUEST:", "TO:", "FROM:", "SUBJECT:"):
            assert marker not in result


class TestExtractChapters:
    def test_returns_h2_titles(self):
        f = ReportFormatter()
        content = "## Executive Summary\n\nbody\n\n## SWOT Analysis\n\nbody"
        assert f._extract_chapters(content) == ["Executive Summary", "SWOT Analysis"]

    def test_strips_numeric_prefixes(self):
        f = ReportFormatter()
        content = "## 1. Overview\n\nbody\n\n## 2) Strategy\n\nbody"
        chapters = f._extract_chapters(content)
        assert chapters == ["Overview", "Strategy"]

    def test_ignores_h1_and_h3(self):
        f = ReportFormatter()
        content = "# Title\n\n## Chapter A\n\n### Subsection\n\nbody"
        assert f._extract_chapters(content) == ["Chapter A"]

    def test_dedupes(self):
        f = ReportFormatter()
        content = "## Same\n\nx\n\n## Same\n\ny"
        assert f._extract_chapters(content) == ["Same"]


class TestGenerateCleanToc:
    def test_emits_numbered_anchor_links(self):
        f = ReportFormatter()
        toc = f._generate_clean_toc(["Executive Summary", "SWOT Analysis"])
        assert "## Table of Contents" in toc
        assert "1. [Executive Summary](#executive-summary)" in toc
        assert "2. [SWOT Analysis](#swot-analysis)" in toc

    def test_removes_status_markers(self):
        f = ReportFormatter()
        toc = f._generate_clean_toc(["Done", "Pending"])
        assert "✓" not in toc
        assert "✗" not in toc

    def test_replaces_and_in_anchor(self):
        f = ReportFormatter()
        toc = f._generate_clean_toc(["Sales & Marketing"])
        assert "(#sales-and-marketing)" in toc

    def test_strips_non_alphanumeric_in_anchor(self):
        f = ReportFormatter()
        toc = f._generate_clean_toc(["Q1: Strategy!"])
        # `:`, `!` should be stripped from anchor
        assert "(#q1-strategy)" in toc


class TestFormatNumberedCitations:
    def test_converts_inline_cite_refs(self):
        f = ReportFormatter()
        content = "Stat [cite: 1, 2] supports growth."
        citations = [{"number": "1", "url": "https://a.example", "title": "A"}]
        result = f._format_numbered_citations(content, citations)
        assert "[1] [2]" in result
        assert "[cite:" not in result

    def test_returns_content_when_no_citations(self):
        f = ReportFormatter()
        content = "Plain body."
        assert f._format_numbered_citations(content, []) == "Plain body."

    def test_appends_references_section(self):
        f = ReportFormatter()
        content = "Body [cite: 1]"
        citations = [{"number": "1", "url": "https://example.com/a", "title": "Example"}]
        result = f._format_numbered_citations(content, citations)
        assert "## References" in result
        assert "[Example](https://example.com/a)" in result

    def test_dedupes_repeated_urls(self):
        f = ReportFormatter()
        content = "Body [cite: 1]"
        citations = [
            {"number": "1", "url": "https://example.com/a", "title": "A"},
            {"number": "2", "url": "https://example.com/a", "title": "A again"},
            {"number": "3", "url": "https://example.com/b", "title": "B"},
        ]
        result = f._format_numbered_citations(content, citations)
        # Only two unique URLs in the references section
        assert result.count("](https://example.com/a)") == 1
        assert result.count("](https://example.com/b)") == 1

    def test_uses_domain_when_title_looks_like_redirect(self):
        f = ReportFormatter()
        content = "Body"
        citations = [
            {
                "number": "1",
                "url": "https://www.partstown.com/about",
                "title": "vertexaisearch.cloud.google.com",
            }
        ]
        result = f._format_numbered_citations(content, citations)
        # Domain shown instead of the redirect title
        assert "partstown.com" in result

    def test_unresolved_redirect_marks_link_unavailable(self):
        f = ReportFormatter()
        content = "Body"
        citations = [
            {
                "number": "1",
                "url": ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/x"),
                "title": "partstown.com",
            }
        ]
        result = f._format_numbered_citations(content, citations)
        assert "link unavailable" in result
        # The display text should be the original title (when it's not the redirect domain)
        assert "partstown.com" in result

    def test_inline_sources_block_removed(self):
        f = ReportFormatter()
        content = "Body claim.\n\n**Sources:**\n1. [a](https://a.example)\n2. [b](https://b.example)\n\nMore text."
        citations = [{"number": "1", "url": "https://a.example", "title": "a"}]
        result = f._format_numbered_citations(content, citations)
        # The inline **Sources:** block should be stripped, leaving final References at end only.
        assert "**Sources:**" not in result


class TestRelocateKeyMetrics:
    def test_moves_metrics_after_executive_summary(self):
        f = ReportFormatter()
        content = (
            "## Executive Summary\n\nbody intro\n\n"
            "## Other Section\n\nmore\n\n"
            "**KEY METRICS:**\n- Revenue: $1B\n- Headcount: 500\n"
        )
        result = f._relocate_key_metrics(content)
        # KEY METRICS block should now appear before "## Other Section"
        metrics_pos = result.index("**KEY METRICS:**")
        other_pos = result.index("## Other Section")
        assert metrics_pos < other_pos

    def test_no_change_when_no_metrics_block(self):
        f = ReportFormatter()
        content = "## Executive Summary\n\nbody\n\n## Other\n\nmore"
        assert f._relocate_key_metrics(content) == content

    def test_metrics_stripped_when_no_executive_summary(self):
        f = ReportFormatter()
        content = "**KEY METRICS:**\n- Revenue: $1B\n\n## Body Only\n\nmore"
        # With no Executive Summary to insert into, the relocator strips the metrics
        # from their original position and drops them (no reinsertion).
        result = f._relocate_key_metrics(content)
        assert "KEY METRICS" not in result
        assert "## Body Only" in result


class TestCountChapters:
    def test_counts_h2_headings(self):
        f = ReportFormatter()
        content = "## A\n\nx\n\n## B\n\ny\n\n## C\n\nz"
        assert f.count_chapters(content) == 3

    def test_zero_for_no_chapters(self):
        f = ReportFormatter()
        assert f.count_chapters("plain text") == 0


# ---------------------------------------------------------------------------
# ReportFormatter.format_report (end-to-end)
# ---------------------------------------------------------------------------


class TestFormatReportEndToEnd:
    def test_returns_formatted_report_dataclass(self):
        f = ReportFormatter()
        raw = (
            "# Strategic Company Overview: Acme\n\n"
            "## Executive Summary\n\nbody intro\n\n"
            "## SWOT Analysis\n\nbody body body\n"
        )
        with patch(
            "primr.ai.deep_research.resolve_citation_urls_sync",
            side_effect=lambda x: x,
        ):
            result = f.format_report(raw, "Acme")
        assert isinstance(result, FormattedReport)
        assert result.company_name == "Acme"
        assert "Executive Summary" in result.chapters
        assert result.word_count > 0

    def test_strips_prohibited_patterns_from_raw(self):
        f = ReportFormatter()
        raw = (
            "✓ Status\n# Strategic Company Overview: Acme\n\n"
            "## Executive Summary\n\nbody [DEBUG] inside"
        )
        with patch(
            "primr.ai.deep_research.resolve_citation_urls_sync",
            side_effect=lambda x: x,
        ):
            result = f.format_report(raw, "Acme")
        assert "✓" not in result.markdown
        assert "[DEBUG]" not in result.markdown

    @pytest.mark.parametrize("style", ["numbered", "footnote"])
    def test_citation_style_param_accepted(self, style):
        f = ReportFormatter()
        raw = "# Strategic Company Overview: Acme\n\n## Chap\n\nbody"
        with patch(
            "primr.ai.deep_research.resolve_citation_urls_sync",
            side_effect=lambda x: x,
        ):
            # Should not raise regardless of style param
            assert f.format_report(raw, "Acme", citation_style=style)
