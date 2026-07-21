"""
Command-line interface for Primr research tool.

This module provides the CLI entry point and argument parsing:
- Main entry point for the primr command
- Argument parsing and validation
- Command dispatch to appropriate runners
- Utility commands (doctor, list-recent, etc.)
Usage:
    from primr.core.cli import main, parse_args, run_doctor

    # Run CLI
    main()

    # Parse arguments only
    config = parse_args(["Acme Corp", "https://acme.example", "--mode", "deep"])
"""

# PYTHON_ARGCOMPLETE_OK  (lets the global argcomplete script offer tab completion)

import argparse
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from primr.ai.genai_factory import default_genai_http_options
from primr.cli_help import (
    add_init_doctor_arguments,
    maybe_print_root_help,
    maybe_print_scoped_help,
)
from primr.config.config import LOGS_DIR, OUTPUT_DIR, WORKING_DIR
from primr.config.models import PrimrModels
from primr.core.cli_batch import (
    _DANGEROUS_LEAD_CHARS as _DANGEROUS_LEAD_CHARS,
)
from primr.core.cli_batch import (
    _classify_columns as _classify_columns,
)
from primr.core.cli_batch import (
    _ColumnMap as _ColumnMap,
)
from primr.core.cli_batch import (
    _csv_safe as _csv_safe,
)
from primr.core.cli_batch import _ensure_valid_url
from primr.core.cli_batch import (
    _read_batch_file as _read_batch_file,
)
from primr.core.cli_calibration_args import add_calibration_arguments
from primr.core.cli_command_output import report_command_error
from primr.core.cli_dispatch import (
    is_mcp_command,
    is_skills_command,
    is_update_command,
    run_mcp,
    run_skills,
    run_update_cli,
)
from primr.core.cli_doctor import (
    _check_api_connectivity as _check_api_connectivity,
)
from primr.core.cli_doctor import (
    _check_api_keys as _check_api_keys,
)
from primr.core.cli_doctor import (
    _check_dependencies as _check_dependencies,
)
from primr.core.cli_doctor import (
    _check_filesystem as _check_filesystem,
)
from primr.core.cli_doctor import (
    _check_gemini_resources as _check_gemini_resources,
)
from primr.core.cli_doctor import (
    _check_providers as _check_providers,
)
from primr.core.cli_doctor import (
    run_doctor,
)
from primr.core.cli_dryrun import run_dry_run
from primr.core.cli_errors import guard_dispatch
from primr.core.cli_eval_args import add_eval_arguments
from primr.core.cli_inference import prepare_batch_inference_runtime
from primr.core.cli_init import (
    _ensure_project_env_file as _ensure_project_env_file,
)
from primr.core.cli_init import (
    _install_playwright_browsers as _install_playwright_browsers,
)
from primr.core.cli_init import (
    _key_looks_configured as _key_looks_configured,
)
from primr.core.cli_init import (
    _playwright_browsers_ready as _playwright_browsers_ready,
)
from primr.core.cli_init import (
    _prompt_yes_no,
    _run_init_flow,
    _should_offer_interactive_key_setup,
)
from primr.core.cli_init import (
    _validate_key_live as _validate_key_live,
)
from primr.core.cli_job_cleanup import run_clear_pending_jobs
from primr.core.cli_keys import run_keys
from primr.core.cli_memory import (
    handle_company as _handle_company,
)
from primr.core.cli_memory import (
    handle_memory as _handle_memory,
)
from primr.core.cli_memory import (
    rewrite_company_command_args as _rewrite_company_command_args,
)
from primr.core.cli_parser import (
    CLI_EPILOG,
    _determine_command,
    add_inference_arguments,
    add_research_input_arguments,
    add_vendor_research_arguments,
    enable_shell_completion,
)
from primr.core.cli_parser import (
    _discover_strategies as _discover_strategies,
)
from primr.core.cli_plan import run_plan
from primr.core.cli_preflight import _run_network_preflight_checks, _run_preflight_checks
from primr.core.cli_recovery import (
    check_pending_jobs,
    resume_pending_jobs,
)
from primr.core.cli_research_request import (
    report_research_workspace_error,
    resolve_research_context_files,
    validate_research_request,
)
from primr.core.cli_validation_policy import should_include_api_keys
from primr.core.cli_vendor import run_generate_vendor
from primr.utils.banner import maybe_show_startup_banner
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("cli")


def _list_installed_ollama_models() -> set[str]:
    """Best-effort listing of locally available Ollama models."""
    import subprocess

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
    except Exception:
        return set()

    models: set[str] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("name "):
            continue
        parts = stripped.split()
        if parts:
            models.add(parts[0])
    return models


def _resolve_local_judge_models(config: "CLIConfig") -> tuple[list[str], list[str]]:
    """Resolve the requested local judge models and return (selected, missing)."""
    from primr.config.local_eval_models import get_local_eval_model_list

    selected: list[str] = []
    if config.eval_judge_models:
        selected.extend(config.eval_judge_models)
    elif config.eval_judge_model_list:
        selected.extend(get_local_eval_model_list(config.eval_judge_model_list))
    else:
        selected.append(config.eval_judge_model)

    # Deduplicate while preserving order.
    selected = list(dict.fromkeys(model.strip() for model in selected if model and model.strip()))
    installed = _list_installed_ollama_models()
    if not installed:
        return selected, []

    available = [model for model in selected if model in installed]
    missing = [model for model in selected if model not in installed]
    return available, missing


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
    # Agentic architecture commands
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
    platforms: tuple[str, ...] | None = None  # None = auto-detect from recon
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
    json_output: bool = False  # --json: machine-readable stdout
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
    strategy_type: str = "ai"  # Type of strategy to generate
    framing_purpose: str | None = None  # Research framing (tradecraft Step 1)
    framing_audience: str | None = None
    framing_decision: str | None = None
    framing_question: str | None = None
    resume_latest: bool = False
    resume_local: bool = False
    lite_strategy: bool = False  # Use Pro model instead of Deep Research for strategy
    # Opt in to the thorough (Deep Research) engine for standalone --ai-strategy-only.
    # That command defaults to the ~$1 lite engine; this flag restores Deep Research.
    deep_research_strategy: bool = False
    fast_mode: bool = False  # Use Grok 4.1 for fast research (~12 min, ~$0.25)
    premium_mode: bool = False  # Force Gemini + Deep Research pipeline
    grok_tier: str = "hybrid"  # Grok model tier: fast, hybrid, max
    inference_profile: str = "cloud"  # Capability-routing profile for wired stages
    acknowledge_host_agent_may_bill: bool = False
    # Default on after the n=3 pilot; --no-continuous-reasoning disables it.
    continuous_reasoning: bool = True
    no_qa: bool = False  # Disable automatic quality assessment
    verify: bool = False  # Run post-QA claim verification
    budget_usd: float | None = None  # Per-run cost ceiling (--budget)
    skip_scrape_validation: bool = False  # Continue even when scrape quality is too low
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
    calibrate_judge: str = "cloud"  # cloud | local | auto
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
        """Backward-compatible alias. Returns platforms or the agnostic default."""
        if self.platforms is not None:
            return self.platforms

        from primr.core.platform_mapper import DEFAULT_PLATFORM_FALLBACK

        return DEFAULT_PLATFORM_FALLBACK

    @property
    def cloud_vendor(self) -> str:
        """Backward-compatible single vendor access."""
        return self.cloud_vendors[0]

    @property
    def has_company_info(self) -> bool:
        """Check if company name or website is provided."""
        return bool(self.company_name or self.website)


class CLIRunner(Protocol):
    """Protocol for CLI command runners."""

    def run(self, config: CLIConfig) -> int:
        """Run the command and return exit code."""
        ...


# Mode name mapping (new -> old internal names)
MODE_MAP = {
    "scrape": "scrape-only",  # Scrape + insights (uses LLM for summarization)
    "deep": "deep-research",
    "full": "complete",
    "premium": "complete",  # Explicitly request Gemini + Deep Research pipeline
    "parallel": "hybrid",
    # Also accept old names for backwards compatibility
    "structured": "structured",
    "deep-research": "deep-research",
    "complete": "complete",
    "hybrid": "hybrid",
    "scrape-only": "scrape-only",
}


