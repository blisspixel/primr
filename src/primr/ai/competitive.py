"""
Competitive intelligence analysis module.

Provides competitor identification, comparison, and SWOT analysis.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CompetitorType(Enum):
    """Types of competitors."""
    DIRECT = "direct"  # Same product/service, same market
    INDIRECT = "indirect"  # Different product, same need
    POTENTIAL = "potential"  # Could enter market
    SUBSTITUTE = "substitute"  # Alternative solution


class MarketPosition(Enum):
    """Market positioning categories."""
    LEADER = "leader"
    CHALLENGER = "challenger"
    FOLLOWER = "follower"
    NICHER = "nicher"
    EMERGING = "emerging"


class ThreatLevel(Enum):
    """Competitive threat levels."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


@dataclass
class SWOTItem:
    """A single SWOT item."""
    text: str
    category: str  # strength, weakness, opportunity, threat
    confidence: float = 0.8
    source: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class SWOTAnalysis:
    """Complete SWOT analysis."""
    company_name: str
    strengths: list[SWOTItem] = field(default_factory=list)
    weaknesses: list[SWOTItem] = field(default_factory=list)
    opportunities: list[SWOTItem] = field(default_factory=list)
    threats: list[SWOTItem] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "company_name": self.company_name,
            "strengths": [{"text": s.text, "confidence": s.confidence} for s in self.strengths],
            "weaknesses": [{"text": w.text, "confidence": w.confidence} for w in self.weaknesses],
            "opportunities": [{"text": o.text, "confidence": o.confidence} for o in self.opportunities],
            "threats": [{"text": t.text, "confidence": t.confidence} for t in self.threats],
            "generated_at": self.generated_at.isoformat(),
        }

    def get_summary(self) -> str:
        """Get a brief summary of the SWOT analysis."""
        return (
            f"SWOT for {self.company_name}: "
            f"{len(self.strengths)} strengths, {len(self.weaknesses)} weaknesses, "
            f"{len(self.opportunities)} opportunities, {len(self.threats)} threats"
        )


@dataclass
class Competitor:
    """A competitor company."""
    name: str
    competitor_type: CompetitorType
    market_position: MarketPosition
    threat_level: ThreatLevel
    description: str = ""
    website: str | None = None
    products: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    market_share: float | None = None  # Percentage
    confidence: float = 0.7


@dataclass
class CompetitiveComparison:
    """Comparison between companies."""
    company_name: str
    competitor_name: str
    dimensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    overall_assessment: str = ""
    competitive_advantage: list[str] = field(default_factory=list)
    competitive_disadvantage: list[str] = field(default_factory=list)


@dataclass
class MarketAnalysis:
    """Market analysis results."""
    industry: str
    market_size: str | None = None
    growth_rate: str | None = None
    key_trends: list[str] = field(default_factory=list)
    entry_barriers: list[str] = field(default_factory=list)
    success_factors: list[str] = field(default_factory=list)


