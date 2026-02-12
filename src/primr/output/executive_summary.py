"""
Executive summary generation for company research reports.

This module provides:
- Automatic executive summary generation
- Key findings extraction
- Confidence indicators
- Source citations
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from primr.utils.logging_config import get_logger

logger = get_logger("output.executive_summary")


class FindingCategory(Enum):
    """Categories of key findings."""

    COMPANY_OVERVIEW = "company_overview"
    FINANCIAL = "financial"
    LEADERSHIP = "leadership"
    PRODUCTS_SERVICES = "products_services"
    MARKET_POSITION = "market_position"
    RECENT_NEWS = "recent_news"
    RISKS = "risks"
    OPPORTUNITIES = "opportunities"


class ConfidenceIndicator(Enum):
    """Confidence indicators for findings."""

    HIGH = "high"      # Multiple authoritative sources
    MEDIUM = "medium"  # Some corroboration
    LOW = "low"        # Single source or unverified


@dataclass
class KeyFinding:
    """A key finding from the research."""

    category: FindingCategory
    summary: str
    details: str = ""
    confidence: ConfidenceIndicator = ConfidenceIndicator.MEDIUM
    sources: list[str] = field(default_factory=list)
    importance: int = 5  # 1-10 scale

    @property
    def confidence_icon(self) -> str:
        """Get icon for confidence level."""
        icons = {
            ConfidenceIndicator.HIGH: "✓✓",
            ConfidenceIndicator.MEDIUM: "✓",
            ConfidenceIndicator.LOW: "?",
        }
        return icons.get(self.confidence, "")


@dataclass
class SourceCitation:
    """A source citation."""

    title: str
    url: str
    accessed_date: str = ""
    relevance: str = ""

    def format_citation(self, style: str = "inline") -> str:
        """Format the citation."""
        if style == "inline":
            return f"[{self.title}]({self.url})"
        elif style == "footnote":
            return f"{self.title}. Available at: {self.url}"
        else:
            return f"{self.title} - {self.url}"


@dataclass
class ExecutiveSummary:
    """Complete executive summary."""

    company_name: str
    one_liner: str = ""
    overview: str = ""
    key_findings: list[KeyFinding] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    sources: list[SourceCitation] = field(default_factory=list)
    confidence_score: float = 0.0

    @property
    def swot_available(self) -> bool:
        """Check if SWOT analysis is available."""
        return bool(self.strengths or self.weaknesses or
                   self.opportunities or self.threats)


class ExecutiveSummaryGenerator:
    """
    Generates executive summaries from research content.

    Example:
        generator = ExecutiveSummaryGenerator()
        summary = generator.generate(
            company_name="Acme Corp",
            sections={"overview": "...", "financials": "..."}
        )
        print(summary.one_liner)
    """

    # Keywords for categorizing findings
    CATEGORY_KEYWORDS = {
        FindingCategory.FINANCIAL: [
            "revenue", "profit", "earnings", "growth", "margin", "sales",
            "billion", "million", "quarter", "fiscal", "financial",
        ],
        FindingCategory.LEADERSHIP: [
            "ceo", "cfo", "cto", "president", "founder", "executive",
            "leadership", "management", "board", "director",
        ],
        FindingCategory.PRODUCTS_SERVICES: [
            "product", "service", "solution", "platform", "offering",
            "launch", "release", "feature", "technology",
        ],
        FindingCategory.MARKET_POSITION: [
            "market", "competitor", "industry", "share", "position",
            "leader", "ranking", "segment", "sector",
        ],
        FindingCategory.RECENT_NEWS: [
            "announced", "recently", "news", "update", "latest",
            "today", "yesterday", "this week", "this month",
        ],
        FindingCategory.RISKS: [
            "risk", "challenge", "threat", "concern", "issue",
            "problem", "decline", "loss", "lawsuit", "regulation",
        ],
        FindingCategory.OPPORTUNITIES: [
            "opportunity", "growth", "expansion", "potential",
            "emerging", "new market", "partnership", "acquisition",
        ],
    }

    def __init__(self):
        """Initialize the generator."""
        logger.debug("ExecutiveSummaryGenerator initialized")

    def generate(
        self,
        company_name: str,
        sections: dict[str, str],
        sources: list[dict[str, str]] | None = None,
    ) -> ExecutiveSummary:
        """
        Generate an executive summary from research sections.

        Args:
            company_name: Name of the company
            sections: Dictionary of section name to content
            sources: Optional list of source dictionaries

        Returns:
            ExecutiveSummary with all components
        """
        # Generate one-liner
        one_liner = self._generate_one_liner(company_name, sections)

        # Generate overview
        overview = self._generate_overview(company_name, sections)

        # Extract key findings
        key_findings = self._extract_key_findings(sections)

        # Extract SWOT
        swot = self._extract_swot(sections)

        # Generate recommendations
        recommendations = self._generate_recommendations(key_findings, swot)

        # Process sources
        source_citations = self._process_sources(sources or [])

        # Calculate confidence
        confidence = self._calculate_confidence(key_findings, source_citations)

        return ExecutiveSummary(
            company_name=company_name,
            one_liner=one_liner,
            overview=overview,
            key_findings=key_findings,
            strengths=swot.get("strengths", []),
            weaknesses=swot.get("weaknesses", []),
            opportunities=swot.get("opportunities", []),
            threats=swot.get("threats", []),
            recommendations=recommendations,
            sources=source_citations,
            confidence_score=confidence,
        )

    def generate_one_liner(self, company_name: str, content: str) -> str:
        """
        Generate a one-line company description.

        Args:
            company_name: Name of the company
            content: Content to summarize

        Returns:
            One-line description
        """
        return self._generate_one_liner(company_name, {"content": content})

    def extract_key_points(
        self,
        content: str,
        max_points: int = 5,
    ) -> list[str]:
        """
        Extract key points from content.

        Args:
            content: Content to analyze
            max_points: Maximum number of points

        Returns:
            List of key points
        """
        points = []

        # Split into sentences
        sentences = re.split(r'[.!?]+', content)

        # Score sentences by importance
        scored = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:
                continue

            score = self._score_sentence_importance(sentence)
            scored.append((score, sentence))

        # Sort by score and take top N
        scored.sort(reverse=True)
        for _score, sentence in scored[:max_points]:
            # Clean up the sentence
            point = sentence.strip()
            if not point.endswith('.'):
                point += '.'
            points.append(point)

        return points

    def format_summary(
        self,
        summary: ExecutiveSummary,
        format_type: str = "markdown",
    ) -> str:
        """
        Format the executive summary.

        Args:
            summary: ExecutiveSummary to format
            format_type: "markdown", "text", or "html"

        Returns:
            Formatted summary string
        """
        if format_type == "markdown":
            return self._format_markdown(summary)
        elif format_type == "html":
            return self._format_html(summary)
        else:
            return self._format_text(summary)

    def _generate_one_liner(
        self,
        company_name: str,
        sections: dict[str, str],
    ) -> str:
        """Generate a one-line description."""
        # Look for overview or about section
        overview_content = ""
        for key in ["overview", "about", "company_overview", "description"]:
            if key in sections:
                overview_content = sections[key]
                break

        if not overview_content:
            overview_content = " ".join(sections.values())[:1000]

        # Extract first meaningful sentence
        sentences = re.split(r'[.!?]+', overview_content)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 30 and company_name.lower() in sentence.lower():
                return sentence + "."

        # Fallback: construct from keywords
        industry = self._extract_industry(overview_content)
        if industry:
            return f"{company_name} is a company in the {industry} industry."

        return f"{company_name} is a company providing products and services."

    def _generate_overview(
        self,
        company_name: str,
        sections: dict[str, str],
    ) -> str:
        """Generate overview paragraph."""
        overview_parts = []

        # Get key information
        for key in ["overview", "about", "company_overview"]:
            if key in sections:
                content = sections[key]
                points = self.extract_key_points(content, max_points=3)
                overview_parts.extend(points)
                break

        # Add financial highlights if available
        for key in ["financials", "financial", "revenue"]:
            if key in sections:
                content = sections[key]
                financial_points = self._extract_financial_highlights(content)
                if financial_points:
                    overview_parts.append(financial_points[0])
                break

        if overview_parts:
            return " ".join(overview_parts)

        return f"{company_name} is a company that operates in its industry."

    def _extract_key_findings(
        self,
        sections: dict[str, str],
    ) -> list[KeyFinding]:
        """Extract key findings from sections."""
        findings = []

        for _section_name, content in sections.items():
            # Determine category
            category = self._categorize_content(content)

            # Extract key points
            points = self.extract_key_points(content, max_points=2)

            for point in points:
                importance = self._score_sentence_importance(point)
                confidence = self._estimate_confidence(point)

                findings.append(KeyFinding(
                    category=category,
                    summary=point,
                    confidence=confidence,
                    importance=min(int(importance * 10), 10),
                ))

        # Sort by importance
        findings.sort(key=lambda f: f.importance, reverse=True)

        return findings[:10]  # Top 10 findings

    def _extract_swot(
        self,
        sections: dict[str, str],
    ) -> dict[str, list[str]]:
        """Extract SWOT analysis from content."""
        swot: dict[str, list[str]] = {
            "strengths": [],
            "weaknesses": [],
            "opportunities": [],
            "threats": [],
        }

        all_content = " ".join(sections.values())

        # Extract strengths (positive internal)
        strength_patterns = [
            r'strength[s]?[:\s]+([^.]+)',
            r'(?:strong|leading|excellent|best)[^.]*(?:in|at|for)[^.]+',
        ]
        for pattern in strength_patterns:
            matches = re.findall(pattern, all_content, re.I)
            for match in matches[:3]:
                if len(match) > 20:
                    swot["strengths"].append(match.strip())

        # Extract weaknesses (negative internal)
        weakness_patterns = [
            r'weakness[es]?[:\s]+([^.]+)',
            r'(?:challenge|struggle|lack|limited)[^.]+',
        ]
        for pattern in weakness_patterns:
            matches = re.findall(pattern, all_content, re.I)
            for match in matches[:3]:
                if len(match) > 20:
                    swot["weaknesses"].append(match.strip())

        # Extract opportunities (positive external)
        opportunity_patterns = [
            r'opportunit(?:y|ies)[:\s]+([^.]+)',
            r'(?:potential|emerging|growth)[^.]*(?:market|opportunity)[^.]+',
        ]
        for pattern in opportunity_patterns:
            matches = re.findall(pattern, all_content, re.I)
            for match in matches[:3]:
                if len(match) > 20:
                    swot["opportunities"].append(match.strip())

        # Extract threats (negative external)
        threat_patterns = [
            r'threat[s]?[:\s]+([^.]+)',
            r'(?:risk|competition|regulatory)[^.]+(?:threat|challenge)[^.]+',
        ]
        for pattern in threat_patterns:
            matches = re.findall(pattern, all_content, re.I)
            for match in matches[:3]:
                if len(match) > 20:
                    swot["threats"].append(match.strip())

        return swot

    def _generate_recommendations(
        self,
        findings: list[KeyFinding],
        swot: dict[str, list[str]],
    ) -> list[str]:
        """Generate recommendations based on findings."""
        recommendations = []

        # Based on opportunities
        if swot.get("opportunities"):
            recommendations.append(
                f"Consider exploring opportunities in: {swot['opportunities'][0][:100]}"
            )

        # Based on risks
        risk_findings = [f for f in findings if f.category == FindingCategory.RISKS]
        if risk_findings:
            recommendations.append(
                f"Monitor and mitigate identified risks related to: {risk_findings[0].summary[:100]}"
            )

        # Based on market position
        market_findings = [f for f in findings if f.category == FindingCategory.MARKET_POSITION]
        if market_findings:
            recommendations.append(
                "Evaluate competitive positioning and market strategy"
            )

        # Default recommendation
        if not recommendations:
            recommendations.append(
                "Continue monitoring company developments and industry trends"
            )

        return recommendations[:5]

    def _process_sources(
        self,
        sources: list[dict[str, str]],
    ) -> list[SourceCitation]:
        """Process source dictionaries into citations."""
        citations = []

        for source in sources:
            citation = SourceCitation(
                title=source.get("title", "Unknown Source"),
                url=source.get("url", ""),
                accessed_date=source.get("date", ""),
                relevance=source.get("relevance", ""),
            )
            citations.append(citation)

        return citations

    def _calculate_confidence(
        self,
        findings: list[KeyFinding],
        sources: list[SourceCitation],
    ) -> float:
        """Calculate overall confidence score."""
        if not findings:
            return 0.0

        # Base score from findings confidence
        confidence_scores = {
            ConfidenceIndicator.HIGH: 1.0,
            ConfidenceIndicator.MEDIUM: 0.6,
            ConfidenceIndicator.LOW: 0.3,
        }

        finding_score = sum(
            confidence_scores.get(f.confidence, 0.5) for f in findings
        ) / len(findings)

        # Bonus for multiple sources
        source_bonus = min(len(sources) * 0.05, 0.2)

        return min(finding_score + source_bonus, 1.0)

    def _categorize_content(self, content: str) -> FindingCategory:
        """Categorize content based on keywords."""
        content_lower = content.lower()

        best_category = FindingCategory.COMPANY_OVERVIEW
        best_score = 0

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def _score_sentence_importance(self, sentence: str) -> float:
        """Score sentence importance (0-1)."""
        score = 0.0
        sentence_lower = sentence.lower()

        # Important keywords
        important_words = [
            "revenue", "profit", "growth", "market", "leader", "ceo",
            "announced", "launched", "acquired", "partnership", "billion",
        ]
        for word in important_words:
            if word in sentence_lower:
                score += 0.1

        # Numbers indicate specificity
        if re.search(r'\d+', sentence):
            score += 0.15

        # Proper length
        if 50 < len(sentence) < 200:
            score += 0.1

        return min(score, 1.0)

    def _estimate_confidence(self, text: str) -> ConfidenceIndicator:
        """Estimate confidence level for text."""
        # High confidence indicators
        high_indicators = ["confirmed", "reported", "announced", "according to"]
        if any(ind in text.lower() for ind in high_indicators):
            return ConfidenceIndicator.HIGH

        # Low confidence indicators
        low_indicators = ["may", "might", "possibly", "rumored", "unconfirmed"]
        if any(ind in text.lower() for ind in low_indicators):
            return ConfidenceIndicator.LOW

        return ConfidenceIndicator.MEDIUM

    def _extract_industry(self, content: str) -> str | None:
        """Extract industry from content."""
        industry_patterns = [
            r'(?:in the|operates in|industry:?)\s+([a-z]+(?:\s+[a-z]+)?)\s+(?:industry|sector)',
            r'([a-z]+(?:\s+[a-z]+)?)\s+company',
        ]

        for pattern in industry_patterns:
            match = re.search(pattern, content.lower())
            if match:
                return match.group(1).title()

        return None

    def _extract_financial_highlights(self, content: str) -> list[str]:
        """Extract financial highlights."""
        highlights = []

        # Revenue patterns
        revenue_match = re.search(
            r'revenue\s+(?:of\s+)?\$?([\d.]+)\s*([BMK](?:illion)?)',
            content, re.I
        )
        if revenue_match:
            highlights.append(
                f"Revenue of ${revenue_match.group(1)}{revenue_match.group(2)}"
            )

        # Growth patterns
        growth_match = re.search(
            r'(\d+(?:\.\d+)?)\s*%\s+(?:revenue\s+)?growth',
            content, re.I
        )
        if growth_match:
            highlights.append(f"{growth_match.group(1)}% growth")

        return highlights

    def _format_markdown(self, summary: ExecutiveSummary) -> str:
        """Format summary as markdown."""
        lines = [
            f"# Executive Summary: {summary.company_name}",
            "",
            f"**{summary.one_liner}**",
            "",
            "## Overview",
            summary.overview,
            "",
        ]

        if summary.key_findings:
            lines.extend([
                "## Key Findings",
                "",
            ])
            for finding in summary.key_findings[:5]:
                icon = finding.confidence_icon
                lines.append(f"- {icon} {finding.summary}")
            lines.append("")

        if summary.swot_available:
            lines.extend([
                "## SWOT Analysis",
                "",
            ])
            if summary.strengths:
                lines.append("**Strengths:**")
                for s in summary.strengths[:3]:
                    lines.append(f"- {s}")
            if summary.weaknesses:
                lines.append("**Weaknesses:**")
                for w in summary.weaknesses[:3]:
                    lines.append(f"- {w}")
            if summary.opportunities:
                lines.append("**Opportunities:**")
                for o in summary.opportunities[:3]:
                    lines.append(f"- {o}")
            if summary.threats:
                lines.append("**Threats:**")
                for t in summary.threats[:3]:
                    lines.append(f"- {t}")
            lines.append("")

        if summary.recommendations:
            lines.extend([
                "## Recommendations",
                "",
            ])
            for rec in summary.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        lines.append(f"*Confidence Score: {summary.confidence_score:.0%}*")

        return "\n".join(lines)

    def _format_text(self, summary: ExecutiveSummary) -> str:
        """Format summary as plain text."""
        lines = [
            f"EXECUTIVE SUMMARY: {summary.company_name}",
            "=" * 50,
            "",
            summary.one_liner,
            "",
            "OVERVIEW",
            "-" * 20,
            summary.overview,
            "",
        ]

        if summary.key_findings:
            lines.extend([
                "KEY FINDINGS",
                "-" * 20,
            ])
            for i, finding in enumerate(summary.key_findings[:5], 1):
                lines.append(f"{i}. {finding.summary}")
            lines.append("")

        if summary.recommendations:
            lines.extend([
                "RECOMMENDATIONS",
                "-" * 20,
            ])
            for rec in summary.recommendations:
                lines.append(f"* {rec}")

        return "\n".join(lines)

    def _format_html(self, summary: ExecutiveSummary) -> str:
        """Format summary as HTML."""
        html = f"""
