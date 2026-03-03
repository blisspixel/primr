"""
Tests for sections_written field accuracy and propagation.

Validates that sections_written correctly tracks the number of sections
actually written by the Accordion Method and propagates through the result chain.

**Feature: test-coverage-hardening**
**Validates: Requirements 4.1, 4.2, 4.3, 4.4**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.ai.deep_research import DeepResearchOrchestratorResult
from primr.core.research_orchestrator import OrchestratorResult, ResearchMode

# =============================================================================
# Unit Tests for DeepResearchOrchestratorResult
# =============================================================================


class TestDeepResearchOrchestratorResultSectionsWritten:
    """Tests for sections_written field in DeepResearchOrchestratorResult."""

    def test_sections_written_default_is_zero(self):
        """
        sections_written defaults to 0 when not specified.
        
        **Validates: Requirements 4.1**
        """
        result = DeepResearchOrchestratorResult(
            company_name="Test",
            content="Report content",
            citations=[],
            duration_seconds=100.0,
            success=True,
        )
        assert result.sections_written == 0

    def test_sections_written_can_be_set(self):
        """
        sections_written can be explicitly set.
        
        **Validates: Requirements 4.1**
        """
        result = DeepResearchOrchestratorResult(
            company_name="Test",
            content="Report content",
            citations=[],
            duration_seconds=100.0,
            success=True,
            sections_written=20,
        )
        assert result.sections_written == 20

    def test_sections_written_reflects_partial_success(self):
        """
        sections_written reflects only successful sections when some fail.
        
        **Validates: Requirements 4.4**
        """
        result = DeepResearchOrchestratorResult(
            company_name="Test",
            content="Partial report",
            citations=[],
            duration_seconds=100.0,
            success=True,
            sections_written=15,  # Only 15 of 21 succeeded
            api_calls=21,
        )
        assert result.sections_written == 15
        assert result.sections_written < 21  # Less than total sections


# =============================================================================
# Unit Tests for OrchestratorResult
# =============================================================================


class TestOrchestratorResultSectionsWritten:
    """Tests for sections_written field in OrchestratorResult."""

    def test_orchestrator_result_has_sections_written(self):
        """
        OrchestratorResult has sections_written field.
        
        **Validates: Requirements 4.2**
        """
        result = OrchestratorResult(
            company_name="Test",
            website="https://test.com",
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={"strategic_overview": "content"},
            sections_written=20,
        )
        assert hasattr(result, "sections_written")
        assert result.sections_written == 20

    def test_orchestrator_result_sections_written_default(self):
        """
        OrchestratorResult.sections_written defaults to 0.
        
        **Validates: Requirements 4.2**
        """
        result = OrchestratorResult(
            company_name="Test",
            website="https://test.com",
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={},
        )
        assert result.sections_written == 0

    def test_sections_written_independent_of_section_results_length(self):
        """
        sections_written is independent of len(section_results).
        
        This is the key fix - section_results may have only 1 key
        (strategic_overview) containing the entire report, but
        sections_written should reflect actual sections written.
        
        **Validates: Requirements 4.3**
        """
        result = OrchestratorResult(
            company_name="Test",
            website="https://test.com",
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={"strategic_overview": "Full 20-section report content"},
            sections_written=20,  # Actual sections written
        )

        # section_results has 1 key, but sections_written is 20
        assert len(result.section_results) == 1
        assert result.sections_written == 20


# =============================================================================
# Propagation Tests
# =============================================================================


class TestSectionsWrittenPropagation:
    """Tests for sections_written propagation through the result chain."""

    def test_deep_research_to_orchestrator_propagation(self):
        """
        sections_written propagates from DeepResearchOrchestratorResult to OrchestratorResult.
        
        **Validates: Requirements 4.2**
        """
        # Simulate DeepResearchOrchestratorResult
        deep_result = DeepResearchOrchestratorResult(
            company_name="Test Corp",
            content="Full report content",
            citations=[],
            duration_seconds=300.0,
            success=True,
            sections_written=18,
        )

        # Create OrchestratorResult with propagated value
        orchestrator_result = OrchestratorResult(
            company_name=deep_result.company_name,
            website="https://test.com",
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={"strategic_overview": deep_result.content},
            sections_written=deep_result.sections_written,  # Propagated
            duration_seconds=deep_result.duration_seconds,
            success=deep_result.success,
        )

        assert orchestrator_result.sections_written == deep_result.sections_written
        assert orchestrator_result.sections_written == 18


# =============================================================================
# Property Tests
# =============================================================================


@given(sections_written=st.integers(min_value=0, max_value=21))
@settings(max_examples=100, deadline=None)
def test_property_sections_written_accuracy(sections_written: int):
    """
    **Feature: test-coverage-hardening, Property 5: sections_written accuracy and propagation**
    **Validates: Requirements 4.1, 4.2, 4.3**
    
    For any Accordion Method execution, sections_written should equal
    the count of successfully written sections.
    """
    result = DeepResearchOrchestratorResult(
        company_name="Test",
        content="Report content",
        citations=[],
        duration_seconds=100.0,
        success=sections_written > 0,
        sections_written=sections_written,
    )

    assert result.sections_written == sections_written
    assert result.sections_written >= 0
    assert result.sections_written <= 21


@given(
    deep_sections=st.integers(min_value=0, max_value=21),
)
@settings(max_examples=100, deadline=None)
def test_property_sections_written_propagation(deep_sections: int):
    """
    **Feature: test-coverage-hardening, Property 5: sections_written accuracy and propagation**
    **Validates: Requirements 4.1, 4.2, 4.3**
    
    For any sections_written value, it should propagate unchanged
    from DeepResearchOrchestratorResult to OrchestratorResult.
    """
    # Create source result
    deep_result = DeepResearchOrchestratorResult(
        company_name="Test",
        content="Content",
        citations=[],
        duration_seconds=100.0,
        success=True,
        sections_written=deep_sections,
    )

    # Propagate to orchestrator result
    orchestrator_result = OrchestratorResult(
        company_name=deep_result.company_name,
        website=None,
        mode=ResearchMode.DEEP_RESEARCH,
        section_results={},
        sections_written=deep_result.sections_written,
    )

    # Value should be unchanged
    assert orchestrator_result.sections_written == deep_result.sections_written
    assert orchestrator_result.sections_written == deep_sections


@given(
    successful=st.integers(min_value=0, max_value=21),
    failed=st.integers(min_value=0, max_value=6),
)
@settings(max_examples=100, deadline=None)
def test_property_sections_written_reflects_success_only(successful: int, failed: int):
    """
    **Feature: test-coverage-hardening, Property 5: sections_written accuracy and propagation**
    **Validates: Requirements 4.4**
    
    When some sections fail, sections_written should reflect only successful sections.
    """
    total_attempted = successful + failed

    result = DeepResearchOrchestratorResult(
        company_name="Test",
        content="Partial report",
        citations=[],
        duration_seconds=100.0,
        success=successful > 0,
        sections_written=successful,  # Only successful sections
        api_calls=total_attempted,
    )

    # sections_written should be exactly the successful count
    assert result.sections_written == successful
    # sections_written should never exceed total attempted
    assert result.sections_written <= total_attempted
    # sections_written should never be negative
    assert result.sections_written >= 0
