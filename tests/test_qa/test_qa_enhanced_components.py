"""
Unit tests for enhanced QA components.

Tests the core functionality of the enhanced QA system components
including SimpleQAAnalyzer, SimpleJSONParser, and integration logic.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

from src.primr.qa.simple_analyzer import SimpleQAAnalyzer, SimpleQAResult
from src.primr.qa.json_parser import SimpleJSONParser
from src.primr.qa.integration import QAIntegration
from src.primr.qa.models import ReportContent, ReportMetadata, QAOptions
from src.primr.config.models import PrimrModels


class TestSimpleQAAnalyzer:
    """Unit tests for SimpleQAAnalyzer."""
    
    def test_initialization(self):
        """Test analyzer initialization with proper configuration."""
        analyzer = SimpleQAAnalyzer()
        
        # Should use centralized model config
        assert analyzer.model_name == PrimrModels.QA_MODEL
        assert analyzer.error_handler is not None
        assert analyzer.json_parser is not None
    
    def test_build_assessment_prompt(self):
        """Test assessment prompt building with proper structure."""
        analyzer = SimpleQAAnalyzer()
        
        test_report = ReportContent(
            company_name="Test Corp",
            content="Test content for prompt building.",
            sections={"Executive Summary": "Summary content", "Analysis": "Analysis content"},
            citations=["Source 1", "Source 2"],
            metadata=ReportMetadata(
                company_name="Test Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        prompt = analyzer._build_assessment_prompt(test_report)
        
        # Verify prompt structure - updated for consultant-focused prompt
        assert "Test Corp" in prompt
        assert "consultant" in prompt.lower()
        assert "JSON format" in prompt
        assert "Executive Summary: 2 words" in prompt
        assert "Analysis: 2 words" in prompt
        assert "2 sources" in prompt
        # Check for key evaluation criteria
        assert "ready_for_use" in prompt
        assert "confidence_level" in prompt
        assert "key_strengths" in prompt
        assert "areas_for_improvement" in prompt
    
    def test_successful_assessment(self):
        """Test successful assessment with valid JSON response."""
        analyzer = SimpleQAAnalyzer()
        
        test_report = ReportContent(
            company_name="Success Corp",
            content="Test content for successful assessment.",
            sections={"Analysis": "Test analysis"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Success Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        mock_response = """{
            "ready_for_use": true,
            "confidence_level": "high",
            "key_strengths": ["Strong analysis", "Good citations"],
            "areas_for_improvement": ["Minor formatting"],
            "recommendation": "Report is ready for internal use"
        }"""
        
        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response
            
            result = analyzer.assess_report(test_report)
            
            assert isinstance(result, SimpleQAResult)
            assert result.parsing_success == True
            assert result.ready_for_use == True
            assert result.confidence_level == "high"
            assert len(result.key_strengths) == 2
            assert len(result.areas_for_improvement) == 1
            assert "ready for internal use" in result.recommendation
    
    def test_retry_logic_with_rate_limit(self):
        """Test retry logic handles rate limits with exponential backoff."""
        analyzer = SimpleQAAnalyzer()
        
        test_report = ReportContent(
            company_name="Retry Corp",
            content="Test content for retry testing.",
            sections={"Analysis": "Test analysis"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Retry Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        success_response = """{
            "ready_for_use": true,
            "confidence_level": "medium",
            "key_strengths": ["Successful after retry"],
            "areas_for_improvement": [],
            "recommendation": "Assessment completed after handling rate limit"
        }"""
        
        call_count = 0
        def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate limit exceeded (429)")
            return success_response
        
        with patch.object(analyzer, 'ai_client') as mock_client:
            with patch('time.sleep'):  # Mock sleep to speed up test
                mock_client.generate.side_effect = mock_generate
                
                result = analyzer.assess_report(test_report)
                
                assert isinstance(result, SimpleQAResult)
                assert result.parsing_success == True
                assert "after handling rate limit" in result.recommendation
                assert call_count == 2  # Should have retried once
    
    def test_error_result_creation(self):
        """Test error result creation with diagnostic information."""
        analyzer = SimpleQAAnalyzer()
        
        # Test rate limit error
        rate_limit_result = analyzer._create_error_result("Rate limit exceeded (429)")
        assert rate_limit_result.ready_for_use == False
        assert rate_limit_result.confidence_level == "low"
        assert "rate limit" in rate_limit_result.recommendation.lower()
        assert "retry later" in rate_limit_result.recommendation.lower()
        
        # Test quota error
        quota_result = analyzer._create_error_result("Daily quota exceeded")
        assert "quota exhausted" in quota_result.recommendation.lower()
        assert "manual review" in quota_result.recommendation.lower()
        
        # Test generic error
        generic_result = analyzer._create_error_result("Unknown error occurred")
        assert "technical issue" in generic_result.recommendation.lower()


class TestSimpleJSONParser:
    """Unit tests for SimpleJSONParser."""
    
    def test_initialization(self):
        """Test JSON parser initialization."""
        parser = SimpleJSONParser()
        
        assert parser.extraction_attempts == 0
        assert parser.successful_extractions == 0
    
    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        parser = SimpleJSONParser()
        
        valid_response = """{
            "ready_for_use": true,
            "confidence_level": "high",
            "key_strengths": ["Good analysis"],
            "areas_for_improvement": ["Minor issues"],
            "recommendation": "Ready for use"
        }"""
        
        result = parser.parse_qa_response(valid_response)
        
        assert result is not None
        assert result["ready_for_use"] == True
        assert result["confidence_level"] == "high"
        assert len(result["key_strengths"]) == 1
        assert parser.successful_extractions == 1
    
    def test_parse_markdown_wrapped_json(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        parser = SimpleJSONParser()
        
        markdown_response = """Here's the assessment:
        
