"""
Subagent Architecture for Primr.

This module implements specialized research subagents that handle
distinct phases of the research pipeline with isolated context
and clear responsibilities.

Subagents:
    - ScraperSubagent: Tier escalation, content extraction, soft block detection
    - AnalystSubagent: Insight synthesis, hypothesis generation, confidence scoring
    - WriterSubagent: Report generation, citation management
    - QASubagent: Quality assessment, feedback generation

Each subagent operates with isolated context (SubagentContext) and
returns structured results (SubagentResult) that can be passed to
subsequent stages.

Example:
    from primr.agentic.subagents import (
        SubagentContext,
        ScraperSubagent,
        AnalystSubagent,
    )

    context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
    )

    scraper = ScraperSubagent(context)
    scrape_result = await scraper.execute()

    # Pass results to analyst
    analyst_context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
        parent_results={"corpus_path": scrape_result.data.corpus_path},
    )
    analyst = AnalystSubagent(analyst_context)
    analysis_result = await analyst.execute()
"""

from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)
from primr.agentic.subagents.scraper import ScraperSubagent, ScrapeResult
from primr.agentic.subagents.analyst import AnalystSubagent, AnalysisResult
from primr.agentic.subagents.writer import WriterSubagent, WriterResult
from primr.agentic.subagents.qa import QASubagent, QAResult

__all__ = [
    # Base
    "Subagent",
    "SubagentContext",
    "SubagentResult",
    "SubagentStatus",
    # Scraper
    "ScraperSubagent",
    "ScrapeResult",
    # Analyst
    "AnalystSubagent",
    "AnalysisResult",
    # Writer
    "WriterSubagent",
    "WriterResult",
    # QA
    "QASubagent",
    "QAResult",
]
