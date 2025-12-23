"""
Core QA analyzer using AI model for quality assessment.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List

from .models import (
    QAAnalysis, ClassifiedIssue, CitationCheckResult, LogicCheckResult,
    CompletenessCheckResult, ConfidenceAssessment, ReportContent,
    IssueType, Severity
)
from .issue_classifier import IssueClassifier
from .error_handler import (
    QAModelError, QAAnalysisError, QARetryHandler, QAErrorHandler,
    with_retry, safe_qa_operation
)

logger = logging.getLogger(__name__)


class QAAnalyzer:
    """Performs quality analysis on reports using AI model."""
    
    def __init__(self, model_name: str = "gemini-2.0-flash-thinking-exp"):
        """Initialize with QA model configuration."""
        self.model_name = model_name
        self.issue_classifier = IssueClassifier()
        self.retry_handler = QARetryHandler(max_retries=3, base_delay=2.0)
        self.error_handler = QAErrorHandler()
        self._setup_ai_client()
    
    def _setup_ai_client(self):
        """Setup AI client for QA analysis."""
        try:
            # Import Primr's AI utilities
            from ..ai.client import get_client
            
            self.ai_client = get_client()
            logger.info(f"QA analyzer initialized with model: {self.model_name}")
            
        except Exception as e:
            error_msg = self.error_handler.handle_model_error(e, self.model_name)
            logger.error(f"Failed to setup AI client for QA: {error_msg}")
            self.ai_client = None
    
    @safe_qa_operation("QA Analysis")
    def analyze_report(self, report: ReportContent) -> QAAnalysis:
        """
        Perform comprehensive quality analysis.
        
        Args:
            report: Report content to analyze
            
        Returns:
            QAAnalysis with scores and issues
        """
        if not self.ai_client:
            logger.warning("AI client not available, using fallback analysis")
            return self._create_fallback_analysis(report)
        
        try:
            logger.info(f"Starting QA analysis for {report.company_name}")
            
            # Use retry logic for AI analysis
            def perform_analysis():
                # Create structured prompt for QA analysis
                prompt = self._build_qa_prompt(report)
                
                # Get AI analysis with timeout and retry
                response = self.ai_client.generate(prompt)
                
                if not response or len(response.strip()) < 50:
                    raise QAAnalysisError("AI response was empty or too short")
                
                return response
            
            # Execute with retry logic for rate limits and transient errors
            response = self.retry_handler.retry_with_backoff(
                perform_analysis,
                retryable_exceptions=(QAModelError, ConnectionError, TimeoutError),
                operation_name=f"QA analysis for {report.company_name}"
            )
            
            # Parse AI response into structured analysis
            analysis = self._parse_ai_response(response, report)
            
            # Apply issue classification and scoring
            analysis = self.issue_classifier.ensure_score_consistency(analysis)
            
            logger.info(f"QA analysis completed for {report.company_name}")
            return analysis
            
        except Exception as e:
            error_msg = self.error_handler.handle_analysis_error(e, report.company_name)
            logger.error(f"QA analysis failed: {error_msg}")
            return self._create_fallback_analysis(report)
    
    def _build_qa_prompt(self, report: ReportContent) -> str:
        """Build structured prompt for QA analysis."""
        
        # Dynamically determine report type and expected sections
        report_type = self._identify_report_type(report)
        expected_sections = self._get_expected_sections(report_type, report.sections.keys())
        
        prompt = f"""You are a quality assurance analyst reviewing a {report_type} report for {report.company_name}.

ANALYSIS FRAMEWORK:
Evaluate this report across four critical dimensions:

1. CITATION ACCURACY
   - Are claims properly attributed to sources?
   - Are citation formats consistent?
   - Are quantitative claims appropriately qualified (estimates vs confirmed data)?
   - Note: You cannot verify external links or source validity - focus on attribution patterns

2. LOGICAL CONSISTENCY  
   - Are there internal contradictions within the report?
   - Do conclusions follow logically from evidence presented?
   - Are analytical leaps properly supported by reasoning?
   - Are assumptions clearly stated?

3. COMPLETENESS
   - Are all expected sections for a {report_type} present?
   - Is analysis depth appropriate for each section?
   - Are key topics adequately covered for the report type?

