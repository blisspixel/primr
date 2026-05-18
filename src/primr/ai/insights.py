"""
Predictive insights module.

Provides risk assessment, opportunity identification, and strategic recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
from typing import Any


class RiskCategory(Enum):
    """Categories of business risk."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    MARKET = "market"
    REGULATORY = "regulatory"
    REPUTATIONAL = "reputational"
    TECHNOLOGY = "technology"
    COMPETITIVE = "competitive"
    STRATEGIC = "strategic"


class RiskLevel(Enum):
    """Risk severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class OpportunityType(Enum):
    """Types of business opportunities."""

    MARKET_EXPANSION = "market_expansion"
    PRODUCT_INNOVATION = "product_innovation"
    PARTNERSHIP = "partnership"
    ACQUISITION = "acquisition"
    COST_REDUCTION = "cost_reduction"
    TECHNOLOGY = "technology"
    TALENT = "talent"
    REGULATORY = "regulatory"


class RecommendationType(Enum):
    """Types of strategic recommendations."""

    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    CONTINGENCY = "contingency"


@dataclass
class Risk:
    """An identified business risk."""

    risk_id: str
    category: RiskCategory
    level: RiskLevel
    title: str
    description: str
    likelihood: float = 0.5  # 0-1
    impact: float = 0.5  # 0-1
    mitigations: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    confidence: float = 0.7

    @property
    def risk_score(self) -> float:
        """Calculate risk score (likelihood * impact)."""
        return self.likelihood * self.impact

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "risk_id": self.risk_id,
            "category": self.category.value,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "risk_score": self.risk_score,
            "mitigations": self.mitigations,
            "confidence": self.confidence,
        }


@dataclass
class Opportunity:
    """An identified business opportunity."""

    opportunity_id: str
    opportunity_type: OpportunityType
    title: str
    description: str
    potential_value: str = ""  # e.g., "$10M revenue"
    timeframe: str = ""  # e.g., "6-12 months"
    requirements: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "opportunity_id": self.opportunity_id,
            "type": self.opportunity_type.value,
            "title": self.title,
            "description": self.description,
            "potential_value": self.potential_value,
            "timeframe": self.timeframe,
            "requirements": self.requirements,
            "risks": self.risks,
            "confidence": self.confidence,
        }


@dataclass
class Recommendation:
    """A strategic recommendation."""

    recommendation_id: str
    recommendation_type: RecommendationType
    title: str
    description: str
    rationale: str = ""
    priority: int = 5  # 1-10, higher = more important
    effort: str = ""  # e.g., "Low", "Medium", "High"
    expected_outcome: str = ""
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "recommendation_id": self.recommendation_id,
            "type": self.recommendation_type.value,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "priority": self.priority,
            "effort": self.effort,
            "expected_outcome": self.expected_outcome,
        }


@dataclass
class InsightReport:
    """Complete insights report for a company."""

    company_name: str
    risks: list[Risk] = field(default_factory=list)
    opportunities: list[Opportunity] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def get_summary(self) -> dict[str, Any]:
        """Get summary of insights."""
        return {
            "company_name": self.company_name,
            "total_risks": len(self.risks),
            "critical_risks": sum(1 for r in self.risks if r.level == RiskLevel.CRITICAL),
            "high_risks": sum(1 for r in self.risks if r.level == RiskLevel.HIGH),
            "total_opportunities": len(self.opportunities),
            "total_recommendations": len(self.recommendations),
            "generated_at": self.generated_at.isoformat(),
        }


class InsightAnalyzer:
    """Analyzes content to generate predictive insights."""

    # Risk indicators by category
    RISK_INDICATORS = {
        RiskCategory.FINANCIAL: [
            ("debt", "high debt levels", RiskLevel.HIGH),
            ("loss", "financial losses", RiskLevel.HIGH),
            ("declining revenue", "revenue decline", RiskLevel.HIGH),
            ("cash flow", "cash flow concerns", RiskLevel.MEDIUM),
            ("credit", "credit risk", RiskLevel.MEDIUM),
        ],
        RiskCategory.OPERATIONAL: [
            ("supply chain", "supply chain disruption", RiskLevel.HIGH),
            ("outage", "service outages", RiskLevel.HIGH),
            ("shortage", "resource shortages", RiskLevel.MEDIUM),
            ("delay", "operational delays", RiskLevel.MEDIUM),
        ],
        RiskCategory.MARKET: [
            ("market share loss", "declining market share", RiskLevel.HIGH),
            ("competition", "competitive pressure", RiskLevel.MEDIUM),
            ("demand", "demand fluctuation", RiskLevel.MEDIUM),
            ("pricing pressure", "pricing challenges", RiskLevel.MEDIUM),
        ],
        RiskCategory.REGULATORY: [
            ("lawsuit", "legal action", RiskLevel.HIGH),
            ("investigation", "regulatory investigation", RiskLevel.HIGH),
            ("compliance", "compliance issues", RiskLevel.MEDIUM),
            ("regulation", "regulatory changes", RiskLevel.MEDIUM),
            ("fine", "regulatory fines", RiskLevel.HIGH),
        ],
        RiskCategory.REPUTATIONAL: [
            ("scandal", "reputation damage", RiskLevel.CRITICAL),
            ("controversy", "public controversy", RiskLevel.HIGH),
            ("criticism", "public criticism", RiskLevel.MEDIUM),
            ("negative press", "negative media coverage", RiskLevel.MEDIUM),
        ],
        RiskCategory.TECHNOLOGY: [
            ("breach", "security breach", RiskLevel.CRITICAL),
            ("hack", "cyber attack", RiskLevel.CRITICAL),
            ("vulnerability", "security vulnerability", RiskLevel.HIGH),
            ("legacy system", "technology debt", RiskLevel.MEDIUM),
            ("outage", "system downtime", RiskLevel.MEDIUM),
        ],
    }

    # Opportunity indicators
    OPPORTUNITY_INDICATORS = {
        OpportunityType.MARKET_EXPANSION: [
            "new market",
            "expansion",
            "international",
            "global",
            "emerging market",
        ],
        OpportunityType.PRODUCT_INNOVATION: [
            "innovation",
            "new product",
            "r&d",
            "patent",
            "breakthrough",
        ],
        OpportunityType.PARTNERSHIP: ["partnership", "collaboration", "alliance", "joint venture"],
        OpportunityType.ACQUISITION: ["acquisition target", "merger opportunity", "consolidation"],
        OpportunityType.COST_REDUCTION: [
            "efficiency",
            "automation",
            "cost savings",
            "optimization",
        ],
        OpportunityType.TECHNOLOGY: [
            "digital transformation",
            "ai adoption",
            "cloud migration",
            "modernization",
        ],
    }

    def __init__(self):
        """Initialize the analyzer."""
        self._lock = threading.Lock()
        self._id_counter = 0

    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID."""
        with self._lock:
            self._id_counter += 1
            return f"{prefix}_{self._id_counter}"

    def assess_risks(
        self,
        company_name: str,
        content: str,
    ) -> list[Risk]:
        """Assess risks from content.

        Args:
            company_name: Company name
            content: Text content to analyze

        Returns:
            List of identified risks
        """
        risks: list[Risk] = []
        content_lower = content.lower()
        seen_titles: set[str] = set()

        for category, indicators in self.RISK_INDICATORS.items():
            for keyword, title, level in indicators:
                if keyword in content_lower and title not in seen_titles:
                    seen_titles.add(title)

                    # Extract context
                    description = self._extract_context(content, keyword)

                    # Determine likelihood and impact
                    likelihood, impact = self._assess_risk_factors(content_lower, keyword, level)

                    risk = Risk(
                        risk_id=self._generate_id("risk"),
                        category=category,
                        level=level,
                        title=title.capitalize(),
                        description=description,
                        likelihood=likelihood,
                        impact=impact,
                        mitigations=self._suggest_mitigations(category, title),
                    )
                    risks.append(risk)

        # Sort by risk score
        risks.sort(key=lambda r: r.risk_score, reverse=True)
        return risks[:10]  # Top 10 risks

    def identify_opportunities(
        self,
        company_name: str,
        content: str,
    ) -> list[Opportunity]:
        """Identify opportunities from content.

        Args:
            company_name: Company name
            content: Text content to analyze

        Returns:
            List of identified opportunities
        """
        opportunities: list[Opportunity] = []
        content_lower = content.lower()
        seen_types: set[OpportunityType] = set()

        for opp_type, keywords in self.OPPORTUNITY_INDICATORS.items():
            if opp_type in seen_types:
                continue

            for keyword in keywords:
                if keyword in content_lower:
                    seen_types.add(opp_type)

                    description = self._extract_context(content, keyword)

                    opportunity = Opportunity(
                        opportunity_id=self._generate_id("opp"),
                        opportunity_type=opp_type,
                        title=self._format_opportunity_title(opp_type),
                        description=description,
                        timeframe=self._estimate_timeframe(opp_type),
                        requirements=self._identify_requirements(opp_type),
                    )
                    opportunities.append(opportunity)
                    break

        return opportunities

    def generate_recommendations(
        self,
        company_name: str,
        risks: list[Risk],
        opportunities: list[Opportunity],
    ) -> list[Recommendation]:
        """Generate strategic recommendations.

        Args:
            company_name: Company name
            risks: Identified risks
            opportunities: Identified opportunities

        Returns:
            List of recommendations
        """
        recommendations: list[Recommendation] = []

        # Risk-based recommendations
        for risk in risks[:5]:  # Top 5 risks
            if risk.level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                rec = Recommendation(
                    recommendation_id=self._generate_id("rec"),
                    recommendation_type=RecommendationType.IMMEDIATE,
                    title=f"Address {risk.title}",
                    description=f"Implement mitigation strategies for {risk.title.lower()}",
                    rationale=f"Risk score: {risk.risk_score:.2f}",
                    priority=9 if risk.level == RiskLevel.CRITICAL else 7,
                    effort="High" if risk.level == RiskLevel.CRITICAL else "Medium",
                    expected_outcome=f"Reduced {risk.category.value} risk exposure",
                )
                recommendations.append(rec)

        # Opportunity-based recommendations
        for opp in opportunities[:3]:  # Top 3 opportunities
            rec = Recommendation(
                recommendation_id=self._generate_id("rec"),
                recommendation_type=RecommendationType.SHORT_TERM,
                title=f"Pursue {opp.title}",
                description=f"Develop strategy to capitalize on {opp.title.lower()}",
                rationale=f"Potential value: {opp.potential_value or 'Significant'}",
                priority=6,
                effort="Medium",
                expected_outcome=opp.title,
            )
            recommendations.append(rec)

        # Sort by priority
        recommendations.sort(key=lambda r: r.priority, reverse=True)
        return recommendations

    def generate_insights(
        self,
        company_name: str,
        content: str,
    ) -> InsightReport:
        """Generate complete insights report.

        Args:
            company_name: Company name
            content: Text content to analyze

        Returns:
            Complete insight report
        """
        risks = self.assess_risks(company_name, content)
        opportunities = self.identify_opportunities(company_name, content)
        recommendations = self.generate_recommendations(company_name, risks, opportunities)

        return InsightReport(
            company_name=company_name,
            risks=risks,
            opportunities=opportunities,
            recommendations=recommendations,
        )

    def _extract_context(self, content: str, keyword: str) -> str:
        """Extract context around a keyword."""
        sentences = content.replace("\n", " ").split(".")
        for sentence in sentences:
            if keyword in sentence.lower():
                return sentence.strip()[:300]
        return f"Related to {keyword}"

    def _assess_risk_factors(
        self,
        content: str,
        keyword: str,
        base_level: RiskLevel,
    ) -> tuple[float, float]:
        """Assess likelihood and impact factors."""
        # Base values by level
        level_factors = {
            RiskLevel.CRITICAL: (0.8, 0.9),
            RiskLevel.HIGH: (0.7, 0.7),
            RiskLevel.MEDIUM: (0.5, 0.5),
            RiskLevel.LOW: (0.3, 0.3),
            RiskLevel.MINIMAL: (0.1, 0.2),
        }
        likelihood, impact = level_factors.get(base_level, (0.5, 0.5))

        # Adjust based on urgency words
        if any(word in content for word in ["immediate", "urgent", "critical"]):
            likelihood = min(1.0, likelihood + 0.1)
        if any(word in content for word in ["significant", "major", "substantial"]):
            impact = min(1.0, impact + 0.1)

        return likelihood, impact

    def _suggest_mitigations(
        self,
        category: RiskCategory,
        title: str,
    ) -> list[str]:
        """Suggest risk mitigations."""
        mitigations = {
            RiskCategory.FINANCIAL: [
                "Review financial controls",
                "Diversify revenue streams",
                "Strengthen cash reserves",
            ],
            RiskCategory.OPERATIONAL: [
                "Develop contingency plans",
                "Diversify suppliers",
                "Implement redundancy",
            ],
            RiskCategory.MARKET: [
                "Enhance competitive positioning",
                "Invest in customer retention",
                "Explore new markets",
            ],
            RiskCategory.REGULATORY: [
                "Strengthen compliance program",
                "Engage legal counsel",
                "Monitor regulatory changes",
            ],
            RiskCategory.REPUTATIONAL: [
                "Develop crisis communication plan",
                "Enhance stakeholder engagement",
                "Monitor public sentiment",
            ],
            RiskCategory.TECHNOLOGY: [
                "Enhance security measures",
                "Implement regular audits",
                "Develop incident response plan",
            ],
        }
        return mitigations.get(category, ["Develop mitigation strategy"])

    def _format_opportunity_title(self, opp_type: OpportunityType) -> str:
        """Format opportunity title."""
        titles = {
            OpportunityType.MARKET_EXPANSION: "Market Expansion Opportunity",
            OpportunityType.PRODUCT_INNOVATION: "Product Innovation Potential",
            OpportunityType.PARTNERSHIP: "Strategic Partnership Opportunity",
            OpportunityType.ACQUISITION: "Acquisition Opportunity",
            OpportunityType.COST_REDUCTION: "Cost Optimization Opportunity",
            OpportunityType.TECHNOLOGY: "Technology Advancement Opportunity",
            OpportunityType.TALENT: "Talent Acquisition Opportunity",
            OpportunityType.REGULATORY: "Regulatory Advantage Opportunity",
        }
        return titles.get(opp_type, "Business Opportunity")

    def _estimate_timeframe(self, opp_type: OpportunityType) -> str:
        """Estimate timeframe for opportunity."""
        timeframes = {
            OpportunityType.MARKET_EXPANSION: "12-24 months",
            OpportunityType.PRODUCT_INNOVATION: "6-18 months",
            OpportunityType.PARTNERSHIP: "3-6 months",
            OpportunityType.ACQUISITION: "6-12 months",
            OpportunityType.COST_REDUCTION: "3-12 months",
            OpportunityType.TECHNOLOGY: "6-18 months",
        }
        return timeframes.get(opp_type, "6-12 months")

    def _identify_requirements(self, opp_type: OpportunityType) -> list[str]:
        """Identify requirements for opportunity."""
        requirements = {
            OpportunityType.MARKET_EXPANSION: [
                "Market research",
                "Local partnerships",
                "Regulatory compliance",
            ],
            OpportunityType.PRODUCT_INNOVATION: [
                "R&D investment",
                "Customer feedback",
                "Technical expertise",
            ],
            OpportunityType.PARTNERSHIP: [
                "Partner identification",
                "Due diligence",
                "Contract negotiation",
            ],
            OpportunityType.ACQUISITION: [
                "Target identification",
                "Financial analysis",
                "Integration planning",
            ],
            OpportunityType.COST_REDUCTION: [
                "Process analysis",
                "Technology investment",
                "Change management",
            ],
            OpportunityType.TECHNOLOGY: [
                "Technology assessment",
                "Vendor evaluation",
                "Implementation planning",
            ],
        }
        return requirements.get(opp_type, ["Strategic planning"])