def parse_args(args: list[str] | None = None) -> CLIConfig:
    """
    Parse command-line arguments.

    Args:
        args: List of arguments (defaults to sys.argv[1:])

    Returns:
        CLIConfig with parsed values
    """
    maybe_print_root_help(args)
    maybe_print_scoped_help(args)
    parser = _create_parser()
    parsed = parser.parse_args(_rewrite_company_command_args(args, parser))
    get = getattr

    command = _determine_command(parsed, Command, _POSITIONAL_COMMANDS, _FLAG_COMMANDS)

    mode = MODE_MAP.get(parsed.mode, parsed.mode)

    if getattr(parsed, "no_ai_strategy", False):
        ai_strategy = False
    elif mode in ("scrape-only",):
        ai_strategy = False  # Scrape mode doesn't need AI strategy
    else:
        ai_strategy = True

    # Continuous reasoning is on by default after the n=3 pilot.
    # --no-continuous-reasoning explicitly disables it for one run.
    if getattr(parsed, "no_continuous_reasoning", False):
        continuous_reasoning = False
    else:
        continuous_reasoning = getattr(parsed, "continuous_reasoning", True)

    context_files = tuple(getattr(parsed, "context", None) or [])

    banner_arg = getattr(parsed, "banner", None)
    no_banner = getattr(parsed, "no_banner", False)
    banner_explicit = banner_arg is not None or no_banner
    if no_banner:
        banner_mode = "off"
    elif banner_arg is None:
        banner_mode = "auto"
    else:
        banner_mode = banner_arg

    is_batch = bool(getattr(parsed, "batch", None) or parsed.csv)
    requires_confirmation = is_batch or bool(
        getattr(parsed, "ai_strategy_only", None)
        or getattr(parsed, "generate_vendor_research", None)
    )
    skip_confirm_flag = getattr(parsed, "skip_confirm", False)
    skip_confirm = skip_confirm_flag if requires_confirmation else True

    # Handle --platform / --cloud-vendor resolution
    raw_platforms = getattr(parsed, "platform", None)
    raw_cloud_vendor = getattr(parsed, "cloud_vendor", None)

    if raw_cloud_vendor is not None:
        import sys as _sys

        print("WARNING: --cloud-vendor is deprecated, use --platform instead", file=_sys.stderr)
        platforms = tuple(dict.fromkeys(raw_cloud_vendor))
    elif raw_platforms is not None:
        _PLATFORM_ALIASES: dict[str, str] = {
            "microsoft": "azure",
            "amazon": "aws",
            "google": "gcp",
            "nvidia": "private",
        }
        expanded: list[str] = []
        for p in raw_platforms:
            if p == "ms":
                expanded.extend(["azure", "private"])
            else:
                expanded.append(_PLATFORM_ALIASES.get(p, p))
        platforms = tuple(dict.fromkeys(expanded))
    else:
        platforms = None

    return CLIConfig(
        command=command,
        company_name=parsed.company,
        website=parsed.website,
        mode=mode,
        citation_style=getattr(parsed, "citation_style", "numbered"),
        ai_strategy=ai_strategy,
        platforms=platforms,
        skip_recon=getattr(parsed, "skip_recon", False),
        skip_confirm=skip_confirm,
        context_files=context_files,
        context_folder=getattr(parsed, "context_folder", None),
        refresh_vendor_research=getattr(parsed, "refresh_vendor_research", False),
        generate_vendor=getattr(parsed, "generate_vendor_research", None),
        csv_file=parsed.csv,
        batch_file=getattr(parsed, "batch", None),
        industry=getattr(parsed, "industry", None),
        limit=getattr(parsed, "limit", None),
        enrich=getattr(parsed, "enrich", False),
        output_dir=getattr(parsed, "output_dir", None),
        open_after=getattr(parsed, "open", False),
        quiet=parsed.quiet,
        json_output=parsed.json,
        verbose=parsed.verbose,
        test_accordion_topic=getattr(parsed, "test_accordion", None),
        test_accordion_pages=getattr(parsed, "accordion_pages", 50),
        analyze_report_path=getattr(parsed, "analyze_report", None),
        qa_company=getattr(parsed, "qa", None),
        qa_recent_count=getattr(parsed, "qa_recent", None),
        max_scrape_time=getattr(parsed, "max_scrape_time", None),
        ai_strategy_only_path=getattr(parsed, "ai_strategy_only", None),
        dry_run_requested=getattr(parsed, "dry_run", False),
        discovery_notes_path=getattr(parsed, "discovery_notes", None),
        strategy_type=getattr(parsed, "strategy_type", "ai"),
        framing_purpose=getattr(parsed, "purpose", None),
        framing_audience=getattr(parsed, "audience", None),
        framing_decision=getattr(parsed, "decision", None),
        framing_question=getattr(parsed, "question", None),
        improve_path=(
            getattr(parsed, "improve", None)
            or (
                parsed.website
                if (parsed.company and str(parsed.company).lower() == "improve")
                else None
            )
        ),
        improve_in_place=getattr(parsed, "in_place", False),
        improve_agentic=getattr(parsed, "improve_agentic", False),
        refine_company=(
            parsed.website if (parsed.company and str(parsed.company).lower() == "refine") else None
        ),
        refine_target_grade=getattr(parsed, "target_grade", 90.0),
        calibrate_target=(
            parsed.website
            if (parsed.company and str(parsed.company).lower() == "calibrate")
            else None
        ),
        calibrate_recent=getattr(parsed, "calibrate_recent", None),
        calibrate_max_per_label=getattr(parsed, "max_per_label", 10),
        calibrate_dry_run=getattr(parsed, "dry_run", False),
        calibrate_judge=getattr(parsed, "judge", "cloud"),
        calibrate_judge_model=getattr(parsed, "judge_model", None),
        calibrate_judge_compare=getattr(parsed, "judge_compare", False),
        calibrate_pack_manifest=getattr(parsed, "pack_manifest", None),
        calibrate_pack_selection=getattr(parsed, "pack_selection", None),
        calibrate_pack_selection_template=get(parsed, "pack_selection_template", None),
        calibrate_inspect_selection=get(parsed, "inspect_selection", None),
        calibrate_baseline_from=get(parsed, "baseline_from", None),
        calibrate_baseline_out=get(parsed, "baseline_out", None),
        calibrate_baseline_md=get(parsed, "baseline_md", None),
        calibrate_baseline_min_reports=get(parsed, "baseline_min_reports", 5),
        calibrate_inspect_baseline=get(parsed, "inspect_baseline", None),
        calibrate_inspect_baseline_decision=get(parsed, "inspect_baseline_decision", None),
        calibrate_baseline_decision_from=get(parsed, "baseline_decision_from", None),
        calibrate_baseline_decision_out=get(parsed, "baseline_decision_out", None),
        calibrate_baseline_decision=get(parsed, "baseline_decision", None),
        calibrate_baseline_decision_reviewer=get(parsed, "baseline_decision_reviewer", None),
        calibrate_baseline_decision_rationale=get(parsed, "baseline_decision_rationale", None),
        calibrate_baseline_decision_notes=tuple(get(parsed, "baseline_decision_note", ())),
        banner_mode=banner_mode,
        banner_explicit=banner_explicit,
        resume_latest=getattr(parsed, "resume_latest", False),
        resume_local=getattr(parsed, "resume_local", False),
        lite_strategy=getattr(parsed, "lite_strategy", False),
        deep_research_strategy=getattr(parsed, "deep_research_strategy", False),
        fast_mode=getattr(parsed, "fast_mode", False),
        premium_mode=(
            getattr(parsed, "premium_mode", False) or getattr(parsed, "mode", None) == "premium"
        ),
        grok_tier=getattr(parsed, "grok_tier", "hybrid"),
        inference_profile=getattr(parsed, "inference_profile", "cloud"),
        acknowledge_host_agent_may_bill=getattr(parsed, "acknowledge_host_agent_may_bill", False),
        continuous_reasoning=continuous_reasoning,
        no_qa=getattr(parsed, "no_qa", False),
        verify=getattr(parsed, "verify", False),
        budget_usd=getattr(parsed, "budget", None),
        skip_scrape_validation=getattr(parsed, "skip_scrape_validation", False),
        browser_headed=getattr(parsed, "browser_headed", False),
        browser_session_mode=getattr(parsed, "browser_session", "isolated"),
        memory_company=getattr(parsed, "memory", None),
        memory_list=getattr(parsed, "memory_list", False),
        company_profile_track=getattr(parsed, "company_track", None),
        company_profile_url=getattr(parsed, "company_url", None),
        company_profile_show=getattr(parsed, "company_show", None),
        company_profile_export=getattr(parsed, "company_export", None),
        company_profile_list=getattr(parsed, "company_list", False),
        orchestrate_max_cost=getattr(parsed, "max_cost", None),
        roadmap_version=getattr(parsed, "roadmap_version", None),
        eval_mode=getattr(parsed, "eval_mode", False),
        eval_id=getattr(parsed, "eval_id", None),
        eval_root=getattr(parsed, "eval_root", "output/evals"),
        eval_profiles=tuple(
            dict.fromkeys(getattr(parsed, "eval_profiles", ["full", "lite", "fast"]))
        ),
        eval_baseline=getattr(parsed, "eval_baseline", "full"),
        eval_manifest=getattr(parsed, "eval_manifest", None),
        eval_run_missing=getattr(parsed, "eval_run_missing", False),
        eval_max_new_runs=getattr(parsed, "eval_max_new_runs", 0),
        eval_max_estimated_cost=getattr(parsed, "eval_max_estimated_cost", 0.0),
        eval_quality_ratio_threshold=getattr(parsed, "eval_quality_ratio_threshold", 0.8),
        eval_cost_ratio_threshold=getattr(parsed, "eval_cost_ratio_threshold", 0.2),
        eval_company=getattr(parsed, "eval_company", None),
        eval_source_dir=getattr(parsed, "eval_source_dir", "output"),
        eval_auto_stage=not getattr(parsed, "eval_no_auto_stage", False),
        eval_llm_judge=getattr(parsed, "eval_llm_judge", False),
        eval_judge_provider=getattr(parsed, "eval_judge_provider", "grok"),
        eval_judge_model=getattr(parsed, "eval_judge_model", "grok-4.3"),
        eval_judge_models=tuple(dict.fromkeys(getattr(parsed, "eval_judge_models", []) or [])),
        eval_judge_model_list=getattr(parsed, "eval_judge_model_list", None),
        eval_judge_base_url=getattr(parsed, "eval_judge_base_url", None),
        eval_judge_api_key_env=getattr(parsed, "eval_judge_api_key_env", "LOCAL_LLM_API_KEY"),
        eval_judge_max_pairs=getattr(parsed, "eval_judge_max_pairs", 1),
        eval_judge_passes=getattr(parsed, "eval_judge_passes", 1),
        eval_judge_max_cost=getattr(parsed, "eval_judge_max_cost", 0.0),
        eval_local_stage=getattr(parsed, "eval_local_stage", None),
        eval_stage_semantic_judge=getattr(parsed, "eval_stage_semantic_judge", False),
        eval_stage_semantic_judge_model=getattr(parsed, "eval_stage_semantic_judge_model", None),
        eval_source_relevance_fixture=getattr(parsed, "eval_source_relevance_fixture", None),
        eval_page_access_fixture=getattr(parsed, "eval_page_access_fixture", None),
        eval_working_root=getattr(parsed, "eval_working_root", "working"),
        eval_stage_scorecard=getattr(parsed, "eval_stage_scorecard", False),
        eval_stage_quality=getattr(parsed, "eval_stage_quality", None),
        eval_stage_route_root=getattr(parsed, "eval_stage_route_root", None),
        eval_stage_id=getattr(parsed, "eval_stage_id", None),
        eval_stage_min_quality_score=getattr(parsed, "eval_stage_min_quality_score", 85.0),
        eval_stage_max_failure_rate=getattr(parsed, "eval_stage_max_failure_rate", 0.0),
        doctor_fix=getattr(parsed, "fix", False),
        doctor_scraper_stats=getattr(parsed, "scraper_stats", False),
        init_non_interactive=getattr(parsed, "non_interactive", False),
        init_yes=getattr(parsed, "yes", False),
        init_skip_browsers=getattr(parsed, "skip_browsers", False),
        init_no_doctor=getattr(parsed, "no_doctor", False),
    )


def _is_recon_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr recon ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "recon"


def _is_keys_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr keys ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] in {"keys", "key"}


def _run_recon(args: list[str] | None) -> int:
    """Delegate to the external recon-tool Typer CLI, returning an exit code.

    Recon is now a separate pip-installable project (``recon-tool``) maintained
    out-of-tree. We only mount its Typer app here so ``primr recon <domain>``
    continues to work as a shorthand. The recon-tool package itself handles
    shorthand routing via invoke_without_command, so no sys.argv preprocessing
    is needed from primr.
    """
    try:
        from recon_tool.cli import app as recon_app
    except ImportError:
        print(
            "Error: recon-tool is not installed. Run: pip install recon-tool",
            file=sys.stderr,
        )
        return 1

    argv = args if args is not None else sys.argv[1:]
    # Strip the leading "recon" token - the Typer app doesn't expect it.
    recon_argv = argv[1:]

    # Typer/Click reads from sys.argv by default. Temporarily replace it so
    # the recon app sees the correct arguments.
    saved_argv = sys.argv
    try:
        sys.argv = ["recon", *list(recon_argv)]
        recon_app(standalone_mode=False)
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.argv = saved_argv