```json
{
    "ready_for_use": false,
    "confidence_level": "medium",
    "key_strengths": ["Some strengths"],
    "areas_for_improvement": ["Needs work"],
    "recommendation": "Improvements needed"
}
```

That's my analysis."""
        
        result = parser.parse_qa_response(markdown_response)
        
        assert result is not None
        assert result["ready_for_use"] == False
        assert result["confidence_level"] == "medium"
        assert parser.successful_extractions == 1
    
    def test_regex_fallback_extraction(self):
        """Test regex fallback when JSON parsing fails."""
        parser = SimpleJSONParser()
        
        malformed_response = """
        The report analysis shows:
        "ready_for_use": true
        "confidence_level": "medium"
        "key_strengths": ["Good structure", "Clear analysis"]
        "areas_for_improvement": ["Needs citations"]
        "recommendation": "Generally good report with minor improvements needed"
        """
        
        result = parser.extract_with_regex_fallback(malformed_response)
        
        assert result["ready_for_use"] == True
        assert result["confidence_level"] == "medium"
        assert len(result["key_strengths"]) == 2
        assert len(result["areas_for_improvement"]) == 1
        assert "improvements needed" in result["recommendation"]
    
    def test_json_structure_validation(self):
        """Test JSON structure validation."""
        parser = SimpleJSONParser()
        
        # Valid structure
        valid_data = {
            "ready_for_use": True,
            "confidence_level": "high",
            "key_strengths": ["Good"],
            "areas_for_improvement": ["Minor"],
            "recommendation": "Ready"
        }
        assert parser._validate_qa_structure(valid_data) == True
        
        # Missing field
        invalid_data = {
            "ready_for_use": True,
            "confidence_level": "high",
            "key_strengths": ["Good"]
            # Missing areas_for_improvement and recommendation
        }
        assert parser._validate_qa_structure(invalid_data) == False
        
        # Invalid confidence level
        invalid_confidence = {
            "ready_for_use": True,
            "confidence_level": "invalid",
            "key_strengths": ["Good"],
            "areas_for_improvement": ["Minor"],
            "recommendation": "Ready"
        }
        assert parser._validate_qa_structure(invalid_confidence) == False
    
    def test_parsing_statistics(self):
        """Test parsing statistics tracking."""
        parser = SimpleJSONParser()
        
        # Successful parse
        valid_response = '{"ready_for_use": true, "confidence_level": "high", "key_strengths": [], "areas_for_improvement": [], "recommendation": "Good"}'
        parser.parse_qa_response(valid_response)
        
        # Failed parse
        invalid_response = "not json at all"
        parser.parse_qa_response(invalid_response)
        
        stats = parser.get_parsing_stats()
        assert stats["total_attempts"] == 2
        assert stats["successful_extractions"] == 1
        assert stats["success_rate"] == 50.0
        assert stats["failed_extractions"] == 1


