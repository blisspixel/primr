"""
Property-based tests for the DocumentBuilder.

Uses Hypothesis to verify document structure and content correctness.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.output.chapter_config import CHAPTER_CONFIG, get_chapter_for_section, get_section_number


class TestChapterGrouping:
    """
    **Feature: report-excellence, Property 10: Chapter grouping correctness**
    **Validates: Requirements 1.4**
    
    For any section in the input, it SHALL appear under the correct chapter
    heading as defined in the chapter configuration.
    """

    def test_all_sections_have_chapter_assignment(self):
        """Every section in CHAPTER_CONFIG has a valid chapter assignment."""
        for chapter_name, chapter_data in CHAPTER_CONFIG.items():
            sections = chapter_data.get('sections', [])
            assert len(sections) > 0, f"Chapter '{chapter_name}' has no sections"

            for section_title, section_key in sections:
                chapter, num = get_chapter_for_section(section_key)
                assert chapter == chapter_name, \
                    f"Section '{section_key}' should be in '{chapter_name}' but got '{chapter}'"

    def test_section_numbers_are_sequential(self):
        """Section numbers within each chapter are sequential."""
        for chapter_num, (chapter_name, chapter_data) in enumerate(CHAPTER_CONFIG.items(), 1):
            sections = chapter_data.get('sections', [])

            for section_idx, (section_title, section_key) in enumerate(sections, 1):
                expected_num = f"{chapter_num}.{section_idx}"
                actual_num = get_section_number(section_key)
                assert actual_num == expected_num, \
                    f"Section '{section_key}' should be '{expected_num}' but got '{actual_num}'"

    def test_chapter_config_has_five_chapters(self):
        """CHAPTER_CONFIG has exactly 5 chapters as per design."""
        assert len(CHAPTER_CONFIG) == 5, f"Expected 5 chapters, got {len(CHAPTER_CONFIG)}"

    @settings(max_examples=50)
    @given(section_key=st.sampled_from([
        'mission_vision', 'company_history', 'key_achievements',
        'detailed_products_services', 'unique_selling_proposition',
        'target_audience', 'main_types_of_users',
        'financial_overview', 'business_drivers_and_kpis',
        'primary_apps_sources_of_data',
        'industry_insights', 'potential_business_value', 'potential_business_drivers',
        'board_of_directors_concerns', 'value_theory', 'strategic_recommendations'
    ]))
    def test_get_section_number_returns_valid_format(self, section_key):
        """get_section_number returns valid X.Y format for all sections."""
        section_num = get_section_number(section_key)

        assert section_num, f"Section '{section_key}' has no number"
        parts = section_num.split('.')
        assert len(parts) == 2, f"Section number '{section_num}' should be X.Y format"
        assert parts[0].isdigit(), "Chapter number should be digit"
        assert parts[1].isdigit(), "Section number should be digit"


class TestNestedListIndentation:
    """
    **Feature: report-excellence, Property 7: Nested list indentation preservation**
    **Validates: Requirements 7.3**
    
    For any input with nested bullet lists, the output SHALL preserve
    the relative indentation levels.
    """

    @settings(max_examples=50)
    @given(indent_level=st.integers(min_value=0, max_value=3))
    def test_indent_levels_are_preserved(self, indent_level):
        """Indent levels 0-3 are valid and preserved."""
        from primr.output.markdown_parser import MarkdownParser

        parser = MarkdownParser()
        indent = '    ' * indent_level
        line = f"{indent}* Test bullet"

        result = parser.parse_line(line)

        assert result.type == 'bullet'
        assert result.level == indent_level

    def test_nested_bullets_maintain_hierarchy(self):
        """Nested bullets maintain their relative hierarchy."""
        from primr.output.markdown_parser import MarkdownParser

        parser = MarkdownParser()
        content = """* Level 0
    * Level 1
        * Level 2
    * Back to Level 1
* Back to Level 0"""

        blocks = parser.parse_content(content)

        # Should be one bullet_list block
        bullet_blocks = [b for b in blocks if b.type == 'bullet_list']
        assert len(bullet_blocks) == 1

        # Check levels
        levels = [line.level for line in bullet_blocks[0].lines]
        assert levels == [0, 1, 2, 1, 0]


class TestDefensiveParsing:
    """
    **Feature: consulting-tier-report, Property: Defensive content parsing**
    **Validates: Requirements 29.2 - Graceful handling of malformed content**
    
    For any malformed or unparseable content, the DocumentBuilder SHALL
    fall back to plain text rendering without crashing.
    """

    def test_malformed_content_does_not_crash(self):
        """DocumentBuilder handles malformed content gracefully."""
        from primr.output.document_builder import DocumentBuilder

        # Content with various edge cases that might break parsing
        malformed_sections = {
            'company_overview': '# Broken\n\n```unclosed code block\nsome code',
            'detailed_products_services': '| broken | table\n| no | closing',
            'mission_vision': '**unclosed bold\n\n*unclosed italic',
            'financial_overview': '\x00\x01\x02 binary garbage \xff\xfe',
        }

        # Should not raise any exception
        builder = DocumentBuilder('Test Company', malformed_sections)
        document = builder.build()

        # Document should still be created
        assert document is not None
        assert len(document.paragraphs) > 0

    def test_empty_content_handled(self):
        """DocumentBuilder handles empty content gracefully."""
        from primr.output.document_builder import DocumentBuilder

        empty_sections = {
            'company_overview': '',
            'detailed_products_services': '   ',
            'mission_vision': '\n\n\n',
        }

        builder = DocumentBuilder('Test Company', empty_sections)
        document = builder.build()

        assert document is not None

    def test_none_content_handled(self):
        """DocumentBuilder handles None values gracefully."""
        from primr.output.document_builder import DocumentBuilder

        # Mix of valid and None content
        sections = {
            'company_overview': 'Valid content here',
            'detailed_products_services': None,
        }

        builder = DocumentBuilder('Test Company', sections)
        document = builder.build()

        assert document is not None

    @settings(max_examples=20)
    @given(content=st.text(min_size=0, max_size=1000))
    def test_arbitrary_content_never_crashes(self, content):
        """DocumentBuilder never crashes on arbitrary text input."""
        from primr.output.document_builder import DocumentBuilder

        sections = {'company_overview': content}

        # Should never raise
        builder = DocumentBuilder('Test Company', sections)
        document = builder.build()

        assert document is not None