def main(args: list[str] | None = None) -> int:
    """Run the main CLI entry point and return its process exit code."""
    # Intercept "primr recon ..." before argparse - delegate to the recon Typer app.
    if _is_recon_command(args):
        return _run_recon(args)
    if _is_keys_command(args):
        return run_keys(args)
    if is_mcp_command(args):
        return run_mcp(args)
    if is_skills_command(args):
        return run_skills(args)
    if is_update_command(args):
        return run_update_cli(args)

    from pathlib import Path

    from primr.utils.config_validation import validate_config
    from primr.utils.logging_config import setup_logging

    config = parse_args(args)

    # Validate configuration early, requiring provider keys only for command paths that use them.
    include_api_keys = should_include_api_keys(config)

    validation_result = validate_config(include_api_keys=include_api_keys)
    if not validation_result.valid:
        if config.json_output:
            return report_command_error(
                json_output=True,
                operation=config.command.value,
                error_type="configuration_invalid",
                message="Configuration validation failed",
                hints=tuple(str(error) for error in validation_result.errors),
            )
        if _should_offer_interactive_key_setup(validation_result):
            console.warn("No API keys configured yet.")
            console.info("Primr will tell you what each key is for and where to get it.")
            console.blank()
            if _prompt_yes_no(
                "Set them up now? (paste keys when prompted, no .env editing)", default=True
            ):
                init_rc = _run_init_flow(
                    non_interactive=False,
                    assume_yes=False,
                    skip_browsers=True,
                    run_doctor_after=False,
                )
                if init_rc != 0:
                    return init_rc
                from primr.utils.config_validation import reset_config

                reset_config()
                validation_result = validate_config(include_api_keys=include_api_keys)
                if validation_result.valid:
                    console.blank()
                    console.ok("Keys saved. Continuing...")
                    console.blank()
                else:
                    console.error("Configuration validation failed:")
                    for err in validation_result.errors:
                        console.error(f"  - {err}")
                    return 1
            else:
                console.info("Run 'primr init' when you're ready.")
                return 1
        else:
            console.error("Configuration validation failed:")
            for err in validation_result.errors:
                console.error(f"  - {err}")
            return 1

    # Setup logging to proper directory (not root!)
    log_level = "DEBUG" if config.verbose else "INFO"
    console_level = "INFO" if config.verbose else "WARNING"
    setup_logging(
        level=log_level,
        log_dir=Path(LOGS_DIR).parent,  # logs/ directory (LOGS_DIR is logs/chat_history)
        console_level=console_level,
    )

    # Configure console. --json implies quiet so progress chrome can't
    # interleave with the JSON object on stdout.
    if config.quiet or config.json_output:
        from primr.utils.console import Console, set_console

        set_console(Console(quiet=True))
    elif config.verbose:
        from primr.utils.console import Console, set_console

        set_console(Console(verbose=True))

    maybe_show_startup_banner(
        mode=config.banner_mode,
        quiet=config.quiet,
        explicit=config.banner_explicit,
    )

    # Allow explicit "primr --banner" as a no-op command.
    if (
        config.banner_explicit
        and config.command == Command.RESEARCH
        and not config.has_company_info
    ):
        return 0

    # Dispatch to appropriate handler
    handlers = {
        Command.INIT: _handle_init,
        Command.DOCTOR: _handle_doctor,
        Command.LIST_RECENT: _handle_list_recent,
        Command.CLEAN_TEMP: _handle_clean_temp,
        Command.CHECK_QUOTA: _handle_check_quota,
        Command.CHECK_JOBS: _handle_check_jobs,
        Command.RESUME_LATEST: _handle_resume_latest,
        Command.CLEAR_JOBS: _handle_clear_jobs,
        Command.LIST_STRATEGIES: _handle_list_strategies,
        Command.SHOW_USAGE: _handle_show_usage,
        Command.DRY_RUN: run_dry_run,
        Command.PLAN: run_plan,
        Command.GENERATE_VENDOR: run_generate_vendor,
        Command.BATCH: _handle_batch,
        Command.ENRICH: _handle_enrich,
        Command.TEST_ACCORDION: _handle_test_accordion,
        Command.ANALYZE_REPORT: _handle_analyze_report,
        Command.QA: _handle_qa,
        Command.QA_RECENT: _handle_qa_recent,
        Command.AI_STRATEGY_ONLY: _handle_ai_strategy_only,
        Command.EVAL: _handle_eval,
        Command.RESEARCH: _handle_research,
        # Agentic architecture handlers
        Command.COMPANY: _handle_company,
        Command.MEMORY: _handle_memory,
        Command.ORCHESTRATE: _handle_orchestrate,
        Command.ROADMAP: _handle_roadmap,
        Command.IMPROVE: _handle_improve,
        Command.REFINE: _handle_refine,
        Command.CALIBRATE: _handle_calibrate,
    }

    handler = handlers.get(config.command, _handle_research)
    # guard_dispatch adds top-level interrupt/error handling (route to
    # `primr doctor`, --verbose for the traceback) and the post-run update notice.
    return guard_dispatch(handler, config)


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="primr",
        description="Primr - AI-powered company research",
        # No prefix abbreviation: argparse's default expands any unambiguous
        # flag prefix (e.g. `--qa-` silently ran the QA summary), which makes
        # typos execute real commands. Found by the Hypothesis CLI property
        # test (invalid flags must exit non-zero).
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )

    from primr import __version__ as _primr_version

    parser.add_argument(
        "--version",
        action="version",
        version=f"primr {_primr_version}",
    )
    parser.add_argument(
        "--help-all",
        action="help",
        help="Show every command and advanced option",
    )

    # Positional arguments
    parser.add_argument("company", nargs="?", type=str, help="Company name")
    parser.add_argument("website", nargs="?", type=str, help="Company website URL")

    # Batch mode
    parser.add_argument("--csv", type=str, help="CSV file for batch processing")
    parser.add_argument(
        "--batch", type=str, metavar="FILE", help="Excel (.xlsx) or CSV file for batch research"
    )
    parser.add_argument("--industry", type=str, help="Filter batch rows by industry column value")
    parser.add_argument("--limit", type=int, help="Max number of companies to process in batch")
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich mode: look up websites, save CSV, don't run research",
    )
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="Explicitly approve non-interactive batch, strategy, or vendor research execution",
    )

    # Research options
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        choices=[
            "scrape",
            "deep",
            "full",
            "premium",
            "parallel",
            "structured",
            "deep-research",
            "complete",
            "hybrid",
        ],
        default="full",
        help="Research mode: scrape (corpus + insights), deep, full (default, uses fast mode when XAI_API_KEY set), premium (Gemini + Deep Research)",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout (research result, or estimate with --dry-run)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed output")
    add_init_doctor_arguments(parser)
    parser.add_argument(
        "--banner",
        nargs="?",
        const="animated",
        choices=["auto", "off", "static", "animated"],
        default=None,
        help="Control startup banner (default: auto for interactive terminals)",
    )
    parser.add_argument("--no-banner", action="store_true", help="Disable startup banner")
    parser.add_argument(
        "--citation-style",
        type=str,
        choices=["numbered", "inline", "sidecar"],
        default="numbered",
        help="Citation style (default: numbered)",
    )
    parser.add_argument(
        "--ai-strategy", action="store_true", default=True, help="Generate AI recommendations"
    )
    parser.add_argument("--no-ai-strategy", action="store_true", help="Disable AI strategy")
    parser.add_argument("--no-qa", action="store_true", help="Disable automatic quality assessment")
    parser.add_argument(
        "--verify", action="store_true", help="Run post-QA claim verification (~$0.01, 3-5 min)"
    )
    parser.add_argument(
        "--skip-scrape-validation",
        action="store_true",
        help="Allow run to continue even when website scraping is too thin/failing",
    )
    parser.add_argument(
        "--browser-headed",
        "--headed",
        action="store_true",
        help="Use a visible browser window for scraping instead of forcing headless mode",
    )
    parser.add_argument(
        "--browser-session",
        choices=["isolated", "persistent"],
        default="persistent",
        help="Browser session behavior: persistent per host for the run (default) or isolated per page",
    )
    parser.add_argument(
        "--resume-local",
        action="store_true",
        help="Reuse latest incomplete local working folder for this company and continue from checkpoints",
    )
    # --platform / --cloud-vendor mutually exclusive group
    platform_group = parser.add_mutually_exclusive_group()
    platform_group.add_argument(
        "--platform",
        type=str,
        nargs="+",
        choices=[
            "azure",
            "microsoft",
            "aws",
            "amazon",
            "gcp",
            "google",
            "agnostic",
            "private",
            "nvidia",
            "ms",
        ],
        default=None,
        help="Target platform(s). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private, ms=azure+private. Auto-detected from recon if omitted.",
    )
    platform_group.add_argument(
        "--cloud-vendor",
        type=str,
        nargs="+",
        choices=["azure", "aws", "gcp", "agnostic", "private"],
        default=None,
        help=argparse.SUPPRESS,  # Hidden deprecated alias
    )
    parser.add_argument(
        "--skip-recon",
        action="store_true",
        help="Skip DNS intelligence pre-flight step",
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        dest="lite_strategy",
        help="Use the Pro model for AI strategy (the default for --ai-strategy-only): fast, ~$1, less depth",
    )
    parser.add_argument(
        "--deep-research",
        action="store_true",
        dest="deep_research_strategy",
        help="Opt --ai-strategy-only into the thorough Deep Research engine (~$2.50/task) instead of the ~$1 default",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        dest="fast_mode",
        help="Fast mode (now the default when XAI_API_KEY is set). Explicit flag for backward compat",
    )
    parser.add_argument(
        "--premium",
        action="store_true",
        dest="premium_mode",
        help="Premium mode: Gemini + Deep Research pipeline (~$5, 50-75 min). Use for maximum depth",
    )
    parser.add_argument(
        "--grok-tier",
        choices=["fast", "hybrid", "max"],
        default="hybrid",
        dest="grok_tier",
        help="Grok tier: fast, hybrid (default), or max; use --dry-run for price",
    )
    add_inference_arguments(parser)
    parser.add_argument(
        "--continuous-reasoning",
        action="store_true",
        default=True,
        dest="continuous_reasoning",
        help=(
            "Share a single Grok session across workbook + cross-validation so the "
            "validator inherits corpus + workbook reasoning. On by default after the "
            "n=3 pilot; pass --no-continuous-reasoning to revert to fresh-call topology. "
            "Cost impact varies by company (avg ~+12%%, range -4%% to +32%%)."
        ),
    )
    parser.add_argument(
        "--no-continuous-reasoning",
        action="store_true",
        help=(
            "Disable the shared Grok session for workbook + cross-validation "
            "(revert to the fresh-call topology used before the n=3 pilot)."
        ),
    )
    add_research_input_arguments(parser)
    parser.add_argument("--dry-run", action="store_true", help="Show cost estimate only")
    parser.add_argument(
        "--plan", action="store_true", help="Preview framing + hypothesis tree + outline, then exit"
    )
    parser.add_argument("--show-usage", action="store_true", help="Display usage statistics")
    parser.add_argument("--open", action="store_true", help="Open report after generation")
    parser.add_argument("--output-dir", type=str, help="Custom output directory")
    parser.add_argument("--list-recent", action="store_true", help="List recent outputs")
    parser.add_argument("--clean-temp", action="store_true", help="Clean temporary files")
    add_vendor_research_arguments(parser)
    parser.add_argument(
        "--check-jobs",
        action="store_true",
        help="Read pending cloud job status and show the latest local run state",
    )
    parser.add_argument(
        "--resume-latest",
        "--resume-jobs",
        action="store_true",
        help="Finalize completed jobs and acknowledge provider-terminal jobs",
    )
    parser.add_argument(
        "--clear-jobs",
        action="store_true",
        help="Confirm and remove all pending recovery records",
    )
    parser.add_argument(
        "--list-strategies", action="store_true", help="List available strategy documents"
    )
    parser.add_argument("--check-quota", action="store_true", help="Check API quota")
    parser.add_argument(
        "--max-scrape-time",
        type=int,
        default=None,
        help="Max minutes for scraping phase (default: 10, env: PRIMR_MAX_SCRAPE_TIME)",
    )

    # Accordion Method test
    parser.add_argument(
        "--test-accordion",
        type=str,
        metavar="TOPIC",
        help="Test Accordion Method with a standalone topic (e.g., 'Oceanography 2026-2030')",
    )
    parser.add_argument(
        "--accordion-pages",
        type=int,
        default=50,
        help="Target pages for Accordion test (default: 50)",
    )

    # Report analysis
    parser.add_argument(
        "--analyze-report",
        type=str,
        metavar="PATH",
        help="Analyze quality of an existing report file",
    )

    parser.add_argument(
        "--improve",
        type=str,
        metavar="PATH",
        help="Improve an existing .md/.txt report or strategy output",
    )
    parser.add_argument(
        "--in-place", action="store_true", help="When used with --improve, overwrite the input file"
    )
    parser.add_argument(
        "--improve-agentic",
        action="store_true",
        help="With --improve, run an agentic review pass before deterministic cleanup",
    )
    parser.add_argument(
        "--target-grade",
        type=float,
        default=90.0,
        help="With 'refine', the QA grade to iterate toward (default: 90)",
    )
    add_calibration_arguments(parser)
    # QA review
    parser.add_argument(
        "--qa",
        type=str,
        metavar="COMPANY_OR_PATH",
        help="Show detailed QA analysis for a company report or analyze a specific file path",
    )
    parser.add_argument(
        "--qa-recent",
        type=int,
        nargs="?",
        const=5,
        metavar="N",
        help="Show QA summary for N most recent reports (default: 5)",
    )

    # AI Strategy retry/resume
    parser.add_argument(
        "--ai-strategy-only",
        type=str,
        metavar="REPORT_PATH",
        help="Generate a governed strategy from an existing report; use --dry-run first",
    )

    # Agentic architecture commands
    parser.add_argument(
        "--memory",
        type=str,
        metavar="COMPANY",
        help="View research memory (hypotheses) for a company",
    )
    parser.add_argument(
        "--memory-list", action="store_true", help="List all companies with research memory"
    )
    parser.add_argument(
        "--company-track",
        type=str,
        metavar="COMPANY",
        help="Track a company profile in the local per-user data directory",
    )
    parser.add_argument(
        "--company-url",
        type=str,
        metavar="URL",
        help="Company URL for --company-track",
    )
    parser.add_argument(
        "--company-list",
        action="store_true",
        help="List tracked company profiles",
    )
    parser.add_argument(
        "--company-show",
        type=str,
        metavar="COMPANY",
        help="Show a tracked company profile",
    )
    parser.add_argument(
        "--company-export",
        type=str,
        metavar="COMPANY",
        help="Export a tracked company profile bundle",
    )
    parser.add_argument(
        "--orchestrate",
        action="store_true",
        help="Run orchestrated research with subagent coordination (experimental)",
    )
    parser.add_argument(
        "--max-cost", type=float, help="Maximum cost budget for orchestrated research (USD)"
    )
    parser.add_argument(
        "--budget",
        type=float,
        help=(
            "Per-run cost ceiling in USD. Refuses to start when the estimate "
            "exceeds it. Fast-mode full runs also checkpoint optional stages "
            "against actual spend; non-fast Deep Research paths checkpoint "
            "optional strategy documents after the required Deep Research task."
        ),
    )
    parser.add_argument("--roadmap", action="store_true", help="Show roadmap information")
    parser.add_argument(
        "--roadmap-version",
        type=str,
        metavar="VERSION",
        help="Show details for a specific roadmap version (e.g., 'v1.7.0')",
    )

    add_eval_arguments(parser)

    # Tab completion via argcomplete when installed (no-op otherwise).
    enable_shell_completion(parser)
    return parser


