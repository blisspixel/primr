"""
Simplified QA analyzer focused on practical assessment: "Is this report ready for internal use?"
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass

from .models import ReportContent
from .error_handler import QAErrorHandler, safe_qa_operation
from .json_parser import SimpleJSONParser
from ..config.models import PrimrModels

logger = logging.getLogger(__name__)


@dataclass
class SimpleQAResult:
    """Simple QA result focused on practical assessment."""
    ready_for_use: bool
    confidence_level: Literal["high", "medium", "low"]
    key_strengths: List[str]
    areas_for_improvement: List[str]
    recommendation: str
    parsing_success: bool = True
    error_message: Optional[str] = None


class SimpleQAAnalyzer:
    """Simplified QA analyzer for practical report assessment."""
    
    def __init__(self, model_name: str = PrimrModels.QA_MODEL):
        """Initialize with QA model configuration."""
        self.model_name = model_name
        self.fallback_model = PrimrModels.get_fallback_models(model_name)[0] if PrimrModels.get_fallback_models(model_name) else PrimrModels.REASONING_MODEL
        self.error_handler = QAErrorHandler()
        self.json_parser = SimpleJSONParser()
        self._setup_ai_client()
    
    def _setup_ai_client(self):
        """Setup AI client for QA analysis."""
        try:
            from ..ai.client import get_client
            self.ai_client = get_client()
            logger.info(f"Simple QA analyzer initialized with model: {self.model_name}")
        except Exception as e:
            error_msg = self.error_handler.handle_model_error(e, self.model_name)
            logger.error(f"Failed to setup AI client for QA: {error_msg}")
            self.ai_client = None
    
    @safe_qa_operation("Simple QA Assessment")
    def assess_report(self, report: ReportContent) -> SimpleQAResult:
        """
        Assess if report is ready for internal use.
        
        Args:
            report: Report content to assess
            
        Returns:
            SimpleQAResult with practical assessment
        """
        if not self.ai_client:
            logger.warning("AI client not available, using error fallback")
            return self._create_error_result("AI client not available")
        
        try:
            logger.info(f"Starting simple QA assessment for {report.company_name}")
            
            # Build assessment prompt
            prompt = self._build_assessment_prompt(report)
            
            # Try primary model with retry logic
            result = self._try_assessment_with_retry(prompt, report.company_name, is_primary=True)
            if result:
                return result
            
            # Try fallback model with retry logic
            logger.info(f"Primary model failed, trying fallback model for {report.company_name}")
            result = self._try_assessment_with_retry(prompt, report.company_name, is_primary=False)
            if result:
                return result
            
            # If both models fail completely, return diagnostic result
            return self._create_error_result("Both primary and fallback models failed after retries")
            
        except Exception as e:
            error_msg = self.error_handler.handle_analysis_error(e, report.company_name)
            logger.error(f"Simple QA assessment failed: {error_msg}")
            return self._create_error_result(error_msg)
    
    def _try_assessment_with_retry(self, prompt: str, company_name: str, is_primary: bool = True, max_retries: int = 3) -> Optional[SimpleQAResult]:
        """
        Try assessment with exponential backoff retry logic.
        
        Args:
            prompt: Assessment prompt
            company_name: Company name for logging
            is_primary: Whether this is the primary model attempt
            max_retries: Maximum number of retry attempts
            
        Returns:
            SimpleQAResult if successful, None if all retries failed
        """
        import time
        
        model_type = "primary" if is_primary else "fallback"
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"Assessment attempt {attempt + 1}/{max_retries} using {model_type} model for {company_name}")
                
                response = self.ai_client.generate(
                    prompt, 
                    model_type="research",
                    thinking_level="high",
                    temperature=0.3
                )
                
                if response and len(response.strip()) > 20:
                    result = self._parse_json_response(response)
                    if result.parsing_success:
                        logger.info(f"QA assessment completed using {model_type} model for {company_name} (attempt {attempt + 1})")
                        return result
                    elif attempt == max_retries - 1:
                        # On final attempt, return even parsing failures
                        logger.warning(f"Final attempt with {model_type} model had parsing issues for {company_name}")
                        return result
                else:
                    logger.warning(f"Empty or short response from {model_type} model for {company_name} (attempt {attempt + 1})")
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check for rate limiting
                if "429" in error_str or "rate limit" in error_str or "resource_exhausted" in error_str:
                    if attempt < max_retries - 1:
                        # Exponential backoff for rate limits: 5s, 10s, 20s
                        delay = min(5 * (2 ** attempt), 60)
                        logger.warning(f"Rate limit hit with {model_type} model for {company_name}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded for {model_type} model after {max_retries} attempts for {company_name}")
                        return self._create_error_result(f"Rate limit exceeded for {model_type} model")
                
                # Check for quota exhaustion (stop immediately)
                if "quota" in error_str and "exceeded" in error_str:
                    logger.error(f"API quota exhausted for {model_type} model for {company_name}")
                    return self._create_error_result("API quota exhausted - upgrade plan or wait for reset")
                
                # For other errors, retry with shorter backoff
                if attempt < max_retries - 1:
                    delay = min(2 ** attempt, 10)  # 1s, 2s, 4s (max 10s)
                    logger.warning(f"{model_type} model error for {company_name}: {e}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    logger.error(f"{model_type} model failed after {max_retries} attempts for {company_name}: {e}")
        
        return None
    
    def _build_assessment_prompt(self, report: ReportContent) -> str:
        """Build assessment prompt focused on consultant readiness."""
        
        # Get section breakdown for better analysis
        section_summary = []
        for section_name, section_content in report.sections.items():
            word_count = len(section_content.split())
            section_summary.append(f"- {section_name}: {word_count} words")
        
        sections_text = "\n".join(section_summary) if section_summary else "No sections identified"
        
        # Count inline citations like [cite: 1, 2, 3] in addition to bibliography
        inline_citation_count = self._count_inline_citations(report.content)
        total_citations = len(report.citations) + inline_citation_count
        
        # Determine report type and adjust evaluation criteria
        report_type = self._determine_report_type(report)
        evaluation_context = self._get_evaluation_context(report_type)
        
        prompt = f"""You are evaluating whether this {report_type.lower()} achieves its core purpose: priming a consultant to deeply understand this company so they can help them be more successful.

