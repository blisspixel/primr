"""
Property-based tests for report generation data models.

Uses Hypothesis to verify correctness properties across many random inputs.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.output.models import (
    ChapterContent,
    CompanySnapshot,
    ContentBlock,
    DocumentMetadata,
    ExecutiveSummary,
    ParsedLine,
    SectionContent,
)

# =============================================================================
# Generators for property-based testing
# =============================================================================


@st.composite
def unicode_text(draw):
    """Generate text with various Unicode characters including special chars."""
    return draw(
        st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(
                whitelist_categories=["L", "N", "P", "S", "Sc", "Sm"],
                whitelist_characters="éèêëàâäùûüôöîïç€£¥©®™°±×÷",
            ),
        )
    )


@st.composite
def parsed_line_data(draw):
    """Generate valid ParsedLine data."""
    line_type = draw(
        st.sampled_from(
            ["heading", "subheading", "bullet", "numbered", "text", "empty", "inline_header"]
        )
    )
    content = draw(unicode_text())
    level = draw(st.integers(min_value=0, max_value=4))
    raw = draw(st.text(min_size=0, max_size=300))
    metadata = draw(
        st.dictionaries(
            keys=st.text(
                min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=["L"])
            ),
            values=st.text(min_size=0, max_size=50),
            max_size=5,
        )
    )
    return line_type, content, level, raw, metadata


@st.composite
def company_snapshot_data(draw):
    """Generate valid CompanySnapshot data with Unicode characters."""
    return {
        "company_name": draw(unicode_text()),
        "website": draw(st.text(min_size=0, max_size=100)),
        "industry": draw(unicode_text()),
        "founded": draw(
            st.one_of(st.none(), st.text(min_size=4, max_size=4, alphabet="0123456789"))
        ),
        "headquarters": draw(st.one_of(st.none(), unicode_text())),
        "revenue": draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        "employees": draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        "ticker": draw(
            st.one_of(
                st.none(), st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            )
        ),
    }


# =============================================================================
# Property Tests
# =============================================================================


class TestSpecialCharacterPreservation:
    """
    **Feature: report-excellence, Property 8: Special character preservation**
    **Validates: Requirements 7.4**

    For any input containing Unicode characters (accented letters, currency symbols, etc.),
    the data models SHALL preserve the identical characters without encoding corruption.
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=parsed_line_data())
    def test_parsed_line_preserves_unicode(self, data):
        """ParsedLine preserves all Unicode characters in content and raw fields."""
        line_type, content, level, raw, metadata = data

        parsed = ParsedLine(
            type=line_type, content=content, level=level, raw=raw, metadata=metadata
        )

        # Verify content is preserved exactly
        assert parsed.content == content, "Content was corrupted"
        assert parsed.raw == raw, "Raw was corrupted"
        assert parsed.type == line_type
        assert parsed.level == level
        assert parsed.metadata == metadata

    @settings(max_examples=100)
    @given(data=company_snapshot_data())
    def test_company_snapshot_preserves_unicode(self, data):
        """CompanySnapshot preserves all Unicode characters in all fields."""
        snapshot = CompanySnapshot(**data)

        # Verify all fields are preserved exactly
        assert snapshot.company_name == data["company_name"]
        assert snapshot.website == data["website"]
        assert snapshot.industry == data["industry"]
        assert snapshot.founded == data["founded"]
        assert snapshot.headquarters == data["headquarters"]
        assert snapshot.revenue == data["revenue"]
        assert snapshot.employees == data["employees"]
        assert snapshot.ticker == data["ticker"]

    @settings(max_examples=100)
    @given(content=unicode_text())
    def test_content_block_preserves_unicode(self, content):
        """ContentBlock preserves Unicode in nested ParsedLine objects."""
        line = ParsedLine(type="text", content=content, level=0, raw=content, metadata={})
        block = ContentBlock(type="paragraph", lines=[line], properties={})

        # Verify content is preserved through nesting
        assert block.lines[0].content == content
        assert block.lines[0].raw == content

    @settings(max_examples=100)
    @given(narrative=unicode_text(), takeaway=unicode_text(), one_liner=unicode_text())
    def test_executive_summary_preserves_unicode(self, narrative, takeaway, one_liner):
        """ExecutiveSummary preserves Unicode in all text fields."""
        summary = ExecutiveSummary(
            narrative=narrative,
            key_takeaways=[takeaway],
            metrics_snapshot={"key": takeaway},
            risk_factors=[takeaway],
            one_liner=one_liner,
        )

        assert summary.narrative == narrative
        assert summary.key_takeaways[0] == takeaway
        assert summary.metrics_snapshot["key"] == takeaway
        assert summary.risk_factors[0] == takeaway
        assert summary.one_liner == one_liner

    @settings(max_examples=100)
    @given(title=unicode_text(), section_title=unicode_text())
    def test_chapter_content_preserves_unicode(self, title, section_title):
        """ChapterContent and SectionContent preserve Unicode in titles."""
        section = SectionContent(
            number="1.1", title=section_title, key="test_key", blocks=[], has_content=True
        )

        chapter = ChapterContent(number=1, title=title, icon="🏢", sections=[section])

        assert chapter.title == title
        assert chapter.sections[0].title == section_title

    @settings(max_examples=100)
    @given(company_name=unicode_text())
    def test_document_metadata_preserves_unicode(self, company_name):
        """DocumentMetadata preserves Unicode in company name."""
        metadata = DocumentMetadata(company_name=company_name)

        assert metadata.company_name == company_name