_POSITIONAL_COMMANDS: dict[str, Command] = {
    "init": Command.INIT,
    "doctor": Command.DOCTOR,
    "company": Command.COMPANY,
    "memory": Command.MEMORY,
    "orchestrate": Command.ORCHESTRATE,
    "roadmap": Command.ROADMAP,
    "improve": Command.IMPROVE,
    "refine": Command.REFINE,
    "calibrate": Command.CALIBRATE,
}

# (attr_name, command) - checked with getattr(args, attr, None) for truthiness
_FLAG_COMMANDS: list[tuple[str, Command]] = [
    ("company_track", Command.COMPANY),
    ("company_list", Command.COMPANY),
    ("company_show", Command.COMPANY),
    ("company_export", Command.COMPANY),
    ("memory", Command.MEMORY),
    ("memory_list", Command.MEMORY),
    ("orchestrate", Command.ORCHESTRATE),
    ("roadmap", Command.ROADMAP),
    ("roadmap_version", Command.ROADMAP),
    ("improve", Command.IMPROVE),
    ("eval_mode", Command.EVAL),
    ("ai_strategy_only", Command.AI_STRATEGY_ONLY),
    # qa_recent handled separately (is not None check)
    ("qa", Command.QA),
    ("analyze_report", Command.ANALYZE_REPORT),
    ("test_accordion", Command.TEST_ACCORDION),
    ("show_usage", Command.SHOW_USAGE),
    ("list_recent", Command.LIST_RECENT),
    ("clean_temp", Command.CLEAN_TEMP),
    ("check_quota", Command.CHECK_QUOTA),
    ("check_jobs", Command.CHECK_JOBS),
    ("resume_latest", Command.RESUME_LATEST),
    ("clear_jobs", Command.CLEAR_JOBS),
    ("list_strategies", Command.LIST_STRATEGIES),
    ("plan", Command.PLAN),
    ("generate_vendor_research", Command.GENERATE_VENDOR),
]


def _handle_init(config: CLIConfig) -> int:
    """Handle guided setup."""
    return _run_init_flow(
        non_interactive=config.init_non_interactive,
        assume_yes=config.init_yes,
        skip_browsers=config.init_skip_browsers,
        run_doctor_after=not config.init_no_doctor,
    )


def _handle_doctor(config: CLIConfig) -> int:
    """Handle doctor command."""
    if config.doctor_scraper_stats:
        from primr.core.cli_doctor import run_scraper_stats

        return run_scraper_stats()
    return run_doctor(fix=config.doctor_fix)


def _handle_list_recent(config: CLIConfig) -> int:
    """Handle list-recent command."""
    return list_recent_outputs(output_dir=config.output_dir, json_output=config.json_output)


def _handle_clean_temp(config: CLIConfig) -> int:
    """Handle clean-temp command."""
    clean_temp_files()
    return 0


def _handle_check_quota(config: CLIConfig) -> int:
    """Handle check-quota command."""
    check_api_quota()
    return 0


def _handle_check_jobs(config: CLIConfig) -> int:
    """Handle check-jobs command."""
    return check_pending_jobs(json_output=config.json_output)


def _handle_resume_latest(config: CLIConfig) -> int:
    """Handle resume-latest command."""
    return resume_pending_jobs()


def _handle_clear_jobs(config: CLIConfig) -> int:
    """Remove the pending recovery records confirmed by the operator."""
    return run_clear_pending_jobs(assume_yes=config.init_yes, confirm=_prompt_yes_no)


def _handle_show_usage(config: CLIConfig) -> int:
    """Handle show-usage command."""
    from primr.utils.usage_tracker import get_usage_tracker

    tracker = get_usage_tracker()
    print(tracker.display_usage_history())
    print(_format_vendor_research_freshness())
    return 0


def _format_vendor_research_freshness() -> str:
    """Show when each cached vendor research file was last refreshed.

    Vendor research is shared per-user (one paid Deep Research task per
    vendor); surfacing the age here makes it visible when a refresh is due
    instead of silently reusing stale context.
    """
    from datetime import datetime as _dt

    from primr.core.vendor_research import (
        get_vendor_news_ttl_days,
        get_vendor_research_dir,
    )

    lines = ["", "Vendor Research Freshness:", "-" * 40]
    ttl_days = get_vendor_news_ttl_days()
    try:
        research_files = sorted(get_vendor_research_dir().glob("vendor-research-*.txt"))
    except Exception:
        research_files = []

    if not research_files:
        lines.append("  (no cached vendor research yet)")
        return "\n".join(lines)

    for path in research_files:
        age_days = (_dt.now() - _dt.fromtimestamp(path.stat().st_mtime)).days
        status = "fresh" if age_days <= ttl_days else f"stale (> {ttl_days}d TTL)"
        lines.append(f"  {path.name:<44} | {age_days}d old | {status}")
    lines.append(
        f"  TTL: {ttl_days} day(s) (PRIMR_VENDOR_NEWS_TTL_DAYS) | "
        "refresh with --refresh-vendor-research"
    )
    return "\n".join(lines)


def _handle_enrich(config: CLIConfig) -> int:
    """Handle batch enrich command."""
    if not config.batch_file:
        return _batch_handler_error(
            config,
            'No batch file specified. Usage: primr --batch "file.xlsx" --enrich',
            operation="batch_enrich",
        )

    unsupported = _unsupported_enrich_option(config)
    if unsupported:
        return _batch_handler_error(
            config,
            f"{unsupported} is not supported for batch enrichment.",
            operation="batch_enrich",
        )

    return enrich_batch(
        config.batch_file,
        industry=config.industry,
        limit=config.limit,
        mode=config.mode,
        dry_run=config.dry_run_requested,
        json_output=config.json_output,
        skip_confirm=config.skip_confirm,
        budget_usd=config.budget_usd,
        output_dir=config.output_dir,
    )


def _unsupported_batch_option(config: CLIConfig) -> str | None:
    """Return the first option whose batch semantics are not governed yet."""
    checks = (
        (bool(config.context_files), "--context"),
        (bool(config.context_folder), "--context-folder"),
        (bool(config.discovery_notes_path), "--discovery-notes"),
        (bool(config.framing_purpose), "--purpose"),
        (bool(config.framing_audience), "--audience"),
        (bool(config.framing_decision), "--decision"),
        (bool(config.framing_question), "--question"),
        (config.resume_local, "--resume-local"),
        (config.refresh_vendor_research, "--refresh-vendor-research"),
        (config.open_after, "--open"),
        (config.acknowledge_host_agent_may_bill, "--acknowledge-host-agent-may-bill"),
    )
    return next((option for enabled, option in checks if enabled), None)


def _unsupported_enrich_option(config: CLIConfig) -> str | None:
    """Return the first shared option that enrichment would otherwise ignore."""
    checks = (
        (bool(config.context_files), "--context"),
        (bool(config.context_folder), "--context-folder"),
        (bool(config.discovery_notes_path), "--discovery-notes"),
        (bool(config.framing_purpose), "--purpose"),
        (bool(config.framing_audience), "--audience"),
        (bool(config.framing_decision), "--decision"),
        (bool(config.framing_question), "--question"),
        (config.resume_local, "--resume-local"),
        (config.refresh_vendor_research, "--refresh-vendor-research"),
        (config.open_after, "--open"),
        (config.acknowledge_host_agent_may_bill, "--acknowledge-host-agent-may-bill"),
    )
    return next((option for enabled, option in checks if enabled), None)


def _batch_handler_error(
    config: CLIConfig,
    message: str,
    *,
    operation: str = "batch_research",
) -> int:
    """Emit exactly one structured error for JSON callers, or one human error."""
    if config.json_output:
        from primr.core.cli_output import emit_json

        emit_json(
            {
                "schema_version": (
                    "primr.batch-enrich-plan.v1"
                    if operation == "batch_enrich"
                    else "primr.batch-plan.v1"
                ),
                "operation": operation,
                "error": True,
                "message": message,
            }
        )
    else:
        console.error(message)
    return 1


