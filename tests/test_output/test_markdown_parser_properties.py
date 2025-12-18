"""
Property-based tests for the MarkdownParser.

Uses Hypothesis to verify correctness properties across many random inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from primr.output.markdown_parser import MarkdownParser


# =============================================================================
# Generators for property-based testing
# =============================================================================

@st.composite
def markdown_bullet_line(draw):
    """Generate bullet lines with varying formats."""
    bullet_char = draw(st.sampled_from(['*', '-', '•']))
    spaces = draw(st.integers(min_value=1, max_value=4))
    indent_levels = draw(st.integers(min_value=0, max_value=3))
    indent = ' ' * (indent_levels * 4)
    # Content must not be empty and not start with bullet chars
    content = draw(st.text(
        min_size=1, 
        max_size=100,
        alphabet=st.characters(whitelist_categories=['L', 'N', 'P', 'S'])
    ))
    # Ensure content doesn't start with whitespace
    content = content.lstrip()
    assume(len(content) > 0)
    return indent + bullet_char + ' ' * spaces + content, content, indent_levels, bullet_char


@st.composite
def markdown_heading_line(draw):
    """Generate heading lines with 1-4 # characters."""
    level = draw(st.integers(min_value=1, max_value=4))
    content = draw(st.text(
        min_size=1, 
        max_size=50,
        alphabet=st.characters(whitelist_categories=['L', 'N', 'S'])
    ))
    content = content.strip()
    assume(len(content) > 0)
    return '#' * level + ' ' + content, content, level


@st.composite
def markdown_numbered_line(draw):
    """Generate numbered list lines."""
    number = draw(st.integers(min_value=1, max_value=99))
    separator = draw(st.sampled_from(['.', ')']))
    indent_levels = draw(st.integers(min_value=0, max_value=3))
    indent = ' ' * (indent_levels * 4)
    content = draw(st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=['L', 'N', 'P', 'S'])
    ))
    content = content.strip()
    assume(len(content) > 0)
    return indent + str(number) + separator + ' ' + content, content, indent_levels, str(number)


@st.composite
def inline_header_line(draw):
    """Generate 'Header: content' patterns."""
    # Header must start with capital, be 3-40 chars, only letters and spaces
    header_chars = draw(st.text(
        min_size=2, 
        max_size=39,
        alphabet=st.characters(whitelist_categories=['L'])
    ))
    # Ensure first char is uppercase
    header = header_chars[0].upper() + header_chars[1:]
    content = draw(st.text(
        min_size=1, 
        max_size=100,
        alphabet=st.characters(whitelist_categories=['L', 'N', 'P', 'S'])
    ))
    content = content.strip()
    assume(len(content) > 0)
    assume(header.lower() not in {'http', 'https', 'ftp', 'mailto', 'tel'})
    return f"{header}: {content}", header, content


@st.composite
def plain_text_line(draw):
    """Generate plain text that doesn't match any markdown pattern."""
    # Start with lowercase to avoid inline header detection
    first_char = draw(st.sampled_from('abcdefghijklmnopqrstuvwxyz'))
    rest = draw(st.text(
        min_size=5,
        max_size=100,
        alphabet=st.characters(whitelist_categories=['L', 'N', 'P', 'S'])
    ))
    # Ensure it doesn't start with markdown syntax
    text = first_char + rest
    assume(not text.startswith('#'))
    assume(not text.startswith('*'))
    assume(not text.startswith('-'))
    assume(not text.startswith('•'))
    assume(':' not in text[:30] or text[0].islower())  # Avoid inline header
    return text


# =============================================================================
# Property Tests
# =============================================================================

class TestBulletParsing:
    """
    **Feature: report-excellence, Property 1: Bullet parsing handles all format variations**
    **Validates: Requirements 3.2, 7.1**
    
    For any input line starting with a bullet character (*, -, •) followed by 1-4 spaces,
    the parser SHALL return a bullet type with the content correctly extracted.
    """
    
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=markdown_bullet_line())
    def test_bullet_parsing_extracts_content(self, data):
        """Parser correctly extracts bullet content regardless of format."""
        line, expected_content, expected_indent, bullet_char = data
        parser = MarkdownParser()
        
        result = parser.parse_line(line)
        
        assert result.type == 'bullet', f"Expected 'bullet', got '{result.type}' for line: {line!r}"
        assert result.content == expected_content, f"Content mismatch: {result.content!r} != {expected_content!r}"
        assert result.level == expected_indent, f"Indent mismatch: {result.level} != {expected_indent}"
        assert result.metadata.get('bullet_char') == bullet_char

    @settings(max_examples=100)
    @given(
        bullet_char=st.sampled_from(['*', '-', '•']),
        spaces=st.integers(min_value=1, max_value=4),
        content=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=['L', 'N']))
    )
    def test_bullet_all_formats_recognized(self, bullet_char, spaces, content):
        """All bullet formats (*, -, •) with 1-4 spaces are recognized."""
        assume(content.strip())
        content = content.strip()
        line = bullet_char + ' ' * spaces + content
        parser = MarkdownParser()
        
        result = parser.parse_line(line)
        
        assert result.type == 'bullet', f"Failed for: {line!r}"


