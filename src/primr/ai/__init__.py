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
    "AggregatedReport",
    # Async client
    "AsyncAIClient",
    "BatchResult",
    "BatchStats",
    "ChapterPlan",
    "ChapterResult",
    "Citation",
    # Competitive intelligence
    "CompetitiveAnalyzer",
    "CompetitiveComparison",
    "Competitor",
    "CompetitorType",
    # Deep Research Agent
    "DeepResearchClient",
    "ExecutionResult",
    # Predictive insights
    "InsightAnalyzer",
    # Consulting-tier components
    "InsightEngine",
    "InsightReport",
    "MarketAnalysis",
    "MarketPosition",
    # Recursive Hierarchical Research Architecture
    "MasterArchitect",
    "NormalizedSection",
    "Opportunity",
    "OpportunityType",
    "QualityGrader",
    "Recommendation",
    "RecommendationType",
    "ReportAggregator",
    "ReportPlan",
    "ResearchNodeExecutor",
    "ResearchProgress",
    "ResearchResult",
    "ResearchStatus",
    # Result normalization
    "ResultNormalizer",
    "Risk",
    "RiskCategory",
    "RiskLevel",
    "SWOTAnalysis",
    "SWOTItem",
    "ThreatLevel",
    "analyze_market",
    "assess_risks",
    "compare_companies",
    "deep_research",
    "generate_insights",
    "generate_parallel",
    "generate_recommendations",
    "generate_swot",
    "get_batch_stats",
    "get_client",
    "get_competitive_analyzer",
    "get_deep_research_client",
    "get_insight_analyzer",
    "get_master_architect",
    "get_report_aggregator",
    "get_research_executor",
    # Agents
    "grade_report",
    "identify_competitors",
    "identify_opportunities",
    "llm",
    "llm_fast",
    "normalize_deep_research",
    "research_company",
    "reset_client",
    "reset_competitive_analyzer",
    "reset_deep_research_client",
    "reset_insight_analyzer",
    "reset_master_architect",
    "reset_report_aggregator",
    "reset_research_executor",
    "run_parallel",
    "summarize_scraped_content",
]