def _handle_batch(config: CLIConfig) -> int:
    """Handle batch processing (Excel or CSV)."""
    batch_path = config.batch_file or config.csv_file
    if not batch_path:
        return _batch_handler_error(
            config,
            'No file specified. Usage: primr --batch "file.xlsx" --mode scrape',
        )
    unsupported = _unsupported_batch_option(config)
    if unsupported:
        return _batch_handler_error(
            config,
            f"{unsupported} is not supported for batch research because its cost and "
            "per-row semantics are not yet governed.",
        )
    if config.json_output and not config.dry_run_requested:
        return _batch_handler_error(
            config,
            "--json is supported for batch dry-run only",
        )
    if not prepare_batch_inference_runtime(config, console):
        return 1
    from primr.core.cli_budget import resolve_batch_modes, strategy_runtime_error

    resolved_modes = resolve_batch_modes(config)
    if isinstance(resolved_modes, str):
        return _batch_handler_error(config, resolved_modes)
    use_fast_mode, use_premium_mode, mode_label = resolved_modes
    runtime_error = strategy_runtime_error(config, fast_mode=use_fast_mode)
    if runtime_error:
        return _batch_handler_error(config, runtime_error)

    def execution_preflight() -> tuple[bool, list[str]]:
        """Run network-bearing diagnostics only after batch approval."""
        preflight_ok, preflight_errors = _run_preflight_checks(
            config.mode,
            premium_mode=use_premium_mode,
            fast_mode=use_fast_mode,
            allow_network=False,
        )
        if preflight_ok:
            os.environ["PRIMR_BROWSER_SESSION_MODE"] = config.browser_session_mode
            if config.browser_headed:
                os.environ["PRIMR_BROWSER_HEADED"] = "1"
            else:
                os.environ.pop("PRIMR_BROWSER_HEADED", None)
        return preflight_ok, preflight_errors

    legacy_csv = bool(config.csv_file and not config.batch_file)
    if legacy_csv and not config.json_output:
        console.warn("--csv is deprecated; using the governed --batch workflow")
    from primr.core.cli_budget import build_run_estimate, estimate_strategy_types

    estimate = build_run_estimate(
        config,
        fast_mode=use_fast_mode,
        premium_mode=use_premium_mode,
    )
    return process_batch(
        batch_path,
        mode=config.mode,
        citation_style=config.citation_style,
        ai_strategy=config.ai_strategy,
        platforms=config.platforms,
        industry=config.industry,
        limit=config.limit,
        skip_confirm=config.skip_confirm,
        dry_run=config.dry_run_requested,
        json_output=config.json_output,
        per_company_estimate=estimate,
        mode_label=mode_label,
        output_dir=config.output_dir,
        strategies=estimate_strategy_types(config) or None,
        no_qa=config.no_qa,
        max_scrape_time=config.max_scrape_time,
        lite_strategy=config.lite_strategy,
        fast_mode=use_fast_mode,
        premium_mode=use_premium_mode,
        skip_scrape_validation=config.skip_scrape_validation,
        verify=config.verify,
        grok_tier=config.grok_tier,
        skip_recon=config.skip_recon,
        continuous_reasoning=config.continuous_reasoning,
        budget_usd=config.budget_usd,
        execution_preflight=None if config.dry_run_requested else execution_preflight,
        deprecated_alias="--csv" if legacy_csv else None,
    )


def _handle_test_accordion(config: CLIConfig) -> int:
    """Handle test-accordion command."""
    from primr.ai.accordion_test import run_accordion_test

    if not config.test_accordion_topic:
        console.error("No topic specified for Accordion test")
        console.info('Usage: primr --test-accordion "Oceanography 2026-2030"')
        return 1

    console.banner("Accordion Method Test")
    console.info(f"Topic: {config.test_accordion_topic}")
    console.info(f"Target: {config.test_accordion_pages} pages")
    console.blank()

    result = run_accordion_test(
        topic=config.test_accordion_topic,
        target_pages=config.test_accordion_pages,
    )

    if result.success:
        console.blank()
        console.success_box(
            f"Test completed: {result.page_estimate:.1f} pages", f"Output: {result.output_path}"
        )
        return 0
    else:
        console.blank()
        console.error(f"Test failed: {result.error or 'Unknown error'}")
        return 1


def _handle_analyze_report(config: CLIConfig) -> int:
    """Handle report analysis command."""
    if not config.analyze_report_path:
        console.error("Report path is required for analysis")
        return 1

    try:
        # Package-qualified import. A bare `from report_analyzer import ...`
        # resolves against sys.path, so running the CLI from a directory that
        # contains a malicious report_analyzer.py would execute it; it also
        # fails for installed users since the helper lives under primr.qa.
        from primr.qa.report_analyzer import ReportAnalyzer

        analyzer = ReportAnalyzer(config.analyze_report_path)
        report = analyzer.generate_report()
        print(report)
        return 0
    except Exception as e:
        console.error(f"Analysis failed: {e}")
        return 1


def _handle_improve(config: CLIConfig) -> int:
    """Handle output improvement command."""
    from primr.core.research_agent import improve_output_file

    improve_path = config.improve_path
    if not improve_path:
        console.error("Path is required for improve")
        console.info('Usage: primr --improve "path/to/output.md" [--in-place]')
        console.info('   or: primr improve "path/to/output.md" [--in-place]')
        return 1

    result_path = improve_output_file(
        improve_path, in_place=config.improve_in_place, use_agentic=config.improve_agentic
    )
    if not result_path:
        return 1

    action = "Updated" if config.improve_in_place else "Improved"
    console.success_box(f"{action} output", result_path)
    return 0


