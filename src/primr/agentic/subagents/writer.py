"""
Writer Subagent for report generation.

This subagent handles the writing phase of the research pipeline,
generating comprehensive research reports with proper citations
and formatting.

Responsibilities:
    - Generate structured research reports
    - Include citations and evidence
    - Format output in markdown
    - Track report metadata

Integration:
    Delegates to the existing primr report generation pipeline,
    wrapping it with subagent lifecycle management.

Example:
    context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
        parent_results={
            "insights_path": Path("./output/acme/insights.md"),
            "hypotheses": hypotheses_list,
        },
    )
    writer = WriterSubagent(context)
    result = await writer.execute()

    if result.is_success:
        print(f"Report generated at: {result.data.report_path}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING

from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)

if TYPE_CHECKING:
    from primr.agentic.models import Hypothesis

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT DATA CLASS
# =============================================================================


@dataclass
class WriterResult:
    """
    Result data from report writing operation.

    Attributes:
        report_path: Path to the generated report
        word_count: Total word count of the report
        section_count: Number of sections in the report
        citation_count: Number of citations included
        format: Output format (markdown, html, pdf)
        generated_at: Timestamp of generation
    """

    report_path: Path
    word_count: int = 0
    section_count: int = 0
    citation_count: int = 0
    format: str = "markdown"
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "report_path": str(self.report_path),
            "word_count": self.word_count,
            "section_count": self.section_count,
            "citation_count": self.citation_count,
            "format": self.format,
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# WRITER SUBAGENT
# =============================================================================


class WriterSubagent(Subagent[WriterResult]):
    """
    Subagent for research report generation.

    Generates comprehensive research reports from insights and
    hypotheses, with proper formatting and citations.

    Report Structure:
        1. Executive Summary
        2. Company Overview
        3. Key Findings
        4. Detailed Analysis
        5. Hypotheses & Confidence
        6. Sources & Citations

    Example:
        writer = WriterSubagent(context)
        result = await writer.execute()

        if result.is_success:
            print(f"Report: {result.data.report_path}")
            print(f"Words: {result.data.word_count}")
    """

    def __init__(
        self,
        context: SubagentContext,
        output_format: str = "markdown",
    ):
        """
        Initialize writer subagent.

        Args:
            context: Subagent context
            output_format: Output format (markdown, html)
        """
        super().__init__(context, name="WriterSubagent")
        self._output_format = output_format

    @property
    def output_format(self) -> str:
        """Get the output format."""
        return self._output_format

    async def execute(self) -> SubagentResult[WriterResult]:
        """
        Execute report generation.

        Returns:
            SubagentResult containing WriterResult on success
        """
        self._status = SubagentStatus.RUNNING
        start_time = time.time()

        logger.info(f"WriterSubagent starting for {self.company_name}")

        try:
            # Get inputs from parent results
            insights_path = self._context.get_parent_result("insights_path")
            hypotheses = self._context.get_parent_result("hypotheses", [])

            if insights_path and isinstance(insights_path, str):
                insights_path = Path(insights_path)

            # Generate report
            report_result = await self._generate_report(insights_path, hypotheses)

            duration = time.time() - start_time
            self._status = SubagentStatus.COMPLETED

            logger.info(
                f"WriterSubagent completed for {self.company_name}: "
                f"{report_result.word_count} words in {duration:.1f}s"
            )

            return SubagentResult(
                status=self._status,
                data=report_result,
                metrics={
                    "duration_seconds": duration,
                    "word_count": report_result.word_count,
                    "words_per_second": (
                        report_result.word_count / duration if duration > 0 else 0
                    ),
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            self._status = SubagentStatus.FAILED

            logger.error(f"WriterSubagent failed for {self.company_name}: {e}")

            return SubagentResult(
                status=self._status,
                error=str(e),
                metrics={"duration_seconds": duration},
            )

    async def _generate_report(
        self,
        insights_path: Path | None,
        hypotheses: list[Hypothesis],
    ) -> WriterResult:
        """
        Generate the research report.

        Args:
            insights_path: Path to insights file
            hypotheses: List of hypotheses to include

        Returns:
            WriterResult with report metadata
        """
        # The agentic WriterSubagent currently always uses the basic-report
        # path — there is no `primr.output.report.generate_report` in this
        # codebase. The rich research pipeline lives in
        # `primr.core.research_agent`; wiring this subagent to it is tracked
        # separately. Until then, the basic report is the only real path.
        return await self._generate_basic_report(insights_path, hypotheses)

    async def _generate_basic_report(
        self,
        insights_path: Path | None,
        hypotheses: list[Hypothesis],
    ) -> WriterResult:
        """
        Generate a basic report when full pipeline unavailable.

        Args:
            insights_path: Path to insights file
            hypotheses: List of hypotheses

        Returns:
            WriterResult with basic report
        """
        report_path = self.working_dir / f"{self._safe_filename()}_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        # Build report content
        sections = []

        # Header
        sections.append(f"# Research Report: {self.company_name}")
        sections.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

        # Executive Summary
        sections.append("## Executive Summary\n")
        sections.append(f"Research report for {self.company_name} ({self.company_url}).\n")

        # Insights
        sections.append("## Key Insights\n")
        if insights_path and insights_path.exists():
            insights_content = insights_path.read_text(encoding="utf-8")
            # Extract key points (simplified)
            sections.append(
                insights_content[:2000] + "...\n"
                if len(insights_content) > 2000
                else insights_content + "\n"
            )
        else:
            sections.append("*No insights available.*\n")

        # Hypotheses
        sections.append("## Research Hypotheses\n")
        if hypotheses:
            for h in hypotheses:
                confidence = getattr(h, "confidence", None)
                conf_str = confidence.value if confidence else "unknown"
                sections.append(f"- **{h.claim}** ({conf_str})\n")
        else:
            sections.append("*No hypotheses generated.*\n")

        # Sources
        sections.append("## Sources\n")
        sections.append(f"- Primary: {self.company_url}\n")

        # Write report
        content = "\n".join(sections)
        report_path.write_text(content, encoding="utf-8")

        # Calculate metrics
        word_count = len(content.split())
        section_count = content.count("## ")

        return WriterResult(
            report_path=report_path,
            word_count=word_count,
            section_count=section_count,
            citation_count=1,  # Just the primary URL
            format=self._output_format,
        )

    def _safe_filename(self) -> str:
        """Generate a safe filename from company name."""
        return (
            self.company_name.lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
        )[:50]

    def get_required_tools(self) -> list[str]:
        """
        Return list of MCP tools this subagent needs.

        WriterSubagent uses the internal pipeline, not MCP tools.

        Returns:
            Empty list (uses internal pipeline)
        """
        return []
