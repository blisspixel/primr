"""
Insight Engine for extracting strategic insights from research data.

Extracts non-obvious insights, identifies risks and opportunities,
and generates actionable recommendations.
"""
import json

from primr.ai.llm import llm
from primr.core.report_models import ConfidenceLevel, GatheredData, Insight, InsightCategory
from primr.utils.formatting import clean_content
from primr.utils.logging_config import get_logger

logger = get_logger("insight_engine")


INSIGHT_EXTRACTION_PROMPT = """Analyze the following research data about {company_name} and extract strategic insights.

Research Data:
{data_summary}

Extract exactly {min_insights} to {max_insights} strategic insights that are:
- Non-obvious (not immediately apparent from the company website)
- Actionable (can inform business decisions)
- Evidence-based (supported by the data)

For each insight, provide:
1. A clear, concise title
2. A detailed description (2-3 sentences)
3. Supporting evidence (specific facts from the data)
4. Confidence level: VERIFIED (from official sources), REPORTED (from news), INFERRED (derived from signals), or ESTIMATED (best guess)
5. Category: STRATEGIC, FINANCIAL, OPERATIONAL, RISK, OPPORTUNITY, COMPETITIVE, TECHNOLOGY, or LEADERSHIP

Return as JSON array:
[
  {{
    "title": "Insight title",
    "description": "Detailed description",
    "evidence": ["Evidence point 1", "Evidence point 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "STRATEGIC|FINANCIAL|OPERATIONAL|RISK|OPPORTUNITY|COMPETITIVE|TECHNOLOGY|LEADERSHIP",
    "sources": ["source1", "source2"]
  }}
]

Return ONLY the JSON array, no other text."""


RISK_IDENTIFICATION_PROMPT = """Analyze the following research data about {company_name} and identify potential risks and vulnerabilities.

Research Data:
{data_summary}

Identify 3-5 strategic risks including:
- Competitive threats
- Market risks
- Operational vulnerabilities
- Financial concerns
- Regulatory or compliance risks

For each risk, provide:
1. A clear title
2. Description of the risk and potential impact
3. Evidence supporting this risk assessment
4. Confidence level

Return as JSON array:
[
  {{
    "title": "Risk title",
    "description": "Risk description and impact",
    "evidence": ["Evidence 1", "Evidence 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "RISK",
    "sources": []
  }}
]

Return ONLY the JSON array, no other text."""


OPPORTUNITY_PROMPT = """Analyze the following research data about {company_name} and identify strategic opportunities.

Research Data:
{data_summary}

Identify 3-5 opportunities including:
- Market expansion possibilities
- Product or service improvements
- Partnership opportunities
- Operational efficiencies
- Technology advantages

For each opportunity, provide:
1. A clear title
2. Description and potential value
3. Evidence supporting this opportunity
4. Confidence level

Return as JSON array:
[
  {{
    "title": "Opportunity title",
    "description": "Opportunity description and value",
    "evidence": ["Evidence 1", "Evidence 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "OPPORTUNITY",
    "sources": []
  }}
]

Return ONLY the JSON array, no other text."""


RECOMMENDATION_PROMPT = """Based on the following insights about {company_name}, generate actionable strategic recommendations.

Insights:
{insights_summary}

Generate exactly {count} recommendations that are:
- Specific and actionable (not generic advice)
- Prioritized by impact and feasibility
- Supported by the insights

For each recommendation, provide:
1. A clear title
2. Detailed description of the recommended action
3. Rationale explaining why this is recommended
4. Evidence from the insights supporting this recommendation

Return as JSON array:
[
  {{
    "title": "Recommendation title",
    "description": "Detailed action description",
    "rationale": "Why this is recommended",
    "evidence": ["Supporting insight 1", "Supporting insight 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "STRATEGIC",
    "sources": []
  }}
]

Return ONLY the JSON array, no other text."""