def _find_refine_inputs(company: str) -> tuple[str | None, str | None, str, str | None]:
    """Locate the latest markdown report + run context for a company.

    Returns (report_path, website, analysis_workbook, working_folder).
    """
    import glob as _glob
    import json as _json
    from pathlib import Path

    # Latest markdown Strategic Overview in OUTPUT_DIR
    pattern = os.path.join(OUTPUT_DIR, _glob.escape(company.replace(" ", "_")) + "*Overview*.md")
    candidates = _glob.glob(pattern) or _glob.glob(
        os.path.join(OUTPUT_DIR, _glob.escape(company) + "*Overview*.md")
    )
    report_path = max(candidates, key=os.path.getmtime) if candidates else None

    # Latest working folder for run context (website, workbook)
    website: str | None = None
    workbook = ""
    working_folder: str | None = None
    company_dir = Path(WORKING_DIR) / company.replace(" ", "_")
    if company_dir.is_dir():
        run_dirs = sorted(
            (d for d in company_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for run_dir in run_dirs:
            state_file = run_dir / "_run_state.json"
            if not state_file.exists():
                continue
            working_folder = str(run_dir)
            try:
                state = _json.loads(state_file.read_text(encoding="utf-8"))
                website = state.get("website")
            except Exception:
                pass
            workbook_file = run_dir / "analysis_workbook.md"
            if workbook_file.exists():
                try:
                    workbook = workbook_file.read_text(encoding="utf-8")[:20_000]
                except Exception:
                    workbook = ""
            break

    return report_path, website, workbook, working_folder


def _handle_refine(config: CLIConfig) -> int:
    """Handle the QA iteration loop: primr refine "Company"."""
    from primr.core.refine import refine_report

    company = config.refine_company
    if not company:
        console.error("Company name is required for refine")
        console.info('Usage: primr refine "Company Name" [--in-place] [--target-grade 90]')
        return 1

    report_path, website, workbook, working_folder = _find_refine_inputs(company)
    if not report_path:
        console.error(f"No markdown Strategic Overview found for '{company}' in {OUTPUT_DIR}")
        console.info("Run research first, or pass the report through: primr improve <path>")
        return 1

    console.banner("QA Refine")
    console.info(f"Report: {report_path}")
    if working_folder:
        console.info(f"Run context: {working_folder}")
    console.info(f"Target grade: {config.refine_target_grade:.0f}")

    result = refine_report(
        company,
        report_path,
        website=website,
        working_folder=working_folder,
        analysis_workbook=workbook,
        target_grade=config.refine_target_grade,
        in_place=config.improve_in_place,
    )

    console.info(
        f"Grade: {result.initial_grade:.0f} -> {result.final_grade:.0f} "
        f"({result.iterations} iteration(s), "
        f"{len(result.sections_regenerated)} section(s) regenerated)"
    )
    console.info(f"Stop reason: {result.stop_reason.replace('_', ' ')}")
    if result.output_path:
        console.success_box("Refined output", result.output_path)
    else:
        console.ok("No sections needed regeneration - report left unchanged")
    return 0


def _handle_calibrate(config: CLIConfig) -> int:
    """Handle the label-calibration audit: primr calibrate "Company"."""
    from primr.qa.calibration_cli import handle_calibrate

    return handle_calibrate(config, console)


def _handle_qa(config: CLIConfig) -> int:
    """Handle QA review command."""
    if not config.qa_company:
        console.error("Company name or file path is required for QA review")
        console.info('Usage: primr --qa "Company Name"')
        console.info('   or: primr --qa "path/to/report.docx"')
        return 1

    try:
        from pathlib import Path

        from primr.qa.command import QACommand

        qa_command = QACommand()
        potential_path = Path(config.qa_company)

        if potential_path.exists() and potential_path.is_file():
            return qa_command.analyze_report_file(config.qa_company)
        elif (
            config.qa_company.endswith((".docx", ".pdf"))
            or "\\" in config.qa_company
            or "/" in config.qa_company
        ):
            # Looks like a file path but doesn't exist
            console.error(f"File not found: {config.qa_company}")
            return 1
        else:
            # Treat as company name
            return qa_command.show_detailed_analysis(config.qa_company)
    except Exception as e:
        console.error(f"QA review failed: {e}")
        return 1


def _handle_qa_recent(config: CLIConfig) -> int:
    """Handle QA recent summary command."""
    count = config.qa_recent_count if config.qa_recent_count is not None else 5

    try:
        from primr.qa.command import QACommand

        qa_command = QACommand()
        return qa_command.show_recent_qa_summary(count)
    except Exception as e:
        console.error(f"QA recent summary failed: {e}")
        return 1


def _handle_ai_strategy_only(config: CLIConfig) -> int:
    """Handle governed strategy generation using an existing report."""
    from primr.core.cli_strategy import handle_ai_strategy_only
    from primr.core.research_agent import _generate_strategy_section

    return handle_ai_strategy_only(
        config,
        open_result=open_file,
        generate_strategy=_generate_strategy_section,
    )


# =============================================================================
# AGENTIC ARCHITECTURE HANDLERS
# =============================================================================


def _handle_orchestrate(config: CLIConfig) -> int:
    """Handle orchestrated research command."""
    import asyncio
    from pathlib import Path

    from primr.agentic import CostGuardHook, HookSystem, SSRFGuardHook
    from primr.agentic.memory import ResearchMemory
    from primr.agentic.orchestrator import OrchestratorConfig, ResearchOrchestrator

    # Validate inputs - handle both "orchestrate Company URL" and "--orchestrate Company URL"
    company_name = config.company_name
    website = config.website

    # If 'orchestrate' was used as positional, shift args
    if company_name and company_name.lower() == "orchestrate":
        company_name = website  # website position has company name
        website = None  # Need to get from somewhere else

    if not company_name or not website:
        console.error("Company name and website required")
        console.info('Usage: primr orchestrate "Company Name" https://company.com')
        console.info('   or: primr "Company Name" https://company.com --orchestrate')
        return 1

    website = _ensure_valid_url(website)

    console.banner("Orchestrated Research (Experimental)")
    console.info(f"Company: {company_name}")
    console.info(f"Website: {website}")
    if config.orchestrate_max_cost:
        console.info(f"Max Cost: ${config.orchestrate_max_cost:.2f}")
    console.blank()

    # Initialize components
    output_path = Path("./output")

    memory = ResearchMemory()
    hooks = HookSystem()

    # Register hooks
    if config.orchestrate_max_cost:
        hooks.register(CostGuardHook(max_cost_usd=config.orchestrate_max_cost))
    hooks.register(SSRFGuardHook())

    orchestrator_config = OrchestratorConfig(
        output_dir=output_path,
        fail_fast=False,
    )

    orchestrator = ResearchOrchestrator(
        config=orchestrator_config,
        memory=memory,
        hook_system=hooks,
    )

    console.step("Running orchestrated pipeline...")

    try:
        result = asyncio.run(
            orchestrator.research(
                company_name=company_name,
                company_url=website,
                mode="full",
            )
        )

        console.blank()

        if result.is_success:
            console.success_box("Research completed", f"Duration: {result.duration_seconds:.1f}s")
            if result.report_path:
                console.info(f"Report: {result.report_path}")
            console.info(f"Hypotheses: {len(result.hypotheses)}")
            console.info(f"Stages: {', '.join(result.completed_stages)}")
            return 0
        else:
            console.error("Research failed")
            for error in result.errors:
                console.error(f"  • {error}")
            if result.completed_stages:
                console.info(f"Completed stages: {', '.join(result.completed_stages)}")
            return 1

    except Exception as e:
        console.error(f"Orchestration failed: {e}")
        return 1


def _handle_roadmap(config: CLIConfig) -> int:
    """Handle roadmap query command."""
    from primr.agentic.roadmap_api import RoadmapAPI

    try:
        api = RoadmapAPI()
    except Exception as e:
        console.error(f"Failed to load roadmap: {e}")
        return 1

    # Show specific version
    if config.roadmap_version:
        version_str = config.roadmap_version
        if not version_str.startswith("v"):
            version_str = f"v{version_str}"

        # Remove 'v' prefix for lookup since Version uses number without 'v'
        version_num = version_str[1:] if version_str.startswith("v") else version_str
        version = api.get_version(version_num)
        if not version:
            console.error(f"Version {version_str} not found")
            console.info("Available versions:")
            from primr.agentic.models import VersionStatus

            for v in api.list_by_status(VersionStatus.COMPLETED)[:5]:
                console.info(f"  • v{v.number}")
            return 1

        console.banner(f"Roadmap: v{version.number}")
        console.info(f"Status: {version.status.value}")
        if version.title:
            console.info(f"Title: {version.title}")
        console.blank()

        if version.features:
            console.step(f"Features ({len(version.features)})")
            for feature in version.features:
                console.info(f"  • {feature.name}")
                if feature.description:
                    console.info(f"    {feature.description[:80]}...")
        return 0

    # Show roadmap overview
    console.banner("Primr Roadmap")

    current = api.get_current_version()
    if current:
        console.info(f"Current Version: v{current.number}")
    next_ver = api.get_next_version()
    if next_ver:
        console.info(f"Next Version: v{next_ver.number}")
    console.blank()

    # Show completed versions
    from primr.agentic.models import VersionStatus

    completed = api.list_by_status(VersionStatus.COMPLETED)
    if completed:
        console.step(f"Completed ({len(completed)})")
        for v in completed[-5:]:  # Show last 5
            console.ok(f"  v{v.number}: {v.title or 'No description'}")
        if len(completed) > 5:
            console.info(f"  ... and {len(completed) - 5} more")
        console.blank()

    # Show planned versions
    planned = api.list_by_status(VersionStatus.PLANNED)
    if planned:
        console.step(f"Planned ({len(planned)})")
        for v in planned[:3]:  # Show next 3
            console.info(f"  v{v.number}: {v.title or 'No description'}")
        console.blank()

    console.info("Use --roadmap-version VERSION for details")
    return 0


def _handle_eval(config: CLIConfig) -> int:
    """Handle versioned model/profile evaluation."""
    import csv
    import glob
    import shutil
    from pathlib import Path

    from primr.config.config import FAST_FEEDBACK_RULES_PATH, OUTPUT_DIR
    from primr.core.cli_local_stage_eval import handle_stage_quality_generation
    from primr.core.model_eval import (
        LLMJudgeMetadata,
        auto_stage_existing_reports,
        evaluate_outputs,
        get_eval_judge_candidate_profiles,
        get_eval_profile,
        list_eval_profile_names,
        run_grok_judge,
        run_local_judge,
        write_fast_feedback_guidance,
        write_llm_judge_report,
        write_local_judge_sweep_markdown,
        write_local_judge_sweep_summary,
    )
    from primr.core.research_agent import perform_research
    from primr.utils.cost_estimator import estimate_cost

    if not config.eval_id:
        console.error("--eval-id is required for --eval")
        console.info("Usage: primr --eval --eval-id eval-2026-02-r1")
        return 1

    if config.eval_baseline not in config.eval_profiles:
        console.error(
            f"--eval-baseline '{config.eval_baseline}' must be included in --eval-profiles"
        )
        return 1

    # Validate profile names against runtime-registered eval slots.
    unknown_profiles = [p for p in config.eval_profiles if get_eval_profile(p) is None]
    if unknown_profiles:
        registered = ", ".join(list_eval_profile_names())
        console.error(
            f"Unregistered eval profile(s): {', '.join(unknown_profiles)}. "
            f"Registered slots: {registered}."
        )
        console.info(
            "Register a new slot with primr.core.model_eval.register_eval_profile() "
            "before running eval against it."
        )
        return 1
    if get_eval_profile(config.eval_baseline) is None:
        console.error(f"--eval-baseline '{config.eval_baseline}' is not a registered profile slot.")
        return 1

    eval_root = Path(config.eval_root)
    # _safe_eval_dir rejects traversal/separators in eval_id and confirms
    # the resolved directory stays under eval_root before any mkdir/write.
    try:
        from primr.core.model_eval import _safe_eval_dir

        eval_dir = _safe_eval_dir(eval_root, config.eval_id)
    except ValueError as e:
        console.error(f"Invalid --eval-id: {e}")
        return 1
    eval_dir.mkdir(parents=True, exist_ok=True)
    generated_stage_quality_path: Path | None = None
    manifest_path = Path(config.eval_manifest) if config.eval_manifest else None
    if config.eval_company and manifest_path is None:
        company_manifest = eval_dir / "eval_company_manifest.csv"
        company_manifest.write_text(
            "company\n" + config.eval_company.strip() + "\n",
            encoding="utf-8",
        )
        manifest_path = company_manifest

    if config.eval_auto_stage:
        staged = auto_stage_existing_reports(
            eval_id=config.eval_id,
            eval_root=eval_root,
            source_dir=Path(config.eval_source_dir),
            profiles=config.eval_profiles,
            company=config.eval_company,
            usage_file=Path("logs") / "usage_history.json",
        )
        staged_count = sum(len(v) for v in staged.values())
        if staged_count > 0:
            console.info(f"Auto-staged {staged_count} existing report(s) into eval folders.")
        else:
            console.info("Auto-stage found no matching local reports.")

    if config.eval_run_missing:
        if not manifest_path:
            console.error(
                "--eval-run-missing requires --eval-manifest (CSV with company/company_name + website)"
            )
            return 1
        if config.eval_max_new_runs <= 0:
            console.error("--eval-run-missing requires --eval-max-new-runs > 0")
            return 1
        if config.eval_max_estimated_cost <= 0:
            console.error("--eval-run-missing requires --eval-max-estimated-cost > 0")
            return 1

        current = evaluate_outputs(
            eval_id=config.eval_id,
            eval_root=eval_root,
            profiles=config.eval_profiles,
            baseline=config.eval_baseline,
            quality_ratio_threshold=config.eval_quality_ratio_threshold,
            cost_ratio_threshold=config.eval_cost_ratio_threshold,
            manifest_path=manifest_path,
        )

        if current.missing_pairs:
            websites: dict[str, str] = {}
            with open(manifest_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for manifest_row in reader:
                    name = (
                        (manifest_row.get("company") or manifest_row.get("company_name") or "")
                        .strip()
                        .lower()
                    )
                    website = (manifest_row.get("website") or manifest_row.get("url") or "").strip()
                    if name and website:
                        websites[name] = website

            to_run = current.missing_pairs[: config.eval_max_new_runs]

            def _profile_estimate(profile: str) -> float:
                # Consult the slot registry first - registered slots may declare
                # an explicit estimated_cost_usd (v1.24.0 cross-provider slots).
                slot = get_eval_profile(profile)
                if slot is not None and slot.estimated_cost_usd is not None:
                    return slot.estimated_cost_usd

                # Built-in slots fall through to the legacy mode-based estimator.
                if profile == "fast":
                    return estimate_cost(
                        "complete", include_ai_strategy=True, fast_mode=True
                    ).total_cost
                if profile == "lite":
                    return estimate_cost(
                        "complete", include_ai_strategy=True, lite_strategy=True
                    ).total_cost
                return estimate_cost("complete", include_ai_strategy=True).total_cost

            estimated_total = sum(_profile_estimate(profile) for _, profile in to_run)
            if estimated_total > config.eval_max_estimated_cost:
                console.error(
                    f"Estimated cost for planned runs (${estimated_total:.2f}) exceeds cap "
                    f"(${config.eval_max_estimated_cost:.2f})."
                )
                console.info("Increase --eval-max-estimated-cost or lower --eval-max-new-runs.")
                return 1

            console.step("Eval run-missing")
            console.info(f"Executing {len(to_run)} run(s), estimated <= ${estimated_total:.2f}")

            from primr.ai.routing import EvalRecipeOverride

            for company, profile in to_run:
                website = websites.get(company.lower())
                if not website:
                    console.warn(f"Skipping {company} ({profile}): website missing in manifest")
                    continue

                profile_output = eval_dir / profile
                profile_output.mkdir(parents=True, exist_ok=True)

                # Resolve the slot's recipe; install it as an override so the
                # writing-tier defaults in research_agent pick up the slot's
                # writing model. Built-in slots (full/lite/fast) have recipe=None
                # and fall through to the legacy mode flags below.
                slot = get_eval_profile(profile)
                slot_recipe = slot.recipe if slot is not None else None

                console.info(f"Running {company} [{profile}]")
                with EvalRecipeOverride(slot_recipe):
                    run_result = perform_research(
                        company_name=company,
                        website=website,
                        mode="complete",
                        ai_strategy=True,
                        skip_confirm=True,
                        lite_strategy=(profile == "lite"),
                        fast_mode=(profile == "fast"),
                    )
                if not run_result:
                    console.warn(f"Run failed: {company} [{profile}]")
                    continue

                # Copy latest strategic overview artifact to eval profile folder.
                # Match either underscored company names (Acme_Corp_Inc.) or
                # space-preserving names (Acme Corp Inc.) - primr's actual
                # output filenames preserve spaces, but historical patterns
                # used underscores.
                output_root = Path(OUTPUT_DIR)
                company_prefix_underscore = company.replace(" ", "_")
                # Escape the company-name fragments so brackets / "?" / "*"
                # in a manifest name don't get reinterpreted as glob
                # metacharacters and silently miss the just-staged report.
                # Same bug class as the batch resume fix in 793e5d1.
                matches: list[Path] = []
                for ext in ("*.md", "*.txt"):
                    matches.extend(
                        output_root.glob(
                            f"{glob.escape(company_prefix_underscore)}_Strategic_Overview_{ext}"
                        )
                    )
                    matches.extend(
                        output_root.glob(f"{glob.escape(company)}_Strategic_Overview_{ext}")
                    )
                # Dedupe (the two patterns can both match in some setups)
                matches = list(dict.fromkeys(matches).keys())
                if matches:
                    latest = max(matches, key=lambda p: p.stat().st_mtime)
                    # Always copy with an underscored filename so eval
                    # downstream tooling (scorecard reader) can rely on the
                    # convention.
                    canonical_name = (
                        f"{company_prefix_underscore}_Strategic_Overview{latest.suffix}"
                    )
                    shutil.copy2(latest, profile_output / canonical_name)
                    console.info(
                        f"Staged report into eval folder: {profile_output.name}/{canonical_name}"
                    )
                else:
                    console.warn(
                        f"Could not locate output artifact to copy for {company} [{profile}]"
                    )

    eval_result = evaluate_outputs(
        eval_id=config.eval_id,
        eval_root=eval_root,
        profiles=config.eval_profiles,
        baseline=config.eval_baseline,
        quality_ratio_threshold=config.eval_quality_ratio_threshold,
        cost_ratio_threshold=config.eval_cost_ratio_threshold,
        manifest_path=manifest_path,
    )

    console.banner("Eval Scorecard")
    console.info(f"Eval ID: {config.eval_id}")
    console.info(f"Profiles: {', '.join(config.eval_profiles)}")
    console.info(f"Baseline: {config.eval_baseline}")
    console.blank()
    for row in eval_result.decision_rows:
        console.info(f"- {row}")
    console.blank()
    has_any_reports = any(summary.report_count > 0 for summary in eval_result.profile_summaries)
    if not has_any_reports:
        console.warn("No reports found for this eval id yet.")
        console.info(
            "Place outputs under output/evals/<eval-id>/<profile>/ or run with --eval-run-missing."
        )
    elif eval_result.missing_pairs:
        console.warn(f"Missing profile/company pairs: {len(eval_result.missing_pairs)}")
        console.info("Re-run with --eval-run-missing plus spend caps to fill gaps.")
    else:
        console.ok("All profile/company pairs present.")
    console.info(f"Scorecard: {eval_result.scorecard_md}")
    console.info(f"CSV: {eval_result.scorecard_csv}")

    judge_rows = []
    if config.eval_llm_judge:
        if config.eval_judge_provider == "grok" and config.eval_judge_max_cost <= 0:
            console.error(
                "--eval-llm-judge with --eval-judge-provider grok requires --eval-judge-max-cost > 0"
            )
            return 1
        if not eval_result.metrics:
            console.warn("No staged metrics available for LLM judge.")
            return 0
        candidate_profiles = get_eval_judge_candidate_profiles(
            eval_result,
            baseline_profile=config.eval_baseline,
        )
        if not candidate_profiles:
            console.warn("No non-baseline profile with reports available for LLM judge.")
            return 0
        console.blank()
        console.step("LLM Judge")
        judge_target = (
            config.eval_judge_model_list
            if config.eval_judge_model_list
            else ", ".join(config.eval_judge_models)
            if config.eval_judge_models
            else config.eval_judge_model
        )
        console.info(
            f"Provider={config.eval_judge_provider}, Target={judge_target}, "
            f"Baseline={config.eval_baseline}, Candidates={', '.join(candidate_profiles)}, "
            f"MaxPairsPerCandidate={config.eval_judge_max_pairs}, Passes={config.eval_judge_passes}, "
            f"MaxCost=${config.eval_judge_max_cost:.2f}"
        )
        try:
            if config.eval_judge_provider == "grok":
                judge_metadata = LLMJudgeMetadata(
                    provider=config.eval_judge_provider,
                    model=config.eval_judge_model,
                )
                all_rows = []
                judge_cost = 0.0
                for candidate_profile in candidate_profiles:
                    rows, profile_cost = run_grok_judge(
                        eval_result=eval_result,
                        baseline_profile=config.eval_baseline,
                        candidate_profile=candidate_profile,
                        max_pairs=max(1, config.eval_judge_max_pairs),
                        passes=max(1, config.eval_judge_passes),
                        max_cost_usd=max(0.0, config.eval_judge_max_cost - judge_cost),
                        model=config.eval_judge_model,
                    )
                    all_rows.extend(rows)
                    judge_cost += profile_cost
                    if config.eval_judge_max_cost > 0 and judge_cost >= config.eval_judge_max_cost:
                        break
                judge_rows = all_rows
                judge_path = Path(config.eval_root) / config.eval_id / "llm_judge.json"
                write_llm_judge_report(
                    judge_path, all_rows, round(judge_cost, 4), metadata=judge_metadata
                )
                console.info(f"LLM judge rows: {len(all_rows)}")
                console.info(f"LLM judge cost: ${judge_cost:.4f}")
                console.info(f"LLM judge output: {judge_path}")
            elif config.eval_judge_provider == "local":
                judge_models, missing_models = _resolve_local_judge_models(config)
                if config.eval_judge_model_list:
                    console.info(f"Local judge model list: {config.eval_judge_model_list}")
                if missing_models:
                    console.warn(
                        "Skipping local judge models not installed in Ollama: "
                        + ", ".join(missing_models)
                    )
                if not judge_models:
                    console.error(
                        "No local judge models available after resolving the requested list."
                    )
                    return 1
                sweep_results: list[tuple[LLMJudgeMetadata, list[Any], float]] = []
                last_rows: list[Any] = []
                console.info(
                    f"Resolved local judge models ({len(judge_models)}): " + ", ".join(judge_models)
                )
                for model_name in judge_models:
                    judge_metadata = LLMJudgeMetadata(
                        provider="local",
                        model=model_name,
                        base_url=config.eval_judge_base_url,
                        api_key_env=config.eval_judge_api_key_env,
                    )
                    console.info(f"Running local judge model: {model_name}")
                    rows = []
                    judge_cost = 0.0
                    for candidate_profile in candidate_profiles:
                        profile_rows, profile_cost = run_local_judge(
                            eval_result=eval_result,
                            baseline_profile=config.eval_baseline,
                            candidate_profile=candidate_profile,
                            max_pairs=max(1, config.eval_judge_max_pairs),
                            passes=max(1, config.eval_judge_passes),
                            max_cost_usd=max(0.0, config.eval_judge_max_cost - judge_cost),
                            model=model_name,
                            base_url=config.eval_judge_base_url,
                            api_key_env=config.eval_judge_api_key_env,
                        )
                        rows.extend(profile_rows)
                        judge_cost += profile_cost
                        if (
                            config.eval_judge_max_cost > 0
                            and judge_cost >= config.eval_judge_max_cost
                        ):
                            break
                    sweep_results.append((judge_metadata, rows, round(judge_cost, 4)))
                    last_rows = rows
                    model_slug = (
                        re.sub(r"[^a-zA-Z0-9]+", "-", model_name).strip("-").lower() or "model"
                    )
                    judge_path = (
                        Path(config.eval_root) / config.eval_id / f"llm_judge.{model_slug}.json"
                    )
                    write_llm_judge_report(
                        judge_path, rows, round(judge_cost, 4), metadata=judge_metadata
                    )
                    console.info(f"  rows: {len(rows)}")
                    console.info(f"  cost: ${judge_cost:.4f}")
                    console.info(f"  output: {judge_path}")
                judge_rows = last_rows
                summary_json = Path(config.eval_root) / config.eval_id / "local_judge_summary.json"
                summary_md = Path(config.eval_root) / config.eval_id / "local_judge_summary.md"
                write_local_judge_sweep_summary(
                    summary_json,
                    eval_id=config.eval_id,
                    baseline_profile=config.eval_baseline,
                    candidate_profiles=candidate_profiles,
                    results=sweep_results,
                )
                write_local_judge_sweep_markdown(
                    summary_md,
                    eval_id=config.eval_id,
                    baseline_profile=config.eval_baseline,
                    candidate_profiles=candidate_profiles,
                    results=sweep_results,
                )
                console.info(
                    "Local judge backend: "
                    f"base_url={config.eval_judge_base_url or 'env/default'}, "
                    f"api_key_env={config.eval_judge_api_key_env}"
                )
                console.info(f"Local judge sweep summary: {summary_json}")
                console.info(f"Local judge sweep markdown: {summary_md}")
            else:
                console.error(f"Unsupported eval judge provider: {config.eval_judge_provider}")
                return 1
        except Exception as e:
            console.warn(f"LLM judge skipped due to provider/network error: {e}")
            console.info("Deterministic eval scorecard is still valid.")

    judge_models, missing_models = (
        _resolve_local_judge_models(config)
        if config.eval_local_stage == "website-summary"
        else ([], [])
    )
    stage_exit_code, generated_stage_quality_path = handle_stage_quality_generation(
        config, eval_result.metrics, judge_models, missing_models, console
    )
    if stage_exit_code != 0:
        return stage_exit_code

    if config.eval_stage_scorecard:
        quality_path = (
            Path(config.eval_stage_quality)
            if config.eval_stage_quality
            else generated_stage_quality_path
        )
        if quality_path is None:
            console.error("--eval-stage-scorecard requires --eval-stage-quality")
            return 1
        try:
            from primr.core.stage_eval_scorecard_cli import (
                write_stage_eval_scorecard_from_files,
            )

            artifacts = write_stage_eval_scorecard_from_files(
                route_root=Path(config.eval_stage_route_root or config.eval_working_root),
                quality_path=quality_path,
                output_dir=eval_dir,
                stage_id=config.eval_stage_id,
                min_quality_score=config.eval_stage_min_quality_score,
                max_failure_rate=config.eval_stage_max_failure_rate,
            )
        except (OSError, ValueError) as e:
            console.error(f"Stage eval scorecard failed: {e}")
            return 1
        console.info(
            "Stage eval scorecard rows: "
            f"{artifacts.scorecard_rows} from {artifacts.route_rows} route group(s) "
            f"and {artifacts.quality_evidence_rows} quality evidence row(s)."
        )
        console.info(f"Stage eval scorecard: {artifacts.markdown_path}")
        console.info(f"Stage eval scorecard JSON: {artifacts.json_path}")

    # Persist fast-mode feedback guidance for future --fast runs.
    if "fast" in config.eval_profiles and any(m.profile == "fast" for m in eval_result.metrics):
        feedback_path = Path(config.eval_root) / config.eval_id / "fast_feedback_guidance.md"
        write_fast_feedback_guidance(
            feedback_path,
            eval_result=eval_result,
            judge_rows=judge_rows,
        )
        # Promote latest guidance to a stable path consumed by fast report prompts.
        Path(FAST_FEEDBACK_RULES_PATH).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(feedback_path, Path(FAST_FEEDBACK_RULES_PATH))
        console.info(f"Fast feedback guidance: {feedback_path}")
        console.info(f"Promoted guidance: {FAST_FEEDBACK_RULES_PATH}")
    return 0


def _handle_research(config: CLIConfig) -> int:
    """Handle research command."""
    from primr.core.research_agent import perform_research
    from primr.core.workspace import ResumeLeaseError

    request = validate_research_request(config)
    if request is None:
        return 1
    company_name = request.company_name
    website = request.website

    from primr.core.cli_budget import resolve_runtime_selection, strategy_runtime_error

    selection = resolve_runtime_selection(config)
    use_fast_mode = selection.fast_mode
    use_premium_mode = selection.premium_mode

    runtime_error = strategy_runtime_error(config, fast_mode=use_fast_mode)
    if runtime_error:
        return report_command_error(
            json_output=config.json_output,
            operation="research",
            error_type="unsupported_strategy_runtime",
            message=runtime_error,
        )

    def report_preflight_failure(errors: list[str]) -> int:
        if config.json_output:
            return report_command_error(
                json_output=True,
                operation="research",
                error_type="preflight_failed",
                message="Preflight checks failed",
                hints=(*errors, "Run 'primr doctor' for detailed diagnostics"),
            )
        for error in errors:
            console.error(error)
        console.blank()
        console.info("Run 'primr doctor' for detailed diagnostics")
        return 1

    # Local checks are safe to run before the cost gate.
    if not config.json_output:
        console.step("Preflight checks")
    preflight_ok, preflight_errors = _run_preflight_checks(
        config.mode,
        premium_mode=use_premium_mode,
        fast_mode=use_fast_mode,
        refresh_vendor_research=(config.refresh_vendor_research and config.ai_strategy),
        allow_network=False,
    )
    if not preflight_ok:
        return report_preflight_failure(preflight_errors)

    if selection.auto_fast_mode and not config.json_output:
        tier_label = {
            "fast": "Grok 4.3 (low-effort)",
            "hybrid": "Grok 4.3 hybrid",
            "max": "Grok 4.3 max",
        }
        console.info(
            f"Using {tier_label.get(config.grok_tier, 'Grok')} fast mode; "
            "for deeper research add --premium"
        )
    elif not use_fast_mode and not config.json_output:
        console.info("Using standard mode (Gemini). Set XAI_API_KEY for faster, cheaper runs.")

    if use_fast_mode and config.lite_strategy and not config.json_output:
        console.warn("--lite is ignored with --fast (fast mode uses Grok for all calls)")

    context_files = resolve_research_context_files(config)
    if context_files is None:
        return 1

    # Same helper the --budget gate and dry-run price with (estimate = run).
    from primr.core.cli_budget import estimate_strategy_types

    strategy_types = estimate_strategy_types(config) or None

    os.environ["PRIMR_BROWSER_SESSION_MODE"] = config.browser_session_mode
    if config.browser_headed:
        os.environ["PRIMR_BROWSER_HEADED"] = "1"
    else:
        os.environ.pop("PRIMR_BROWSER_HEADED", None)

    from primr.core.cli_budget import activate_run_budget

    try:
        budget_activation = activate_run_budget(
            config,
            fast_mode=use_fast_mode,
            premium_mode=use_premium_mode,
            emit_output=not config.json_output,
        )
        if not budget_activation.ok:
            return report_command_error(
                json_output=config.json_output,
                operation="research",
                error_type="budget_refused",
                message=budget_activation.error_message or "Run budget was refused",
                hints=budget_activation.hints,
            )

        network_ok, network_errors = _run_network_preflight_checks(
            config.mode,
            premium_mode=use_premium_mode,
            fast_mode=use_fast_mode,
            refresh_vendor_research=(config.refresh_vendor_research and config.ai_strategy),
        )
        if not network_ok:
            return report_preflight_failure(network_errors)
        if not config.json_output:
            console.ok("All systems ready")

        run_context: dict[str, str] = {}
        result_path = perform_research(
            company_name,
            website,
            mode=config.mode,
            citation_style=config.citation_style,
            ai_strategy=config.ai_strategy,
            platforms=config.platforms,
            output_dir=config.output_dir,
            skip_confirm=config.skip_confirm,
            context_files=context_files if context_files else None,
            refresh_vendor_research=config.refresh_vendor_research,
            strategies=strategy_types,
            no_qa=config.no_qa,
            max_scrape_time=config.max_scrape_time,
            discovery_notes_path=config.discovery_notes_path,
            framing_purpose=config.framing_purpose,
            framing_audience=config.framing_audience,
            framing_decision=config.framing_decision,
            framing_question=config.framing_question,
            lite_strategy=config.lite_strategy,
            fast_mode=use_fast_mode,
            premium_mode=use_premium_mode,
            skip_scrape_validation=config.skip_scrape_validation,
            resume_local=config.resume_local,
            verify=config.verify,
            grok_tier=config.grok_tier,
            skip_recon=config.skip_recon,
            continuous_reasoning=config.continuous_reasoning,
            run_context=run_context,
        )
    except ResumeLeaseError as exc:
        if config.json_output:
            return report_research_workspace_error(exc, json_output=True)
        report_research_workspace_error(exc, json_output=False)
        result_path = None
    finally:
        from primr.utils.run_budget import clear_run_budget

        clear_run_budget()

    from primr.core.cli_research_result import finalize_research_command

    return finalize_research_command(
        result_path=result_path,
        run_context=run_context,
        company_name=company_name,
        website=website,
        mode=config.mode,
        json_output=config.json_output,
        open_after=config.open_after,
        open_result=open_file,
    )


def list_recent_outputs(output_dir: str | None = None, *, json_output: bool = False) -> int:
    """List recent research outputs from the output directory."""
    from primr.core.cli_artifacts import list_recent_outputs as render_recent_outputs

    return render_recent_outputs(
        output_dir or OUTPUT_DIR,
        working_dir=WORKING_DIR,
        logs_dir=os.path.dirname(LOGS_DIR),
        json_output=json_output,
    )


def clean_temp_files() -> None:
    """Clean up temporary files from working directory."""
    import glob

    working_dirs = glob.glob(os.path.join(WORKING_DIR, "*"))
    temp_files = glob.glob(os.path.join(WORKING_DIR, "*.tmp"))
    cleaned = 0

    for d in working_dirs:
        if os.path.isdir(d):
            try:
                contents = os.listdir(d)
                if not contents:
                    os.rmdir(d)
                    cleaned += 1
            except Exception:
                logger.debug("Failed to remove temp directory %s", d, exc_info=True)

    for f in temp_files:
        try:
            os.remove(f)
            cleaned += 1
        except Exception:
            logger.debug("Failed to remove temp file %s", f, exc_info=True)

    print(f"Cleaned {cleaned} temporary files/directories.")


def check_api_quota() -> None:
    """Check if Gemini API quota is available."""
    from google import genai

    from primr.config.settings import get_settings

    settings = get_settings()
    if not settings.api.gemini_key:
        console.error("GEMINI_API_KEY not configured in .env")
        return

    console.banner("API Quota Check")
    console.info("Testing Gemini API availability...")

    try:
        client = genai.Client(
            api_key=settings.api.gemini_key, http_options=default_genai_http_options()
        )
        response = client.models.generate_content(
            model=PrimrModels.FAST_MODEL, contents="Say 'OK' in one word."
        )
        if response and response.text:
            console.ok("API quota is available")
            console.info("You can run research now.")
        else:
            console.warn("API responded but with empty content")
    except Exception as e:
        error_str = str(e).lower()
        if "resource_exhausted" in error_str and ("per_day" in error_str or "quota" in error_str):
            console.error("Daily API quota is EXHAUSTED")
            console.info("Options:")
            console.info("  1. Wait until quota resets (usually midnight PT)")
            console.info("  2. Upgrade your API plan at https://ai.google.dev")
        elif "429" in str(e):
            console.warn("Rate limited - try again in a few minutes")
        elif "invalid" in error_str and "key" in error_str:
            console.error("Invalid API key")
        else:
            console.error(f"API check failed: {e}")


def _handle_list_strategies(config: CLIConfig) -> int:
    """List available strategy documents (dynamically from YAML configs)."""
    from pathlib import Path

    import yaml  # type: ignore[import-untyped]

    console.banner("Available Strategy Documents")

    console.info("Strategy documents are outside-in decision support grounded in evidence.")
    console.info("Validate material assumptions before investment decisions.")
    console.blank()

    strategies_dir = Path(__file__).parent.parent / "prompts" / "strategies"

    active: list[dict[str, str]] = []
    placeholders: list[dict[str, str]] = []

    active.append(
        {
            "name": "ai",
            "display_name": "AI Strategy",
            "description": "Business-first AI portfolio, economics, operating model, architecture, and governance",
            "usage": 'primr "Company" https://example.com',
            "standalone": 'primr --ai-strategy-only "output/report.md" --dry-run',
        }
    )

    if strategies_dir.exists():
        for yaml_path in sorted(strategies_dir.glob("*.yaml")):
            stem = yaml_path.stem
            if stem in ("ai_strategy", "ai_first_transformation"):
                continue
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                meta = data.get("meta", {})
                status = meta.get("status", "active")
                display = meta.get("name", stem.replace("_", " ").title())
                desc = meta.get("cli_description") or meta.get("description", "")
                expected_pages = meta.get("expected_pages", "")

                entry = {
                    "name": stem,
                    "display_name": display,
                    "description": desc,
                    "expected_pages": expected_pages,
                    "usage": f'primr "Company" https://example.com --strategy-type {stem}',
                    "standalone": (
                        'primr --ai-strategy-only "output/report.md" '
                        f"--strategy-type {stem} --dry-run"
                    ),
                }
                if stem == "skills":
                    entry["usage"] = 'primr skills "Company" https://example.com'
                    entry["standalone"] = "Not available; use primr skills"
                if status == "placeholder":
                    placeholders.append(entry)
                else:
                    active.append(entry)
            except Exception as e:
                logger.warning("Failed to load strategy %s: %s", yaml_path.name, e)
                continue

    console.step(f"Available Strategies ({len(active)} active)")
    for s in active:
        console.ok(f"  {s['display_name']} ({s['name']})")
        if s.get("description"):
            desc = s["description"]
            console.info(f"    {desc}")
        if s.get("expected_pages"):
            console.muted(f"    Expected: {s['expected_pages']} pages")
        console.info(f"    Command:          {s['usage']}")
        console.info(f"    Standalone:       {s['standalone']}")
        console.blank()

    if placeholders:
        console.step(f"Placeholder Strategies ({len(placeholders)} - not yet implemented)")
        console.blank()
        for s in placeholders:
            console.warn(f"  {s['display_name']} ({s['name']})")
            if s.get("description"):
                console.info(f"    {s['description']}")
            console.blank()

    console.step("How to Generate Strategies")
    console.info(
        '  1. During research:   primr "Company" https://example.com --strategy-type customer_experience'
    )
    console.info('  2. Multi-platform AI: primr "Company" https://example.com --platform aws azure')
    console.info('  3. Existing report:    primr --ai-strategy-only "output/report.md" --dry-run')
    console.info("     Review the standalone estimate, then approve the exact execution plan.")
    console.blank()

    return 0


# =============================================================================
# BATCH / ENRICH FUNCTIONS
# =============================================================================


def enrich_batch(
    file_path: str,
    industry: str | None = None,
    limit: int | None = None,
    mode: str = "complete",
    *,
    dry_run: bool = False,
    json_output: bool = False,
    skip_confirm: bool = False,
    budget_usd: float | None = None,
    output_dir: str | Path | None = None,
) -> int:
    """
    Enrich a batch file: detect columns, filter by industry, look up websites,
    save enriched CSV. Does NOT run research.

    Returns:
        Exit code (0 for success)
    """
    from primr.core.cli_batch_runtime import enrich_batch as run_governed_enrichment

    return run_governed_enrichment(
        file_path,
        industry=industry,
        limit=limit,
        mode=mode,
        dry_run=dry_run,
        json_output=json_output,
        skip_confirm=skip_confirm,
        budget_usd=budget_usd,
        output_dir=output_dir,
    )


def process_batch(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    platforms: tuple[str, ...] | None = None,
    industry: str | None = None,
    limit: int | None = None,
    skip_confirm: bool = True,
    *,
    dry_run: bool = False,
    json_output: bool = False,
    per_company_estimate=None,
    mode_label: str | None = None,
    output_dir: str | Path | None = None,
    strategies: list[str] | None = None,
    no_qa: bool = False,
    max_scrape_time: int | None = None,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    skip_scrape_validation: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    skip_recon: bool = False,
    continuous_reasoning: bool = True,
    budget_usd: float | None = None,
    execution_preflight: Callable[[], tuple[bool, list[str]]] | None = None,
    deprecated_alias: str | None = None,
) -> int:
    """
    Process a batch file (Excel or CSV) for research.

    Handles deterministic column detection, optional industry filtering,
    validation, a single batch approval, and sequential research execution.
    Rows without websites must be enriched before research.

    Returns:
        Exit code (0 for success)
    """
    from primr.core.cli_batch_runtime import process_batch as run_governed_batch
    from primr.core.research_agent import perform_research

    return run_governed_batch(
        file_path,
        mode=mode,
        citation_style=citation_style,
        ai_strategy=ai_strategy,
        platforms=platforms,
        industry=industry,
        limit=limit,
        skip_confirm=skip_confirm,
        dry_run=dry_run,
        json_output=json_output,
        per_company_estimate=per_company_estimate,
        mode_label=mode_label,
        output_dir=output_dir,
        strategies=strategies,
        no_qa=no_qa,
        max_scrape_time=max_scrape_time,
        lite_strategy=lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        skip_scrape_validation=skip_scrape_validation,
        verify=verify,
        grok_tier=grok_tier,
        skip_recon=skip_recon,
        continuous_reasoning=continuous_reasoning,
        budget_usd=budget_usd,
        execution_preflight=execution_preflight,
        deprecated_alias=deprecated_alias,
        research_runner=perform_research,
    )


def process_csv(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    platforms: tuple[str, ...] | None = None,
) -> None:
    """Retain the legacy name while using the governed batch approval path."""
    from primr.core.cli_batch_runtime import process_batch as run_governed_batch
    from primr.core.research_agent import perform_research

    run_governed_batch(
        file_path,
        mode=mode,
        citation_style=citation_style,
        ai_strategy=ai_strategy,
        platforms=platforms,
        skip_confirm=False,
        research_runner=perform_research,
    )


def open_file(filepath: str) -> None:
    """Open a file with the system default application."""
    from primr.utils.files import open_with_default_app

    try:
        open_with_default_app(filepath)
    except Exception as e:
        console.warn(f"Could not open file: {e}")