The goal is NOT a polished client deliverable. The goal is internal intelligence that helps a consultant:
1. Understand how this company creates value and what makes them tick
2. Identify where they're likely struggling or have unmet needs
3. Walk into a conversation ready to be genuinely helpful
4. Spot opportunities where support could help them move faster

{evaluation_context}

WHAT MAKES A REPORT USEFUL FOR THIS PURPOSE:

Deep Understanding:
- Clear picture of how the company makes money and creates value
- Understanding of their strategic priorities and where they're headed
- Insight into their competitive position and market dynamics
- Sense of their culture, constraints, and decision-making patterns

Actionable Intelligence:
- Specific hypotheses about their challenges (not generic observations)
- "Where They're Likely to Say Yes" - concrete engagement opportunities
- Evidence-backed insights a consultant can reference in conversation
- Tensions or patterns that suggest where help would be welcomed

Quality Signals:
- Hypothesis-driven framing (things to validate, not declarations)
- Appropriate precision (ranges for estimates, exact figures only from filings)
- No repetition across sections (each insight lives in one place)
- Citations that let a consultant dig deeper if needed

RED FLAGS:
- Generic observations that could apply to any company
- Missing or shallow analysis of how they actually make money
- No clear hypotheses about where they need help
- Placeholder values or truncated sections
- Repetitive content across frameworks

REPORT DETAILS:
Company: {report.company_name}
Report Type: {report_type}
Total Length: {len(report.content.split())} words
Bibliography Citations: {len(report.citations)} sources
Inline Citations: {inline_citation_count} references
Total Citation References: {total_citations}
Section Breakdown:
{sections_text}

REPORT CONTENT:
{report.content}

Based on your analysis, provide your assessment in this exact JSON format:
{{
    "ready_for_use": true,
    "confidence_level": "high",
    "key_strengths": ["Specific strength 1", "Specific strength 2", "Specific strength 3"],
    "areas_for_improvement": ["Specific improvement 1", "Specific improvement 2"],
    "recommendation": "Clear recommendation with reasoning"
}}

ASSESSMENT GUIDELINES:
- Be specific in strengths and improvements (not generic)
- Flag any placeholder values, truncated sections, or missing citations
- Evaluate hypothesis-driven framing vs declarative statements
- Check for insight repetition across sections
- Base confidence_level on actual evidence quality and completeness
- Make recommendation actionable for internal research use
- Only return the JSON, no other text"""

        return prompt
    
    def _count_inline_citations(self, content: str) -> int:
        """Count inline citations like [cite: 1, 2, 3] in the content."""
        import re
        
        inline_pattern = r'\[cite:\s*([\d,\s]+)\]'
        all_nums = set()
        
        for match in re.finditer(inline_pattern, content):
            nums = [n.strip() for n in match.group(1).split(',')]
            all_nums.update(nums)
        
        return len(all_nums)
    
    def _determine_report_type(self, report: ReportContent) -> str:
        """Determine the type of report based on content and structure."""
        content_lower = report.content.lower()
        
        # Check for strategy/vision indicators
        strategy_indicators = ['ai strategy', 'strategic roadmap', 'vision', 'future state', 'transformation', 'digital strategy']
        if any(indicator in content_lower for indicator in strategy_indicators):
            return "AI Strategy Report"
        
        # Check for comprehensive research indicators
        research_indicators = ['market analysis', 'competitive landscape', 'swot analysis', 'financial overview', 'strategic overview']
        research_count = sum(1 for indicator in research_indicators if indicator in content_lower)
        
        if research_count >= 3:
            return "Comprehensive Strategic Analysis"
        
        # Default based on section count and length
        if len(report.sections) > 50 and len(report.content) > 50000:
            return "Comprehensive Strategic Analysis"
        elif 'strategy' in content_lower:
            return "Strategic Report"
        else:
            return "Business Analysis Report"
    
    def _get_evaluation_context(self, report_type: str) -> str:
        """Get evaluation criteria based on report type."""
        
        if "AI Strategy" in report_type or "Strategic Report" in report_type:
            return """FOR AI/STRATEGY REPORTS - Does this prepare a consultant to have a valuable conversation about AI/technology adoption?