class InsightEngine:
    """Extracts strategic insights from gathered research data."""

    def __init__(self, model_type: str = "research"):
        self.model_type = model_type

    def _summarize_data(self, data: list[GatheredData], max_chars: int = 10000) -> str:
        """Create a summary of gathered data for prompts."""
        summaries = []
        total_chars = 0

        for item in data:
            if total_chars >= max_chars:
                break

            source_info = f"[{item.source_type.value}] {item.title or item.source_url}"
            content_preview = item.content[:500] if len(item.content) > 500 else item.content
            summary = f"{source_info}\n{content_preview}\n"

            summaries.append(summary)
            total_chars += len(summary)

        return "\n---\n".join(summaries)

    def _parse_insights_response(self, response: str) -> list[Insight]:
        """Parse LLM response into Insight objects."""
        insights = []

        try:
            # Clean up response to extract JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            data = json.loads(response)

            for item in data:
                try:
                    insight = Insight(
                        title=clean_content(item.get("title", "")),
                        description=clean_content(item.get("description", "")),
                        evidence=[clean_content(e) for e in item.get("evidence", [])],
                        confidence=ConfidenceLevel(item.get("confidence", "INFERRED").lower()),
                        category=InsightCategory(item.get("category", "STRATEGIC").lower()),
                        sources=item.get("sources", []),
                        rationale=clean_content(item.get("rationale", "")),
                    )
                    insights.append(insight)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse insight: {e}")
                    continue

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse insights JSON: {e}")

        return insights

    def extract_insights(
        self,
        data: list[GatheredData],
        company_name: str,
        min_insights: int = 5,
        max_insights: int = 8
    ) -> list[Insight]:
        """
        Extract strategic insights from gathered data.

        Args:
            data: List of gathered research data
            company_name: Name of the company being researched
            min_insights: Minimum number of insights to generate
            max_insights: Maximum number of insights to generate

        Returns:
            List of Insight objects
        """
        if not data:
            return []

        data_summary = self._summarize_data(data)

        prompt = INSIGHT_EXTRACTION_PROMPT.format(
            company_name=company_name,
            data_summary=data_summary,
            min_insights=min_insights,
            max_insights=max_insights
        )

        try:
            response = llm(prompt, model_type=self.model_type)
            insights = self._parse_insights_response(response)

            # Ensure minimum insights
            if len(insights) < min_insights:
                logger.warning(f"Only got {len(insights)} insights, expected at least {min_insights}")

            return insights[:max_insights]

        except Exception as e:
            logger.error(f"Failed to extract insights: {e}")
            return []

    def identify_risks(
        self,
        data: list[GatheredData],
        company_name: str
    ) -> list[Insight]:
        """
        Identify potential risks and vulnerabilities.

        Args:
            data: List of gathered research data
            company_name: Name of the company being researched

        Returns:
            List of risk Insights
        """
        if not data:
            return []

        data_summary = self._summarize_data(data)

        prompt = RISK_IDENTIFICATION_PROMPT.format(
            company_name=company_name,
            data_summary=data_summary
        )

        try:
            response = llm(prompt, model_type=self.model_type)
            risks = self._parse_insights_response(response)

            # Ensure all are categorized as risks
            for risk in risks:
                risk.category = InsightCategory.RISK

            return risks

        except Exception as e:
            logger.error(f"Failed to identify risks: {e}")
            return []

    def identify_opportunities(
        self,
        data: list[GatheredData],
        company_name: str
    ) -> list[Insight]:
        """
        Identify strategic opportunities.

        Args:
            data: List of gathered research data
            company_name: Name of the company being researched

        Returns:
            List of opportunity Insights
        """
        if not data:
            return []

        data_summary = self._summarize_data(data)

        prompt = OPPORTUNITY_PROMPT.format(
            company_name=company_name,
            data_summary=data_summary
        )

        try:
            response = llm(prompt, model_type=self.model_type)
            opportunities = self._parse_insights_response(response)

            # Ensure all are categorized as opportunities
            for opp in opportunities:
                opp.category = InsightCategory.OPPORTUNITY

            return opportunities

        except Exception as e:
            logger.error(f"Failed to identify opportunities: {e}")
            return []

    def generate_recommendations(
        self,
        insights: list[Insight],
        company_name: str,
        count: int = 5
    ) -> list[Insight]:
        """
        Generate actionable recommendations based on insights.

        Args:
            insights: List of insights to base recommendations on
            company_name: Name of the company
            count: Number of recommendations to generate (3-5)

        Returns:
            List of recommendation Insights with rationale
        """
        if not insights:
            return []

        # Ensure count is in valid range
        count = max(3, min(5, count))

        # Summarize insights for the prompt
        insights_summary = "\n".join([
            f"- {i.title}: {i.description}"
            for i in insights
        ])

        prompt = RECOMMENDATION_PROMPT.format(
            company_name=company_name,
            insights_summary=insights_summary,
            count=count
        )

        try:
            response = llm(prompt, model_type=self.model_type)
            recommendations = self._parse_insights_response(response)

            # Ensure all have rationale and are categorized as strategic
            for rec in recommendations:
                rec.category = InsightCategory.STRATEGIC
                if not rec.rationale:
                    rec.rationale = rec.description

            return recommendations[:count]

        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            return []

    def analyze_competitive_position(
        self,
        company_name: str,
        competitors: list[str],
        data: list[GatheredData] | None = None
    ) -> list[Insight]:
        """
        Analyze competitive positioning.

        Args:
            company_name: Name of the company
            competitors: List of competitor names
            data: Optional gathered data about competitors

        Returns:
            List of competitive insights
        """
        if not competitors:
            return []

        data_summary = self._summarize_data(data) if data else "No additional data available."

        prompt = f"""Analyze the competitive position of {company_name} against these competitors: {', '.join(competitors)}.

Additional Research Data:
{data_summary}

Provide 3-5 competitive insights covering:
- Market positioning differences
- Competitive advantages and disadvantages
- Potential competitive threats
- Differentiation opportunities

Return as JSON array:
[
  {{
    "title": "Competitive insight title",
    "description": "Detailed analysis",
    "evidence": ["Evidence 1", "Evidence 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "COMPETITIVE",
    "sources": []
  }}
]

Return ONLY the JSON array, no other text."""

        try:
            response = llm(prompt, model_type=self.model_type)
            insights = self._parse_insights_response(response)

            for insight in insights:
                insight.category = InsightCategory.COMPETITIVE

            return insights

        except Exception as e:
            logger.error(f"Failed to analyze competitive position: {e}")
            return []


