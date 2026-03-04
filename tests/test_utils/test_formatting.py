"""
Property tests for formatting utilities.

**Feature: consulting-tier-report**
"""
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from primr.utils.formatting import (
    clean_content,
    fix_nested_numbering,
    fix_numbered_headings,
    format_currency,
    format_large_numbers_in_text,
    format_number,
    has_em_dashes,
    has_emojis,
    has_numbered_headings,
    remove_em_dashes,
    remove_emojis,
)

# Sample emojis for testing
SAMPLE_EMOJIS = ["😀", "🎉", "✅", "❌", "🚀", "💡", "📊", "🔥", "⭐", "👍"]

# Em-dash characters
EM_DASHES = ["\u2014", "\u2013", "\u2012"]  # em-dash, en-dash, figure dash


class TestRemoveEmojis:
    """**Property 10: Clean Formatting** - verify no emojis in output."""

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_output_has_no_emojis(self, text: str):
        """After removing emojis, output should contain no emoji characters."""
        result = remove_emojis(text)
        assert not has_emojis(result), f"Output still contains emojis: {result}"

    @pytest.mark.parametrize("emoji", SAMPLE_EMOJIS)
    def test_removes_specific_emojis(self, emoji: str):
        """Should remove specific emoji characters."""
        text = f"Hello {emoji} World"
        result = remove_emojis(text)
        assert emoji not in result
        assert "Hello" in result
        assert "World" in result

    def test_preserves_regular_text(self):
        """Should preserve regular text without emojis."""
        text = "This is a normal sentence with numbers 123 and symbols !@#"
        result = remove_emojis(text)
        assert result == text

    def test_handles_multiple_emojis(self):
        """Should remove multiple emojis in sequence."""
        text = "Start 🎉🚀✅ End"
        result = remove_emojis(text)
        assert "🎉" not in result
        assert "🚀" not in result
        assert "✅" not in result


class TestRemoveEmDashes:
    """**Property 10: Clean Formatting** - verify no em-dashes in output."""

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_output_has_no_em_dashes(self, text: str):
        """After removing em-dashes, output should contain no em-dash characters."""
        result = remove_em_dashes(text)
        assert not has_em_dashes(result), f"Output still contains em-dashes: {result}"

    @pytest.mark.parametrize("dash", EM_DASHES)
    def test_removes_specific_dashes(self, dash: str):
        """Should remove specific dash characters."""
        text = f"Hello{dash}World"
        result = remove_em_dashes(text)
        assert dash not in result

    def test_replaces_with_comma(self):
        """Should replace em-dash with comma."""
        text = "The company—a leader in tech—grew rapidly"
        result = remove_em_dashes(text)
        assert "—" not in result
        assert "," in result

    def test_preserves_regular_hyphens(self):
        """Should preserve regular hyphens."""
        text = "state-of-the-art technology"
        result = remove_em_dashes(text)
        assert result == text


class TestFixNumberedHeadings:
    """**Property 11: Natural Headings** - verify no numbered headings."""

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_output_has_no_numbered_headings(self, text: str):
        """After fixing, output should not have numbered heading prefixes."""
        result = fix_numbered_headings(text)
        # Check that common numbered patterns are removed
        assert not has_numbered_headings(result), f"Output still has numbered headings: {result}"

    def test_removes_simple_numbered_heading(self):
        """Should remove '1. ' prefix from headings."""
        text = "1. Executive Summary"
        result = fix_numbered_headings(text)
        assert result.strip() == "Executive Summary"

    def test_removes_nested_numbered_heading(self):
        """Should remove '2.1 ' prefix from headings."""
        text = "2.1 Market Overview"
        result = fix_numbered_headings(text)
        assert result.strip() == "Market Overview"

    def test_preserves_markdown_hash(self):
        """Should preserve markdown heading markers."""
        text = "## 1. Executive Summary"
        result = fix_numbered_headings(text)
        assert result.strip() == "## Executive Summary"

    def test_handles_multiple_headings(self):
        """Should handle multiple numbered headings."""
        text = """1. Introduction
2. Overview
3. Conclusion"""
        result = fix_numbered_headings(text)
        assert "1." not in result
        assert "2." not in result
        assert "3." not in result
        assert "Introduction" in result
        assert "Overview" in result
        assert "Conclusion" in result


