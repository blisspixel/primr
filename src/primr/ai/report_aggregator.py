"""
Report Aggregator for Recursive Hierarchical Research.

This module provides the ReportAggregator class that combines multiple
chapter outputs into a cohesive, comprehensive strategic document.

The aggregator:
- Concatenates chapters in order
- Generates a table of contents
- Smooths transitions between chapters
- Handles missing chapters gracefully
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from google import genai

from primr.ai.research_executor import ChapterResult
from primr.config.models import PrimrModels
from primr.config.settings import get_settings
from primr.utils.logging_config import get_logger

logger = get_logger("ai.report_aggregator")


@dataclass
class AggregatedReport:
    """A complete aggregated research report."""

    company_name: str
    content: str
    table_of_contents: str
    chapter_count: int
    total_word_count: int
    citations: list[dict[str, str]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    missing_chapters: list[str] = field(default_factory=list)

    @property
    def estimated_pages(self) -> int:
        """Estimate page count (assuming ~500 words per page)."""
        return max(1, self.total_word_count // 500)

    def to_markdown(self) -> str:
        """Get the full report as markdown."""
        return self.content


class ReportAggregator:
    """
    Combines chapter outputs into a cohesive document.

    The aggregator handles:
    - Table of contents generation
    - Chapter ordering and formatting
    - Transition smoothing (optional)
    - Missing chapter notation
    - Citation consolidation

    Example:
        aggregator = ReportAggregator()
        report = await aggregator.aggregate(chapter_results, "Acme Corp")
        print(report.to_markdown())
    """

    # Model for transition smoothing (optional)
    SMOOTHING_MODEL = PrimrModels.FAST_MODEL

    def __init__(self, api_key: str | None = None):
        """
        Initialize the Report Aggregator.

        Args:
            api_key: Optional API key override
        """
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        logger.debug("Report Aggregator initialized")

    async def aggregate(
        self,
        chapters: list[ChapterResult],
        company_name: str,
        smooth_transitions: bool = False,
    ) -> AggregatedReport:
        """
        Aggregate chapter results into a single comprehensive document.

        Args:
            chapters: List of chapter results from ResearchNodeExecutor
            company_name: Name of the company
            smooth_transitions: Whether to use AI to smooth chapter transitions

        Returns:
            AggregatedReport with combined content
        """
        logger.info(f"Aggregating {len(chapters)} chapters for {company_name}")

        # Sort chapters by number
        sorted_chapters = sorted(chapters, key=lambda x: x.chapter_number)

        # Track successful and failed chapters
        successful_chapters = [ch for ch in sorted_chapters if ch.success]
        failed_chapters = [ch for ch in sorted_chapters if not ch.success]

        if failed_chapters:
            logger.warning(
                f"{len(failed_chapters)} chapters failed: "
                f"{[ch.title for ch in failed_chapters]}"
            )

        # Generate table of contents
        toc = self._generate_toc(sorted_chapters, company_name)

        # Build the document header
        header = self._build_header(company_name, len(successful_chapters))

        # Concatenate chapter contents
        chapter_contents = []
        for chapter in sorted_chapters:
            if chapter.success and chapter.content:
                # Clean up the chapter content
                content = self._clean_chapter_content(chapter)
                chapter_contents.append(content)
            else:
                # Note the missing chapter
                chapter_contents.append(
                    f"\n## {chapter.chapter_number}. {chapter.title}\n\n"
                    f"*This chapter could not be generated. Error: {chapter.error}*\n"
                )

        # Combine all parts
        full_content = "\n\n".join([
            header,
            toc,
            "---\n",
            "\n\n---\n\n".join(chapter_contents),
        ])

        # Optional: Smooth transitions between chapters
        if smooth_transitions and len(successful_chapters) > 1:
            full_content = await self._smooth_transitions(full_content, company_name)

        # Consolidate citations
        all_citations = self._consolidate_citations(successful_chapters)

        # Calculate totals
        total_words = sum(ch.word_count for ch in successful_chapters)

        report = AggregatedReport(
            company_name=company_name,
            content=full_content,
            table_of_contents=toc,
            chapter_count=len(successful_chapters),
            total_word_count=total_words,
            citations=all_citations,
            missing_chapters=[ch.title for ch in failed_chapters],
        )

        logger.info(
            f"Aggregation complete: {report.chapter_count} chapters, "
            f"~{report.total_word_count} words, ~{report.estimated_pages} pages"
        )

        return report

    def _build_header(self, company_name: str, chapter_count: int) -> str:
        """Build the document header."""
        date_str = datetime.now().strftime("%B %d, %Y")

        return f"""# Strategic Company Overview: {company_name}

