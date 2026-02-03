"""
Property-based tests for Subagent Architecture.

This module validates the correctness properties of the Subagent
Architecture using the Hypothesis library. Each test corresponds
to a formal property from the design document.

Properties tested:
- Property 16: Analyst Hypothesis Generation
- Property 17: QA Score Production

Additional tests:
- Subagent lifecycle management
- Context isolation
- Result structure validation

Validates: Requirements 3.3, 3.5, 3.7
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from primr.agentic.models import ConfidenceLevel, Hypothesis
from primr.agentic.subagents import (
    AnalysisResult,
    AnalystSubagent,
    QAResult,
    QASubagent,
    ScrapeResult,
    ScraperSubagent,
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
    WriterResult,
    WriterSubagent,
)


# =============================================================================
# STRATEGIES
# =============================================================================

# ASCII-only text for Windows compatibility
ascii_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        max_codepoint=127,
    ),
    min_size=1,
    max_size=50,
)

# Company names (ASCII only)
company_names = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        max_codepoint=127,
    ),
    min_size=1,
    max_size=30,
).filter(lambda x: x.strip() != "")

# URLs
urls = st.from_regex(
    r"https://[a-z]{3,10}\.(com|org|io)",
    fullmatch=True,
)

# Confidence levels
confidence_levels = st.sampled_from(list(ConfidenceLevel))

# QA scores
qa_scores = st.integers(min_value=0, max_value=100)


@st.composite
def subagent_contexts(draw) -> SubagentContext:
    """Generate valid SubagentContext objects."""
    return SubagentContext(
        company_name=draw(company_names),
        company_url=draw(urls),
        working_dir=Path(tempfile.mkdtemp()),
        prior_hypotheses=[],
        parent_results={},
    )


@st.composite
def hypotheses(draw) -> Hypothesis:
    """Generate valid Hypothesis objects."""
    return Hypothesis(
        id=f"h_{draw(st.integers(min_value=1, max_value=9999)):04d}",
        claim=draw(ascii_text),
        confidence=draw(confidence_levels),
        topic=draw(st.sampled_from(["technology", "financials", "general"])),
    )


# =============================================================================
# PROPERTY 16: Analyst Hypothesis Generation
# =============================================================================

# Feature: agentic-architecture, Property 16: Analyst Hypothesis Generation
@given(
    company_name=company_names,
    company_url=urls,
    claims=st.lists(ascii_text, min_size=0, max_size=5),
)
@settings(max_examples=30, deadline=None)
def test_analyst_hypothesis_generation(
    company_name: str,
    company_url: str,
    claims: list[str],
):
    """
    Analyst generates hypotheses with valid confidence levels.

    For any corpus input to the AnalystSubagent, the result should
    contain a list of hypotheses where each hypothesis has a valid
    confidence level (one of the ConfidenceLevel enum values).

    Validates: Requirements 3.3
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Create mock corpus
        corpus_dir = working_dir / "corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)

        # Create mock insights data
        insights_data = {"claims": claims, "key_points": claims}

        # Create context with corpus path
        context = SubagentContext(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
            parent_results={"corpus_path": corpus_dir},
        )

        analyst = AnalystSubagent(context)

        # Generate hypotheses directly (bypass async execute)
        hypotheses = analyst._generate_hypotheses(insights_data)

        # Verify all hypotheses have valid confidence levels
        for h in hypotheses:
            assert isinstance(h.confidence, ConfidenceLevel), (
                f"Invalid confidence type: {type(h.confidence)}"
            )
            assert h.confidence in list(ConfidenceLevel), (
                f"Invalid confidence value: {h.confidence}"
            )

        # Verify hypothesis count matches claims
        assert len(hypotheses) == len([c for c in claims if c.strip()])