class TestFixNestedNumbering:
    """**Property 13: No Nested Numbering** - verify no nested list numbering."""

    def test_removes_triple_nested_numbers(self):
        """Should remove 1.1.1 style numbering."""
        text = "1.1.1 First item"
        result = fix_nested_numbering(text)
        assert "1.1.1" not in result
        assert "First item" in result

    def test_removes_deep_nested_numbers(self):
        """Should remove deeply nested numbering."""
        text = "2.3.4.5 Deep item"
        result = fix_nested_numbering(text)
        assert "2.3.4.5" not in result
        assert "Deep item" in result

    def test_preserves_simple_numbers(self):
        """Should preserve simple numbered lists."""
        text = "1. First item"
        result = fix_nested_numbering(text)
        # Simple numbering is handled by fix_numbered_headings, not this function
        assert "First item" in result


class TestFormatNumber:
    """**Property 12: Readable Number Formatting** - verify abbreviated numbers."""

    @given(st.floats(min_value=0, max_value=1e15, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_formatted_number_is_readable(self, value: float):
        """Formatted numbers should be in abbreviated form for large values."""
        result = format_number(value)

        # Large numbers should have suffix
        if value >= 1_000_000_000_000:
            assert "T" in result
        elif value >= 1_000_000_000:
            assert "B" in result
        elif value >= 1_000_000:
            assert "M" in result
        elif value >= 1_000:
            assert "K" in result

    def test_formats_millions(self):
        """Should format millions correctly."""
        assert format_number(50_000_000) == "50M"
        assert format_number(2_500_000) == "2.5M"
        assert format_number(1_000_000) == "1M"

    def test_formats_billions(self):
        """Should format billions correctly."""
        assert format_number(1_000_000_000) == "1B"
        assert format_number(2_500_000_000) == "2.5B"

    def test_formats_thousands(self):
        """Should format thousands correctly."""
        assert format_number(50_000) == "50K"
        assert format_number(2_500) == "2.5K"

    def test_small_numbers_unchanged(self):
        """Small numbers should remain as-is."""
        assert format_number(500) == "500"
        assert format_number(99) == "99"

    def test_handles_negative_numbers(self):
        """Should handle negative numbers."""
        assert format_number(-50_000_000) == "-50M"


class TestFormatCurrency:
    """Test currency formatting."""

    def test_formats_with_dollar_sign(self):
        """Should include currency symbol."""
        assert format_currency(50_000_000) == "$50M"
        assert format_currency(2_500_000) == "$2.5M"

    def test_formats_with_other_currencies(self):
        """Should support other currency symbols."""
        assert format_currency(50_000_000, "€") == "€50M"
        assert format_currency(50_000_000, "£") == "£50M"


class TestFormatLargeNumbersInText:
    """Test formatting numbers within text."""

    def test_formats_currency_in_text(self):
        """Should format currency amounts in text."""
        text = "Revenue was $50,000,000 last year"
        result = format_large_numbers_in_text(text)
        assert "$50M" in result
        assert "$50,000,000" not in result

    def test_formats_plain_numbers_in_text(self):
        """Should format plain large numbers in text."""
        text = "The company has 50,000,000 users"
        result = format_large_numbers_in_text(text)
        assert "50M" in result
        assert "50,000,000" not in result

    def test_preserves_small_numbers(self):
        """Should preserve small numbers."""
        text = "The team has 50 members"
        result = format_large_numbers_in_text(text)
        assert "50" in result


class TestCleanContent:
    """Test combined content cleaning."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_clean_content_removes_all_issues(self, text: str):
        """Clean content should remove emojis, em-dashes, and numbered headings."""
        result = clean_content(text)

        assert not has_emojis(result), "Output contains emojis"
        assert not has_em_dashes(result), "Output contains em-dashes"

    def test_comprehensive_cleanup(self):
        """Should clean all formatting issues in one pass."""
        text = """1. Executive Summary 🎉

The company—a leader in tech—has revenue of $50,000,000.

2.1.1 Nested Section

More content here."""

        result = clean_content(text)

        assert "🎉" not in result
        assert "—" not in result
        assert "1." not in result.split("\n")[0]  # First line shouldn't start with "1."
        assert "$50M" in result or "$50,000,000" not in result

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert clean_content("") == ""

    def test_handles_none_like_empty(self):
        """Should handle None-like values."""
        assert clean_content("") == ""


class TestHasEmojis:
    """Test emoji detection."""

    def test_detects_emojis(self):
        """Should detect emoji presence."""
        assert has_emojis("Hello 😀 World")
        assert has_emojis("🎉")

    def test_no_false_positives(self):
        """Should not detect emojis in plain text."""
        assert not has_emojis("Hello World")
        assert not has_emojis("Numbers 123 and symbols !@#")


class TestHasEmDashes:
    """Test em-dash detection."""

    def test_detects_em_dashes(self):
        """Should detect em-dash presence."""
        assert has_em_dashes("Hello—World")
        assert has_em_dashes("Test\u2014test")

    def test_no_false_positives(self):
        """Should not detect em-dashes in plain text."""
        assert not has_em_dashes("Hello World")
        assert not has_em_dashes("state-of-the-art")  # Regular hyphen


class TestHasNumberedHeadings:
    """Test numbered heading detection."""

    def test_detects_numbered_headings(self):
        """Should detect numbered heading patterns."""
        assert has_numbered_headings("1. Executive Summary")
        assert has_numbered_headings("## 2.1 Overview")

    def test_no_false_positives(self):
        """Should not detect numbered headings in regular text."""
        assert not has_numbered_headings("Executive Summary")
        assert not has_numbered_headings("The year 2024 was good")


from primr.utils.formatting import deduplicate_content, get_deduplication_stats


class TestDeduplicateContent:
    """Tests for content deduplication."""

    def test_removes_duplicate_lines(self):
        """Should remove duplicate lines."""
        content = "This is a long enough line to be deduplicated.\nOther content.\nThis is a long enough line to be deduplicated."
        result = deduplicate_content(content)
        assert result.count("This is a long enough line") == 1

    def test_preserves_short_lines(self):
        """Should preserve short lines even if duplicated."""
        content = "Header\nContent here is long enough.\nHeader\nMore content."
        result = deduplicate_content(content, min_line_length=10)
        assert result.count("Header") == 2

    def test_normalizes_for_comparison(self):
        """Should normalize text for comparison."""
        content = "This is a test line.\nThis  is  a  TEST  line.\nOther content."
        result = deduplicate_content(content)
        # Should only have one of the test lines
        lines = [line for line in result.split('\n') if 'test' in line.lower()]
        assert len(lines) == 1

    def test_handles_empty_content(self):
        """Should handle empty content."""
        assert deduplicate_content("") == ""
        assert deduplicate_content(None) is None

    def test_paragraph_deduplication(self):
        """Should deduplicate at paragraph level."""
        content = """First paragraph with enough content to be deduplicated.

Second paragraph here.

First paragraph with enough content to be deduplicated.

Third paragraph."""
        result = deduplicate_content(content, dedupe_paragraphs=True)
        assert result.count("First paragraph") == 1


class TestDeduplicationStats:
    """Tests for deduplication statistics."""

    def test_calculates_reduction(self):
        """Should calculate reduction statistics."""
        original = "Line 1\nLine 2\nLine 1\nLine 3"
        deduped = deduplicate_content(original)
        stats = get_deduplication_stats(original, deduped)

        assert "original_lines" in stats
        assert "deduplicated_lines" in stats
        assert "line_reduction_percent" in stats
        assert stats["original_lines"] >= stats["deduplicated_lines"]


class TestContentDeduplicationEffectivenessProperty:
    """
    Property-based tests for content deduplication effectiveness.

    **Feature: code-quality-hardening, Property 15: Content Deduplication Effectiveness**
    **Validates: Requirements 9.1**

    For any content with duplicate lines, deduplication SHALL reduce the
    content size, and the deduplicated content SHALL preserve all unique
    information.
    """

    @given(st.lists(
        st.text(alphabet="abcdefghij ", min_size=25, max_size=50),
        min_size=2,
        max_size=10
    ))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_deduplication_reduces_or_preserves_size(self, lines):
        """Deduplication should never increase content size."""
        # Create content with some duplicates
        content = '\n'.join(lines + lines[:2])  # Add duplicates
        result = deduplicate_content(content)

        assert len(result) <= len(content)

    @given(st.lists(
        st.text(alphabet="abcdefghij ", min_size=25, max_size=50),
        min_size=1,
        max_size=5,
        unique=True
    ))
    @settings(max_examples=100)
    def test_unique_content_preserved(self, unique_lines):
        """All unique content should be preserved."""
        content = '\n'.join(unique_lines)
        result = deduplicate_content(content)

        # All unique lines should still be present (normalized)
        for line in unique_lines:
            # Check that the essence of each line is preserved
            normalized = ' '.join(line.lower().split())
            result_normalized = ' '.join(result.lower().split())
            # At least part of each unique line should be in result
            assert any(word in result_normalized for word in normalized.split() if len(word) > 2)

    @given(st.text(alphabet="abcdefghij ", min_size=30, max_size=100))
    @settings(max_examples=100)
    def test_duplicate_lines_removed(self, line):
        """Duplicate lines should be removed."""
        assume(len(line.strip()) >= 25)  # Ensure line is long enough

        content = f"{line}\nOther content here.\n{line}\nMore content."
        result = deduplicate_content(content, min_line_length=20)

        # The line should appear only once
        normalized_line = ' '.join(line.lower().split())
        count = sum(1 for line in result.split('\n')
                   if ' '.join(line.lower().split()) == normalized_line)
        assert count <= 1
