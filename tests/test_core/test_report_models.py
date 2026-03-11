"""
Property tests for report data models.

**Feature: consulting-tier-report**
"""

from datetime import datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.core.report_models import (
    ConfidenceLevel,
    ConfidenceNote,
    GatheredData,
    Insight,
    InsightCategory,
    QualityScore,
    ReportMetadata,
    SectionContent,
    SourceCitation,
    SourceType,
)

# Strategies for generating test data
source_type_strategy = st.sampled_from(list(SourceType))
confidence_level_strategy = st.sampled_from(list(ConfidenceLevel))
insight_category_strategy = st.sampled_from(list(InsightCategory))
datetime_strategy = st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2030, 12, 31))


@st.composite
def source_citation_strategy(draw):
    return SourceCitation(
        url=draw(st.text(min_size=1, max_size=200).filter(lambda x: x.strip())),
        title=draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip())),
        source_type=draw(source_type_strategy),
        accessed_at=draw(datetime_strategy),
        excerpt=draw(st.text(max_size=500)),
    )


@st.composite
def gathered_data_strategy(draw):
    return GatheredData(
        content=draw(st.text(min_size=1, max_size=1000).filter(lambda x: x.strip())),
        source_url=draw(st.text(min_size=1, max_size=200).filter(lambda x: x.strip())),
        source_type=draw(source_type_strategy),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0)),
        gathered_at=draw(datetime_strategy),
        title=draw(st.text(max_size=100)),
    )


@st.composite
def confidence_note_strategy(draw):
    return ConfidenceNote(
        statement=draw(st.text(min_size=1, max_size=200).filter(lambda x: x.strip())),
        confidence=draw(confidence_level_strategy),
        basis=draw(st.text(min_size=1, max_size=200).filter(lambda x: x.strip())),
    )


@st.composite
def insight_strategy(draw):
    return Insight(
        title=draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip())),
        description=draw(st.text(min_size=1, max_size=500).filter(lambda x: x.strip())),
        evidence=draw(
            st.lists(
                st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
                min_size=1,
                max_size=5,
            )
        ),
        confidence=draw(confidence_level_strategy),
        category=draw(insight_category_strategy),
        sources=draw(
            st.lists(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                min_size=1,
                max_size=5,
            )
        ),
        rationale=draw(st.text(max_size=300)),
    )


@st.composite
def section_content_strategy(draw):
    return SectionContent(
        title=draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip())),
        content=draw(st.text(min_size=1, max_size=1000).filter(lambda x: x.strip())),
        sources=draw(st.lists(source_citation_strategy(), max_size=5)),
        confidence_notes=draw(st.lists(confidence_note_strategy(), max_size=3)),
    )


@st.composite
def report_metadata_strategy(draw):
    return ReportMetadata(
        company_name=draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip())),
        website=draw(st.text(min_size=1, max_size=200).filter(lambda x: x.strip())),
        industry=draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip())),
        generated_at=draw(datetime_strategy),
        research_duration_seconds=draw(st.floats(min_value=0.0, max_value=3600.0)),
        sources_count=draw(st.integers(min_value=0, max_value=100)),
    )


@st.composite
def quality_score_strategy(draw):
    return QualityScore(
        score=draw(st.floats(min_value=0.0, max_value=10.0)),
        issues=draw(
            st.lists(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()), max_size=5)
        ),
        suggestions=draw(
            st.lists(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()), max_size=5)
        ),
        needs_refinement=draw(st.booleans()),
    )


class TestSourceCitationSerialization:
    """**Property 7: Source Attribution** - verify source citations serialize correctly."""

    @given(source_citation_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_roundtrip_serialization(self, citation: SourceCitation):
        """SourceCitation should serialize and deserialize without data loss."""
        data = citation.to_dict()
        restored = SourceCitation.from_dict(data)

        assert restored.url == citation.url
        assert restored.title == citation.title
        assert restored.source_type == citation.source_type
        assert restored.accessed_at == citation.accessed_at
        assert restored.excerpt == citation.excerpt


class TestGatheredDataSerialization:
    """Test GatheredData serialization."""

    @given(gathered_data_strategy())
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, data: GatheredData):
        """GatheredData should serialize and deserialize without data loss."""
        serialized = data.to_dict()
        restored = GatheredData.from_dict(serialized)

        assert restored.content == data.content
        assert restored.source_url == data.source_url
        assert restored.source_type == data.source_type
        assert abs(restored.confidence - data.confidence) < 0.0001
        assert restored.gathered_at == data.gathered_at
        assert restored.title == data.title


class TestConfidenceNoteSerialization:
    """Test ConfidenceNote serialization."""

    @given(confidence_note_strategy())
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, note: ConfidenceNote):
        """ConfidenceNote should serialize and deserialize without data loss."""
        data = note.to_dict()
        restored = ConfidenceNote.from_dict(data)

        assert restored.statement == note.statement
        assert restored.confidence == note.confidence
        assert restored.basis == note.basis


class TestInsightSerialization:
    """Test Insight serialization."""

    @given(insight_strategy())
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, insight: Insight):
        """Insight should serialize and deserialize without data loss."""
        data = insight.to_dict()
        restored = Insight.from_dict(data)

        assert restored.title == insight.title
        assert restored.description == insight.description
        assert restored.evidence == insight.evidence
        assert restored.confidence == insight.confidence
        assert restored.category == insight.category
        assert restored.sources == insight.sources
        assert restored.rationale == insight.rationale


class TestSectionContentSerialization:
    """Test SectionContent serialization."""

    @given(section_content_strategy())
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, section: SectionContent):
        """SectionContent should serialize and deserialize without data loss."""
        data = section.to_dict()
        restored = SectionContent.from_dict(data)

        assert restored.title == section.title
        assert restored.content == section.content
        assert len(restored.sources) == len(section.sources)
        assert len(restored.confidence_notes) == len(section.confidence_notes)


class TestReportMetadataSerialization:
    """Test ReportMetadata serialization."""

    @given(report_metadata_strategy())
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, metadata: ReportMetadata):
        """ReportMetadata should serialize and deserialize without data loss."""
        data = metadata.to_dict()
        restored = ReportMetadata.from_dict(data)

        assert restored.company_name == metadata.company_name
        assert restored.website == metadata.website
        assert restored.industry == metadata.industry
        assert restored.generated_at == metadata.generated_at
        assert abs(restored.research_duration_seconds - metadata.research_duration_seconds) < 0.0001
        assert restored.sources_count == metadata.sources_count


class TestQualityScoreSerialization:
    """Test QualityScore serialization."""

    @given(quality_score_strategy())
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, score: QualityScore):
        """QualityScore should serialize and deserialize without data loss."""
        data = score.to_dict()
        restored = QualityScore.from_dict(data)

        assert abs(restored.score - score.score) < 0.0001
        assert restored.issues == score.issues
        assert restored.suggestions == score.suggestions
        assert restored.needs_refinement == score.needs_refinement