# Feature: agentic-architecture, Property 16: Analyst confidence scoring
@given(
    hypotheses_list=st.lists(hypotheses(), min_size=1, max_size=10),
)
@settings(max_examples=30, deadline=None)
def test_analyst_confidence_scoring(hypotheses_list: list[Hypothesis]):
    """
    Analyst confidence scores are in valid range.

    For any set of hypotheses, confidence scores should be
    between 0 and 1 (inclusive).

    Validates: Requirements 3.3
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        context = SubagentContext(
            company_name="Test",
            company_url="https://test.com",
            working_dir=Path(tmpdir),
        )

        analyst = AnalystSubagent(context)
        scores = analyst._score_confidence(hypotheses_list)

        # Verify all scores are in valid range
        for h_id, score in scores.items():
            assert 0.0 <= score <= 1.0, (
                f"Score {score} for {h_id} out of range [0, 1]"
            )


# =============================================================================
# PROPERTY 17: QA Score Production
# =============================================================================

# Feature: agentic-architecture, Property 17: QA Score Production
@given(
    company_name=company_names,
    company_url=urls,
    report_content=st.text(
        alphabet=st.characters(max_codepoint=127),
        min_size=10,
        max_size=500,
    ),
)
@settings(max_examples=30, deadline=None)
def test_qa_score_production(
    company_name: str,
    company_url: str,
    report_content: str,
):
    """
    QA produces valid scores and feedback.

    For any report input to the QASubagent, the result should
    contain a numeric score between 0 and 100 and a list of
    feedback items.

    Validates: Requirements 3.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)

        # Create mock report
        report_path = working_dir / "report.md"
        report_path.write_text(report_content, encoding="utf-8")

        context = SubagentContext(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
            parent_results={"report_path": report_path},
        )

        qa = QASubagent(context)

        # Run basic assessment directly
        result = asyncio.run(qa._basic_assessment(report_path))

        # Verify score is in valid range
        assert isinstance(result.score, int), (
            f"Score should be int, got {type(result.score)}"
        )
        assert 0 <= result.score <= 100, (
            f"Score {result.score} out of range [0, 100]"
        )

        # Verify feedback is a list
        assert isinstance(result.feedback, list), (
            f"Feedback should be list, got {type(result.feedback)}"
        )


# Feature: agentic-architecture, Property 17: QA grade assignment
@given(score=qa_scores)
@settings(max_examples=50, deadline=None)
def test_qa_grade_assignment(score: int):
    """
    QA grades are correctly assigned based on score.

    Validates: Requirements 3.5
    """
    result = QAResult(score=score)

    # Verify grade is assigned correctly
    if score >= 90:
        assert result.grade == "A"
    elif score >= 80:
        assert result.grade == "B"
    elif score >= 70:
        assert result.grade == "C"
    elif score >= 60:
        assert result.grade == "D"
    else:
        assert result.grade == "F"


# =============================================================================
# SUBAGENT LIFECYCLE TESTS
# =============================================================================

# Feature: agentic-architecture, Subagent lifecycle management
@given(context=subagent_contexts())
@settings(max_examples=20, deadline=None)
def test_subagent_initial_status(context: SubagentContext):
    """
    Subagents start in IDLE status.

    Validates: Requirements 3.7
    """
    # Test each subagent type
    scraper = ScraperSubagent(context)
    assert scraper.status == SubagentStatus.IDLE

    analyst_context = context.with_parent_results(corpus_path=context.working_dir)
    analyst = AnalystSubagent(analyst_context)
    assert analyst.status == SubagentStatus.IDLE

    writer = WriterSubagent(context)
    assert writer.status == SubagentStatus.IDLE

    qa_context = context.with_parent_results(report_path=context.working_dir / "report.md")
    qa = QASubagent(qa_context)
    assert qa.status == SubagentStatus.IDLE


# Feature: agentic-architecture, Subagent context isolation
@given(
    context=subagent_contexts(),
    extra_key=ascii_text,
    extra_value=ascii_text,
)
@settings(max_examples=20, deadline=None)
def test_subagent_context_isolation(
    context: SubagentContext,
    extra_key: str,
    extra_value: str,
):
    """
    Subagent context with_parent_results creates isolated copy.

    Validates: Requirements 3.7
    """
    assume(extra_key.strip() != "")

    # Create derived context
    derived = context.with_parent_results(**{extra_key: extra_value})

    # Original should not have the new key
    assert extra_key not in context.parent_results

    # Derived should have the new key
    assert extra_key in derived.parent_results
    assert derived.parent_results[extra_key] == extra_value

    # Other attributes should be equal
    assert derived.company_name == context.company_name
    assert derived.company_url == context.company_url


# =============================================================================
# RESULT STRUCTURE TESTS
# =============================================================================

# Feature: agentic-architecture, SubagentResult structure
@given(
    status=st.sampled_from(list(SubagentStatus)),
    error_msg=st.one_of(st.none(), ascii_text),
)
@settings(max_examples=30, deadline=None)
def test_subagent_result_structure(
    status: SubagentStatus,
    error_msg: str | None,
):
    """
    SubagentResult correctly reports success/failure.

    Validates: Requirements 3.7
    """
    result: SubagentResult[Any] = SubagentResult(
        status=status,
        error=error_msg,
    )

    # is_success should match COMPLETED status
    assert result.is_success == (status == SubagentStatus.COMPLETED)

    # is_failure should match FAILED status
    assert result.is_failure == (status == SubagentStatus.FAILED)


