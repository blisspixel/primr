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

from primr.agentic.subagents.analyst import AnalysisResult, AnalystSubagent
from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)
from primr.agentic.subagents.qa import QAResult, QASubagent
from primr.agentic.subagents.scraper import ScrapeResult, ScraperSubagent
from primr.agentic.subagents.writer import WriterResult, WriterSubagent

__all__ = [
    "AnalysisResult",
    # Analyst
    "AnalystSubagent",
    "QAResult",
    # QA
    "QASubagent",
    "ScrapeResult",
    # Scraper
    "ScraperSubagent",
    # Base
    "Subagent",
    "SubagentContext",
    "SubagentResult",
    "SubagentStatus",
    "WriterResult",
    # Writer
    "WriterSubagent",
]