class TestHeadingParsing:
    """
    **Feature: report-excellence, Property 2: Heading parsing preserves hierarchy**
    **Validates: Requirements 7.2**
    
    For any input line starting with 1-4 # characters followed by a space,
    the parser SHALL return a heading type with the correct level.
    """
    
    @settings(max_examples=100)
    @given(data=markdown_heading_line())
    def test_heading_parsing_preserves_level(self, data):
        """Parser correctly identifies heading level."""
        line, expected_content, expected_level = data
        parser = MarkdownParser()
        
        result = parser.parse_line(line)
        
        assert result.type == 'heading', f"Expected 'heading', got '{result.type}'"
        assert result.level == expected_level, f"Level mismatch: {result.level} != {expected_level}"
        assert result.content == expected_content

    @settings(max_examples=100)
    @given(level=st.integers(min_value=1, max_value=4))
    def test_all_heading_levels_recognized(self, level):
        """All heading levels 1-4 are correctly recognized."""
        line = '#' * level + ' Test Heading'
        parser = MarkdownParser()
        
        result = parser.parse_line(line)
        
        assert result.type == 'heading'
        assert result.level == level



class TestSubHeadingDetection:
    """
    **Feature: report-excellence, Property 11: Sub-heading detection from content patterns**
    **Validates: Requirements 3.1**
    
    For any content block containing a line that is plain text (no bullet) followed
    immediately by bullet items, the plain text line SHALL be formatted as a sub-heading.
    """
    
    @settings(max_examples=100)
    @given(
        subheading_text=st.text(min_size=3, max_size=50, alphabet=st.characters(whitelist_categories=['L', 'N', 'S'])),
        bullet_content=st.text(min_size=3, max_size=50, alphabet=st.characters(whitelist_categories=['L', 'N']))
    )
    def test_text_before_bullets_becomes_subheading(self, subheading_text, bullet_content):
        """Plain text followed by bullets is detected as sub-heading."""
        subheading_text = subheading_text.strip()
        bullet_content = bullet_content.strip()
        assume(len(subheading_text) > 0)
        assume(len(bullet_content) > 0)
        assume(not subheading_text.startswith('#'))
        assume(not subheading_text.startswith('*'))
        assume(not subheading_text.startswith('-'))
        
        content = f"{subheading_text}\n* {bullet_content}"
        parser = MarkdownParser()
        
        blocks = parser.parse_content(content)
        
        # Should have 2 blocks: subheading and bullet_list
        assert len(blocks) >= 2, f"Expected at least 2 blocks, got {len(blocks)}"
        
        # First block should be the detected subheading
        assert blocks[0].type == 'heading', f"Expected 'heading' block, got '{blocks[0].type}'"
        assert blocks[0].lines[0].type == 'subheading', f"Expected 'subheading' line type"
        assert blocks[0].lines[0].metadata.get('detected') == True

    @settings(max_examples=100)
    @given(
        text1=st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=['L'])),
        text2=st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=['L']))
    )
    def test_consecutive_text_not_subheading(self, text1, text2):
        """Plain text followed by more plain text is NOT a sub-heading."""
        text1 = text1.strip()
        text2 = text2.strip()
        assume(len(text1) > 0)
        assume(len(text2) > 0)
        assume(not text1.startswith('#'))
        assume(not text2.startswith('#'))
        # Ensure they don't look like inline headers
        assume(':' not in text1[:20])
        assume(':' not in text2[:20])
        
        content = f"{text1}\n{text2}"
        parser = MarkdownParser()
        
        blocks = parser.parse_content(content)
        
        # Should be a single paragraph block
        assert len(blocks) == 1, f"Expected 1 block, got {len(blocks)}"
        assert blocks[0].type == 'paragraph'
        # Neither line should be a subheading
        for line in blocks[0].lines:
            assert line.type != 'subheading', "Text followed by text should not be subheading"


