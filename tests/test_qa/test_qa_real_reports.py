"""
Tests with realistic report content to validate QA improvements.

This module tests the enhanced QA system with realistic report content
to ensure it provides meaningful feedback instead of generic fallbacks.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.primr.qa.integration import QAIntegration
from src.primr.qa.models import QAOptions, ReportContent, ReportMetadata
from src.primr.qa.simple_analyzer import SimpleQAAnalyzer, SimpleQAResult


class TestRealReportValidation:
    """Test QA system with realistic report content."""

    def test_evertrue_llc_style_comprehensive_report(self):
        """
        Test with a comprehensive strategic analysis similar to the Evertrue LLC case
        mentioned in the requirements. This validates the system can handle real-world
        comprehensive reports without falling back to generic responses.
        """
        # Create realistic comprehensive report content
        evertrue_content = """
# Evertrue LLC - Strategic Analysis

## Executive Summary

Evertrue LLC operates as a leading provider of alumni engagement technology solutions, serving higher education institutions across North America. The company has demonstrated strong market positioning with a 23% year-over-year revenue growth and expanding client base of 150+ institutions.

Key findings suggest Evertrue maintains competitive advantages through its integrated platform approach, combining donor management, event coordination, and analytics capabilities. However, the analysis reveals potential vulnerabilities in international expansion and dependency on the higher education sector.

## Market Analysis

The alumni engagement technology market represents a $2.1B total addressable market, with projected CAGR of 12% through 2027. Key growth drivers include:

- Increasing digitization of alumni relations
- Growing emphasis on donor retention and lifetime value
- Integration demands for comprehensive CRM solutions
- Rising importance of data analytics in fundraising

Market segmentation shows higher education institutions (65% market share) leading adoption, followed by corporate alumni programs (25%) and non-profit organizations (10%).

## Competitive Landscape

Evertrue competes in a fragmented market with several key players:

**Direct Competitors:**
- Blackbaud (market leader, 35% share)
- Salesforce Nonprofit Cloud (25% share)
- DonorPerfect (15% share)

**Emerging Threats:**
- Specialized analytics providers (Tableau, Power BI integrations)
- CRM generalists expanding into nonprofit space
- New entrants focusing on mobile-first experiences

Competitive analysis reveals Evertrue's differentiation through user experience design and higher education specialization, though this creates both strength and vulnerability.

## SWOT Analysis

**Strengths:**
- Strong product-market fit in higher education segment
- Established client relationships with high retention rates (92%)
- Innovative technology platform with modern architecture
- Experienced leadership team with domain expertise

**Weaknesses:**
- Limited international presence (5% of revenue)
- High dependency on higher education sector
- Smaller scale compared to market leaders
- Limited marketing budget constraining growth

**Opportunities:**
- Corporate alumni program expansion
- International market entry (Europe, Asia-Pacific)
- AI-driven insights and predictive analytics
- Strategic partnerships with complementary providers

**Threats:**
- Economic downturns affecting education budgets
- Increased competition from well-funded entrants
- Technology disruption from mobile-native solutions
- Regulatory changes in data privacy (GDPR, CCPA)

## Financial Overview

Financial analysis based on available data and industry benchmarks:

**Revenue Metrics:**
- Annual recurring revenue: $12-15M (estimated)
- Revenue growth: 23% YoY
- Client retention rate: 92%
- Average contract value: $80-120K annually

**Unit Economics:**
- Customer acquisition cost: $15-25K
- Lifetime value: $400-600K
- LTV/CAC ratio: 20-30x (strong)
- Gross margins: 75-80% (typical for SaaS)

**Profitability:**
- EBITDA margins estimated at 15-20%
- Path to profitability demonstrated
- Cash flow positive operations

## Value Chain Analysis

**Primary Activities:**
- Software development and platform maintenance
- Client onboarding and implementation services
- Customer success and support operations
- Sales and marketing activities

**Support Activities:**
- Technology infrastructure and security
- Human resources and talent acquisition
- Financial management and reporting
- Strategic partnerships and business development

**Key Value Drivers:**
- Platform reliability and uptime (99.9% SLA)
- User experience and interface design
- Data integration capabilities
- Customer success outcomes

