"""AI module exports with lazy loading.

Avoid importing heavy optional dependencies (for example google.genai and MCP
transitive imports) until specific symbols are actually requested.
"""

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    # Sync client
    "AIClient": ("primr.ai.client", "AIClient"),
    "get_client": ("primr.ai.client", "get_client"),
    "llm": ("primr.ai.client", "llm"),
    "llm_fast": ("primr.ai.client", "llm_fast"),
    "reset_client": ("primr.ai.client", "reset_client"),
    # Async client
    "AsyncAIClient": ("primr.ai.async_client", "AsyncAIClient"),
    "BatchResult": ("primr.ai.async_client", "BatchResult"),
    "BatchStats": ("primr.ai.async_client", "BatchStats"),
    "generate_parallel": ("primr.ai.async_client", "generate_parallel"),
    "get_batch_stats": ("primr.ai.async_client", "get_batch_stats"),
    "run_parallel": ("primr.ai.async_client", "run_parallel"),
    # Competitive intelligence
    "CompetitiveAnalyzer": ("primr.ai.competitive", "CompetitiveAnalyzer"),
    "CompetitiveComparison": ("primr.ai.competitive", "CompetitiveComparison"),
    "Competitor": ("primr.ai.competitive", "Competitor"),
    "CompetitorType": ("primr.ai.competitive", "CompetitorType"),
    "MarketAnalysis": ("primr.ai.competitive", "MarketAnalysis"),
    "MarketPosition": ("primr.ai.competitive", "MarketPosition"),
    "SWOTAnalysis": ("primr.ai.competitive", "SWOTAnalysis"),
    "SWOTItem": ("primr.ai.competitive", "SWOTItem"),
    "ThreatLevel": ("primr.ai.competitive", "ThreatLevel"),
    "analyze_market": ("primr.ai.competitive", "analyze_market"),
    "compare_companies": ("primr.ai.competitive", "compare_companies"),
    "generate_swot": ("primr.ai.competitive", "generate_swot"),
    "get_competitive_analyzer": ("primr.ai.competitive", "get_competitive_analyzer"),
    "identify_competitors": ("primr.ai.competitive", "identify_competitors"),
    "reset_competitive_analyzer": ("primr.ai.competitive", "reset_competitive_analyzer"),
    # Deep research
    "DeepResearchClient": ("primr.ai.deep_research", "DeepResearchClient"),
    "ResearchProgress": ("primr.ai.deep_research", "ResearchProgress"),
    "ResearchResult": ("primr.ai.deep_research", "ResearchResult"),
    "ResearchStatus": ("primr.ai.deep_research", "ResearchStatus"),
    "deep_research": ("primr.ai.deep_research", "deep_research"),
    "get_deep_research_client": ("primr.ai.deep_research", "get_deep_research_client"),
    "research_company": ("primr.ai.deep_research", "research_company"),
    "reset_deep_research_client": ("primr.ai.deep_research", "reset_deep_research_client"),
    # Grading and summarization
    "grade_report": ("primr.ai.grading_agent", "grade_report"),
    "InsightEngine": ("primr.ai.insight_engine", "InsightEngine"),
    "summarize_scraped_content": ("primr.ai.summarize", "summarize_scraped_content"),
    "QualityGrader": ("primr.ai.quality_grader", "QualityGrader"),
    # Host-agent runner seam
    "HostAgentBillingMode": ("primr.ai.host_agent_runner", "HostAgentBillingMode"),
    "HostAgentKind": ("primr.ai.host_agent_runner", "HostAgentKind"),
    "HostAgentPolicy": ("primr.ai.host_agent_runner", "HostAgentPolicy"),
    "HostAgentResult": ("primr.ai.host_agent_runner", "HostAgentResult"),
    "HostAgentRunner": ("primr.ai.host_agent_runner", "HostAgentRunner"),
    "HostAgentStagePacket": ("primr.ai.host_agent_runner", "HostAgentStagePacket"),
    "HostAgentUnavailableError": ("primr.ai.host_agent_runner", "HostAgentUnavailableError"),
    "render_host_agent_prompt": ("primr.ai.host_agent_runner", "render_host_agent_prompt"),
    # Insights
    "InsightAnalyzer": ("primr.ai.insights", "InsightAnalyzer"),
    "InsightReport": ("primr.ai.insights", "InsightReport"),
    "Opportunity": ("primr.ai.insights", "Opportunity"),
    "OpportunityType": ("primr.ai.insights", "OpportunityType"),
    "Recommendation": ("primr.ai.insights", "Recommendation"),
    "RecommendationType": ("primr.ai.insights", "RecommendationType"),
    "Risk": ("primr.ai.insights", "Risk"),
    "RiskCategory": ("primr.ai.insights", "RiskCategory"),
    "RiskLevel": ("primr.ai.insights", "RiskLevel"),
    "assess_risks": ("primr.ai.insights", "assess_risks"),
    "generate_insights": ("primr.ai.insights", "generate_insights"),
    "generate_recommendations": ("primr.ai.insights", "generate_recommendations"),
    "get_insight_analyzer": ("primr.ai.insights", "get_insight_analyzer"),
    "identify_opportunities": ("primr.ai.insights", "identify_opportunities"),
    "reset_insight_analyzer": ("primr.ai.insights", "reset_insight_analyzer"),
    # Recursive hierarchical architecture
    "AggregatedReport": ("primr.ai.report_aggregator", "AggregatedReport"),
    "ReportAggregator": ("primr.ai.report_aggregator", "ReportAggregator"),
    "get_report_aggregator": ("primr.ai.report_aggregator", "get_report_aggregator"),
    "reset_report_aggregator": ("primr.ai.report_aggregator", "reset_report_aggregator"),
    "ChapterPlan": ("primr.ai.report_architect", "ChapterPlan"),
    "MasterArchitect": ("primr.ai.report_architect", "MasterArchitect"),
    "ReportPlan": ("primr.ai.report_architect", "ReportPlan"),
    "get_master_architect": ("primr.ai.report_architect", "get_master_architect"),
    "reset_master_architect": ("primr.ai.report_architect", "reset_master_architect"),
    "ChapterResult": ("primr.ai.research_executor", "ChapterResult"),
    "ExecutionResult": ("primr.ai.research_executor", "ExecutionResult"),
    "ResearchNodeExecutor": ("primr.ai.research_executor", "ResearchNodeExecutor"),
    "get_research_executor": ("primr.ai.research_executor", "get_research_executor"),
    "reset_research_executor": ("primr.ai.research_executor", "reset_research_executor"),
    # Result normalization
    "Citation": ("primr.ai.result_normalizer", "Citation"),
    "NormalizedSection": ("primr.ai.result_normalizer", "NormalizedSection"),
    "ResultNormalizer": ("primr.ai.result_normalizer", "ResultNormalizer"),
    "normalize_deep_research": ("primr.ai.result_normalizer", "normalize_deep_research"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'primr.ai' has no attribute '{name}'")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