# Feature: agentic-architecture, ScrapeResult success rate
@given(
    pages_scraped=st.integers(min_value=0, max_value=100),
    pages_failed=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=50, deadline=None)
def test_scrape_result_success_rate(pages_scraped: int, pages_failed: int):
    """
    ScrapeResult success rate is correctly calculated.

    Validates: Requirements 3.2
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        result = ScrapeResult(
            pages_scraped=pages_scraped,
            pages_failed=pages_failed,
            corpus_path=Path(tmpdir),
        )

        total = pages_scraped + pages_failed
        if total == 0:
            assert result.success_rate == 0.0
        else:
            expected = pages_scraped / total
            assert abs(result.success_rate - expected) < 0.001


# Feature: agentic-architecture, AnalysisResult average confidence
@given(
    scores=st.dictionaries(
        keys=st.text(min_size=1, max_size=10, alphabet=st.characters(max_codepoint=127)),
        values=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=30, deadline=None)
def test_analysis_result_average_confidence(scores: dict[str, float]):
    """
    AnalysisResult average confidence is correctly calculated.

    Validates: Requirements 3.3
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        result = AnalysisResult(
            insights_path=Path(tmpdir) / "insights.md",
            confidence_scores=scores,
        )

        if not scores:
            assert result.average_confidence == 0.0
        else:
            expected = sum(scores.values()) / len(scores)
            assert abs(result.average_confidence - expected) < 0.001


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================

def test_subagent_context_get_parent_result():
    """SubagentContext.get_parent_result returns correct values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        context = SubagentContext(
            company_name="Test",
            company_url="https://test.com",
            working_dir=Path(tmpdir),
            parent_results={"key1": "value1", "key2": 42},
        )

        assert context.get_parent_result("key1") == "value1"
        assert context.get_parent_result("key2") == 42
        assert context.get_parent_result("missing") is None
        assert context.get_parent_result("missing", "default") == "default"


def test_subagent_context_working_dir_conversion():
    """SubagentContext converts string working_dir to Path."""
    context = SubagentContext(
        company_name="Test",
        company_url="https://test.com",
        working_dir="./output",  # type: ignore
    )

    assert isinstance(context.working_dir, Path)
    assert context.working_dir == Path("./output")


def test_subagent_result_get_metric():
    """SubagentResult.get_metric returns correct values."""
    result: SubagentResult[Any] = SubagentResult(
        status=SubagentStatus.COMPLETED,
        metrics={"duration": 1.5, "count": 10.0},
    )

    assert result.get_metric("duration") == 1.5
    assert result.get_metric("count") == 10.0
    assert result.get_metric("missing") == 0.0
    assert result.get_metric("missing", 99.0) == 99.0


def test_scrape_result_to_dict():
    """ScrapeResult.to_dict serializes correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = ScrapeResult(
            pages_scraped=10,
            pages_failed=2,
            corpus_path=Path(tmpdir),
            tier_stats={"tier1": 8, "tier2": 2},
        )

        data = result.to_dict()

        assert data["pages_scraped"] == 10
        assert data["pages_failed"] == 2
        assert data["corpus_path"] == tmpdir
        assert data["tier_stats"] == {"tier1": 8, "tier2": 2}
        assert "success_rate" in data


def test_qa_result_to_dict():
    """QAResult.to_dict serializes correctly."""
    result = QAResult(
        score=85,
        feedback=["Good structure", "Needs more citations"],
        dimension_scores={"completeness": 90, "clarity": 80},
        passed=True,
    )

    data = result.to_dict()

    assert data["score"] == 85
    assert data["grade"] == "B"
    assert len(data["feedback"]) == 2
    assert data["passed"] is True


def test_writer_result_to_dict():
    """WriterResult.to_dict serializes correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = WriterResult(
            report_path=Path(tmpdir) / "report.md",
            word_count=1500,
            section_count=5,
        )

        data = result.to_dict()

        assert "report_path" in data
        assert data["word_count"] == 1500
        assert data["section_count"] == 5
        assert "generated_at" in data


def test_subagent_repr():
    """Subagent __repr__ is informative."""
    with tempfile.TemporaryDirectory() as tmpdir:
        context = SubagentContext(
            company_name="Acme Corp",
            company_url="https://acme.com",
            working_dir=Path(tmpdir),
        )

        scraper = ScraperSubagent(context)
        repr_str = repr(scraper)

        assert "ScraperSubagent" in repr_str
        assert "Acme Corp" in repr_str
        assert "idle" in repr_str