## Strategic Recommendations

Based on comprehensive analysis, recommend the following strategic priorities:

1. **International Expansion:** Establish European operations within 18 months, targeting UK and Germany initially
2. **Product Diversification:** Develop corporate alumni solutions to reduce higher education dependency
3. **Technology Investment:** Enhance AI/ML capabilities for predictive analytics and personalization
4. **Strategic Partnerships:** Explore integration partnerships with major CRM providers
5. **Market Position:** Maintain focus on user experience differentiation while scaling operations

## Risk Assessment

**High Priority Risks:**
- Economic recession impacting education budgets
- Major competitor acquiring key technology or talent
- Data security breach affecting client trust

**Medium Priority Risks:**
- Key personnel departure
- Technology platform scalability challenges
- Regulatory compliance requirements

**Mitigation Strategies:**
- Diversify client base across sectors
- Invest in cybersecurity and compliance
- Develop succession planning for key roles
- Maintain technology debt management

## Conclusion

Evertrue LLC demonstrates strong fundamentals with clear growth trajectory in the alumni engagement technology market. The company's focus on higher education provides both competitive advantage and strategic risk. Recommended strategic initiatives focus on diversification and international expansion while maintaining core market leadership.

The analysis suggests Evertrue is well-positioned for continued growth, with particular strength in product-market fit and client relationships. However, success will depend on execution of diversification strategies and ability to scale operations effectively.
        """

        # Create comprehensive report structure
        evertrue_report = ReportContent(
            company_name="Evertrue LLC",
            content=evertrue_content,
            sections={
                "Executive Summary": evertrue_content[evertrue_content.find("## Executive Summary"):evertrue_content.find("## Market Analysis")],
                "Market Analysis": evertrue_content[evertrue_content.find("## Market Analysis"):evertrue_content.find("## Competitive Landscape")],
                "Competitive Landscape": evertrue_content[evertrue_content.find("## Competitive Landscape"):evertrue_content.find("## SWOT Analysis")],
                "SWOT Analysis": evertrue_content[evertrue_content.find("## SWOT Analysis"):evertrue_content.find("## Financial Overview")],
                "Financial Overview": evertrue_content[evertrue_content.find("## Financial Overview"):evertrue_content.find("## Value Chain Analysis")],
                "Value Chain Analysis": evertrue_content[evertrue_content.find("## Value Chain Analysis"):evertrue_content.find("## Strategic Recommendations")],
                "Strategic Recommendations": evertrue_content[evertrue_content.find("## Strategic Recommendations"):evertrue_content.find("## Risk Assessment")],
                "Risk Assessment": evertrue_content[evertrue_content.find("## Risk Assessment"):evertrue_content.find("## Conclusion")],
                "Conclusion": evertrue_content[evertrue_content.find("## Conclusion"):]
            },
            citations=[
                "Higher Education Marketing Report 2024",
                "Alumni Engagement Technology Market Analysis",
                "Blackbaud Annual Report 2023",
                "Salesforce Nonprofit Trends Report",
                "Education Technology Investment Report",
                "CASE Alumni Relations Survey 2024",
                "TechCrunch Funding Database",
                "Crunchbase Company Profiles",
                "LinkedIn Company Analytics",
                "Industry Expert Interviews"
            ],
            metadata=ReportMetadata(
                company_name="Evertrue LLC",
                generation_date=datetime.now(),
                generation_mode="full",
                model_used="gemini-3-flash-preview",
                file_path=Path("evertrue_comprehensive_analysis.txt")
            ),
            file_path=Path("evertrue_comprehensive_analysis.txt")
        )

        # Test with the enhanced QA analyzer
        analyzer = SimpleQAAnalyzer()

        # Mock a realistic high-quality assessment response
        mock_response = """{
            "ready_for_use": true,
            "confidence_level": "high",
            "key_strengths": [
                "Comprehensive strategic framework covering market, competitive, financial, and operational dimensions",
                "Strong evidentiary base with 10+ credible sources including industry reports and expert interviews",
                "SWOT analysis demonstrates rigorous application of strategic frameworks with specific examples",
                "Financial analysis includes appropriate precision with ranges for estimates and specific metrics",
                "Value chain analysis provides actionable operational insights with clear value drivers",
                "Strategic recommendations are hypothesis-driven and tied to analytical findings",
                "Risk assessment includes both identification and mitigation strategies"
            ],
            "areas_for_improvement": [
                "International market analysis could include more specific regulatory considerations",
                "Competitive threat assessment could expand on emerging technology disruptions",
                "Financial projections could benefit from sensitivity analysis scenarios"
            ],
            "recommendation": "This comprehensive strategic analysis exceeds Primr standards for internal research use. The report demonstrates exceptional analytical rigor, appropriate use of strategic frameworks, and provides highly actionable insights for strategic decision-making. The hypothesis-driven approach and comprehensive evidence base make this suitable for high-stakes internal planning discussions."
        }"""

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = mock_response

            result = analyzer.assess_report(evertrue_report)

            # Validate that comprehensive reports receive proper assessment
            assert isinstance(result, SimpleQAResult)
            assert result.parsing_success, "Should successfully parse comprehensive report"
            assert result.error_message is None, "Should not have errors for well-structured report"
            assert result.confidence_level == "high", "Should have high confidence for comprehensive analysis"
            assert result.ready_for_use, "Should indicate readiness for comprehensive report"

            # Validate quality of feedback
            assert len(result.key_strengths) >= 5, "Should identify multiple strengths in comprehensive report"
            assert len(result.areas_for_improvement) >= 2, "Should provide specific improvement areas"
            assert len(result.recommendation) > 100, "Should provide detailed recommendation"

            # Should not contain generic fallback language
            fallback_phrases = ["generic", "technical issue", "manual review recommended", "parsing issues"]
            recommendation_lower = result.recommendation.lower()
            assert not any(phrase in recommendation_lower for phrase in fallback_phrases), \
                f"Should not use fallback language: {result.recommendation}"

            # Should reference Primr standards
            assert "primr" in result.recommendation.lower(), "Should reference Primr standards"

    def test_integration_with_realistic_report(self):
        """
        Test the full QA integration pipeline with realistic report content
        to ensure end-to-end functionality works as expected.
        """
        # Create a realistic but shorter report for integration testing
        integration_content = """