4. FACTUAL ACCURACY
   - Are quantitative claims properly qualified (estimates vs confirmed)?
   - Are statements appropriately hedged for uncertainty?
   - Are there obvious factual inconsistencies within the report?
   - Note: Focus on internal consistency rather than external fact-checking

QUALITY STANDARDS:
- Excellent (90-100): Comprehensive, well-structured, logically sound
- Good (80-89): Solid analysis with minor gaps or inconsistencies
- Acceptable (70-79): Adequate but could benefit from improvements
- Needs Work (60-69): Significant issues that affect credibility
- Poor (0-59): Major structural or logical flaws

IMPORTANT: Be realistic about limitations. You cannot:
- Verify external links or source validity
- Fact-check against external databases
- Assess real-world accuracy of claims
Focus on internal consistency, logical structure, and appropriate qualification of claims.

Provide your analysis in this JSON format:
{{
    "overall_score": 85,
    "section_scores": {{{self._format_section_scores_template(report.sections.keys())}}},
    "citation_check": {{
        "total_citations": {len(report.citations)},
        "valid_citations": {len(report.citations)},
        "broken_links": [],
        "unsupported_claims": [],
        "score": 85
    }},
    "logic_check": {{
        "contradictions_found": [],
        "unsupported_leaps": [],
        "score": 85
    }},
    "completeness_check": {{
        "expected_sections": {expected_sections},
        "missing_sections": [],
        "weak_sections": [],
        "score": 85
    }},
    "issues": [],
    "confidence_assessment": {{
        "section_confidence": {{{self._format_section_scores_template(report.sections.keys())}}},
        "overall_confidence": 85
    }}
}}

REPORT CONTENT:
{report.content}

