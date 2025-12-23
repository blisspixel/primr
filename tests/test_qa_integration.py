"""
Property-based tests for QA integration.

Feature: report-quality-assurance, Property 1: Automatic QA execution
Validates: Requirements 1.1
"""

import pytest
from hypothesis import given, strategies as st
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import os

from src.primr.qa.integration import QAIntegration
from src.primr.qa.models import QAOptions, QAResult, QAAnalysis


class TestQAIntegration:
    """Property-based tests for QA integration."""
    
    @given(
        company_name=st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).filter(lambda x: x.strip()),
        content_length=st.integers(min_value=100, max_value=5000),
        qa_enabled=st.booleans()
    )
    def test_automatic_qa_execution_property(self, company_name, content_length, qa_enabled):
        """
        Property 1: Automatic QA execution
        
        For any valid company name and report content, when QA is enabled,
        the system should execute QA analysis and return a QAResult.
        When QA is disabled, it should return None.
        
        **Feature: report-quality-assurance, Property 1: Automatic QA execution**
        **Validates: Requirements 1.1**
        """
        try:
            # Create temporary report file with UTF-8 encoding
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                # Generate content of specified length
                content = f"# Report for {company_name}\n" + "Sample content. " * (content_length // 16)
                f.write(content)
                report_path = Path(f.name)
            # Setup QA integration with specified options (disable detailed saving for tests)
            qa_options = QAOptions(enabled=qa_enabled, save_detailed=False)
            qa_integration = QAIntegration(qa_options)
            
            # Mock the analyzer to avoid actual AI calls in tests
            with patch.object(qa_integration, 'analyzer') as mock_analyzer:
                # Mock successful analysis with proper attributes
                mock_analysis = Mock(spec=QAAnalysis)
                mock_analysis.overall_score = 75
                mock_analysis.timestamp = Mock()
                mock_analyzer.analyze_report.return_value = mock_analysis
                
                # Mock report loader
                with patch.object(qa_integration, 'report_loader') as mock_loader:
                    mock_report_content = Mock()
                    mock_report_content.company_name = company_name
                    mock_report_content.content = content
                    mock_loader.load_report_from_path.return_value = mock_report_content
                    
                    # Execute QA
                    result = qa_integration.run_post_generation_qa(report_path, company_name)
                    
                    # Verify property: QA execution behavior matches enabled state
                    if qa_enabled:
                        # When enabled, should return QAResult
                        assert result is not None
                        assert isinstance(result, QAResult)
                        assert result.grade == 75
                        assert company_name.lower() in result.summary.lower() or "grade" in result.summary.lower()
                        
                        # Should have called the analyzer
                        mock_analyzer.analyze_report.assert_called_once()
                        mock_loader.load_report_from_path.assert_called_once_with(report_path)
                    else:
                        # When disabled, should return None
                        assert result is None
                        
                        # Should not have called the analyzer
                        mock_analyzer.analyze_report.assert_not_called()
                        mock_loader.load_report_from_path.assert_not_called()
        
        finally:
            # Cleanup temporary file
            if report_path.exists():
                os.unlink(report_path)
    
    @given(
        company_names=st.lists(
            st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).filter(lambda x: x.strip()),
            min_size=1,
            max_size=5
        )
    )
    def test_qa_result_consistency_property(self, company_names):
        """
        Property: QA results are consistent for the same input
        
        For any company name, running QA multiple times on the same report
        should produce consistent results (same grade, similar analysis).
        """
        # Use first company name for this test
        company_name = company_names[0]
        
        try:
            # Create temporary report file with UTF-8 encoding
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                content = f"# Strategic Analysis for {company_name}\n\nThis is a test report with consistent content."
                f.write(content)
                report_path = Path(f.name)
            qa_options = QAOptions(enabled=True)
            qa_integration = QAIntegration(qa_options)
            
            # Mock the analyzer to return consistent results
            with patch.object(qa_integration, 'analyzer') as mock_analyzer:
                mock_analysis = Mock(spec=QAAnalysis)
                mock_analysis.overall_score = 80  # Consistent score
                mock_analysis.timestamp = Mock()
                mock_analyzer.analyze_report.return_value = mock_analysis
                
                with patch.object(qa_integration, 'report_loader') as mock_loader:
                    mock_report_content = Mock()
                    mock_report_content.company_name = company_name
                    mock_report_content.content = content
                    mock_loader.load_report_from_path.return_value = mock_report_content
                    
                    # Run QA multiple times
                    results = []
                    for _ in range(3):
                        result = qa_integration.run_post_generation_qa(report_path, company_name)
                        results.append(result)
                    
                    # Verify consistency
                    assert all(r is not None for r in results)
                    assert all(r.grade == results[0].grade for r in results)
                    assert all(r.needs_attention == results[0].needs_attention for r in results)
        
        finally:
            if report_path.exists():
                os.unlink(report_path)
    
    @given(
        grade=st.integers(min_value=0, max_value=100)
    )
    def test_cli_summary_format_property(self, grade):
        """
        Property: CLI summary format is consistent
        
        For any grade from 0-100, the CLI summary should follow the format
        "Grade: (XX/100)" with optional warning for low scores.
        """
        qa_integration = QAIntegration()
        summary = qa_integration.format_cli_summary(grade)
        
        # Verify format
        assert f"({grade}/100)" in summary
        assert "Grade:" in summary
        
        # Verify warning for low scores
        if grade < 70:
            assert "Needs Attention" in summary or "warning" in summary.lower()
    
    def test_qa_failure_handling_property(self):
        """
        Property: QA failures are handled gracefully
        
        When QA analysis fails (analyzer throws exception), the system
        should return a QAResult indicating failure rather than crashing.
        """
        company_name = "Test Company"
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write("Test content")
                report_path = Path(f.name)
            qa_integration = QAIntegration(QAOptions(enabled=True))
            
            # Mock analyzer to throw exception
            with patch.object(qa_integration, 'analyzer') as mock_analyzer:
                mock_analyzer.analyze_report.side_effect = Exception("AI service unavailable")
                
                with patch.object(qa_integration, 'report_loader') as mock_loader:
                    mock_report_content = Mock()
                    mock_report_content.company_name = company_name
                    mock_loader.load_report_from_path.return_value = mock_report_content
                    
                    # Should not crash, should return failure result
                    result = qa_integration.run_post_generation_qa(report_path, company_name)
                    
                    assert result is not None
                    assert result.grade == 0  # Failure grade
                    assert "failed" in result.summary.lower() or result.grade == 0
                    assert result.needs_attention is True
        
        finally:
            if report_path.exists():
                os.unlink(report_path)