class CompetitiveAnalyzer:
    """Analyzes competitive landscape and generates insights."""

    # Industry keywords for classification
    INDUSTRY_KEYWORDS = {
        "technology": ["software", "saas", "cloud", "ai", "tech", "digital", "platform"],
        "finance": ["bank", "financial", "fintech", "insurance", "investment", "payment"],
        "healthcare": ["health", "medical", "pharma", "biotech", "hospital", "clinic"],
        "retail": ["retail", "ecommerce", "store", "shop", "consumer", "merchandise"],
        "manufacturing": ["manufacturing", "industrial", "factory", "production"],
        "services": ["consulting", "agency", "service", "professional"],
    }

    # SWOT extraction patterns
    STRENGTH_PATTERNS = [
        r"(?:strong|leading|best|top|excellent|superior)\s+(\w+(?:\s+\w+){0,3})",
        r"(?:market leader|industry leader|pioneer)",
        r"(?:innovative|cutting-edge|state-of-the-art)",
        r"(?:strong brand|brand recognition|trusted)",
        r"(?:experienced team|talented|skilled workforce)",
    ]

    WEAKNESS_PATTERNS = [
        r"(?:limited|lack of|insufficient|weak)\s+(\w+(?:\s+\w+){0,3})",
        r"(?:high cost|expensive|overpriced)",
        r"(?:slow|delayed|behind)",
        r"(?:small market share|limited reach)",
        r"(?:outdated|legacy|aging)",
    ]

    OPPORTUNITY_PATTERNS = [
        r"(?:growing market|market growth|expansion)",
        r"(?:emerging|new market|untapped)",
        r"(?:partnership|acquisition|merger)",
        r"(?:new technology|innovation|digital transformation)",
        r"(?:regulatory change|deregulation)",
    ]

    THREAT_PATTERNS = [
        r"(?:competition|competitor|rival)",
        r"(?:regulation|compliance|legal)",
        r"(?:economic|recession|downturn)",
        r"(?:disruption|disruptive)",
        r"(?:cybersecurity|security threat|data breach)",
    ]

    def __init__(self):
        """Initialize the competitive analyzer."""
        self._lock = threading.Lock()
        self._competitor_cache: dict[str, list[Competitor]] = {}
        self._swot_cache: dict[str, SWOTAnalysis] = {}

    def identify_competitors(
        self,
        company_name: str,
        company_description: str,
        content: str,
        max_competitors: int = 10,
    ) -> list[Competitor]:
        """Identify competitors from content.

        Args:
            company_name: Name of the company being researched
            company_description: Description of the company
            content: Text content to analyze
            max_competitors: Maximum competitors to return

        Returns:
            List of identified competitors
        """
        competitors: list[Competitor] = []

        # Extract company names mentioned as competitors
        competitor_patterns = [
            r"(?:competitor|rival|competing with|competes with)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
            r"(?:vs\.?|versus|compared to)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
            r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:is a competitor|competes)",
        ]

        mentioned_companies: set[str] = set()
        for pattern in competitor_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                name = match.strip()
                if name.lower() != company_name.lower() and len(name) > 2:
                    mentioned_companies.add(name)

        # Classify each competitor
        for name in list(mentioned_companies)[:max_competitors]:
            competitor = self._classify_competitor(name, content, company_description)
            competitors.append(competitor)

        # Sort by threat level
        threat_order = {ThreatLevel.HIGH: 0, ThreatLevel.MEDIUM: 1, ThreatLevel.LOW: 2, ThreatLevel.MINIMAL: 3}
        competitors.sort(key=lambda c: threat_order.get(c.threat_level, 4))

        return competitors

    def generate_swot(
        self,
        company_name: str,
        content: str,
        industry: str | None = None,
    ) -> SWOTAnalysis:
        """Generate SWOT analysis from content.

        Args:
            company_name: Company name
            content: Text content to analyze
            industry: Optional industry classification

        Returns:
            SWOT analysis
        """
        swot = SWOTAnalysis(company_name=company_name)

        # Extract strengths
        swot.strengths = self._extract_swot_items(
            content, self.STRENGTH_PATTERNS, "strength"
        )

        # Extract weaknesses
        swot.weaknesses = self._extract_swot_items(
            content, self.WEAKNESS_PATTERNS, "weakness"
        )

        # Extract opportunities
        swot.opportunities = self._extract_swot_items(
            content, self.OPPORTUNITY_PATTERNS, "opportunity"
        )

        # Extract threats
        swot.threats = self._extract_swot_items(
            content, self.THREAT_PATTERNS, "threat"
        )

        # Add industry-specific items if industry is known
        if industry:
            self._add_industry_insights(swot, industry, content)

        # Cache the result
        with self._lock:
            self._swot_cache[company_name.lower()] = swot

        return swot

    def compare_companies(
        self,
        company_name: str,
        company_content: str,
        competitor_name: str,
        competitor_content: str,
    ) -> CompetitiveComparison:
        """Compare two companies.

        Args:
            company_name: Primary company name
            company_content: Content about primary company
            competitor_name: Competitor name
            competitor_content: Content about competitor

        Returns:
            Competitive comparison
        """
        comparison = CompetitiveComparison(
            company_name=company_name,
            competitor_name=competitor_name,
        )

        # Compare on key dimensions
        dimensions = ["products", "market_presence", "innovation", "pricing", "reputation"]

        for dim in dimensions:
            company_score = self._score_dimension(dim, company_content)
            competitor_score = self._score_dimension(dim, competitor_content)

            comparison.dimensions[dim] = {
                "company_score": company_score,
                "competitor_score": competitor_score,
                "advantage": "company" if company_score > competitor_score else "competitor" if competitor_score > company_score else "tie",
            }

            if company_score > competitor_score:
                comparison.competitive_advantage.append(dim)
            elif competitor_score > company_score:
                comparison.competitive_disadvantage.append(dim)

        # Generate overall assessment
        advantages = len(comparison.competitive_advantage)
        disadvantages = len(comparison.competitive_disadvantage)

        if advantages > disadvantages:
            comparison.overall_assessment = f"{company_name} has competitive advantages in {advantages} areas"
        elif disadvantages > advantages:
            comparison.overall_assessment = f"{competitor_name} has competitive advantages in {disadvantages} areas"
        else:
            comparison.overall_assessment = "Companies are competitively balanced"

        return comparison

    def analyze_market(
        self,
        content: str,
        industry: str | None = None,
    ) -> MarketAnalysis:
        """Analyze market from content.

        Args:
            content: Text content to analyze
            industry: Optional industry classification

        Returns:
            Market analysis
        """
        # Detect industry if not provided
        if not industry:
            industry = self._detect_industry(content)

        analysis = MarketAnalysis(industry=industry)

        # Extract market size
        size_patterns = [
            r"\$(\d+(?:\.\d+)?)\s*(billion|million|trillion)",
            r"market\s+(?:size|value)\s+(?:of\s+)?\$?(\d+(?:\.\d+)?)\s*(B|M|T|billion|million|trillion)",
        ]
        for pattern in size_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                analysis.market_size = f"${match.group(1)} {match.group(2)}"
                break

        # Extract growth rate
        growth_patterns = [
            r"(\d+(?:\.\d+)?)\s*%\s*(?:growth|CAGR|annual growth)",
            r"growing\s+(?:at\s+)?(\d+(?:\.\d+)?)\s*%",
        ]
        for pattern in growth_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                analysis.growth_rate = f"{match.group(1)}%"
                break

        # Extract trends
        trend_keywords = ["trend", "shift", "movement", "change", "transformation"]
        sentences = content.split(".")
        for sentence in sentences:
            if any(kw in sentence.lower() for kw in trend_keywords):
                trend = sentence.strip()
                if len(trend) > 20 and len(trend) < 200:
                    analysis.key_trends.append(trend)
                    if len(analysis.key_trends) >= 5:
                        break

        # Extract entry barriers
        barrier_keywords = ["barrier", "requirement", "regulation", "capital", "expertise"]
        for sentence in sentences:
            if any(kw in sentence.lower() for kw in barrier_keywords):
                barrier = sentence.strip()
                if len(barrier) > 20 and len(barrier) < 200:
                    analysis.entry_barriers.append(barrier)
                    if len(analysis.entry_barriers) >= 5:
                        break

        return analysis

    def get_threat_assessment(
        self,
        company_name: str,
        competitors: list[Competitor],
    ) -> dict[str, Any]:
        """Get overall threat assessment.

        Args:
            company_name: Company name
            competitors: List of competitors

        Returns:
            Threat assessment summary
        """
        if not competitors:
            return {
                "company": company_name,
                "overall_threat": "low",
                "high_threats": 0,
                "medium_threats": 0,
                "low_threats": 0,
                "summary": "No significant competitors identified",
            }

        high = sum(1 for c in competitors if c.threat_level == ThreatLevel.HIGH)
        medium = sum(1 for c in competitors if c.threat_level == ThreatLevel.MEDIUM)
        low = sum(1 for c in competitors if c.threat_level == ThreatLevel.LOW)

        if high >= 3:
            overall = "critical"
        elif high >= 1:
            overall = "high"
        elif medium >= 3:
            overall = "medium"
        else:
            overall = "low"

        return {
            "company": company_name,
            "overall_threat": overall,
            "high_threats": high,
            "medium_threats": medium,
            "low_threats": low,
            "total_competitors": len(competitors),
            "summary": f"{high} high-threat, {medium} medium-threat, {low} low-threat competitors",
        }

    def _classify_competitor(
        self,
        name: str,
        content: str,
        company_description: str,
    ) -> Competitor:
        """Classify a competitor."""
        # Determine competitor type based on context
        name_lower = name.lower()
        content_lower = content.lower()

        # Check for direct competition indicators
        indirect_indicators = ["indirect", "alternative", "substitute"]

        competitor_type = CompetitorType.DIRECT
        for indicator in indirect_indicators:
            if indicator in content_lower and name_lower in content_lower:
                competitor_type = CompetitorType.INDIRECT
                break

        # Determine market position
        position = MarketPosition.FOLLOWER
        if any(term in content_lower for term in ["market leader", "leading", "dominant"]):
            if name_lower in content_lower:
                position = MarketPosition.LEADER
        elif any(term in content_lower for term in ["challenger", "growing", "aggressive"]):
            position = MarketPosition.CHALLENGER
        elif any(term in content_lower for term in ["niche", "specialized", "focused"]):
            position = MarketPosition.NICHER
        elif any(term in content_lower for term in ["emerging", "startup", "new entrant"]):
            position = MarketPosition.EMERGING

        # Determine threat level
        threat = ThreatLevel.MEDIUM
        if position == MarketPosition.LEADER:
            threat = ThreatLevel.HIGH
        elif position == MarketPosition.EMERGING or competitor_type == CompetitorType.INDIRECT:
            threat = ThreatLevel.LOW

        return Competitor(
            name=name,
            competitor_type=competitor_type,
            market_position=position,
            threat_level=threat,
        )

    def _extract_swot_items(
        self,
        content: str,
        patterns: list[str],
        category: str,
    ) -> list[SWOTItem]:
        """Extract SWOT items using patterns."""
        items: list[SWOTItem] = []
        seen: set[str] = set()

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                text = match if isinstance(match, str) else match[0] if match else ""
                text = text.strip()

                if text and text.lower() not in seen and len(text) > 3:
                    seen.add(text.lower())
                    items.append(SWOTItem(
                        text=text.capitalize(),
                        category=category,
                        confidence=0.7,
                    ))

        return items[:5]  # Limit to 5 items per category

    def _add_industry_insights(
        self,
        swot: SWOTAnalysis,
        industry: str,
        content: str,
    ) -> None:
        """Add industry-specific insights to SWOT."""
        industry_lower = industry.lower()

        # Technology industry
        if "tech" in industry_lower or "software" in industry_lower:
            if "innovation" not in [s.text.lower() for s in swot.strengths]:
                if "innovat" in content.lower():
                    swot.strengths.append(SWOTItem(
                        text="Technology innovation capability",
                        category="strength",
                        confidence=0.6,
                    ))
            if not swot.threats:
                swot.threats.append(SWOTItem(
                    text="Rapid technology changes",
                    category="threat",
                    confidence=0.6,
                ))

        # Finance industry
        elif "financ" in industry_lower or "bank" in industry_lower:
            if not swot.threats:
                swot.threats.append(SWOTItem(
                    text="Regulatory compliance requirements",
                    category="threat",
                    confidence=0.7,
                ))

    def _score_dimension(self, dimension: str, content: str) -> float:
        """Score a company on a dimension based on content."""
        content_lower = content.lower()
        score = 0.5  # Neutral baseline

        positive_terms = {
            "products": ["innovative", "leading", "best-in-class", "award-winning"],
            "market_presence": ["global", "worldwide", "market leader", "dominant"],
            "innovation": ["innovative", "cutting-edge", "pioneering", "r&d"],
            "pricing": ["competitive", "value", "affordable", "cost-effective"],
            "reputation": ["trusted", "respected", "renowned", "established"],
        }

        negative_terms = {
            "products": ["outdated", "limited", "basic"],
            "market_presence": ["small", "limited", "regional"],
            "innovation": ["traditional", "legacy", "slow"],
            "pricing": ["expensive", "premium", "costly"],
            "reputation": ["unknown", "new", "controversial"],
        }

        for term in positive_terms.get(dimension, []):
            if term in content_lower:
                score += 0.1

        for term in negative_terms.get(dimension, []):
            if term in content_lower:
                score -= 0.1

        return max(0.0, min(1.0, score))

    def _detect_industry(self, content: str) -> str:
        """Detect industry from content."""
        content_lower = content.lower()
        scores: dict[str, int] = {}

        for industry, keywords in self.INDUSTRY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scores[industry] = score

        if scores:
            return max(scores, key=lambda k: scores[k])
        return "general"

    def clear_cache(self) -> None:
        """Clear all caches."""
        with self._lock:
            self._competitor_cache.clear()
            self._swot_cache.clear()


