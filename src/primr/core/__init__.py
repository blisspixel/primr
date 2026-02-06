"""
Core module - Main orchestration logic for company research.
"""

from primr.core.container import (
    Container,
    create_default_container,
    get_ai_client,
    get_cache,
    get_container,
    get_scraper,
    reset_container,
    set_container,
)
from primr.core.report_models import (
    ConfidenceLevel,
    ConfidenceNote,
    GatheredData,
    Insight,
    InsightCategory,
    QualityScore,
    Report,
    ReportMetadata,
    SectionContent,
    SourceCitation,
    SourceType,
)

__all__ = [
    "ConfidenceLevel",
    "ConfidenceNote",
    "Container",
    "GatheredData",
    "Insight",
    "InsightCategory",
    "QualityScore",
    "Report",
    "ReportMetadata",
    "SectionContent",
    "SourceCitation",
    # Report models
    "SourceType",
    "create_default_container",
    "get_ai_client",
    "get_cache",
    "get_container",
    "get_scraper",
    "reset_container",
    "set_container",
]