Key questions:
- Does it connect AI opportunities to THIS company's specific business model and challenges?
- Are recommendations grounded in their actual capabilities and constraints?
- Would a consultant know what to propose and why it matters to them?
- Are there clear "door openers" - specific pain points where AI could help?"""
        
        else:
            return """FOR COMPANY RESEARCH - Does this give a consultant genuine insight into this company?

Key questions:
- Could a consultant explain how this company makes money and what drives their success?
- Are there specific hypotheses about challenges they're facing (not generic industry issues)?
- Does the "Where They're Likely to Say Yes" section identify real opportunities?
- Would reading this make a consultant more helpful in their first conversation?"""
    
    def _parse_json_response(self, response: str) -> SimpleQAResult:
        """Parse AI response into SimpleQAResult using robust JSON parser."""
        try:
            logger.debug(f"Parsing response: {response[:200]}...")
            
            # Try to parse with the robust JSON parser
            data = self.json_parser.parse_qa_response(response)
            
            if data:
                # Successfully parsed JSON
                return SimpleQAResult(
                    ready_for_use=bool(data['ready_for_use']),
                    confidence_level=data['confidence_level'],
                    key_strengths=data['key_strengths'],
                    areas_for_improvement=data['areas_for_improvement'],
                    recommendation=str(data['recommendation']),
                    parsing_success=True
                )
            else:
                # JSON parsing failed, use regex fallback
                logger.warning("JSON parsing failed, using regex fallback")
                fallback_data = self.json_parser.extract_with_regex_fallback(response)
                
                return SimpleQAResult(
                    ready_for_use=bool(fallback_data['ready_for_use']),
                    confidence_level=fallback_data['confidence_level'],
                    key_strengths=fallback_data['key_strengths'],
                    areas_for_improvement=fallback_data['areas_for_improvement'],
                    recommendation=str(fallback_data['recommendation']),
                    parsing_success=False
                )
                
        except Exception as e:
            logger.error(f"Critical error in JSON parsing: {e}")
            return self._create_parsing_fallback(response)
    
    def _create_parsing_fallback(self, response: str) -> SimpleQAResult:
        """Create fallback result when all parsing strategies fail."""
        logger.warning("Using final parsing fallback")
        
        return SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=["Unable to parse assessment details"],
            areas_for_improvement=["QA response format needs improvement"],
            recommendation="Manual review recommended due to parsing issues",
            parsing_success=False
        )
    
    def _create_error_result(self, error_message: str) -> SimpleQAResult:
        """Create result for complete analysis failure with diagnostic information."""
        
        # Provide more specific diagnostic information based on error type
        diagnostic_info = []
        error_lower = error_message.lower()
        
        if "rate limit" in error_lower or "429" in error_lower:
            diagnostic_info.append("API rate limits exceeded - try again in a few minutes")
            recommendation = "Temporary API rate limit reached. The report may still be of good quality - consider manual review or retry later."
        elif "quota" in error_lower and "exceeded" in error_lower:
            diagnostic_info.append("Daily API quota exhausted - upgrade plan or wait for reset")
            recommendation = "API quota exhausted. Report quality cannot be automatically assessed. Manual review recommended."
        elif "client not available" in error_lower:
            diagnostic_info.append("AI client configuration issue")
            recommendation = "QA system configuration issue. Report may still be usable - manual review recommended."
        elif "parsing" in error_lower:
            diagnostic_info.append("AI response format was unclear")
            recommendation = "QA analysis completed but response format was unclear. Report may still be usable - manual review recommended."
        else:
            diagnostic_info.append("Unexpected technical issue occurred")
            recommendation = f"Technical issue prevented automated assessment: {error_message}. Manual review recommended."
        
        return SimpleQAResult(
            ready_for_use=False,
            confidence_level="low",
            key_strengths=[],
            areas_for_improvement=diagnostic_info,
            recommendation=recommendation,
            parsing_success=False,
            error_message=error_message
        )