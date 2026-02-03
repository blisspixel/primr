"""
Analyst Subagent for insight synthesis and hypothesis generation.

This subagent handles the analysis phase of the research pipeline,
including insight extraction, hypothesis generation, and confidence
scoring.

Responsibilities:
    - Synthesize insights from scraped content
    - Generate testable hypotheses from insights
    - Score confidence levels for each hypothesis
    - Track evidence supporting hypotheses

Integration:
    Delegates to the existing primr.ai.summarize pipeline for
    insight generation, then applies hypothesis extraction logic.

Example:
    context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
        parent_results={"corpus_path": Path("./output/acme/corpus")},
    )
    analyst = AnalystSubagent(context)
    result = await analyst.execute()

    if result.is_success:
        print(f"Generated {len(result.hypotheses)} hypotheses")
        for h in result.hypotheses:
            print(f"  - {h.claim} ({h.confidence.value})")
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from primr.agentic.errors import SubagentError
from primr.agentic.models import ConfidenceLevel, Hypothesis
from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT DATA CLASS
# =============================================================================

@dataclass
class AnalysisResult:
    """
    Result data from analysis operation.

    Attributes:
        insights_path: Path to the generated insights file
        hypotheses: List of generated hypotheses
        confidence_scores: Confidence score for each hypothesis ID
        topics_identified: List of topics found in the content
        key_findings: Summary of key findings
    """

    insights_path: Path
    hypotheses: list[Hypothesis] = field(default_factory=list)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    topics_identified: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)

    @property
    def hypothesis_count(self) -> int:
        """Get the number of hypotheses generated."""
        return len(self.hypotheses)

    @property
    def average_confidence(self) -> float:
        """Calculate average confidence score."""
        if not self.confidence_scores:
            return 0.0
        return sum(self.confidence_scores.values()) / len(self.confidence_scores)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "insights_path": str(self.insights_path),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "confidence_scores": self.confidence_scores,
            "topics_identified": self.topics_identified,
            "key_findings": self.key_findings,
            "hypothesis_count": self.hypothesis_count,
            "average_confidence": self.average_confidence,
        }


# =============================================================================
# ANALYST SUBAGENT
# =============================================================================

class AnalystSubagent(Subagent[AnalysisResult]):
    """
    Subagent for insight synthesis and hypothesis generation.

    Analyzes scraped content to extract insights and generate
    testable hypotheses with confidence scores.

    Hypothesis Generation:
        1. Extract claims from insights
        2. Classify claims by topic
        3. Assign initial confidence (UNTESTED)
        4. Set expiration for time-sensitive claims

    Confidence Levels:
        - UNTESTED: Initial state, no validation
        - VALIDATED: Evidence supports the claim
        - INVALIDATED: Evidence contradicts the claim
        - CONFIRMED: Strong evidence, high confidence

    Example:
        analyst = AnalystSubagent(context)
        result = await analyst.execute()

        # Access generated hypotheses
        for h in result.hypotheses:
            print(f"{h.claim}: {h.confidence.value}")
    """

    # Topic keywords for classification
    TOPIC_KEYWORDS: dict[str, list[str]] = {
        "technology": [
            "software", "platform", "api", "cloud", "data", "ai",
            "machine learning", "infrastructure", "architecture",
        ],
        "financials": [
            "revenue", "profit", "growth", "funding", "valuation",
            "investment", "market", "sales",
        ],
        "leadership": [
            "ceo", "cto", "founder", "executive", "management",
            "board", "leadership", "team",
        ],
        "products": [
            "product", "service", "solution", "offering", "feature",
            "launch", "release",
        ],
        "culture": [
            "culture", "values", "mission", "vision", "employee",
            "workplace", "diversity",
        ],
    }

    def __init__(
        self,
        context: SubagentContext,
        hypothesis_expiry_days: int = 90,
    ):
        """
        Initialize analyst subagent.

        Args:
            context: Subagent context
            hypothesis_expiry_days: Days until hypotheses expire
        """
        super().__init__(context, name="AnalystSubagent")
        self._hypothesis_expiry_days = hypothesis_expiry_days

    @property
    def hypothesis_expiry_days(self) -> int:
        """Get hypothesis expiry period in days."""
        return self._hypothesis_expiry_days

    async def execute(self) -> SubagentResult[AnalysisResult]:
        """
        Execute analysis and hypothesis generation.

        Returns:
            SubagentResult containing AnalysisResult on success
        """
        self._status = SubagentStatus.RUNNING
        start_time = time.time()

        logger.info(f"AnalystSubagent starting for {self.company_name}")

        try:
            # Get corpus path from parent results
            corpus_path = self._context.get_parent_result("corpus_path")
            if corpus_path is None:
                raise SubagentError(
                    message="No corpus_path in parent results",
                    subagent="analyst",
                )

            if isinstance(corpus_path, str):
                corpus_path = Path(corpus_path)

            # Generate insights
            insights_path, insights_data = await self._generate_insights(corpus_path)

            # Generate hypotheses from insights
            hypotheses = self._generate_hypotheses(insights_data)

            # Score confidence
            confidence_scores = self._score_confidence(hypotheses)

            # Extract topics and findings
            topics = self._extract_topics(insights_data)
            findings = self._extract_key_findings(insights_data)

            duration = time.time() - start_time
            self._status = SubagentStatus.COMPLETED

            logger.info(
                f"AnalystSubagent completed for {self.company_name}: "
                f"{len(hypotheses)} hypotheses in {duration:.1f}s"
            )

            result = AnalysisResult(
                insights_path=insights_path,
                hypotheses=hypotheses,
                confidence_scores=confidence_scores,
                topics_identified=topics,
                key_findings=findings,
            )

            return SubagentResult(
                status=self._status,
                data=result,
                hypotheses=hypotheses,
                metrics={
                    "duration_seconds": duration,
                    "hypothesis_count": len(hypotheses),
                    "average_confidence": result.average_confidence,
                },
            )

        except SubagentError:
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._status = SubagentStatus.FAILED

            logger.error(f"AnalystSubagent failed for {self.company_name}: {e}")

            return SubagentResult(
                status=self._status,
                error=str(e),
                metrics={"duration_seconds": duration},
            )

    async def _generate_insights(
        self,
        corpus_path: Path,
    ) -> tuple[Path, dict[str, Any]]:
        """
        Generate insights from corpus.

        Args:
            corpus_path: Path to scraped content corpus

        Returns:
            Tuple of (insights_path, insights_data)
        """
        try:
            from primr.ai.summarize import summarize_scraped_content

            # Load corpus content
            if corpus_path.is_file():
                corpus_content = corpus_path.read_text(encoding="utf-8")
                # Parse as dict mapping URL -> content
                scraped_data = {"corpus": corpus_content}
            elif corpus_path.is_dir():
                # Load all files in directory
                scraped_data = {}
                for file in corpus_path.glob("*.txt"):
                    scraped_data[file.name] = file.read_text(encoding="utf-8")
            else:
                scraped_data = {}

            # summarize_scraped_content is synchronous
            summarize_scraped_content(
                company_name=self.company_name,
                company_website=self.company_url,
                scraped_data=scraped_data,
                folder_path=str(self.working_dir),
            )

            insights_path = self.working_dir / "scraped_website_summary.txt"
            insights_data: dict[str, Any] = {}

            if insights_path.exists():
                content = insights_path.read_text(encoding="utf-8")
                # Extract key points as claims
                insights_data["claims"] = [
                    line.strip("- ").strip()
                    for line in content.split("\n")
                    if line.strip().startswith("-")
                ]

            return insights_path, insights_data

        except ImportError:
            # Summarize module not available - return mock result
            logger.warning(
                "primr.ai.summarize not available, returning mock insights"
            )
            insights_path = self.working_dir / "insights.md"
            insights_path.parent.mkdir(parents=True, exist_ok=True)
            insights_path.write_text(
                f"# Insights for {self.company_name}\n\nNo insights available.",
                encoding="utf-8",
            )

            return insights_path, {}

    def _generate_hypotheses(self, insights_data: dict[str, Any]) -> list[Hypothesis]:
        """
        Generate hypotheses from insights.

        Args:
            insights_data: Structured insights data

        Returns:
            List of generated hypotheses
        """
        hypotheses: list[Hypothesis] = []

        # Extract claims from insights
        claims = insights_data.get("claims", [])
        if not claims:
            # Generate placeholder hypotheses if no claims
            claims = insights_data.get("key_points", [])

        for claim in claims:
            if isinstance(claim, str) and claim.strip():
                hypothesis = Hypothesis(
                    id=f"h_{uuid.uuid4().hex[:8]}",
                    claim=claim.strip(),
                    confidence=ConfidenceLevel.UNTESTED,
                    topic=self._classify_topic(claim),
                    expires_at=datetime.now() + timedelta(days=self._hypothesis_expiry_days),
                )
                hypotheses.append(hypothesis)

        return hypotheses

    def _classify_topic(self, claim: str) -> str:
        """
        Classify a claim into a topic.

        Args:
            claim: The claim text

        Returns:
            Topic name
        """
        claim_lower = claim.lower()

        for topic, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in claim_lower for kw in keywords):
                return topic

        return "general"

    def _score_confidence(self, hypotheses: list[Hypothesis]) -> dict[str, float]:
        """
        Score confidence for each hypothesis.

        Initial scoring is based on:
        - Evidence count
        - Topic specificity
        - Claim clarity

        Args:
            hypotheses: List of hypotheses to score

        Returns:
            Dictionary mapping hypothesis ID to confidence score (0-1)
        """
        scores: dict[str, float] = {}

        for h in hypotheses:
            # Base score for untested hypotheses
            score = 0.5

            # Adjust based on evidence
            score += min(len(h.evidence) * 0.1, 0.3)

            # Adjust based on topic (specific topics score higher)
            if h.topic != "general":
                score += 0.1

            # Adjust based on claim length (moderate length is better)
            claim_len = len(h.claim)
            if 20 <= claim_len <= 200:
                score += 0.1

            scores[h.id] = min(score, 1.0)

        return scores

    def _extract_topics(self, insights_data: dict[str, Any]) -> list[str]:
        """
        Extract topics from insights.

        Args:
            insights_data: Structured insights data

        Returns:
            List of identified topics
        """
        topics = set(insights_data.get("topics", []))

        # Also extract from claims
        for claim in insights_data.get("claims", []):
            if isinstance(claim, str):
                topic = self._classify_topic(claim)
                if topic != "general":
                    topics.add(topic)

        return sorted(topics)

    def _extract_key_findings(self, insights_data: dict[str, Any]) -> list[str]:
        """
        Extract key findings from insights.

        Args:
            insights_data: Structured insights data

        Returns:
            List of key findings
        """
        findings: list[Any] = insights_data.get("key_findings", [])
        if not findings:
            findings = insights_data.get("summary", [])
        if isinstance(findings, str):
            findings = [findings]
        # Filter to strings and limit
        result: list[str] = [str(f) for f in findings[:10] if f]
        return result

    def get_required_tools(self) -> list[str]:
        """
        Return list of MCP tools this subagent needs.

        AnalystSubagent uses the internal pipeline, not MCP tools.

        Returns:
            Empty list (uses internal pipeline)
        """
        return []
