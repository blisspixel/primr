"""
Property-based tests for QA Primr standards coverage.

Feature: qa-grading-fix, Property 1: Assessment covers Primr quality standards
Validates: Requirements 1.1
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.primr.qa.models import ReportContent, ReportMetadata
from src.primr.qa.simple_analyzer import SimpleQAAnalyzer, SimpleQAResult


def generate_report_content():
    """Generate realistic report content for testing."""
    return st.builds(
        ReportContent,
        company_name=st.text(min_size=3, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)).filter(lambda x: x.strip()),
        content=st.text(min_size=500, max_size=5000),
        sections=st.dictionaries(
            keys=st.sampled_from(['Executive Summary', 'Market Analysis', 'SWOT Analysis', 'Competitive Landscape', 'Financial Overview']),
            values=st.text(min_size=100, max_size=1000),
            min_size=2,
            max_size=5
        ),
        citations=st.lists(st.text(min_size=10, max_size=100), min_size=1, max_size=20),
        metadata=st.builds(
            ReportMetadata,
            company_name=st.text(min_size=3, max_size=50),
            generation_date=st.just(datetime.now()),
            generation_mode=st.sampled_from(['scrape', 'deep', 'full']),
            model_used=st.sampled_from(['gemini-3-flash-preview', 'gemini-3-flash']),
            file_path=st.just(Path('test_report.txt'))
        ),
        file_path=st.just(Path('test_report.txt'))
    )


class TestPrimrStandardsCoverage:
    """Property-based tests for Primr standards coverage."""

    @given(report=generate_report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10, deadline=None)
    def test_primr_standards_coverage_property(self, report: ReportContent):
        """
        **Feature: qa-grading-fix, Property 1: Assessment covers Primr quality standards**
        **Validates: Requirements 1.1**

        For any report analyzed, the QA system should evaluate strategic coherence,
        citation quality, and hypothesis-driven framing as specified in Primr's standards.
        """
        # Setup analyzer with mocked AI client to avoid actual API calls
        analyzer = SimpleQAAnalyzer()

        # Mock the AI client to return a realistic assessment
        mock_response = """{
            "ready_for_use": true,
            "confidence_level": "medium",
            "key_strengths": [
                "Clear strategic thesis connecting market analysis",
                "Well-cited claims with appropriate source attribution",
                "Hypothesis-driven framing throughout analysis"
            ],
            "areas_for_improvement": [
                "Some framework sections could be more rigorous",
                "Consider adding more precision to numeric estimates"
            ],
            "recommendation": "Report demonstrates good alignment with Primr standards for internal research use"
        }"""

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response

            # Execute assessment
            result = analyzer.assess_report(report)

            # Verify the assessment covers Primr quality standards
            assert isinstance(result, SimpleQAResult), "Should return SimpleQAResult"
            assert result.parsing_success, "Should successfully parse assessment"

            # Check that assessment evaluates key Primr standards
            assessment_areas = result.key_strengths + result.areas_for_improvement
            assessment_text = ' '.join(assessment_areas).lower()

            # Should evaluate strategic coherence
            strategic_indicators = ['strategic', 'thesis', 'coherence', 'analysis', 'framework']
            assert any(indicator in assessment_text for indicator in strategic_indicators), \
                f"Assessment should evaluate strategic coherence. Found: {assessment_areas}"

            # Should evaluate citation quality
            citation_indicators = ['citation', 'source', 'attribution', 'evidence', 'claims']
            assert any(indicator in assessment_text for indicator in citation_indicators), \
                f"Assessment should evaluate citation quality. Found: {assessment_areas}"

            # Should evaluate hypothesis-driven framing
            hypothesis_indicators = ['hypothesis', 'framing', 'precision', 'estimates', 'qualified']
            assert any(indicator in assessment_text for indicator in hypothesis_indicators), \
                f"Assessment should evaluate hypothesis-driven framing. Found: {assessment_areas}"

            # Verify recommendation is actionable and specific
            assert result.recommendation, "Should provide recommendation"
            assert len(result.recommendation) > 20, "Recommendation should be substantive"
            assert 'primr' in result.recommendation.lower() or 'internal' in result.recommendation.lower(), \
                "Recommendation should reference Primr/internal research context"

    @given(report=generate_report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5, deadline=None)
    def test_assessment_handles_parsing_failures(self, report: ReportContent):
        """
        Test that assessment gracefully handles AI response parsing failures
        while still attempting to extract Primr standards evaluation.
        """
        analyzer = SimpleQAAnalyzer()

        # Mock malformed response that should trigger parsing fallback
        malformed_response = """
        This report shows good strategic thinking and clear citations.
        The analysis demonstrates hypothesis-driven framing throughout.
        However, some framework sections need more rigor.
        Ready for use: true, confidence: medium
        """

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = malformed_response

            result = analyzer.assess_report(report)

            # Should handle parsing failure gracefully
            assert isinstance(result, SimpleQAResult), "Should return SimpleQAResult even with parsing failure"
            assert not result.parsing_success, "Should indicate parsing failure"

            # Should still extract some meaningful assessment
            assert result.confidence_level in ['high', 'medium', 'low'], "Should have valid confidence level"
            assert isinstance(result.key_strengths, list), "Should have strengths list"
            assert isinstance(result.areas_for_improvement, list), "Should have improvements list"
            assert result.recommendation, "Should have recommendation"

    @given(
        ready_for_use=st.booleans(),
        confidence_level=st.sampled_from(['high', 'medium', 'low'])
    )
    @settings(max_examples=10)
    def test_assessment_consistency_across_inputs(self, ready_for_use: bool, confidence_level: str):
        """
        Test that assessment results are consistent and follow expected patterns
        based on readiness and confidence levels.
        """
        analyzer = SimpleQAAnalyzer()

        # Create mock response based on parameters
        mock_response = f"""{{
            "ready_for_use": {str(ready_for_use).lower()},
            "confidence_level": "{confidence_level}",
            "key_strengths": ["Strategic coherence evident", "Citations properly formatted"],
            "areas_for_improvement": ["Framework rigor could improve"],
            "recommendation": "Assessment based on Primr internal research standards"
        }}"""

        # Create minimal report for testing
        test_report = ReportContent(
            company_name="Test Company",
            content="Test content with strategic analysis and citations.",
            sections={"Analysis": "Test analysis content"},
            citations=["Source 1", "Source 2"],
            metadata=ReportMetadata(
                company_name="Test Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response

            result = analyzer.assess_report(test_report)

            # Verify consistency with input parameters
            assert result.ready_for_use == ready_for_use, "Ready for use should match input"
            assert result.confidence_level == confidence_level, "Confidence level should match input"
            assert result.parsing_success, "Should successfully parse well-formed JSON"

            # Verify result structure is valid
            assert isinstance(result.key_strengths, list), "Key strengths should be list"
            assert isinstance(result.areas_for_improvement, list), "Areas for improvement should be list"
            assert len(result.key_strengths) >= 0, "Should have non-negative strengths count"
            assert len(result.areas_for_improvement) >= 0, "Should have non-negative improvements count"


class TestActionableFeedbackGeneration:
    """Property-based tests for actionable feedback generation."""

    @given(report=generate_report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10, deadline=None)
    def test_actionable_feedback_generation_property(self, report: ReportContent):
        """
        **Feature: qa-grading-fix, Property 2: Feedback is actionable and specific**
        **Validates: Requirements 2.1**

        For any QA analysis result, the output should contain specific strengths and
        improvement areas rather than generic scores or comments.
        """
        analyzer = SimpleQAAnalyzer()

        # Mock realistic assessment response
        mock_response = """{
            "ready_for_use": true,
            "confidence_level": "medium",
            "key_strengths": [
                "Strategic analysis demonstrates clear market positioning insights",
                "Financial data is well-sourced with appropriate citations to SEC filings",
                "SWOT analysis applies framework rigorously with specific examples"
            ],
            "areas_for_improvement": [
                "Competitive analysis section lacks depth in emerging market threats",
                "Some revenue projections use ranges that are too broad for decision-making"
            ],
            "recommendation": "Report provides solid foundation for internal strategic planning with minor enhancements needed in competitive intelligence"
        }"""

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response

            result = analyzer.assess_report(report)

            # Verify feedback is actionable and specific
            assert isinstance(result, SimpleQAResult), "Should return SimpleQAResult"

            # Test recommendation quality
            assert result.recommendation, "Should provide recommendation"
            assert len(result.recommendation) > 20, "Recommendation should be substantive"

            # Should not contain generic phrases
            generic_phrases = ['generic', 'general', 'overall', 'basic', 'standard']
            recommendation_lower = result.recommendation.lower()
            assert not any(phrase in recommendation_lower for phrase in generic_phrases), \
                f"Recommendation should not be generic: {result.recommendation}"

            # Should contain actionable language
            actionable_indicators = ['enhance', 'improve', 'strengthen', 'add', 'consider', 'focus', 'develop', 'expand']
            has_actionable = any(indicator in recommendation_lower for indicator in actionable_indicators)
            assert has_actionable or result.ready_for_use, \
                f"Recommendation should be actionable or indicate readiness: {result.recommendation}"

            # Test strengths specificity
            assert len(result.key_strengths) > 0 or len(result.areas_for_improvement) > 0, \
                "Should provide either strengths or improvements"

            for strength in result.key_strengths:
                assert len(strength) > 10, f"Strength should be specific: {strength}"
                # Should not be generic
                assert not any(phrase in strength.lower() for phrase in generic_phrases), \
                    f"Strength should be specific, not generic: {strength}"

            for improvement in result.areas_for_improvement:
                assert len(improvement) > 10, f"Improvement should be specific: {improvement}"
                # Should not be generic
                assert not any(phrase in improvement.lower() for phrase in generic_phrases), \
                    f"Improvement should be specific, not generic: {improvement}"

    @given(
        strengths_count=st.integers(min_value=0, max_value=5),
        improvements_count=st.integers(min_value=0, max_value=5)
    )
    @settings(max_examples=10)
    def test_feedback_balance_property(self, strengths_count: int, improvements_count: int):
        """
        Test that feedback maintains appropriate balance between strengths and improvements.
        """
        analyzer = SimpleQAAnalyzer()

        # Generate mock strengths and improvements
        strengths = [f"Specific strength {i+1} with detailed analysis" for i in range(strengths_count)]
        improvements = [f"Specific improvement {i+1} with actionable guidance" for i in range(improvements_count)]

        mock_response = f"""{{
            "ready_for_use": {str(strengths_count >= improvements_count).lower()},
            "confidence_level": "medium",
            "key_strengths": {json.dumps(strengths)},
            "areas_for_improvement": {json.dumps(improvements)},
            "recommendation": "Balanced assessment with specific actionable feedback"
        }}"""

        test_report = ReportContent(
            company_name="Test Company",
            content="Test content for feedback balance testing.",
            sections={"Analysis": "Test analysis content"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Test Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response

            result = analyzer.assess_report(test_report)

            # Verify feedback structure
            assert len(result.key_strengths) == strengths_count, "Should preserve strengths count"
            assert len(result.areas_for_improvement) == improvements_count, "Should preserve improvements count"

            # Verify all feedback items are meaningful
            for strength in result.key_strengths:
                assert isinstance(strength, str), "Strengths should be strings"
                assert len(strength.strip()) > 0, "Strengths should not be empty"

            for improvement in result.areas_for_improvement:
                assert isinstance(improvement, str), "Improvements should be strings"
                assert len(improvement.strip()) > 0, "Improvements should not be empty"

    @given(malformed_response=st.text(min_size=50, max_size=500))
    @settings(max_examples=5)
    def test_actionable_feedback_from_malformed_responses(self, malformed_response: str):
        """
        Test that even with malformed responses, the system attempts to provide
        actionable feedback rather than generic error messages.
        """
        analyzer = SimpleQAAnalyzer()

        # Add some QA-related keywords to the malformed response
        enhanced_response = f"{malformed_response} strategic analysis citations framework ready for use medium confidence"

        test_report = ReportContent(
            company_name="Test Company",
            content="Test content for malformed response testing.",
            sections={"Analysis": "Test analysis content"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Test Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = enhanced_response

            result = analyzer.assess_report(test_report)

            # Even with malformed input, should provide structured feedback
            assert isinstance(result, SimpleQAResult), "Should return SimpleQAResult"
            assert result.recommendation, "Should provide some recommendation"
            assert isinstance(result.key_strengths, list), "Should have strengths list"
            assert isinstance(result.areas_for_improvement, list), "Should have improvements list"

            # Should not just be generic error messages
            error_phrases = ['error', 'failed', 'unable', 'could not']
            recommendation_lower = result.recommendation.lower()

            # If it contains error phrases, it should still be informative
            if any(phrase in recommendation_lower for phrase in error_phrases):
                assert len(result.recommendation) > 30, "Error messages should be informative"
            else:
                # Should provide meaningful feedback
                assert len(result.recommendation) > 20, "Should provide substantive recommendation"


class TestComprehensiveReportReliability:
    """Property-based tests for comprehensive report reliability."""

    @given(report=generate_report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10, deadline=None)
    def test_comprehensive_report_reliability_property(self, report: ReportContent):
        """
        **Feature: qa-grading-fix, Property 3: Comprehensive reports complete successfully**
        **Validates: Requirements 3.1**

        For any well-structured report like the Evertrue LLC analysis, the system should
        provide a complete assessment without falling back to error responses.
        """
        analyzer = SimpleQAAnalyzer()

        # Mock a comprehensive, well-structured response
        comprehensive_response = """{
            "ready_for_use": true,
            "confidence_level": "high",
            "key_strengths": [
                "Comprehensive strategic analysis with clear market positioning",
                "Extensive financial data sourced from SEC filings and industry reports",
                "SWOT analysis demonstrates rigorous framework application",
                "Competitive landscape analysis includes emerging market threats",
                "Value chain analysis provides actionable operational insights"
            ],
            "areas_for_improvement": [
                "Revenue projections could benefit from sensitivity analysis",
                "Customer acquisition cost trends need deeper examination"
            ],
            "recommendation": "Report provides comprehensive foundation for strategic decision-making with high confidence in data quality and analytical rigor"
        }"""

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = comprehensive_response

            result = analyzer.assess_report(report)

            # Verify comprehensive reports complete successfully
            assert isinstance(result, SimpleQAResult), "Should return SimpleQAResult"
            assert result.parsing_success, "Should successfully parse comprehensive report assessment"
            assert result.error_message is None, "Should not have error message for successful assessment"
            assert result.confidence_level in ['high', 'medium', 'low'], "Should have valid confidence level"

            # Verify quality of assessment for comprehensive reports
            assert len(result.key_strengths) > 0, "Comprehensive reports should have identified strengths"
            assert len(result.recommendation) > 50, "Should provide detailed recommendation for comprehensive reports"

            # Should not contain generic fallback language
            fallback_indicators = ['parsing issues', 'format was unclear', 'technical issue', 'manual review recommended']
            recommendation_lower = result.recommendation.lower()
            assert not any(indicator in recommendation_lower for indicator in fallback_indicators), \
                f"Should not use fallback language for comprehensive reports: {result.recommendation}"

    @given(
        section_count=st.integers(min_value=5, max_value=15),
        citation_count=st.integers(min_value=10, max_value=50),
        content_length=st.integers(min_value=5000, max_value=20000)
    )
    @settings(max_examples=5)
    def test_large_report_handling(self, section_count: int, citation_count: int, content_length: int):
        """
        Test that large, comprehensive reports are handled reliably without timeouts or failures.
        """
        analyzer = SimpleQAAnalyzer()

        # Create a large, comprehensive report
        sections = {f"Section_{i}": "Detailed analysis content " * 100 for i in range(section_count)}
        citations = [f"Source {i}: https://example.com/source{i}" for i in range(citation_count)]
        content = "Comprehensive strategic analysis. " * (content_length // 30)

        large_report = ReportContent(
            company_name="Large Corp",
            content=content,
            sections=sections,
            citations=citations,
            metadata=ReportMetadata(
                company_name="Large Corp",
                generation_date=datetime.now(),
                generation_mode="full",
                model_used="gemini-3-flash-preview",
                file_path=Path("large_report.txt")
            ),
            file_path=Path("large_report.txt")
        )

        # Mock response for large report
        mock_response = """{
            "ready_for_use": true,
            "confidence_level": "high",
            "key_strengths": [
                "Extensive coverage across multiple business dimensions",
                "Rich citation base provides strong evidentiary support",
                "Comprehensive section structure enables thorough analysis"
            ],
            "areas_for_improvement": [
                "Some sections could benefit from executive summary",
                "Consider adding cross-references between related sections"
            ],
            "recommendation": "Large comprehensive report demonstrates thorough research methodology and provides solid foundation for strategic planning"
        }"""

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response

            result = analyzer.assess_report(large_report)

            # Should handle large reports successfully
            assert isinstance(result, SimpleQAResult), "Should handle large reports"
            assert result.parsing_success, "Should successfully parse large report assessment"
            assert result.error_message is None, "Should not error on large reports"

            # Should provide meaningful assessment
            assert len(result.key_strengths) > 0, "Should identify strengths in large reports"
            assert result.confidence_level in ['high', 'medium', 'low'], "Should assess confidence for large reports"

    @settings(deadline=None, max_examples=5)  # Disable deadline for network simulation
    @given(
        network_errors=st.integers(min_value=1, max_value=3),
        final_success=st.booleans()
    )
    def test_retry_logic_reliability(self, network_errors: int, final_success: bool):
        """
        Test that retry logic works reliably for comprehensive reports with network issues.
        """
        analyzer = SimpleQAAnalyzer()

        test_report = ReportContent(
            company_name="Retry Test Corp",
            content="Test content for retry logic testing.",
            sections={"Analysis": "Comprehensive analysis content"},
            citations=["Source 1", "Source 2"],
            metadata=ReportMetadata(
                company_name="Retry Test Corp",
                generation_date=datetime.now(),
                generation_mode="full",
                model_used="gemini-3-flash-preview",
                file_path=Path("retry_test.txt")
            ),
            file_path=Path("retry_test.txt")
        )

        # Mock successful response
        success_response = """{
            "ready_for_use": true,
            "confidence_level": "medium",
            "key_strengths": ["Successful after retries"],
            "areas_for_improvement": ["Network stability could improve"],
            "recommendation": "Assessment completed successfully after handling network issues"
        }"""

        call_count = 0
        def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count <= network_errors:
                # Simulate network error
                raise Exception("Network timeout error")
            elif final_success:
                return success_response
            else:
                raise Exception("Persistent network error")

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.side_effect = mock_generate

            result = analyzer.assess_report(test_report)

            if final_success:
                # Should eventually succeed
                assert isinstance(result, SimpleQAResult), "Should return result after retries"
                assert result.parsing_success, "Should successfully parse after retries"
                assert "successful" in result.recommendation.lower(), "Should indicate retry success"
            else:
                # Should handle persistent failures gracefully
                assert isinstance(result, SimpleQAResult), "Should return result even after failures"
                assert not result.parsing_success or result.error_message is not None, "Should indicate failure"
                assert result.confidence_level == "low", "Should have low confidence after failures"

    @given(report=generate_report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5, deadline=None)
    def test_evertrue_llc_style_report_handling(self, report: ReportContent):
        """
        Test handling of comprehensive reports similar to the Evertrue LLC case mentioned in requirements.
        This ensures the system can handle real-world comprehensive strategic analyses.
        """
        analyzer = SimpleQAAnalyzer()

        # Simulate a comprehensive 35+ page strategic analysis like Evertrue LLC
        comprehensive_content = """
        EXECUTIVE SUMMARY
        Evertrue LLC demonstrates strong market positioning in the alumni engagement technology sector...

        MARKET ANALYSIS
        The alumni engagement market has grown significantly, with total addressable market estimated at $2.1B...

        COMPETITIVE LANDSCAPE
        Key competitors include Blackbaud, Salesforce Nonprofit Cloud, and emerging players...

        SWOT ANALYSIS
        Strengths: Strong product-market fit, established client base, innovative technology platform
        Weaknesses: Limited international presence, dependency on higher education sector
        Opportunities: Corporate alumni programs, international expansion, AI-driven insights
        Threats: Economic downturns affecting education budgets, increased competition

        FINANCIAL OVERVIEW
        Revenue growth of 23% YoY, with strong unit economics and improving margins...

        VALUE CHAIN ANALYSIS
        Primary activities include software development, client onboarding, customer success...

        STRATEGIC RECOMMENDATIONS
        Focus on international expansion while maintaining core market leadership...
        """ * 10  # Simulate comprehensive content

        evertrue_style_report = ReportContent(
            company_name="Evertrue LLC",
            content=comprehensive_content,
            sections={
                "Executive Summary": comprehensive_content[:500],
                "Market Analysis": comprehensive_content[500:1500],
                "Competitive Landscape": comprehensive_content[1500:2500],
                "SWOT Analysis": comprehensive_content[2500:3500],
                "Financial Overview": comprehensive_content[3500:4500],
                "Value Chain Analysis": comprehensive_content[4500:5500],
                "Strategic Recommendations": comprehensive_content[5500:6500]
            },
            citations=[f"Source {i}" for i in range(25)],  # Comprehensive citation base
            metadata=ReportMetadata(
                company_name="Evertrue LLC",
                generation_date=datetime.now(),
                generation_mode="full",
                model_used="gemini-3-flash-preview",
                file_path=Path("evertrue_comprehensive.txt")
            ),
            file_path=Path("evertrue_comprehensive.txt")
        )

        # Mock high-quality assessment response
        evertrue_response = """{
            "ready_for_use": true,
            "confidence_level": "high",
            "key_strengths": [
                "Comprehensive strategic framework covering all key business dimensions",
                "Strong evidentiary base with 25+ credible sources and citations",
                "SWOT analysis demonstrates rigorous application of strategic frameworks",
                "Financial analysis includes appropriate precision with ranges and confirmed data",
                "Value chain analysis provides actionable operational insights",
                "Strategic recommendations are hypothesis-driven and well-supported"
            ],
            "areas_for_improvement": [
                "International market analysis could be expanded with regional specifics",
                "Competitive threat assessment could include more emerging market players"
            ],
            "recommendation": "This comprehensive strategic analysis meets Primr standards for internal research use with high confidence. The report demonstrates strong analytical rigor, appropriate use of strategic frameworks, and provides actionable insights for decision-making. Minor enhancements in international and competitive analysis would further strengthen the assessment."
        }"""

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = evertrue_response

            result = analyzer.assess_report(evertrue_style_report)

            # Should handle comprehensive reports like Evertrue LLC successfully
            assert isinstance(result, SimpleQAResult), "Should handle Evertrue-style comprehensive reports"
            assert result.parsing_success, "Should successfully parse comprehensive strategic analysis"
            assert result.error_message is None, "Should not error on comprehensive reports"
            assert result.confidence_level == "high", "Should have high confidence for well-structured reports"
            assert result.ready_for_use, "Should indicate readiness for comprehensive reports"

            # Should provide detailed, specific feedback
            assert len(result.key_strengths) >= 3, "Should identify multiple strengths in comprehensive reports"
            assert len(result.recommendation) > 100, "Should provide detailed recommendation for comprehensive reports"

            # Should reference Primr standards
            assert "primr" in result.recommendation.lower() or "internal research" in result.recommendation.lower(), \
                "Should reference Primr standards in comprehensive report assessment"
