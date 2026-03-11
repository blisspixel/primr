"""
Section Writer for consulting-tier reports.

Generates report sections with clean formatting, source attribution,
and consulting-quality content.
"""

import json

from primr.ai.llm import llm
from primr.core.report_models import (
    ConfidenceLevel,
    ConfidenceNote,
    GatheredData,
    Insight,
    SectionContent,
    SourceCitation,
)
from primr.utils.formatting import clean_content
from primr.utils.logging_config import get_logger

logger = get_logger("section_writer")


EXECUTIVE_SUMMARY_PROMPT = """Write a consulting-tier executive summary for {company_name}.

Key Insights:
{insights_summary}

Research Data:
{data_summary}

The executive summary must include:
1. Company Snapshot: Brief overview of what the company does
2. Strategic Position: Current market position and competitive standing
3. Key Insights: 3-5 non-obvious strategic insights (most important)
4. Critical Risks: Top risks and vulnerabilities
5. Recommended Actions: Specific next steps

Requirements:
- Maximum 500 words
- Direct, professional tone (not stiff corporate-speak)
- No emojis or decorative characters
- No em-dashes (use commas or periods instead)
- No numbered headings (use natural section breaks)
- Focus on non-obvious insights over publicly available information
- Use readable number formats ($50M not $50,000,000)

Write the executive summary now:"""


SECTION_PROMPT = """Write a consulting-tier {section_type} section for {company_name}.

Context:
{context}

Research Data:
{data_summary}

Requirements:
- Professional, direct tone
- No emojis or decorative characters
- No em-dashes (use commas or periods instead)
- No numbered headings
- Include specific data points and evidence
- Use readable number formats ($50M not $50,000,000)
- Cite sources where appropriate

Write the {section_type} section now:"""


class SectionWriter:
    """Generates report sections with consulting-quality content."""

    def __init__(self, model_type: str = "report"):
        self.model_type = model_type

    def _summarize_insights(self, insights: list[Insight]) -> str:
        """Create a summary of insights for prompts."""
        if not insights:
            return "No insights available."

        return "\n".join(
            [f"- {i.title}: {i.description} (Confidence: {i.confidence.value})" for i in insights]
        )

    def _summarize_data(self, data: list[GatheredData], max_chars: int = 5000) -> str:
        """Create a summary of gathered data for prompts."""
        if not data:
            return "No research data available."

        summaries = []
        total_chars = 0

        for item in data:
            if total_chars >= max_chars:
                break

            summary = f"[{item.source_type.value}] {item.content[:300]}..."
            summaries.append(summary)
            total_chars += len(summary)

        return "\n\n".join(summaries)

    def _extract_sources(self, data: list[GatheredData]) -> list[SourceCitation]:
        """Extract source citations from gathered data."""
        sources = []
        seen_urls = set()

        for item in data:
            if item.source_url not in seen_urls:
                sources.append(
                    SourceCitation(
                        url=item.source_url,
                        title=item.title or item.source_url,
                        source_type=item.source_type,
                        accessed_at=item.gathered_at,
                        excerpt=item.content[:200] if item.content else "",
                    )
                )
                seen_urls.add(item.source_url)

        return sources

    def write_executive_summary(
        self,
        insights: list[Insight],
        data: list[GatheredData],
        company_name: str,
        max_words: int = 500,
    ) -> SectionContent:
        """
        Write an executive summary with all required components.

        Args:
            insights: List of strategic insights
            data: Gathered research data
            company_name: Name of the company
            max_words: Maximum word count (default 500)

        Returns:
            SectionContent with executive summary
        """
        insights_summary = self._summarize_insights(insights)
        data_summary = self._summarize_data(data)

        prompt = EXECUTIVE_SUMMARY_PROMPT.format(
            company_name=company_name, insights_summary=insights_summary, data_summary=data_summary
        )

        try:
            response = llm(prompt, model_type=self.model_type)
            content = clean_content(response)

            # Enforce word limit
            words = content.split()
            if len(words) > max_words:
                content = " ".join(words[:max_words])
                # Try to end at a sentence
                last_period = content.rfind(".")
                if last_period > len(content) * 0.8:
                    content = content[: last_period + 1]

            # Extract confidence notes for estimated data
            confidence_notes = self._extract_confidence_notes(insights)

            return SectionContent(
                title="Executive Summary",
                content=content,
                sources=self._extract_sources(data),
                confidence_notes=confidence_notes,
            )

        except Exception as e:
            logger.error(f"Failed to write executive summary: {e}")
            return SectionContent(
                title="Executive Summary",
                content=f"Executive summary generation failed for {company_name}.",
                sources=[],
                confidence_notes=[],
            )

    def _extract_confidence_notes(self, insights: list[Insight]) -> list[ConfidenceNote]:
        """Extract confidence notes from insights."""
        notes = []

        for insight in insights:
            if insight.confidence in [ConfidenceLevel.ESTIMATED, ConfidenceLevel.INFERRED]:
                notes.append(
                    ConfidenceNote(
                        statement=insight.title,
                        confidence=insight.confidence,
                        basis=f"Based on: {', '.join(insight.evidence[:2])}"
                        if insight.evidence
                        else "Inferred from available data",
                    )
                )

        return notes

    def write_section(
        self, section_type: str, company_name: str, context: str, data: list[GatheredData]
    ) -> SectionContent:
        """
        Write a report section.

        Args:
            section_type: Type of section (e.g., "Financial Overview")
            company_name: Name of the company
            context: Additional context for the section
            data: Gathered research data

        Returns:
            SectionContent with the section
        """
        data_summary = self._summarize_data(data)

        prompt = SECTION_PROMPT.format(
            section_type=section_type,
            company_name=company_name,
            context=context,
            data_summary=data_summary,
        )

        try:
            response = llm(prompt, model_type=self.model_type)
            content = clean_content(response)

            return SectionContent(
                title=section_type,
                content=content,
                sources=self._extract_sources(data),
                confidence_notes=[],
            )

        except Exception as e:
            logger.error(f"Failed to write section {section_type}: {e}")
            return SectionContent(
                title=section_type,
                content=f"Section generation failed for {section_type}.",
                sources=[],
                confidence_notes=[],
            )

    def format_for_readability(self, content: str) -> str:
        """
        Apply formatting cleanup for readability.

        Args:
            content: Raw content to format

        Returns:
            Cleaned and formatted content
        """
        return clean_content(content)

    def write_industry_analysis(
        self, company_name: str, industry: str, data: list[GatheredData]
    ) -> SectionContent:
        """Write industry analysis section."""
        context = f"Industry: {industry}"
        return self.write_section("Industry Analysis", company_name, context, data)

    def write_financial_overview(
        self, company_name: str, financial_data: dict, data: list[GatheredData]
    ) -> SectionContent:
        """Write financial overview section."""
        context = f"Financial Data: {json.dumps(financial_data, default=str)}"
        return self.write_section("Financial Overview", company_name, context, data)

    def write_competitive_analysis(
        self, company_name: str, competitors: list[str], data: list[GatheredData]
    ) -> SectionContent:
        """Write competitive analysis section."""
        context = f"Competitors: {', '.join(competitors)}"
        return self.write_section("Competitive Analysis", company_name, context, data)

    def write_strategic_recommendations(
        self, company_name: str, insights: list[Insight], data: list[GatheredData]
    ) -> SectionContent:
        """Write strategic recommendations section."""
        context = self._summarize_insights(insights)
        return self.write_section("Strategic Recommendations", company_name, context, data)