# Global instance
_analyzer: InsightAnalyzer | None = None
_analyzer_lock = threading.Lock()


def get_insight_analyzer() -> InsightAnalyzer:
    """Get the global insight analyzer instance."""
    global _analyzer
    with _analyzer_lock:
        if _analyzer is None:
            _analyzer = InsightAnalyzer()
        return _analyzer


def reset_insight_analyzer() -> None:
    """Reset the global analyzer (for testing)."""
    global _analyzer
    with _analyzer_lock:
        _analyzer = None


# Convenience functions
def assess_risks(company_name: str, content: str) -> list[Risk]:
    """Assess risks from content."""
    return get_insight_analyzer().assess_risks(company_name, content)


def identify_opportunities(company_name: str, content: str) -> list[Opportunity]:
    """Identify opportunities from content."""
    return get_insight_analyzer().identify_opportunities(company_name, content)


def generate_recommendations(
    company_name: str,
    risks: list[Risk],
    opportunities: list[Opportunity],
) -> list[Recommendation]:
    """Generate strategic recommendations."""
    return get_insight_analyzer().generate_recommendations(company_name, risks, opportunities)


def generate_insights(company_name: str, content: str) -> InsightReport:
    """Generate complete insights report."""
    return get_insight_analyzer().generate_insights(company_name, content)