FINANCIAL_ANALYSIS_PROMPT = """Analyze the financial data for {company_name}.

Available Financial Data:
{financial_data}

Research Data:
{data_summary}

Extract financial insights including:
1. Revenue and growth metrics (if available)
2. Profitability indicators
3. Funding history (for private companies)
4. Financial health assessment
5. Comparison to industry benchmarks

For estimated data, clearly indicate confidence level.

Return as JSON array:
[
  {{
    "title": "Financial insight title",
    "description": "Detailed analysis",
    "evidence": ["Evidence 1", "Evidence 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "FINANCIAL",
    "sources": []
  }}
]

Return ONLY the JSON array, no other text."""


COMPETITOR_ANALYSIS_PROMPT = """Identify and analyze competitors for {company_name} in the {industry} industry.

Company Information:
{company_info}

Research Data:
{data_summary}

Identify at least 5 competitors and analyze:
1. Direct competitors (same products/services)
2. Indirect competitors (alternative solutions)
3. Market positioning of each
4. Competitive advantages and disadvantages
5. Threat level assessment

Return as JSON array:
[
  {{
    "title": "Competitor name or competitive insight",
    "description": "Analysis of competitive position",
    "evidence": ["Evidence 1", "Evidence 2"],
    "confidence": "VERIFIED|REPORTED|INFERRED|ESTIMATED",
    "category": "COMPETITIVE",
    "sources": []
  }}
]

Return ONLY the JSON array, no other text."""


