"""Stable command and configuration contract for Primr CLI workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Command(Enum):
    """CLI commands."""

    RESEARCH = "research"
    INIT = "init"
    DOCTOR = "doctor"
    LIST_RECENT = "list-recent"
    CLEAN_TEMP = "clean-temp"
    CHECK_QUOTA = "check-quota"
    CHECK_JOBS = "check-jobs"
    RESUME_LATEST = "resume-latest"
    CLEAR_JOBS = "clear-jobs"
    LIST_STRATEGIES = "list-strategies"
    SHOW_USAGE = "show-usage"
    DRY_RUN = "dry-run"
    PLAN = "plan"
    GENERATE_VENDOR = "generate-vendor"
    BATCH = "batch"
    ENRICH = "enrich"
    TEST_ACCORDION = "test-accordion"
    ANALYZE_REPORT = "analyze-report"
    QA = "qa"
    QA_RECENT = "qa-recent"
    AI_STRATEGY_ONLY = "ai-strategy-only"
    EVAL = "eval"
    COMPANY = "company"
    MEMORY = "memory"
    ORCHESTRATE = "orchestrate"
    ROADMAP = "roadmap"
    IMPROVE = "improve"
    REFINE = "refine"
    CALIBRATE = "calibrate"


@dataclass(frozen=True)
class CLIConfig:
    """Configuration parsed from CLI arguments."""

    command: Command
    company_name: str | None = None
    website: str | None = None
    mode: str = "complete"
    citation_style: str = "numbered"
    ai_strategy: bool = True
    platforms: tuple[str, ...] | None = None
    skip_recon: bool = False
    skip_confirm: bool = True
    context_files: tuple[str, ...] = ()
    context_folder: str | None = None
    refresh_vendor_research: bool = False
    generate_vendor: str | None = None
    csv_file: str | None = None
    batch_file: str | None = None
    industry: str | None = None
    limit: int | None = None
    enrich: bool = False
    output_dir: str | None = None
    open_after: bool = False
    quiet: bool = False
    json_output: bool = False
    verbose: bool = False
    test_accordion_topic: str | None = None
    test_accordion_pages: int = 50
    analyze_report_path: str | None = None
    qa_company: str | None = None
    qa_recent_count: int | None = None
    max_scrape_time: int | None = None
    ai_strategy_only_path: str | None = None
    dry_run_requested: bool = False
    discovery_notes_path: str | None = None
    strategy_type: str = "ai"
    framing_purpose: str | None = None
    framing_audience: str | None = None
    framing_decision: str | None = None
    framing_question: str | None = None
    resume_latest: bool = False
    resume_local: bool = False
    lite_strategy: bool = False
    deep_research_strategy: bool = False
    fast_mode: bool = False
    premium_mode: bool = False
    grok_tier: str = "hybrid"
    inference_profile: str = "cloud"
    acknowledge_host_agent_may_bill: bool = False
    continuous_reasoning: bool = True
    no_qa: bool = False
    verify: bool = False
    budget_usd: float | None = None
    skip_scrape_validation: bool = False
    browser_headed: bool = False
    browser_session_mode: str = "persistent"
    improve_path: str | None = None
    improve_in_place: bool = False
    improve_agentic: bool = False
    refine_company: str | None = None
    refine_target_grade: float = 90.0
    calibrate_target: str | None = None
    calibrate_recent: int | None = None
    calibrate_max_per_label: int = 10
    calibrate_dry_run: bool = False
    calibrate_judge: str = "cloud"
    calibrate_judge_model: str | None = None
    calibrate_judge_compare: bool = False
    calibrate_pack_manifest: str | None = None
    calibrate_pack_selection: str | None = None
    calibrate_pack_selection_template: str | None = None
    calibrate_inspect_selection: str | None = None
    calibrate_baseline_from: str | None = None
    calibrate_baseline_out: str | None = None
    calibrate_baseline_md: str | None = None
    calibrate_baseline_min_reports: int = 5
    calibrate_inspect_baseline: str | None = None
    calibrate_inspect_baseline_decision: str | None = None
    calibrate_baseline_decision_from: str | None = None
    calibrate_baseline_decision_out: str | None = None
    calibrate_baseline_decision: str | None = None
    calibrate_baseline_decision_reviewer: str | None = None
    calibrate_baseline_decision_rationale: str | None = None
    calibrate_baseline_decision_notes: tuple[str, ...] = ()
    banner_mode: str = "auto"
    banner_explicit: bool = False
    memory_company: str | None = None
    memory_list: bool = False
    company_profile_track: str | None = None
    company_profile_url: str | None = None
    company_profile_show: str | None = None
    company_profile_export: str | None = None
    company_profile_list: bool = False
    orchestrate_max_cost: float | None = None
    roadmap_version: str | None = None
    eval_mode: bool = False
    eval_id: str | None = None
    eval_root: str = "output/evals"
    eval_profiles: tuple[str, ...] = ("full", "lite", "fast")
    eval_baseline: str = "full"
    eval_manifest: str | None = None
    eval_run_missing: bool = False
    eval_max_new_runs: int = 0
    eval_max_estimated_cost: float = 0.0
    eval_quality_ratio_threshold: float = 0.8
    eval_cost_ratio_threshold: float = 0.2
    eval_company: str | None = None
    eval_source_dir: str = "output"
    eval_auto_stage: bool = True
    eval_llm_judge: bool = False
    eval_judge_provider: str = "grok"
    eval_judge_model: str = "grok-4.3"
    eval_judge_models: tuple[str, ...] = ()
    eval_judge_model_list: str | None = None
    eval_judge_base_url: str | None = None
    eval_judge_api_key_env: str = "LOCAL_LLM_API_KEY"
    eval_judge_max_pairs: int = 1
    eval_judge_passes: int = 1
    eval_judge_max_cost: float = 0.0
    eval_local_stage: str | None = None
    eval_stage_semantic_judge: bool = False
    eval_stage_semantic_judge_model: str | None = None
    eval_source_relevance_fixture: str | None = None
    eval_source_relevance_standing_corpus: bool = False
    inspect_source_relevance_standing_corpus: bool = False
    eval_page_access_fixture: str | None = None
    eval_working_root: str = "working"
    eval_stage_scorecard: bool = False
    eval_stage_quality: str | None = None
    eval_stage_route_root: str | None = None
    eval_stage_id: str | None = None
    eval_stage_min_quality_score: float = 85.0
    eval_stage_max_failure_rate: float = 0.0
    doctor_fix: bool = False
    doctor_scraper_stats: bool = False
    init_non_interactive: bool = False
    init_yes: bool = False
    init_skip_browsers: bool = False
    init_no_doctor: bool = False

    @property
    def cloud_vendors(self) -> tuple[str, ...]:
        """Return configured platforms or the agnostic default."""
        if self.platforms is not None:
            return self.platforms

        from primr.core.platform_mapper import DEFAULT_PLATFORM_FALLBACK

        return DEFAULT_PLATFORM_FALLBACK

    @property
    def cloud_vendor(self) -> str:
        """Return the first configured vendor for compatibility."""
        return self.cloud_vendors[0]

    @property
    def has_company_info(self) -> bool:
        """Return whether a company name or website was supplied."""
        return bool(self.company_name or self.website)
