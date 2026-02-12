"""
ExecutiveSummaryGenerator for premium report generation.

Synthesizes key insights from multiple sections into a cohesive executive
summary using the Situation-Complication-Resolution framework.
"""

import re

from primr.output.content_pattern_detector import ContentPatternDetector
from primr.output.models import ExecutiveSummary


class ExecutiveSummaryGenerator:
    """Generates executive summary from section content."""

    # Maximum items per section (Miller's Law)
    MAX_TAKEAWAYS = 7
    MAX_RISK_FACTORS = 5

    def __init__(self, section_results: dict[str, str]):
        """
        Initialize with section results.

        Args:
            section_results: Dict mapping section_key to content string
        """
        self.sections = section_results
        self.detector = ContentPatternDetector()

    def generate(self) -> ExecutiveSummary:
        """
        Generate executive summary with key takeaways.

        Process:
        1. Extract key sentences from USP, Financial, Strategic sections
        2. Identify top 5-7 strategic insights
        3. Synthesize into narrative using S-C-R framework
        4. Extract bullet-point key takeaways
        5. Identify risk factors

        Returns:
            ExecutiveSummary dataclass
        """
        key_insights = self.extract_key_insights()
        risk_factors = self.extract_risk_factors()
        metrics = self._extract_all_metrics()
        narrative = self._generate_narrative()
        one_liner = self._generate_one_liner()

        return ExecutiveSummary(
            narrative=narrative,
            key_takeaways=key_insights[:self.MAX_TAKEAWAYS],
            metrics_snapshot=metrics,
            risk_factors=risk_factors[:self.MAX_RISK_FACTORS],
            one_liner=one_liner
        )

    def extract_key_insights(self) -> list[str]:
        """
        Extract the most important insights for bullet points.

        Looks for sentences containing:
        - Financial figures
        - Competitive differentiators
        - Strategic recommendations
        - Growth indicators

        Returns:
            List of insight strings (max 7)
        """
        insights = []

        # Priority sections for insights
        priority_sections = [
            'unique_selling_proposition',
            'financial_overview',
            'strategic_recommendations',
            'value_theory',
            'business_drivers_and_kpis',
        ]

        for section_key in priority_sections:
            content = self.sections.get(section_key, '')
            if not content:
                continue

            # Extract sentences with financial figures
            sentences = self._split_into_sentences(content)
            for sentence in sentences:
                if self._is_insight_worthy(sentence):
                    # Clean and add
                    clean = self._clean_sentence(sentence)
                    if clean and clean not in insights:
                        insights.append(clean)
                        if len(insights) >= self.MAX_TAKEAWAYS:
                            return insights

        return insights

    def extract_risk_factors(self) -> list[str]:
        """
        Identify risk-related sentences from strategic sections.

        Returns:
            List of risk factor strings (max 5)
        """
        risks = []

        # Sections likely to contain risk information
        risk_sections = [
            'strategic_recommendations',
            'industry_insights',
            'potential_business_drivers',
            'board_of_directors_concerns',
        ]

        for section_key in risk_sections:
            content = self.sections.get(section_key, '')
            if not content:
                continue

            sentences = self._split_into_sentences(content)
            for sentence in sentences:
                if self.detector.detect_risk_keywords(sentence):
                    clean = self._clean_sentence(sentence)
                    if clean and clean not in risks:
                        risks.append(clean)
                        if len(risks) >= self.MAX_RISK_FACTORS:
                            return risks

        return risks

    def _extract_all_metrics(self) -> dict[str, str]:
        """Extract metrics from all relevant sections."""
        all_content = '\n'.join(self.sections.values())
        return self.detector.extract_metrics(all_content)

    def _generate_narrative(self) -> str:
        """
        Generate narrative using Situation-Complication-Resolution framework.

        Returns:
            3-5 paragraph narrative string
        """
        # Get key content
        usp = self.sections.get('unique_selling_proposition', '')
        self.sections.get('financial_overview', '')
        strategic = self.sections.get('strategic_recommendations', '')

        # Build narrative paragraphs
        paragraphs = []

        # Situation: What is the company and its position
        if usp:
            situation = self._extract_first_paragraph(usp)
            if situation:
                paragraphs.append(situation)

        # Complication: Challenges and market dynamics
        industry = self.sections.get('industry_insights', '')
        if industry:
            complication = self._extract_first_paragraph(industry)
            if complication:
                paragraphs.append(complication)

        # Resolution: Strategic direction and recommendations
        if strategic:
            resolution = self._extract_first_paragraph(strategic)
            if resolution:
                paragraphs.append(resolution)

        return '\n\n'.join(paragraphs) if paragraphs else ''

    def _generate_one_liner(self) -> str:
        """
        Generate single-sentence company summary (dinner test).

        Template: "{company} is a {industry} company that {differentiator},
                   generating {revenue} in annual revenue."

        Returns:
            One-liner summary string
        """
        metrics = self._extract_all_metrics()

        # Get company name from sections
        company_name = self.sections.get('company_name', 'The company')
        industry = self.sections.get('industry', '')

        # Get differentiator from USP
        usp = self.sections.get('unique_selling_proposition', '')
        differentiator = self._extract_key_differentiator(usp)

        revenue = metrics.get('revenue', '')

        # Build one-liner
        parts = [company_name]

        if industry:
            parts.append(f"is a {industry} company")

        if differentiator:
            parts.append(f"that {differentiator}")

        if revenue:
            parts.append(f"generating {revenue} in annual revenue")

        if len(parts) > 1:
            return ' '.join(parts) + '.'

        return f"{company_name} provides specialized services in its market."

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _is_insight_worthy(self, sentence: str) -> bool:
        """Check if a sentence is worth including as an insight."""
        # Must be substantial
        if len(sentence) < 30:
            return False

        # Contains financial figures
        if self.detector.extract_financial_figures(sentence):
            return True

        # Contains opportunity keywords
        if self.detector.detect_opportunity_keywords(sentence):
            return True

        # Contains specific numbers or percentages
        return bool(re.search(r'\d+%|\$\d+|\d+\s*(million|billion|M|B|K)', sentence, re.IGNORECASE))

    def _clean_sentence(self, sentence: str) -> str:
        """Clean a sentence for display."""
        # Remove markdown
        clean = re.sub(r'\*\*(.+?)\*\*', r'\1', sentence)
        clean = re.sub(r'__(.+?)__', r'\1', clean)
        clean = re.sub(r'\*(.+?)\*', r'\1', clean)
        clean = clean.strip()

        # Truncate if too long
        if len(clean) > 200:
            clean = clean[:197] + '...'

        return clean

    def _extract_first_paragraph(self, content: str) -> str:
        """Extract the first meaningful paragraph from content."""
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            clean = para.strip()
            # Skip headers and short lines
            if clean and not clean.startswith('#') and len(clean) > 50:
                return self._clean_sentence(clean)
        return ''

    def _extract_key_differentiator(self, usp_content: str) -> str:
        """Extract key differentiator from USP content."""
        if not usp_content:
            return ''

        # Look for key phrases
        sentences = self._split_into_sentences(usp_content)
        for sentence in sentences:
            lower = sentence.lower()
            if any(phrase in lower for phrase in ['unique', 'differentiat', 'speciali', 'leading', 'pioneer']):
                # Extract the key part
                clean = self._clean_sentence(sentence)
                if len(clean) > 100:
                    clean = clean[:97] + '...'
                return clean.lower()

        # Fall back to first sentence
        if sentences:
            clean = self._clean_sentence(sentences[0])
            if len(clean) > 100:
                clean = clean[:97] + '...'
            return clean.lower()

        return ''