class TestGracefulFallback:
    """
    **Feature: report-excellence, Property 12: Graceful fallback for unrecognized formats**
    **Validates: Requirements 7.5**
    
    For any input line that doesn't match any known markdown pattern,
    the parser SHALL return a text type without raising an error.
    """
    
    @settings(max_examples=100)
    @given(text=st.text(min_size=1, max_size=200))
    def test_any_input_returns_valid_result(self, text):
        """Parser never raises an error, always returns a valid ParsedLine."""
        parser = MarkdownParser()
        
        # Should not raise any exception
        result = parser.parse_line(text)
        
        # Should always return a ParsedLine with valid type
        assert result is not None
        assert result.type in ('heading', 'subheading', 'bullet', 'numbered', 
                               'text', 'empty', 'inline_header')
        assert isinstance(result.content, str)
        assert isinstance(result.level, int)
        assert isinstance(result.metadata, dict)

    @settings(max_examples=100)
    @given(text=st.text(min_size=0, max_size=500))
    def test_parse_content_never_raises(self, text):
        """parse_content never raises an error for any input."""
        parser = MarkdownParser()
        
        # Should not raise any exception
        blocks = parser.parse_content(text)
        
        # Should always return a list
        assert isinstance(blocks, list)
        for block in blocks:
            assert block.type in ('heading', 'paragraph', 'bullet_list', 'numbered_list')



class TestBoldMarkdownConversion:
    """
    **Feature: report-excellence, Property 3: Bold markdown conversion**
    **Validates: Requirements 3.4**
    
    For any input text containing **text** or __text__ patterns,
    the output Word runs SHALL have bold formatting applied to the enclosed text.
    """
    
    @settings(max_examples=100)
    @given(
        prefix=st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N', 'S'])),
        bold_content=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=['L', 'N'])),
        suffix=st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N', 'S']))
    )
    def test_double_asterisk_bold_extraction(self, prefix, bold_content, suffix):
        """**text** patterns are correctly identified as bold."""
        bold_content = bold_content.strip()
        assume(len(bold_content) > 0)
        assume('*' not in bold_content)  # Avoid nested patterns
        assume('_' not in bold_content)
        
        text = f"{prefix}**{bold_content}**{suffix}"
        parser = MarkdownParser()
        
        segments = parser.extract_bold_segments(text)
        
        # Find the bold segment
        bold_segments = [(t, b) for t, b in segments if b]
        assert len(bold_segments) >= 1, f"No bold segment found in: {text}"
        assert any(bold_content in t for t, b in bold_segments if b), \
            f"Bold content '{bold_content}' not found in bold segments"

    @settings(max_examples=100)
    @given(
        prefix=st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N', 'S'])),
        bold_content=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=['L', 'N'])),
        suffix=st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N', 'S']))
    )
    def test_double_underscore_bold_extraction(self, prefix, bold_content, suffix):
        """__text__ patterns are correctly identified as bold."""
        bold_content = bold_content.strip()
        assume(len(bold_content) > 0)
        assume('*' not in bold_content)
        assume('_' not in bold_content)
        
        text = f"{prefix}__{bold_content}__{suffix}"
        parser = MarkdownParser()
        
        segments = parser.extract_bold_segments(text)
        
        # Find the bold segment
        bold_segments = [(t, b) for t, b in segments if b]
        assert len(bold_segments) >= 1, f"No bold segment found in: {text}"
        assert any(bold_content in t for t, b in bold_segments if b), \
            f"Bold content '{bold_content}' not found in bold segments"

    @settings(max_examples=100)
    @given(text=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=['L', 'N', 'S'])))
    def test_text_without_bold_preserved(self, text):
        """Text without bold markers is preserved as non-bold."""
        assume('**' not in text)
        assume('__' not in text)
        
        parser = MarkdownParser()
        segments = parser.extract_bold_segments(text)
        
        # Should be single non-bold segment
        assert len(segments) == 1
        assert segments[0] == (text, False)

    @settings(max_examples=100)
    @given(
        bold1=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L'])),
        middle=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'S'])),
        bold2=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L']))
    )
    def test_multiple_bold_segments(self, bold1, middle, bold2):
        """Multiple bold segments in same text are all detected."""
        bold1 = bold1.strip()
        bold2 = bold2.strip()
        middle = middle.strip()
        assume(len(bold1) > 0 and len(bold2) > 0 and len(middle) > 0)
        assume('*' not in bold1 and '*' not in bold2 and '*' not in middle)
        assume('_' not in bold1 and '_' not in bold2 and '_' not in middle)
        
        text = f"**{bold1}** {middle} **{bold2}**"
        parser = MarkdownParser()
        
        segments = parser.extract_bold_segments(text)
        bold_segments = [t for t, b in segments if b]
        
        assert len(bold_segments) == 2, f"Expected 2 bold segments, got {len(bold_segments)}"