# Global instance
_analyzer: CompetitiveAnalyzer | None = None
_analyzer_lock = threading.Lock()


def get_competitive_analyzer() -> CompetitiveAnalyzer:
    """Get the global competitive analyzer instance."""
    global _analyzer
    with _analyzer_lock:
        if _analyzer is None:
            _analyzer = CompetitiveAnalyzer()
        return _analyzer


def reset_competitive_analyzer() -> None:
    """Reset the global analyzer (for testing)."""
    global _analyzer
    with _analyzer_lock:
        _analyzer = None


# Convenience functions
def identify_competitors(
    company_name: str,
    company_description: str,
    content: str,
    max_competitors: int = 10,
) -> list[Competitor]:
    """Identify competitors from content."""
    return get_competitive_analyzer().identify_competitors(
        company_name, company_description, content, max_competitors
    )


def generate_swot(
    company_name: str,
    content: str,
    industry: str | None = None,
) -> SWOTAnalysis:
    """Generate SWOT analysis."""
    return get_competitive_analyzer().generate_swot(company_name, content, industry)


def compare_companies(
    company_name: str,
    company_content: str,
    competitor_name: str,
    competitor_content: str,
) -> CompetitiveComparison:
    """Compare two companies."""
    return get_competitive_analyzer().compare_companies(
        company_name, company_content, competitor_name, competitor_content
    )


def analyze_market(content: str, industry: str | None = None) -> MarketAnalysis:
    """Analyze market from content."""
    return get_competitive_analyzer().analyze_market(content, industry)