<div class="executive-summary">
    <h1>Executive Summary: {summary.company_name}</h1>
    <p class="one-liner"><strong>{summary.one_liner}</strong></p>

    <h2>Overview</h2>
    <p>{summary.overview}</p>
"""

        if summary.key_findings:
            html += """
    <h2>Key Findings</h2>
    <ul class="findings">
"""
            for finding in summary.key_findings[:5]:
                html += f'        <li class="confidence-{finding.confidence.value}">{finding.summary}</li>\n'
            html += "    </ul>\n"

        if summary.recommendations:
            html += """
    <h2>Recommendations</h2>
    <ul class="recommendations">
"""
            for rec in summary.recommendations:
                html += f"        <li>{rec}</li>\n"
            html += "    </ul>\n"

        html += f"""
    <p class="confidence">Confidence Score: {summary.confidence_score:.0%}</p>
</div>
"""
        return html



# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_generator: ExecutiveSummaryGenerator | None = None


def get_summary_generator() -> ExecutiveSummaryGenerator:
    """
    Get the global summary generator instance.

    Returns:
        ExecutiveSummaryGenerator instance
    """
    global _generator
    if _generator is None:
        _generator = ExecutiveSummaryGenerator()
    return _generator


def reset_summary_generator() -> None:
    """Reset the global generator (useful for testing)."""
    global _generator
    _generator = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_executive_summary(
    company_name: str,
    sections: dict[str, str],
    sources: list[dict[str, str]] | None = None,
) -> ExecutiveSummary:
    """
    Generate an executive summary from research sections.

    Args:
        company_name: Name of the company
        sections: Dictionary of section name to content
        sources: Optional list of source dictionaries

    Returns:
        ExecutiveSummary with all components
    """
    return get_summary_generator().generate(company_name, sections, sources)


def generate_one_liner(company_name: str, content: str) -> str:
    """
    Generate a one-line company description.

    Args:
        company_name: Name of the company
        content: Content to summarize

    Returns:
        One-line description
    """
    return get_summary_generator().generate_one_liner(company_name, content)


def extract_key_points(content: str, max_points: int = 5) -> list[str]:
    """
    Extract key points from content.

    Args:
        content: Content to analyze
        max_points: Maximum number of points

    Returns:
        List of key points
    """
    return get_summary_generator().extract_key_points(content, max_points)


def format_executive_summary(
    summary: ExecutiveSummary,
    format_type: str = "markdown",
) -> str:
    """
    Format an executive summary.

    Args:
        summary: ExecutiveSummary to format
        format_type: "markdown", "text", or "html"

    Returns:
        Formatted summary string
    """
    return get_summary_generator().format_summary(summary, format_type)
