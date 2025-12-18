"""
Property tests for content equivalence across formats.

Property 9: Content equivalence across formats
Validates: Requirements 6.4
"""

import pytest
from hypothesis import given, strategies as st, settings

from primr.output.output_utils import strip_markdown_artifacts
from primr.output.markdown_parser import MarkdownParser


class TestProperty9ContentEquivalence:
    """
    Property 9: Content equivalence across formats.
    
    The same source content should produce equivalent information
    in TXT and DOCX formats - no content should be lost or corrupted.
    """

    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ', min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_strip_markdown_preserves_content(self, text):
        """Stripping markdown should preserve the actual content."""
        # Skip text that contains markdown-like patterns
        from hypothesis import assume
        assume('**' not in text)
        assume('__' not in text)
        assume(not text.startswith('#'))
        
        # Add some markdown formatting
        formatted = f"**{text}**"
        stripped = strip_markdown_artifacts(formatted)
        
        # The core content should be preserved
        assert text in stripped or stripped == text

    def test_bold_text_preserved_after_strip(self):
        """Bold text content is preserved when markers are removed."""
        test_cases = [
            ("**Revenue** grew by 15%", "Revenue grew by 15%"),
            ("The __company__ is strong", "The company is strong"),
            ("**Multiple** **bold** items", "Multiple bold items"),
        ]
        
        for markdown, expected in test_cases:
            result = strip_markdown_artifacts(markdown)
            assert result == expected, f"Failed for: {markdown}"

    def test_heading_text_preserved_after_strip(self):
        """Heading text is preserved when markers are removed."""
        test_cases = [
            ("## Company Overview", "Company Overview"),
            ("### Financial Highlights", "Financial Highlights"),
            ("# Main Title", "Main Title"),
        ]
        
        for markdown, expected in test_cases:
            result = strip_markdown_artifacts(markdown)
            assert result == expected, f"Failed for: {markdown}"

    def test_mixed_formatting_preserved(self):
        """Mixed formatting preserves all content."""
        markdown = """## Overview

**Revenue**: $5.2 billion
**Employees**: 10,000

Key points:
* First point
* Second point"""
        
        result = strip_markdown_artifacts(markdown)
        
        # All key content should be present
        assert "Overview" in result
        assert "Revenue" in result
        assert "$5.2 billion" in result
        assert "Employees" in result
        assert "10,000" in result
        assert "First point" in result
        assert "Second point" in result

    def test_parser_and_strip_produce_same_content(self):
        """Parser extraction and strip function produce equivalent content."""
        parser = MarkdownParser()
        
        markdown = """## Section Title

This is **bold text** and normal text.

* Bullet one
* Bullet two"""
        
        # Parse with MarkdownParser
        blocks = parser.parse_content(markdown)
        parsed_content = []
        for block in blocks:
            for line in block.lines:
                # Strip any remaining bold markers from content
                clean = strip_markdown_artifacts(line.content)
                parsed_content.append(clean)
        
        # Strip directly
        stripped = strip_markdown_artifacts(markdown)
        
        # Both should contain the same key content
        for content in parsed_content:
            if content.strip():
                assert content in stripped or any(
                    content in line for line in stripped.split('\n')
                ), f"Content '{content}' not found in stripped output"

    @given(st.lists(st.text(alphabet='abcdefghijklmnopqrstuvwxyz ', min_size=1, max_size=50), min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_bullet_content_preserved(self, items):
        """Bullet list content is fully preserved."""
        # Create markdown bullet list
        markdown = '\n'.join(f"* {item}" for item in items)
        
        # Strip markdown
        stripped = strip_markdown_artifacts(markdown)
        
        # All items should be present
        for item in items:
            assert item.strip() in stripped, f"Item '{item}' not found in stripped output"

    def test_no_content_loss_in_complex_document(self):
        """Complex document structure preserves all content."""
        markdown = """## Executive Summary

**The Bottom Line**: Company X is a leader in technology.

### Key Metrics

* Revenue: $10B
* Growth: 15%
* Employees: 50,000

### Risk Factors

1. Market competition
2. Regulatory changes

## Strategic Assessment

The company has **strong** fundamentals with __solid__ growth prospects."""
        
        stripped = strip_markdown_artifacts(markdown)
        
        # All key content must be present
        required_content = [
            "Executive Summary",
            "The Bottom Line",
            "Company X is a leader",
            "Key Metrics",
            "Revenue",
            "$10B",
            "Growth",
            "15%",
            "Employees",
            "50,000",
            "Risk Factors",
            "Market competition",
            "Regulatory changes",
            "Strategic Assessment",
            "strong",
            "fundamentals",
            "solid",
            "growth prospects",
        ]
        
        for content in required_content:
            assert content in stripped, f"Missing content: {content}"

    def test_special_characters_preserved(self):
        """Special characters in content are preserved."""
        test_cases = [
            "Revenue: $5.2B (up 15%)",
            "Growth rate: 10-15%",
            "Company & Partners",
            "Q1/Q2 results",
            "Email: info@company.com",
        ]
        
        for text in test_cases:
            result = strip_markdown_artifacts(text)
            assert result == text, f"Special chars lost in: {text}"

    def test_whitespace_handling(self):
        """Whitespace is handled appropriately."""
        markdown = """## Title

First paragraph.

Second paragraph."""
        
        stripped = strip_markdown_artifacts(markdown)
        
        # Content should be present
        assert "Title" in stripped
        assert "First paragraph" in stripped
        assert "Second paragraph" in stripped