# TechCorp Strategic Analysis

## Executive Summary
TechCorp demonstrates strong market positioning in the enterprise software sector with 15% YoY growth.

## Market Analysis
The enterprise software market shows continued expansion with cloud adoption driving growth.

## Financial Overview
Revenue of $50M with 80% gross margins indicates healthy unit economics.

## Recommendations
Focus on international expansion while maintaining product innovation leadership.
        """

        # Create temporary report file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(integration_content)
            report_path = Path(f.name)

        try:
            # Test QA integration
            qa_options = QAOptions(enabled=True, save_detailed=False)
            qa_integration = QAIntegration(qa_options)

            # Mock the analyzer to return realistic assessment
            mock_qa_result = SimpleQAResult(
                ready_for_use=True,
                confidence_level="medium",
                key_strengths=[
                    "Clear executive summary with key metrics",
                    "Market analysis provides relevant context",
                    "Financial metrics demonstrate healthy business model"
                ],
                areas_for_improvement=[
                    "Competitive analysis section could be expanded",
                    "Risk assessment would strengthen the analysis"
                ],
                recommendation="Report provides solid foundation for strategic planning with minor enhancements needed",
                parsing_success=True
            )

            with patch.object(qa_integration.analyzer, 'assess_report', return_value=mock_qa_result):
                qa_result = qa_integration.run_post_generation_qa(report_path, "TechCorp")

                # Validate integration results
                assert qa_result is not None, "Should return QA result"
                assert isinstance(qa_result.grade, int), "Should have numerical grade"
                assert 0 <= qa_result.grade <= 100, "Grade should be in valid range"
                assert "Grade:" in qa_result.summary, "Summary should include grade"
                assert not qa_result.needs_attention, "Should not need attention for good report"

                # Validate CLI summary format matches README promise
                assert "Grade: " in qa_result.summary, "Should show grade as promised in README"
                assert "/100" in qa_result.summary, "Should show grade out of 100"

        finally:
            # Clean up temporary file
            report_path.unlink(missing_ok=True)

    def test_error_case_handling(self):
        """
        Test that error cases provide diagnostic information instead of generic fallbacks.
        """
        analyzer = SimpleQAAnalyzer()

        # Create minimal report for error testing
        error_test_report = ReportContent(
            company_name="Error Test Corp",
            content="Minimal content for error testing.",
            sections={"Summary": "Brief summary"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Error Test Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("error_test.txt")
            ),
            file_path=Path("error_test.txt")
        )

        # Test rate limit error handling
        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.side_effect = Exception("Rate limit exceeded (429)")

            result = analyzer.assess_report(error_test_report)

            # Should provide diagnostic information
            assert isinstance(result, SimpleQAResult)
            assert not result.parsing_success
            assert result.error_message is not None
            assert "rate limit" in result.recommendation.lower()
            # Message may say "try again" or "retry later"
            assert "try again" in result.recommendation.lower() or "retry" in result.recommendation.lower()
            assert len(result.areas_for_improvement) > 0, "Should provide diagnostic info"

    def test_malformed_response_handling(self):
        """
        Test that malformed AI responses are handled gracefully with meaningful fallbacks.
        """
        analyzer = SimpleQAAnalyzer()

        test_report = ReportContent(
            company_name="Malformed Test Corp",
            content="Content for malformed response testing.",
            sections={"Analysis": "Test analysis"},
            citations=["Source 1"],
            metadata=ReportMetadata(
                company_name="Malformed Test Corp",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("malformed_test.txt")
            ),
            file_path=Path("malformed_test.txt")
        )

        # Test with malformed JSON response
        malformed_response = """
        This report demonstrates good strategic thinking and analysis.
        The citations are well-formatted and the framework application is solid.
        However, some areas could use more depth.
        Ready for use: true, confidence level: medium
        Strengths include clear structure and good evidence base.
        """

        with patch.object(analyzer, 'ai_client') as mock_client:
            mock_client.generate.return_value = malformed_response

            result = analyzer.assess_report(test_report)

            # Should handle malformed response gracefully
            assert isinstance(result, SimpleQAResult)
            assert not result.parsing_success, "Should indicate parsing failure"
            # Malformed responses may not extract feedback - the fallback returns empty lists
            # The key is that it doesn't crash and provides a recommendation
            assert result.recommendation, "Should provide recommendation"
            assert len(result.recommendation) > 10, "Should provide some recommendation"

    def test_grade_calculation_accuracy(self):
        """
        Test that numerical grade calculation produces reasonable scores
        based on assessment quality indicators.
        """
        from src.primr.qa.integration import QAIntegration

        qa_integration = QAIntegration()

        # Test high-quality assessment
        high_quality_result = SimpleQAResult(
            ready_for_use=True,
            confidence_level="high",
            key_strengths=["Excellent analysis", "Strong evidence", "Clear recommendations"],
            areas_for_improvement=["Minor formatting issue"],
            recommendation="Excellent report ready for use",
            parsing_success=True
        )

        high_grade = qa_integration._calculate_numerical_grade(high_quality_result)
        assert 80 <= high_grade <= 100, f"High quality should get 80-100, got {high_grade}"

        # Test medium-quality assessment
        medium_quality_result = SimpleQAResult(
            ready_for_use=True,
            confidence_level="medium",
            key_strengths=["Good analysis", "Adequate evidence"],
            areas_for_improvement=["Needs more depth", "Citations could improve"],
            recommendation="Good report with minor improvements needed",
            parsing_success=True
        )

        medium_grade = qa_integration._calculate_numerical_grade(medium_quality_result)
        assert 65 <= medium_grade <= 80, f"Medium quality should get 65-80, got {medium_grade}"

        # Test low-quality assessment
        low_quality_result = SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=[],
            areas_for_improvement=["Major gaps", "Poor citations", "Unclear analysis"],
            recommendation="Significant improvements needed",
            parsing_success=True
        )

        low_grade = qa_integration._calculate_numerical_grade(low_quality_result)
        assert 25 <= low_grade <= 50, f"Low quality should get 25-50, got {low_grade}"