class FinancialAnalyzer:
    """Analyzes financial data and generates financial insights."""

    def __init__(self, insight_engine: InsightEngine):
        self.engine = insight_engine

    def analyze_financials(
        self,
        company_name: str,
        financial_data: dict,
        gathered_data: list[GatheredData]
    ) -> list[Insight]:
        """
        Analyze financial data and generate insights.

        Args:
            company_name: Name of the company
            financial_data: Dictionary of financial metrics
            gathered_data: Additional research data

        Returns:
            List of financial insights
        """
        if not financial_data and not gathered_data:
            return []

        data_summary = self.engine._summarize_data(gathered_data) if gathered_data else ""

        # Format financial data for prompt
        financial_str = ""
        if financial_data:
            for key, value in financial_data.items():
                if isinstance(value, int | float) and value >= 1000:
                    from primr.utils.formatting import format_currency
                    formatted = format_currency(value) if "revenue" in key.lower() or "funding" in key.lower() else str(value)
                    financial_str += f"- {key}: {formatted}\n"
                else:
                    financial_str += f"- {key}: {value}\n"
        else:
            financial_str = "No structured financial data available. Estimate from research data."

        prompt = FINANCIAL_ANALYSIS_PROMPT.format(
            company_name=company_name,
            financial_data=financial_str,
            data_summary=data_summary
        )

        try:
            response = llm(prompt, model_type=self.engine.model_type)
            insights = self.engine._parse_insights_response(response)

            # Ensure all are categorized as financial
            for insight in insights:
                insight.category = InsightCategory.FINANCIAL

            return insights

        except Exception as e:
            logger.error(f"Failed to analyze financials: {e}")
            return []

    def estimate_company_size(
        self,
        company_name: str,
        employee_count: int | None = None,
        funding_rounds: list[dict] | None = None,
        gathered_data: list[GatheredData] | None = None
    ) -> Insight:
        """
        Estimate company size when financials are unavailable.

        Args:
            company_name: Name of the company
            employee_count: Number of employees if known
            funding_rounds: List of funding round info
            gathered_data: Additional research data

        Returns:
            Insight with size estimation
        """
        evidence = []
        estimation_basis = []

        if employee_count:
            evidence.append(f"Employee count: {employee_count}")
            # Rough revenue estimation based on employee count
            # Tech companies: ~$200K-$500K revenue per employee
            low_estimate = employee_count * 200000
            high_estimate = employee_count * 500000
            estimation_basis.append(f"Based on {employee_count} employees, estimated revenue range: ${low_estimate/1e6:.1f}M - ${high_estimate/1e6:.1f}M")

        if funding_rounds:
            total_funding = sum(r.get("amount", 0) for r in funding_rounds)
            evidence.append(f"Total funding raised: ${total_funding/1e6:.1f}M")
            estimation_basis.append("Funding history suggests growth-stage company")

        description = f"Company size estimation for {company_name}. " + " ".join(estimation_basis)

        return Insight(
            title=f"{company_name} Size Estimation",
            description=clean_content(description),
            evidence=evidence,
            confidence=ConfidenceLevel.ESTIMATED,
            category=InsightCategory.FINANCIAL,
            sources=[],
            rationale="Estimated based on available signals when direct financial data unavailable"
        )


class CompetitorAnalyzer:
    """Analyzes competitive landscape."""

    def __init__(self, insight_engine: InsightEngine):
        self.engine = insight_engine

    def identify_competitors(
        self,
        company_name: str,
        industry: str,
        company_info: str,
        gathered_data: list[GatheredData],
        min_competitors: int = 5
    ) -> list[Insight]:
        """
        Identify and analyze competitors.

        Args:
            company_name: Name of the company
            industry: Industry sector
            company_info: Brief company description
            gathered_data: Research data
            min_competitors: Minimum number of competitors to identify

        Returns:
            List of competitive insights
        """
        data_summary = self.engine._summarize_data(gathered_data) if gathered_data else ""

        prompt = COMPETITOR_ANALYSIS_PROMPT.format(
            company_name=company_name,
            industry=industry,
            company_info=company_info,
            data_summary=data_summary
        )

        try:
            response = llm(prompt, model_type=self.engine.model_type)
            insights = self.engine._parse_insights_response(response)

            # Ensure all are categorized as competitive
            for insight in insights:
                insight.category = InsightCategory.COMPETITIVE

            # Log warning if fewer than minimum competitors
            if len(insights) < min_competitors:
                logger.warning(f"Only identified {len(insights)} competitors, expected at least {min_competitors}")

            return insights

        except Exception as e:
            logger.error(f"Failed to identify competitors: {e}")
            return []

    def generate_competitive_matrix(
        self,
        company_name: str,
        competitors: list[str],
        criteria: list[str]
    ) -> dict:
        """
        Generate a competitive comparison matrix.

        Args:
            company_name: Name of the company
            competitors: List of competitor names
            criteria: Comparison criteria

        Returns:
            Dictionary with competitive matrix data
        """
        # This would typically call an LLM to fill in the matrix
        # For now, return a structure that can be populated
        matrix = {
            "company": company_name,
            "competitors": competitors,
            "criteria": criteria,
            "scores": {}  # Would be populated with actual analysis
        }
        return matrix