**Prepared by:** Primr Research System
**Date:** {date_str}
**Chapters:** {chapter_count}

---

## About This Document

This comprehensive strategic overview was generated using Primr's Recursive Hierarchical Research Architecture. Each chapter represents an independent deep-dive research task, synthesizing information from the company's own materials (via File Search) and external market intelligence (via web search).

**Hierarchy of Truth:**
1. Company Facts: Sourced from official company materials (highest authority)
2. External Context: Market conditions, competitive intelligence, industry trends
3. Synthesis: Integrated analysis combining internal baseline with external perspective

**Epistemic Standards:**
- Facts are cited; inferences are labeled as such
- Strategic observations are framed as hypotheses to validate
- Unavailable data is noted rather than estimated

"""

    def _generate_toc(
        self,
        chapters: list[ChapterResult],
        company_name: str,
    ) -> str:
        """Generate a clean table of contents (no status markers)."""
        lines = ["## Table of Contents\n"]

        for chapter in chapters:
            # Clean TOC - NO status markers (+/x)
            # Only include successful chapters in TOC
            if not chapter.success:
                continue

            # Create anchor link
            anchor = chapter.title.lower().replace(" ", "-").replace("&", "and")
            anchor = re.sub(r'[^a-z0-9-]', '', anchor)

            lines.append(
                f"{chapter.chapter_number}. [{chapter.title}](#{anchor})"
            )

        return "\n".join(lines)

    def _clean_chapter_content(self, chapter: ChapterResult) -> str:
        """Clean and format chapter content."""
        content = chapter.content

        # Ensure chapter starts with proper header
        if not content.strip().startswith("##"):
            content = f"## {chapter.chapter_number}. {chapter.title}\n\n{content}"
        else:
            # Update existing header to include chapter number
            content = re.sub(
                r'^##\s*',
                f'## {chapter.chapter_number}. ',
                content.strip(),
                count=1
            )

        return content

    def _consolidate_citations(
        self,
        chapters: list[ChapterResult],
    ) -> list[dict[str, str]]:
        """Consolidate citations from all chapters."""
        all_citations: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        citation_num = 1
        for chapter in chapters:
            for citation in chapter.citations:
                url = citation.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_citations.append({
                        'number': str(citation_num),
                        'title': citation.get('title', f'Source {citation_num}'),
                        'url': url,
                        'chapter': chapter.title,
                    })
                    citation_num += 1

        return all_citations

    async def _smooth_transitions(
        self,
        content: str,
        company_name: str,
    ) -> str:
        """
        Use AI to smooth transitions between chapters.

        This is optional and adds ~1-2 minutes to processing.
        """
        logger.info("Smoothing chapter transitions...")

        prompt = f"""You are editing a strategic research document about {company_name}.

The document has multiple chapters that were written independently. Your task is to:
1. Add brief transition sentences between chapters (1-2 sentences max)
2. Ensure consistent terminology throughout
3. Fix any redundant introductions

Do NOT:
- Change the substantive content
- Remove any information
- Add new analysis or claims
- Change the chapter structure

Return the edited document with smooth transitions.

Document:
{content[:50000]}  # Truncate to avoid token limits
"""

        try:
            response = self._client.models.generate_content(
                model=self.SMOOTHING_MODEL,
                contents=prompt,
                config={"temperature": 0.2}
            )

            smoothed = response.text or content
            logger.info("Transitions smoothed successfully")
            return smoothed

        except Exception as e:
            logger.warning(f"Transition smoothing failed: {e}, using original", exc_info=True)
            return content


# =============================================================================
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

import threading

_aggregator: ReportAggregator | None = None
_aggregator_lock = threading.Lock()


def get_report_aggregator() -> ReportAggregator:
    """
    Get the global Report Aggregator instance (thread-safe).
    """
    global _aggregator
    if _aggregator is None:
        with _aggregator_lock:
            if _aggregator is None:
                _aggregator = ReportAggregator()
    return _aggregator


def reset_report_aggregator() -> None:
    """Reset the global aggregator (useful for testing)."""
    global _aggregator
    with _aggregator_lock:
        _aggregator = None