class TestTableParsing:
    """
    **Feature: report-excellence, Property 13: Markdown table parsing**
    **Validates: Deep Research table support**
    
    For any input containing markdown table syntax (|col1|col2|),
    the parser SHALL correctly identify table rows and extract cell content.
    """
    
    def test_simple_table_parsing(self):
        """Parser correctly identifies a simple markdown table."""
        content = """| Company | Revenue | Growth |
|---------|---------|--------|
| Tesla | $81B | 15% |
| Ford | $158B | 5% |"""
        
        parser = MarkdownParser()
        blocks = parser.parse_content(content)
        
        # Should have one table block
        table_blocks = [b for b in blocks if b.type == 'table']
        assert len(table_blocks) == 1, f"Expected 1 table block, got {len(table_blocks)}"
        
        # Parse the table data
        table_data = parser.parse_table_block(table_blocks[0])
        assert table_data['headers'] == ['Company', 'Revenue', 'Growth']
        assert len(table_data['rows']) == 2
        assert table_data['rows'][0] == ['Tesla', '$81B', '15%']
        assert table_data['rows'][1] == ['Ford', '$158B', '5%']

    def test_table_row_detection(self):
        """Individual table rows are correctly detected."""
        parser = MarkdownParser()
        
        # Header row
        result = parser.parse_line("| Name | Value |")
        assert result.type == 'table_row'
        assert result.metadata['cells'] == ['Name', 'Value']
        
        # Separator row
        result = parser.parse_line("|---|---|")
        assert result.type == 'table_separator'
        
        # Data row
        result = parser.parse_line("| Tesla | $81B |")
        assert result.type == 'table_row'
        assert result.metadata['cells'] == ['Tesla', '$81B']

    def test_table_with_alignment_markers(self):
        """Tables with alignment markers (:--, :--:, --:) are parsed correctly."""
        content = """| Left | Center | Right |
|:-----|:------:|------:|
| A | B | C |"""
        
        parser = MarkdownParser()
        blocks = parser.parse_content(content)
        
        table_blocks = [b for b in blocks if b.type == 'table']
        assert len(table_blocks) == 1
        
        table_data = parser.parse_table_block(table_blocks[0])
        assert table_data['headers'] == ['Left', 'Center', 'Right']
        assert table_data['rows'][0] == ['A', 'B', 'C']

    def test_table_mixed_with_other_content(self):
        """Tables mixed with other markdown content are correctly separated."""
        content = """## Competitive Analysis

Here is the comparison:

| Company | Market Share |
|---------|-------------|
| Apple | 25% |
| Samsung | 20% |

Key takeaways:
- Apple leads the market
- Samsung is close behind"""
        
        parser = MarkdownParser()
        blocks = parser.parse_content(content)
        
        # Should have: heading, paragraph, table, paragraph, bullet_list
        block_types = [b.type for b in blocks]
        assert 'heading' in block_types
        assert 'table' in block_types
        assert 'bullet_list' in block_types

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        col1=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N'])),
        col2=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N'])),
        val1=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N'])),
        val2=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=['L', 'N']))
    )
    def test_table_cell_extraction_property(self, col1, col2, val1, val2):
        """Table cells are correctly extracted regardless of content."""
        col1, col2, val1, val2 = col1.strip(), col2.strip(), val1.strip(), val2.strip()
        assume(len(col1) > 0 and len(col2) > 0 and len(val1) > 0 and len(val2) > 0)
        assume('|' not in col1 and '|' not in col2 and '|' not in val1 and '|' not in val2)
        
        content = f"""| {col1} | {col2} |
|---|---|
| {val1} | {val2} |"""
        
        parser = MarkdownParser()
        blocks = parser.parse_content(content)
        
        table_blocks = [b for b in blocks if b.type == 'table']
        assert len(table_blocks) == 1
        
        table_data = parser.parse_table_block(table_blocks[0])
        assert table_data['headers'] == [col1, col2]
        assert table_data['rows'][0] == [val1, val2]

    def test_empty_table_handling(self):
        """Empty or malformed tables are handled gracefully."""
        parser = MarkdownParser()
        
        # Just a separator line (not a valid table)
        result = parser.parse_line("|---|---|")
        assert result.type == 'table_separator'
        
        # Single row table
        content = "| Just | One | Row |"
        blocks = parser.parse_content(content)
        table_blocks = [b for b in blocks if b.type == 'table']
        assert len(table_blocks) == 1
        
        table_data = parser.parse_table_block(table_blocks[0])
        # Single row becomes headers with no data rows
        assert table_data['headers'] == ['Just', 'One', 'Row']
        assert table_data['rows'] == []