Provide only the JSON response, no additional text."""

        return prompt
    
    def _identify_report_type(self, report: ReportContent) -> str:
        """Identify the type of report based on content and sections."""
        content_lower = report.content.lower()
        sections_lower = [s.lower() for s in report.sections.keys()]
        
        # Check for AI strategy indicators
        if any(term in content_lower for term in ['ai strategy', 'artificial intelligence', 'machine learning', 'automation roadmap']):
            return "AI Strategy"
        
        # Check for general strategy indicators
        if any(term in content_lower for term in ['strategic overview', 'strategic analysis', 'strategy']):
            return "Strategic Analysis"
        
        # Check for company overview indicators
        if any(term in content_lower for term in ['company overview', 'company profile', 'business overview']):
            return "Company Overview"
        
        # Check for financial analysis
        if any(term in content_lower for term in ['financial analysis', 'financial overview', 'earnings', 'revenue']):
            return "Financial Analysis"
        
        # Check for market research
        if any(term in content_lower for term in ['market analysis', 'market research', 'industry analysis']):
            return "Market Research"
        
        # Default fallback
        return "Business Intelligence Report"
    
    def _get_expected_sections(self, report_type: str, existing_sections: list) -> list:
        """Get expected sections based on report type."""
        
        base_sections = ["Executive Summary", "Introduction", "Conclusion"]
        
        type_specific_sections = {
            "AI Strategy": [
                "Current State Assessment", "AI Opportunities", "Implementation Roadmap", 
                "Risk Assessment", "Resource Requirements", "Success Metrics"
            ],
            "Strategic Analysis": [
                "Market Position", "Competitive Landscape", "SWOT Analysis", 
                "Strategic Recommendations", "Risk Factors"
            ],
            "Company Overview": [
                "Business Model", "Products and Services", "Financial Performance", 
                "Market Position", "Leadership Team", "Recent Developments"
            ],
            "Financial Analysis": [
                "Revenue Analysis", "Profitability", "Cash Flow", "Balance Sheet", 
                "Financial Ratios", "Outlook"
            ],
            "Market Research": [
                "Market Size", "Growth Trends", "Competitive Analysis", 
                "Customer Segments", "Market Drivers", "Challenges"
            ]
        }
        
        expected = base_sections + type_specific_sections.get(report_type, [])
        
        # Add any major sections that exist but weren't in our template
        for section in existing_sections:
            if len(section) > 5 and section not in expected:  # Avoid very short section names
                expected.append(section)
        
        return expected[:10]  # Limit to reasonable number
    
    def _format_section_scores_template(self, sections: list) -> str:
        """Format section scores template for JSON."""
        # Take first few sections as examples
        sample_sections = list(sections)[:5]
        template_parts = []
        
        for section in sample_sections:
            # Clean section name for JSON
            clean_name = section.replace('"', '\\"')
            template_parts.append(f'"{clean_name}": 0')
        
        return ', '.join(template_parts)
    
    def _parse_ai_response(self, response: str, report: ReportContent) -> QAAnalysis:
        """Parse AI response into structured QA analysis."""
        try:
            logger.debug(f"Raw AI response: {response[:500]}...")
            
            # The response might be wrapped in markdown code blocks
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                if json_end != -1:
                    json_str = response[json_start:json_end].strip()
                else:
                    json_str = response[json_start:].strip()
            else:
                # Extract JSON from response
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                
                if json_start == -1 or json_end == 0:
                    logger.warning("No JSON found in AI response, using fallback")
                    return self._create_fallback_analysis(report)
                
                json_str = response[json_start:json_end]
            
            logger.debug(f"Extracted JSON: {json_str[:200]}...")
            data = json.loads(json_str)
            
            # Parse issues
            issues = []
            for issue_data in data.get('issues', []):
                try:
                    issue = ClassifiedIssue(
                        issue_type=IssueType(issue_data['issue_type']),
                        severity=Severity(issue_data['severity']),
                        section=issue_data['section'],
                        description=issue_data['description'],
                        location=issue_data['location'],
                        suggestion=issue_data.get('suggestion')
                    )
                    issues.append(issue)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse issue: {e}, issue_data: {issue_data}")
                    continue
            
            # Create analysis object with safe defaults
            analysis = QAAnalysis(
                overall_score=data.get('overall_score', 50),
                section_scores=data.get('section_scores', {}),
                issues=issues,
                citation_check=CitationCheckResult(
                    total_citations=data.get('citation_check', {}).get('total_citations', len(report.citations)),
                    valid_citations=data.get('citation_check', {}).get('valid_citations', 0),
                    broken_links=data.get('citation_check', {}).get('broken_links', []),
                    unsupported_claims=data.get('citation_check', {}).get('unsupported_claims', []),
                    score=data.get('citation_check', {}).get('score', 50)
                ),
                logic_check=LogicCheckResult(
                    contradictions_found=data.get('logic_check', {}).get('contradictions_found', []),
                    unsupported_leaps=data.get('logic_check', {}).get('unsupported_leaps', []),
                    score=data.get('logic_check', {}).get('score', 50)
                ),
                completeness_check=CompletenessCheckResult(
                    expected_sections=data.get('completeness_check', {}).get('expected_sections', []),
                    missing_sections=data.get('completeness_check', {}).get('missing_sections', []),
                    weak_sections=data.get('completeness_check', {}).get('weak_sections', []),
                    score=data.get('completeness_check', {}).get('score', 50)
                ),
                confidence_assessment=ConfidenceAssessment(
                    section_confidence=data.get('confidence_assessment', {}).get('section_confidence', {}),
                    overall_confidence=data.get('confidence_assessment', {}).get('overall_confidence', 50)
                ),
                timestamp=datetime.now(),
                model_used=self.model_name
            )
            
            return analysis
            
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
            logger.error(f"Failed to parse AI response: {e}")
            logger.debug(f"Problematic response: {response}")
            return self._create_fallback_analysis(report)
    
    def _create_fallback_analysis(self, report: ReportContent) -> QAAnalysis:
        """Create a basic fallback analysis when AI analysis fails."""
        logger.warning("Creating fallback QA analysis")
        
        return QAAnalysis(
            overall_score=50,  # Neutral score when analysis fails
            section_scores={},
            issues=[
                ClassifiedIssue(
                    issue_type=IssueType.FACTUAL,
                    severity=Severity.HIGH,
                    section="QA System",
                    description="Quality analysis could not be completed due to technical issues",
                    location="QA System",
                    suggestion="Retry QA analysis or check system configuration"
                )
            ],
            citation_check=CitationCheckResult(
                total_citations=len(report.citations),
                valid_citations=0,
                broken_links=[],
                unsupported_claims=[],
                score=50
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[],
                unsupported_leaps=[],
                score=50
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=list(report.sections.keys()),
                missing_sections=[],
                weak_sections=[],
                score=50
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={},
                overall_confidence=50
            ),
            timestamp=datetime.now(),
            model_used=self.model_name
        )