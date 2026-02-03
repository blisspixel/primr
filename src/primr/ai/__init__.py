"""
AI module - LLM interface, grading, and summarization.
"""

from primr.ai.async_client import (
    AsyncAIClient,
    BatchResult,
    BatchStats,
    generate_parallel,
    get_batch_stats,
    run_parallel,
)
from primr.ai.client import (
    AIClient,
    get_client,
    llm,
    llm_fast,
    reset_client,
)
from primr.ai.competitive import (
    CompetitiveAnalyzer,
    CompetitiveComparison,
    Competitor,
    CompetitorType,
    MarketAnalysis,
    MarketPosition,
    SWOTAnalysis,
    SWOTItem,
    ThreatLevel,
    analyze_market,
    compare_companies,
    generate_swot,
    get_competitive_analyzer,
    identify_competitors,
    reset_competitive_analyzer,
)

# Deep Research Agent
from primr.ai.deep_research import (
    DeepResearchClient,
    ResearchProgress,
    ResearchResult,
    ResearchStatus,
    deep_research,
    get_deep_research_client,
    research_company,
    reset_deep_research_client,
)
from primr.ai.grading_agent import grade_report
from primr.ai.insight_engine import InsightEngine
from primr.ai.insights import (
    InsightAnalyzer,
    InsightReport,
    Opportunity,
    OpportunityType,
    Recommendation,
    RecommendationType,
    Risk,
    RiskCategory,
    RiskLevel,
    assess_risks,
    generate_insights,
    generate_recommendations,
    get_insight_analyzer,
    identify_opportunities,
    reset_insight_analyzer,
)
from primr.ai.quality_grader import QualityGrader

# Recursive Hierarchical Research Architecture
from primr.ai.report_aggregator import (
    AggregatedReport,
    ReportAggregator,
    get_report_aggregator,
    reset_report_aggregator,
)
from primr.ai.report_architect import (
    ChapterPlan,
    MasterArchitect,
    ReportPlan,
    get_master_architect,
    reset_master_architect,
)
from primr.ai.research_executor import (
    ChapterResult,
    ExecutionResult,
    ResearchNodeExecutor,
    get_research_executor,
    reset_research_executor,
)
from primr.ai.result_normalizer import (
    Citation,
    NormalizedSection,
    ResultNormalizer,
    normalize_deep_research,
)
from primr.ai.summarize import summarize_scraped_content

__all__ = [
    # Sync client
    "AIClient",
    "get_client",
    "reset_client",
    "llm",
    "llm_fast",
    # Async client
    "AsyncAIClient",
    "BatchResult",
    "BatchStats",
    "get_batch_stats",
    "generate_parallel",
    "run_parallel",
    # Agents
    "grade_report",
    "summarize_scraped_content",
    # Competitive intelligence
    "CompetitiveAnalyzer",
    "Competitor",
    "CompetitorType",
    "MarketPosition",
    "ThreatLevel",
    "SWOTItem",
    "SWOTAnalysis",
    "CompetitiveComparison",
    "MarketAnalysis",
    "get_competitive_analyzer",
    "reset_competitive_analyzer",
    "identify_competitors",
    "generate_swot",
    "compare_companies",
    "analyze_market",
    # Predictive insights
    "InsightAnalyzer",
    "Risk",
    "RiskCategory",
    "RiskLevel",
    "Opportunity",
    "OpportunityType",
    "Recommendation",
    "RecommendationType",
    "InsightReport",
    "get_insight_analyzer",
    "reset_insight_analyzer",
    "assess_risks",
    "identify_opportunities",
    "generate_recommendations",
    "generate_insights",
    # Consulting-tier components
    "InsightEngine",
    "QualityGrader",
    # Deep Research Agent
    "DeepResearchClient",
    "ResearchStatus",
    "ResearchProgress",
    "ResearchResult",
    "get_deep_research_client",
    "reset_deep_research_client",
    "deep_research",
    "research_company",
    # Result normalization
    "ResultNormalizer",
    "Citation",
    "NormalizedSection",
    "normalize_deep_research",
    # Recursive Hierarchical Research Architecture
    "MasterArchitect",
    "ChapterPlan",
    "ReportPlan",
    "get_master_architect",
    "reset_master_architect",
    "ResearchNodeExecutor",
    "ChapterResult",
    "ExecutionResult",
    "get_research_executor",
    "reset_research_executor",
    "ReportAggregator",
    "AggregatedReport",
    "get_report_aggregator",
    "reset_report_aggregator",
]
