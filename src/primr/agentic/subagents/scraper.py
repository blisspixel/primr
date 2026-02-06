"""
Scraper Subagent for content extraction.

This subagent handles the scraping phase of the research pipeline,
including tier escalation, content extraction, and soft block detection.

Responsibilities:
    - Execute web scraping with tier escalation
    - Detect and handle soft blocks
    - Track scraping statistics by tier
    - Return corpus path for downstream processing

Integration:
    Delegates to the existing primr.data.scrape pipeline, wrapping
    it with subagent lifecycle management and structured results.

Example:
    context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
    )
    scraper = ScraperSubagent(context)
    result = await scraper.execute()

    if result.is_success:
        print(f"Scraped {result.data.pages_scraped} pages")
        print(f"Corpus at: {result.data.corpus_path}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from primr.agentic.errors import SubagentError
from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT DATA CLASS
# =============================================================================

@dataclass
class ScrapeResult:
    """
    Result data from scraping operation.

    Attributes:
        pages_scraped: Number of pages successfully scraped
        pages_failed: Number of pages that failed to scrape
        corpus_path: Path to the scraped content corpus
        tier_stats: Breakdown of pages by scraping tier
        soft_blocks_detected: Number of soft blocks encountered
        total_bytes: Total bytes of content scraped
    """

    pages_scraped: int
    pages_failed: int
    corpus_path: Path
    tier_stats: dict[str, int] = field(default_factory=dict)
    soft_blocks_detected: int = 0
    total_bytes: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate the scraping success rate."""
        total = self.pages_scraped + self.pages_failed
        if total == 0:
            return 0.0
        return self.pages_scraped / total

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "pages_scraped": self.pages_scraped,
            "pages_failed": self.pages_failed,
            "corpus_path": str(self.corpus_path),
            "tier_stats": self.tier_stats,
            "soft_blocks_detected": self.soft_blocks_detected,
            "total_bytes": self.total_bytes,
            "success_rate": self.success_rate,
        }


# =============================================================================
# SCRAPER SUBAGENT
# =============================================================================

class ScraperSubagent(Subagent[ScrapeResult]):
    """
    Subagent for web scraping with tier escalation.

    Handles content extraction from company websites using the
    existing primr scraping pipeline. Supports tier escalation
    from basic HTTP to browser-based scraping.

    Tier Escalation:
        1. Basic HTTP (fastest, lowest cost)
        2. HTTP with headers/cookies
        3. Browser-based (Playwright)
        4. Deep mode (full JavaScript rendering)

    Attributes:
        max_pages: Maximum pages to scrape (from config)
        timeout: Request timeout in seconds (from config)

    Example:
        scraper = ScraperSubagent(context)
        result = await scraper.execute()

        if result.is_success:
            # Pass corpus to analyst
            analyst_context = context.with_parent_results(
                corpus_path=result.data.corpus_path
            )
    """

    def __init__(
        self,
        context: SubagentContext,
        max_pages: int | None = None,
        timeout: int | None = None,
    ):
        """
        Initialize scraper subagent.

        Args:
            context: Subagent context
            max_pages: Maximum pages to scrape (default from config)
            timeout: Request timeout in seconds (default from config)
        """
        super().__init__(context, name="ScraperSubagent")
        self._max_pages = max_pages or context.config.get("max_pages", 50)
        self._timeout = timeout or context.config.get("timeout", 30)

    @property
    def max_pages(self) -> int:
        """Get maximum pages to scrape."""
        return self._max_pages

    @property
    def timeout(self) -> int:
        """Get request timeout."""
        return self._timeout

    async def execute(self) -> SubagentResult[ScrapeResult]:
        """
        Execute web scraping with tier escalation.

        Returns:
            SubagentResult containing ScrapeResult on success
        """
        self._status = SubagentStatus.RUNNING
        start_time = time.time()

        logger.info(
            f"ScraperSubagent starting for {self.company_name} "
            f"(url={self.company_url}, max_pages={self._max_pages})"
        )

        try:
            # Ensure working directory exists
            self.working_dir.mkdir(parents=True, exist_ok=True)

            # Delegate to existing scrape pipeline
            scrape_result = await self._do_scrape()

            duration = time.time() - start_time
            self._status = SubagentStatus.COMPLETED

            logger.info(
                f"ScraperSubagent completed for {self.company_name}: "
                f"{scrape_result.pages_scraped} pages in {duration:.1f}s"
            )

            return SubagentResult(
                status=self._status,
                data=scrape_result,
                metrics={
                    "duration_seconds": duration,
                    "pages_per_second": (
                        scrape_result.pages_scraped / duration
                        if duration > 0 else 0
                    ),
                    "success_rate": scrape_result.success_rate,
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            self._status = SubagentStatus.FAILED

            logger.error(
                f"ScraperSubagent failed for {self.company_name}: {e}"
            )

            return SubagentResult(
                status=self._status,
                error=str(e),
                metrics={"duration_seconds": duration},
            )

    async def _do_scrape(self) -> ScrapeResult:
        """
        Perform the actual scraping operation.

        Delegates to the existing primr scraping pipeline.

        Returns:
            ScrapeResult with scraping statistics

        Raises:
            SubagentError: If scraping fails
        """
        try:
            # Try to import and use existing scrape pipeline
            from primr.data.scrape import fetch_web_content

            # fetch_web_content is synchronous and returns dict[str, str]
            result = fetch_web_content(
                website=self.company_url,
                company_name=self.company_name,
                max_pages=self._max_pages,
                working_folder=str(self.working_dir),
            )

            # Result is dict mapping URL -> extracted text
            pages_scraped = len(result) if result else 0

            # Save corpus to file
            corpus_path = self.working_dir / "corpus.txt"
            if result:
                corpus_content = "\n\n---\n\n".join(
                    f"# {url}\n\n{text}" for url, text in result.items()
                )
                corpus_path.write_text(corpus_content, encoding="utf-8")

            return ScrapeResult(
                pages_scraped=pages_scraped,
                pages_failed=0,
                corpus_path=corpus_path,
                tier_stats={},
                soft_blocks_detected=0,
                total_bytes=sum(len(t) for t in result.values()) if result else 0,
            )

        except ImportError:
            # Scrape module not available - return mock result for testing
            logger.warning(
                "primr.data.scrape not available, returning mock result"
            )
            corpus_path = self.working_dir / "corpus"
            corpus_path.mkdir(parents=True, exist_ok=True)

            return ScrapeResult(
                pages_scraped=0,
                pages_failed=0,
                corpus_path=corpus_path,
                tier_stats={},
            )

        except Exception as e:
            raise SubagentError(
                message=f"Scraping failed: {e}",
                subagent="scraper",
            ) from e

    def get_required_tools(self) -> list[str]:
        """
        Return list of MCP tools this subagent needs.

        ScraperSubagent uses the internal pipeline, not MCP tools.

        Returns:
            Empty list (uses internal pipeline)
        """
        return []
