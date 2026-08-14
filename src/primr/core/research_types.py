"""Shared research-orchestrator types (leaf module for cycle-free imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ResearchMode(Enum):
    """Available research modes.

    Modes:
        STRUCTURED: Website scraping + web search, 18 sections (~20-25 min)
        DEEP_RESEARCH: Autonomous web research, 8 sections (~10-15 min)
        COMPLETE: Two-step sequential: structured then deep research (~30-40 min)
        HYBRID: Parallel execution of both engines (legacy, ~25 min)
    """

    STRUCTURED = "structured"
    DEEP_RESEARCH = "deep-research"
    COMPLETE = "complete"  # Two-step sequential: structured then deep research
    HYBRID = "hybrid"  # Parallel execution (legacy)


@dataclass
class ResearchConfig:
    """Configuration for a research task."""

    mode: ResearchMode = ResearchMode.STRUCTURED
    timeout: float = 3600  # 1 hour max
    poll_interval: float = 10
    include_website_scrape: bool = True
    include_web_search: bool = True
    sections: list | None = None  # Specific sections to research
    fail_on_low_scrape: bool = True
    # Extra evidence appended to the Deep Research stage-1 context (COMPLETE
    # and DEEP_RESEARCH modes). Callers own fencing: anything derived from
    # scraped text must arrive already fenced (hiring signals do).
    supplemental_context: str | None = None
    # Optional run working folder for body-free stage_routes persistence.
    folder_path: str | None = None


@dataclass
class OrchestratorResult:
    """Result from the research orchestrator."""

    company_name: str
    website: str | None
    mode: ResearchMode
    section_results: dict[str, str]
    raw_content: str = ""
    citations: list = field(default_factory=list)
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    sections_written: int = 0  # Actual number of sections written (for accordion method)
    search_queries_count: int = 0  # Actual search count from groundingMetadata
    pending_interaction_id: str = ""
    target_pages: int = 0
    actual_pages: int = 0
    target_attained: bool = False