class TestQAIntegration:
    """Unit tests for QA integration components."""
    
    def test_numerical_grade_calculation(self):
        """Test numerical grade calculation logic."""
        integration = QAIntegration()
        
        # High quality, ready for use
        high_quality = SimpleQAResult(
            ready_for_use=True,
            confidence_level="high",
            key_strengths=["Excellent", "Outstanding", "Perfect"],
            areas_for_improvement=["Minor issue"],
            recommendation="Excellent work",
            parsing_success=True
        )
        high_grade = integration._calculate_numerical_grade(high_quality)
        assert 85 <= high_grade <= 95, f"Expected 85-95, got {high_grade}"
        
        # Medium quality, ready for use
        medium_quality = SimpleQAResult(
            ready_for_use=True,
            confidence_level="medium",
            key_strengths=["Good", "Solid"],
            areas_for_improvement=["Needs work", "Could improve"],
            recommendation="Good with improvements",
            parsing_success=True
        )
        medium_grade = integration._calculate_numerical_grade(medium_quality)
        assert 65 <= medium_grade <= 80, f"Expected 65-80, got {medium_grade}"
        
        # Not ready for use
        not_ready = SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=[],
            areas_for_improvement=["Major issues", "Significant problems", "Needs overhaul"],
            recommendation="Not ready",
            parsing_success=True
        )
        low_grade = integration._calculate_numerical_grade(not_ready)
        assert 25 <= low_grade <= 50, f"Expected 25-50, got {low_grade}"
        
        # Parsing failure
        parsing_failure = SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=[],
            areas_for_improvement=[],
            recommendation="Parsing failed",
            parsing_success=False
        )
        failure_grade = integration._calculate_numerical_grade(parsing_failure)
        assert failure_grade == 50, f"Expected 50 for parsing failure, got {failure_grade}"
    
    def test_cli_summary_formatting(self):
        """Test CLI summary formatting with grades."""
        integration = QAIntegration()
        
        # Ready for use, high confidence
        high_result = SimpleQAResult(
            ready_for_use=True,
            confidence_level="high",
            key_strengths=["Great"],
            areas_for_improvement=[],
            recommendation="Excellent",
            parsing_success=True
        )
        high_summary = integration.format_cli_summary(high_result)
        assert "Grade:" in high_summary
        assert "/100" in high_summary
        # Grade should be in 80s range for high confidence ready report
        assert any(str(g) in high_summary for g in range(80, 100))
        
        # Needs work
        needs_work = SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=[],
            areas_for_improvement=["Issues"],
            recommendation="Needs work",
            parsing_success=True
        )
        work_summary = integration.format_cli_summary(needs_work)
        assert "Grade:" in work_summary
        assert "/100" in work_summary
        
        # Parsing failure
        parse_fail = SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=[],
            areas_for_improvement=[],
            recommendation="Failed",
            parsing_success=False
        )
        fail_summary = integration.format_cli_summary(parse_fail)
        assert "Analysis Failed" in fail_summary
    
    def test_error_result_creation(self):
        """Test error result creation in integration."""
        integration = QAIntegration()
        
        error_result = integration._create_error_result("Test error message")
        
        assert error_result.grade == 0
        assert error_result.summary == "Assessment: QA Failed"
        assert error_result.needs_attention == True
        assert error_result.error_message == "Test error message"
    
    def test_qa_options_configuration(self):
        """Test QA options configuration."""
        # Default options
        default_integration = QAIntegration()
        assert default_integration.options.enabled == True
        assert default_integration.options.save_detailed == True
        
        # Custom options
        custom_options = QAOptions(
            enabled=False,
            save_detailed=False,
            model="custom-model"
        )
        custom_integration = QAIntegration(custom_options)
        assert custom_integration.options.enabled == False
        assert custom_integration.options.save_detailed == False
        assert custom_integration.analyzer.model_name == "custom-model"


class TestErrorHandlingScenarios:
    """Unit tests for various error handling scenarios."""
    
    def test_ai_client_unavailable(self):
        """Test handling when AI client is not available."""
        analyzer = SimpleQAAnalyzer()
        analyzer.ai_client = None  # Simulate unavailable client
        
        test_report = ReportContent(
            company_name="No Client Corp",
            content="Test content",
            sections={"Analysis": "Test"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="No Client Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        result = analyzer.assess_report(test_report)
        
        assert isinstance(result, SimpleQAResult)
        assert result.parsing_success == False
        assert result.error_message == "AI client not available"
        assert "configuration issue" in result.recommendation.lower()
    
    def test_quota_exhausted_handling(self):
        """Test handling of API quota exhaustion."""
        analyzer = SimpleQAAnalyzer()
        
        test_report = ReportContent(
            company_name="Quota Corp",
            content="Test content",
            sections={"Analysis": "Test"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Quota Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.side_effect = Exception("Daily quota exceeded")
            
            result = analyzer.assess_report(test_report)
            
            assert isinstance(result, SimpleQAResult)
            assert result.parsing_success == False
            assert "quota exhausted" in result.recommendation.lower()
            assert "upgrade plan" in result.recommendation.lower()
    
    def test_network_timeout_handling(self):
        """Test handling of network timeouts."""
        analyzer = SimpleQAAnalyzer()
        
        test_report = ReportContent(
            company_name="Timeout Corp",
            content="Test content",
            sections={"Analysis": "Test"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Timeout Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        with patch.object(analyzer, 'ai_client') as mock_client:
            with patch('time.sleep'):  # Mock sleep to speed up test
                mock_client.generate.side_effect = Exception("Network timeout")
                
                result = analyzer.assess_report(test_report)
                
                assert isinstance(result, SimpleQAResult)
                assert result.parsing_success == False
                assert "technical issue" in result.recommendation.lower()
                # Should have attempted retries
                assert mock_client.generate.call_count > 1
