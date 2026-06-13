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

import argparse
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from primr.ai.genai_factory import default_genai_http_options
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
from primr.core.cli_batch import (
    _ensure_valid_url,
    _prepare_batch_df,
)
from primr.core.cli_batch import (
    _read_batch_file as _read_batch_file,
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
from primr.core.cli_parser import (
    _determine_command,
    _get_strategy_choices,
    _get_strategy_help,
)
from primr.core.cli_parser import (
    _discover_strategies as _discover_strategies,
)
from primr.core.cli_recovery import (
    _build_recovered_basename as _build_recovered_basename,
)
from primr.core.cli_recovery import (
    _find_latest_run_state as _find_latest_run_state,
)
from primr.core.cli_recovery import (
    _sanitize_output_stem as _sanitize_output_stem,
)
from primr.core.cli_recovery import (
    _save_recovered_outputs,
    resume_pending_jobs,
)
from primr.core.cli_recovery import (
    _show_latest_run_state_hint as _show_latest_run_state_hint,
)
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


# =============================================================================
# ENUMS
# =============================================================================


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
    MEMORY = "memory"
    ORCHESTRATE = "orchestrate"
    ROADMAP = "roadmap"
    IMPROVE = "improve"
    REFINE = "refine"
    CALIBRATE = "calibrate"


# =============================================================================
# DATACLASSES
# =============================================================================


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
    verbose: bool = False
    test_accordion_topic: str | None = None
    test_accordion_pages: int = 50
    analyze_report_path: str | None = None
    qa_company: str | None = None
    qa_recent_count: int | None = None
    max_scrape_time: int | None = None
    ai_strategy_only_path: str | None = None
    discovery_notes_path: str | None = None
    strategy_type: str = "ai"  # Type of strategy to generate
    resume_latest: bool = False
    resume_local: bool = False
    lite_strategy: bool = False  # Use Pro model instead of Deep Research for strategy
    fast_mode: bool = False  # Use Grok 4.1 for fast research (~12 min, ~$0.25)
    premium_mode: bool = False  # Force Gemini + Deep Research pipeline
    grok_tier: str = "hybrid"  # Grok model tier: fast, hybrid, max
    continuous_reasoning: bool = (
        True  # Default-on after the n=3 pilot; --no-continuous-reasoning to disable
    )
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
    banner_mode: str = "auto"
    banner_explicit: bool = False
    # Agentic architecture options
    memory_company: str | None = None
    memory_list: bool = False
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
    eval_working_root: str = "working"
    doctor_fix: bool = False
    doctor_scraper_stats: bool = False
    init_non_interactive: bool = False
    init_yes: bool = False
    init_skip_browsers: bool = False
    init_no_doctor: bool = False

    @property
    def cloud_vendors(self) -> tuple[str, ...]:
        """Backward-compatible alias. Returns platforms or default Microsoft/private."""
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


# =============================================================================
# PROTOCOLS
# =============================================================================


class CLIRunner(Protocol):
    """Protocol for CLI command runners."""

    def run(self, config: CLIConfig) -> int:
        """Run the command and return exit code."""
        ...


# =============================================================================
# MODE MAPPING
# =============================================================================

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


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================


def parse_args(args: list[str] | None = None) -> CLIConfig:
    """
    Parse command-line arguments.

    Args:
        args: List of arguments (defaults to sys.argv[1:])

    Returns:
        CLIConfig with parsed values
    """
    parser = _create_parser()
    parsed = parser.parse_args(args)

    # Determine command
    command = _determine_command(parsed)

    # Map mode name
    mode = MODE_MAP.get(parsed.mode, parsed.mode)

    # AI strategy is on by default for full modes, off for scrape-only
    # --no-ai-strategy explicitly disables it
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

    # Build context files tuple
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

    # Batch commands default to requiring confirmation; everything else skips it.
    # --skip-confirm explicitly skips confirmation for any command.
    is_batch = bool(getattr(parsed, "batch", None) or parsed.csv)
    skip_confirm_flag = getattr(parsed, "skip_confirm", False)
    skip_confirm = skip_confirm_flag if is_batch else True

    # Handle --platform / --cloud-vendor resolution
    raw_platforms = getattr(parsed, "platform", None)
    raw_cloud_vendor = getattr(parsed, "cloud_vendor", None)

    if raw_cloud_vendor is not None:
        import sys as _sys

        print("WARNING: --cloud-vendor is deprecated, use --platform instead", file=_sys.stderr)
        platforms = tuple(dict.fromkeys(raw_cloud_vendor))
    elif raw_platforms is not None:
        # Normalize aliases and expand shorthands
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
        platforms = None  # Will be resolved from recon auto-detection or default

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
        verbose=parsed.verbose,
        test_accordion_topic=getattr(parsed, "test_accordion", None),
        test_accordion_pages=getattr(parsed, "accordion_pages", 50),
        analyze_report_path=getattr(parsed, "analyze_report", None),
        qa_company=getattr(parsed, "qa", None),
        qa_recent_count=getattr(parsed, "qa_recent", None),
        max_scrape_time=getattr(parsed, "max_scrape_time", None),
        ai_strategy_only_path=getattr(parsed, "ai_strategy_only", None),
        discovery_notes_path=getattr(parsed, "discovery_notes", None),
        strategy_type=getattr(parsed, "strategy_type", "ai"),
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
        banner_mode=banner_mode,
        banner_explicit=banner_explicit,
        resume_latest=getattr(parsed, "resume_latest", False),
        resume_local=getattr(parsed, "resume_local", False),
        lite_strategy=getattr(parsed, "lite_strategy", False),
        fast_mode=getattr(parsed, "fast_mode", False),
        # `--mode premium` is documented (and MODE_MAP comments) as requesting
        # the Gemini + Deep Research pipeline, but it maps to "complete" and
        # would otherwise run the cheaper pipeline. Treat it as equivalent to
        # the --premium flag so the requested (and dry-run-priced) pipeline runs.
        premium_mode=(
            getattr(parsed, "premium_mode", False) or getattr(parsed, "mode", None) == "premium"
        ),
        grok_tier=getattr(parsed, "grok_tier", "hybrid"),
        continuous_reasoning=continuous_reasoning,
        no_qa=getattr(parsed, "no_qa", False),
        verify=getattr(parsed, "verify", False),
        budget_usd=getattr(parsed, "budget", None),
        skip_scrape_validation=getattr(parsed, "skip_scrape_validation", False),
        browser_headed=getattr(parsed, "browser_headed", False),
        browser_session_mode=getattr(parsed, "browser_session", "isolated"),
        # Agentic architecture options
        memory_company=getattr(parsed, "memory", None),
        memory_list=getattr(parsed, "memory_list", False),
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
        eval_working_root=getattr(parsed, "eval_working_root", "working"),
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


def _create_keys_parser() -> argparse.ArgumentParser:
    """Create the parser for the keys helper command."""
    from primr.config.env import KEY_ALIASES

    key_choices = sorted(set(KEY_ALIASES) | set(KEY_ALIASES.values()))

    parser = argparse.ArgumentParser(
        prog="primr keys",
        description="Store Primr API keys in the per-user Primr config file.",
    )
    subparsers = parser.add_subparsers(dest="action")

    set_parser = subparsers.add_parser("set", help="Set an API key")
    set_parser.add_argument(
        "provider",
        choices=key_choices,
        help="Key to set. Common choices: gemini, xai",
    )
    set_parser.add_argument(
        "provided_value",
        nargs="?",
        help="Key value. Omit this to enter it without echoing to the terminal.",
    )
    set_parser.add_argument(
        "--value",
        dest="option_value",
        help="Key value for scripts. Prefer the hidden prompt for manual setup.",
    )

    unset_parser = subparsers.add_parser("unset", help="Remove a key from user config")
    unset_parser.add_argument("provider", choices=key_choices)

    subparsers.add_parser("list", help="Show configured key status")
    subparsers.add_parser("path", help="Show where Primr stores user keys")
    return parser


def _run_keys(args: list[str] | None) -> int:
    """Run the ``primr keys`` helper command."""
    import getpass

    from primr.config.env import (
        KEY_HELP,
        describe_key_source,
        get_local_env_path,
        get_user_env_path,
        load_primr_env,
        mask_secret,
        normalize_key_name,
        set_user_key,
        unset_user_key,
    )

    argv = args if args is not None else sys.argv[1:]
    parser = _create_keys_parser()
    keys_args = argv[1:]
    parsed = parser.parse_args(keys_args or ["list"])

    if parsed.action == "path":
        user_path = get_user_env_path()
        console.info(f"User config: {user_path}")
        local_path = get_local_env_path()
        if local_path:
            console.info(f"Local override: {local_path}")
        return 0

    if parsed.action == "list":
        load_primr_env()
        console.banner("Primr Keys")
        console.info(f"User config: {get_user_env_path()}")
        local_path = get_local_env_path()
        if local_path:
            console.info(f"Local override: {local_path}")
        console.blank()
        for env_name, purpose in KEY_HELP.items():
            active, _source, shadowed = describe_key_source(env_name)
            if active:
                console.ok(f"{env_name} configured ({mask_secret(active)}) - {purpose}")
                if shadowed is not None:
                    console.warn(
                        f"  {env_name} is set by an OS environment variable, overriding the "
                        f".env value ({mask_secret(shadowed)}). Clear the env var for the "
                        f".env file to take effect."
                    )
            else:
                console.info(f"{env_name} not set - {purpose}")
        return 0

    if parsed.action == "set":
        env_name = normalize_key_name(parsed.provider)
        value = parsed.option_value or parsed.provided_value
        if value is None:
            if not sys.stdin.isatty():
                console.error("No key value provided and stdin is not interactive")
                console.info(f"Usage: primr keys set {parsed.provider} --value <key>")
                return 1
            value = getpass.getpass(f"{env_name}: ")
        value = value.strip()
        if not value:
            console.error("Key value cannot be empty")
            return 1

        saved_name, path = set_user_key(parsed.provider, value)
        console.ok(f"{saved_name} saved to user config ({mask_secret(value)})")
        console.info(f"Config file: {path}")
        console.info("Run: primr doctor")
        return 0

    if parsed.action == "unset":
        env_name, path, removed = unset_user_key(parsed.provider)
        if removed:
            console.ok(f"{env_name} removed from user config")
            if os.environ.get(env_name):
                console.warn(
                    f"{env_name} is still set by your shell or local .env for this process"
                )
        else:
            console.warn(f"{env_name} was not present in user config")
        console.info(f"Config file: {path}")
        return 0

    parser.print_help()
    return 0


def _is_mcp_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr mcp ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "mcp"


def _run_mcp(args: list[str] | None) -> int:
    """Delegate ``primr mcp ...`` to the MCP server entry point.

    With no additional args, defaults to ``--stdio`` since that's the
    canonical mode for AI-host integration (Claude Code, Cursor, etc.).
    Pass-through args allow ``primr mcp --http --port 8000`` to still work.
    """
    from primr.mcp_server.cli import main as mcp_main

    argv = args if args is not None else sys.argv[1:]
    mcp_argv = argv[1:]  # strip the "mcp" token
    if not mcp_argv:
        mcp_argv = ["--stdio"]

    saved_argv = sys.argv
    try:
        sys.argv = ["primr-mcp", *list(mcp_argv)]
        mcp_main()
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    finally:
        sys.argv = saved_argv


def _is_skills_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr skills ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] == "skills"


def _run_skills(args: list[str] | None) -> int:
    """Delegate to the skill_pack CLI handler."""
    try:
        from primr.skill_pack.cli import run_skills_cli
    except ImportError as exc:
        print(f"Error: skill_pack module unavailable: {exc}", file=sys.stderr)
        return 1
    return run_skills_cli(args)


def _is_update_command(args: list[str] | None) -> bool:
    """Check if the command line is a ``primr update ...`` invocation."""
    argv = args if args is not None else sys.argv[1:]
    return len(argv) >= 1 and argv[0] in {"update", "upgrade", "self-update"}


def _run_update(args: list[str] | None) -> int:
    """Delegate ``primr update`` to the self-upgrade handler."""
    from primr.core.cli_update import run_update

    argv = args if args is not None else sys.argv[1:]
    rest = argv[1:]  # strip the "update" token
    check_only = "--check" in rest or "--check-only" in rest
    yes = "-y" in rest or "--yes" in rest
    return run_update(check_only=check_only, yes=yes)


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
    # Strip the leading "recon" token — the Typer app doesn't expect it.
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
    """
    Main CLI entry point.

    Args:
        args: Optional list of arguments (for testing)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Intercept "primr recon ..." before argparse — delegate to the recon Typer app.
    if _is_recon_command(args):
        return _run_recon(args)
    if _is_keys_command(args):
        return _run_keys(args)
    if _is_mcp_command(args):
        return _run_mcp(args)
    if _is_skills_command(args):
        return _run_skills(args)
    if _is_update_command(args):
        return _run_update(args)

    from pathlib import Path

    from primr.utils.config_validation import validate_config
    from primr.utils.logging_config import setup_logging

    config = parse_args(args)

    # Validate configuration early (skip API key check for utility commands)
    utility_commands = {
        Command.INIT,
        Command.DOCTOR,
        Command.LIST_RECENT,
        Command.CLEAN_TEMP,
        Command.CHECK_JOBS,
        Command.CLEAR_JOBS,
        Command.LIST_STRATEGIES,
        Command.SHOW_USAGE,
        Command.ENRICH,
        Command.EVAL,
        Command.IMPROVE,
    }
    include_api_keys = config.command not in utility_commands
    if config.command == Command.EVAL and config.eval_run_missing:
        include_api_keys = True

    validation_result = validate_config(include_api_keys=include_api_keys)
    if not validation_result.valid:
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

    # Configure console
    if config.quiet:
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
        Command.DRY_RUN: _handle_dry_run,
        Command.GENERATE_VENDOR: _handle_generate_vendor,
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
        Command.MEMORY: _handle_memory,
        Command.ORCHESTRATE: _handle_orchestrate,
        Command.ROADMAP: _handle_roadmap,
        Command.IMPROVE: _handle_improve,
        Command.REFINE: _handle_refine,
        Command.CALIBRATE: _handle_calibrate,
    }

    handler = handlers.get(config.command, _handle_research)
    rc = handler(config)

    # After a successful interactive research run, surface a one-line notice if a
    # newer release exists (cached ~24h, opt-out via PRIMR_NO_UPDATE_CHECK, and
    # never raises). Doctor already shows its own update line, so skip it here.
    if rc == 0 and config.command == Command.RESEARCH and not config.quiet:
        from primr.core.cli_update import notify_if_update_available

        notify_if_update_available()

    return rc


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
        epilog="""
Research Modes:
  full     Scrape + deep research + AI strategy (~60-90 min, ~$6) [DEFAULT]
  scrape   Scrape website + extract insights only (~5-10 min, ~$0.10)
  deep     Autonomous AI web research, 8 sections (~10-15 min, ~$2.50)
  parallel Both engines in parallel (legacy, ~25 min)

Examples:
  primr init                                         # Guided first-run setup
  primr "Acme Corp" https://acme.example
  primr "Acme Corp" acme.example --mode deep
  primr "Acme Corp" acme.example --mode scrape       # Build Site Corpus + Extract Insights
  primr keys set gemini                              # Store Gemini key in user config
  primr keys set xai                                 # Store xAI/Grok key in user config
  primr keys list                                    # Show configured provider keys
  primr doctor                                       # System diagnostics
  primr doctor --fix                                 # Diagnose, then launch guided fixes
  primr update                                       # Upgrade primr to the latest release
  primr update --check                               # Check for a newer version without installing
  primr --qa "Acme Corp"                             # Show detailed QA analysis
  primr --qa-recent 5                                # Show QA summary for recent reports
  primr improve "output/Company_Strategic_Overview_03-06-2026.md"   # Improve one output
  primr improve "output/Company_AI_Strategy_AZURE_03-06-2026.md" --improve-agentic
  primr refine "Acme Corp"                           # QA loop: regenerate weak sections until grade >= 90
  primr refine "Acme Corp" --target-grade 85 --in-place
  primr calibrate "Acme Corp"                        # Audit confidence-label traceability (writes sidecar JSON)
  primr calibrate --calibrate-recent 10 --dry-run    # Preview judge-call count/cost, no spend
  primr --banner                                     # Show startup banner only

AI Strategy Retry (when main report succeeded but AI strategy failed):
  primr --ai-strategy-only "output/Company_Strategic_Overview_01-09-2026.md"
  primr --ai-strategy-only "output/report.md" --platform aws
  primr "Acme Corp" https://acme.example --resume-local
  primr --resume-latest                               # Recover + finalize completed cloud jobs

Versioned Eval (offline-first, no API spend by default):
  primr --eval --eval-id eval-2026-02-r1
  primr --eval --eval-id eval-2026-02-r1 --eval-profiles full lite fast
  primr --eval --eval-id eval-2026-02-r1 --eval-company "Harver"
  primr --eval --eval-id eval-2026-02-r1 --eval-llm-judge --eval-judge-max-cost 0.25
  primr --eval --eval-id eval-2026-02-r1 --eval-run-missing --eval-manifest eval_companies.csv --eval-max-new-runs 2 --eval-max-estimated-cost 12

Agentic Architecture (v1.7.0):
  primr memory "Acme Corp"                           # View hypotheses for a company
  primr --memory-list                                # List all companies with memory
  primr orchestrate "Acme Corp" https://acme.com    # Run orchestrated research
  primr --orchestrate --max-cost 5.0                 # With cost budget
  primr roadmap                                      # Show roadmap overview
  primr --roadmap-version v1.7.0                     # Show version details

Domain Intelligence (Recon):
  primr recon acme.com                               # DNS intelligence lookup
  primr recon acme.com --json                        # Structured JSON output
  primr recon acme.com --md                          # Markdown report
  primr recon acme.com --services                    # M365 vs tech stack split
  primr recon acme.com --full                        # Everything
  primr recon batch domains.txt                      # Batch mode
  primr recon batch domains.txt -c 10                # Batch with concurrency
  primr recon doctor                                 # Connectivity check

Accordion Method Test (for development):
  primr --test-accordion "Oceanography 2026-2030"
  primr --test-accordion "Topic" --accordion-pages 30
""",
    )

    from primr import __version__ as _primr_version

    parser.add_argument(
        "--version",
        action="version",
        version=f"primr {_primr_version}",
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
        "--skip-confirm", action="store_true", help="Skip confirmation prompt for batch research"
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
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed output")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="With 'doctor', launch guided setup for missing keys and browser dependencies",
    )
    parser.add_argument(
        "--scraper-stats",
        action="store_true",
        help=(
            "With 'doctor', show per-tier scrape success rate, latency p95, and "
            "content quality across recent runs"
        ),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="With 'init', print missing setup steps without prompting",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="With 'init', accept safe defaults such as browser installation",
    )
    parser.add_argument(
        "--skip-browsers",
        action="store_true",
        help="With 'init', skip Playwright browser installation",
    )
    parser.add_argument(
        "--no-doctor",
        action="store_true",
        help="With 'init', skip the final doctor verification",
    )
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
        help="Use Pro model instead of Deep Research for AI strategy (faster, cheaper, less depth)",
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
        help="Grok model tier: fast (4.3 low-effort + 4.20-nr, ~$4.27), hybrid (4.3 + 4.20-nr, default), max (4.3 everywhere, ~$3.75)",
    )
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
    parser.add_argument(
        "--discovery-notes",
        type=str,
        help="Path to discovery notes file (freeform meeting insights)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show cost estimate only")
    parser.add_argument("--show-usage", action="store_true", help="Display usage statistics")
    parser.add_argument("--context", type=str, nargs="+", help="Context files for deep mode")
    parser.add_argument("--context-folder", type=str, help="Use working folder as context")
    parser.add_argument("--open", action="store_true", help="Open report after generation")
    parser.add_argument("--output-dir", type=str, help="Custom output directory")
    parser.add_argument("--list-recent", action="store_true", help="List recent outputs")
    parser.add_argument("--clean-temp", action="store_true", help="Clean temporary files")
    parser.add_argument(
        "--refresh-vendor-research", action="store_true", help="Force refresh vendor research"
    )
    parser.add_argument(
        "--generate-vendor-research", type=str, choices=["azure", "aws", "gcp", "agnostic", "all"]
    )
    parser.add_argument("--check-jobs", action="store_true", help="Check pending research jobs")
    parser.add_argument(
        "--resume-latest",
        "--resume-jobs",
        action="store_true",
        help="Recover completed pending jobs and finalize canonical output files",
    )
    parser.add_argument("--clear-jobs", action="store_true", help="Clear stale pending jobs")
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
    # Label calibration (primr calibrate)
    parser.add_argument(
        "--calibrate-recent",
        type=int,
        metavar="N",
        help="With 'calibrate', audit the N most recent reports (one per company)",
    )
    parser.add_argument(
        "--max-per-label",
        type=int,
        default=10,
        metavar="N",
        help="With 'calibrate', max claims sampled per confidence label (default: 10)",
    )
    parser.add_argument(
        "--judge",
        type=str,
        choices=["cloud", "local", "auto"],
        default="cloud",
        help=(
            "With 'calibrate', which LLM judges traceability: cloud (fast tier, default), "
            "local (your OpenAI-compatible server, e.g. Ollama; errors if unavailable), "
            "or auto (local when reachable, else cloud)"
        ),
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        metavar="NAME",
        help="With '--judge local/auto', pin a specific local model instead of auto-picking",
    )
    parser.add_argument(
        "--judge-compare",
        action="store_true",
        help=(
            "With 'calibrate', judge the same claims with BOTH cloud and local and report "
            "agreement, measuring whether your local model can be trusted as the judge. "
            "Sidecars are written from the cloud verdicts."
        ),
    )
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
        help="Generate AI strategy using an existing report as context (retry failed AI strategy)",
    )

    # Strategy type selection
    parser.add_argument(
        "--strategy-type",
        type=str,
        choices=_get_strategy_choices(),
        default="ai",
        help=_get_strategy_help(),
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
            "Per-run cost ceiling in USD for standard research. Refuses to start "
            "when the estimate exceeds it; skips optional stages (strategy "
            "generation) once actual spend reaches it."
        ),
    )
    parser.add_argument("--roadmap", action="store_true", help="Show roadmap information")
    parser.add_argument(
        "--roadmap-version",
        type=str,
        metavar="VERSION",
        help="Show details for a specific roadmap version (e.g., 'v1.7.0')",
    )

    # Versioned model/profile evaluation
    parser.add_argument(
        "--eval",
        action="store_true",
        dest="eval_mode",
        help="Run versioned model/profile evaluation scorecard (offline analysis by default)",
    )
    parser.add_argument(
        "--eval-id", type=str, metavar="EVAL_ID", help="Evaluation run id (e.g., eval-2026-02-r1)"
    )
    parser.add_argument(
        "--eval-root",
        type=str,
        default="output/evals",
        help="Root folder containing eval outputs (default: output/evals)",
    )
    parser.add_argument(
        "--eval-profiles",
        type=str,
        nargs="+",
        default=["full", "lite", "fast"],
        help=(
            "Profiles to compare (default: full lite fast). "
            "Any registered profile slot name is accepted -- see "
            "primr.core.model_eval.list_eval_profile_names() for the full set. "
            "Cross-provider eval slots registered via register_eval_profile() "
            "are accepted at runtime; argparse no longer restricts to the legacy three."
        ),
    )
    parser.add_argument(
        "--eval-baseline",
        type=str,
        default="full",
        help=(
            "Baseline profile for quality/cost ratio comparison (default: full). "
            "Must be a registered profile slot name."
        ),
    )
    parser.add_argument(
        "--eval-manifest",
        type=str,
        metavar="CSV_PATH",
        help="CSV manifest with company/company_name and website columns (required for --eval-run-missing)",
    )
    parser.add_argument(
        "--eval-run-missing",
        action="store_true",
        help="Execute missing profile/company runs (requires explicit spend guardrails)",
    )
    parser.add_argument(
        "--eval-max-new-runs",
        type=int,
        default=0,
        help="Maximum number of missing runs to execute when --eval-run-missing is set (default: 0)",
    )
    parser.add_argument(
        "--eval-max-estimated-cost",
        type=float,
        default=0.0,
        help="Hard spend cap in USD for missing runs when --eval-run-missing is set (default: 0.0)",
    )
    parser.add_argument(
        "--eval-quality-ratio-threshold",
        type=float,
        default=0.8,
        help="Minimum quality ratio vs baseline for pass/fail (default: 0.8)",
    )
    parser.add_argument(
        "--eval-cost-ratio-threshold",
        type=float,
        default=0.2,
        help="Maximum estimated cost ratio vs baseline for pass/fail (default: 0.2)",
    )
    parser.add_argument(
        "--eval-company",
        type=str,
        help="Target a specific company for auto-staging from existing outputs",
    )
    parser.add_argument(
        "--eval-source-dir",
        type=str,
        default="output",
        help="Source directory to auto-stage reports from (default: output)",
    )
    parser.add_argument(
        "--eval-no-auto-stage",
        action="store_true",
        help="Disable automatic staging from existing local outputs",
    )
    parser.add_argument(
        "--eval-llm-judge",
        action="store_true",
        help="Optional LLM judge overlay for eval scorecard (incurs API cost)",
    )
    parser.add_argument(
        "--eval-judge-provider",
        type=str,
        choices=["grok", "local"],
        default="grok",
        help="LLM judge provider (default: grok; use local for OpenAI-compatible backends such as Ollama)",
    )
    parser.add_argument(
        "--eval-judge-model",
        type=str,
        default="grok-4.3",
        help="Model name for LLM judge (for local judge, set this to your Ollama/OpenAI-compatible model name)",
    )
    parser.add_argument(
        "--eval-judge-models",
        type=str,
        nargs="+",
        default=None,
        help="For local judge sweeps: run the same eval comparison across multiple OpenAI-compatible model names",
    )
    parser.add_argument(
        "--eval-judge-model-list",
        type=str,
        default=None,
        help="Named local judge model list (for example: 4090-top10 or installed-starter)",
    )
    parser.add_argument(
        "--eval-judge-base-url",
        type=str,
        default=None,
        help="Base URL for local/OpenAI-compatible eval judge (defaults to LOCAL_LLM_BASE_URL, OLLAMA_BASE_URL, or http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--eval-judge-api-key-env",
        type=str,
        default="LOCAL_LLM_API_KEY",
        help="Environment variable name containing the API key for the local/OpenAI-compatible judge (default: LOCAL_LLM_API_KEY)",
    )
    parser.add_argument(
        "--eval-judge-max-pairs",
        type=int,
        default=1,
        help="Max company profile pairs to judge (default: 1)",
    )
    parser.add_argument(
        "--eval-judge-passes",
        type=int,
        default=1,
        help="Judge passes per pair for variance reduction (default: 1, cheapest)",
    )
    parser.add_argument(
        "--eval-judge-max-cost",
        type=float,
        default=0.0,
        help="Hard cost cap in USD for LLM judge pass (required when --eval-llm-judge)",
    )
    parser.add_argument(
        "--eval-local-stage",
        type=str,
        choices=["website-summary"],
        default=None,
        help="Run a local generation eval for a production-adjacent stage (currently: website-summary)",
    )
    parser.add_argument(
        "--eval-working-root",
        type=str,
        default="working",
        help="Root directory containing working run folders for stage-level eval inputs (default: working)",
    )

    return parser


_POSITIONAL_COMMANDS: dict[str, Command] = {
    "init": Command.INIT,
    "doctor": Command.DOCTOR,
    "memory": Command.MEMORY,
    "orchestrate": Command.ORCHESTRATE,
    "roadmap": Command.ROADMAP,
    "improve": Command.IMPROVE,
    "refine": Command.REFINE,
    "calibrate": Command.CALIBRATE,
}

# (attr_name, command) — checked with getattr(args, attr, None) for truthiness
_FLAG_COMMANDS: list[tuple[str, Command]] = [
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
    ("dry_run", Command.DRY_RUN),
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
    list_recent_outputs()
    return 0


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
    check_pending_jobs()
    return 0


def _handle_resume_latest(config: CLIConfig) -> int:
    """Handle resume-latest command."""
    return resume_pending_jobs()


def _handle_clear_jobs(config: CLIConfig) -> int:
    """Handle clear-jobs command - removes stale pending jobs."""
    import json

    from primr.ai.deep_research import get_pending_jobs
    from primr.config.config import LOGS_DIR

    jobs = get_pending_jobs()
    if not jobs:
        console.info("No pending jobs to clear.")
        return 0

    console.info(f"Clearing {len(jobs)} stale job(s)...")

    jobs_file = os.path.join(LOGS_DIR, "pending_research_jobs.json")
    with open(jobs_file, "w", encoding="utf-8") as f:
        json.dump({}, f)

    console.ok(f"Cleared {len(jobs)} pending jobs")
    return 0


def _handle_show_usage(config: CLIConfig) -> int:
    """Handle show-usage command."""
    from primr.utils.usage_tracker import get_usage_tracker

    tracker = get_usage_tracker()
    print(tracker.display_usage_history())
    print(_format_vendor_research_freshness())
    return 0


def _format_vendor_research_freshness() -> str:
    """Show when each cached vendor research file was last refreshed.

    Vendor research is shared per-user (one ~$0.50 Deep Research file per
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


def _handle_dry_run(config: CLIConfig) -> int:
    """Handle dry-run command."""
    from primr.utils.cost_estimator import estimate_cost

    # Resolve mode: same logic as _handle_research
    if config.premium_mode and config.fast_mode:
        console.error("Cannot use both --fast and --premium. Choose one.")
        return 1

    use_fast_mode = config.fast_mode
    use_premium_mode = config.premium_mode

    if (
        not use_fast_mode
        and not use_premium_mode
        and config.mode in ("complete", "structured", "hybrid")
    ):
        if os.environ.get("XAI_API_KEY"):
            use_fast_mode = True

    # Validate compatibility
    if use_fast_mode and config.mode not in ("complete", "structured", "hybrid"):
        console.error(f"--fast only works with full mode, not --mode {config.mode}")
        console.info('Usage: primr "Company" https://url --fast [--platform aws azure] --dry-run')
        return 1
    if use_premium_mode and config.mode not in ("complete", "structured", "hybrid"):
        console.error(f"--premium only works with full mode, not --mode {config.mode}")
        return 1

    tier_labels = {"fast": "Grok 4.1", "hybrid": "Grok 4.3 hybrid", "max": "Grok 4.3 max"}
    if use_premium_mode:
        mode_label = "premium (Gemini + Deep Research)"
    elif use_fast_mode:
        mode_label = f"standard ({tier_labels.get(config.grok_tier, 'Grok')})"
    else:
        mode_label = config.mode
    print("")
    print("=" * 60)
    print(f"COST ESTIMATE: {mode_label} mode")
    if config.ai_strategy and not use_fast_mode:
        strategy_label = (
            "AI Strategy (Pro mode)" if config.lite_strategy else "AI Strategy analysis"
        )
        print(f"(includes {strategy_label})")
    elif use_fast_mode and config.ai_strategy:
        print("(includes AI Strategy via Grok)")
    print("=" * 60)
    print("")

    estimate = estimate_cost(
        config.mode,
        config.ai_strategy,
        num_vendors=len(config.cloud_vendors),
        lite_strategy=config.lite_strategy,
        fast_mode=use_fast_mode,
        premium_mode=use_premium_mode,
        grok_tier=config.grok_tier,
    )
    print(str(estimate))

    # Recon pre-flight step (DNS intelligence — no API cost)
    if not config.skip_recon:
        print("")
        print("RECON PRE-FLIGHT")
        print("-" * 40)
        print("  DNS intelligence lookup:  $0.00  (~2-3 seconds)")
        print("  (no API keys required)")
    else:
        print("")
        print("RECON PRE-FLIGHT: skipped (--skip-recon)")

    # Recovery table summary (pipeline-resilience feature)
    # Validates: Requirements 14.1, 14.2
    print("")
    print("RECOVERY TABLE")
    print("-" * 40)
    from primr.pipeline.recovery import build_default_recovery_table
    from primr.pipeline.stages import STAGE_CLASSIFICATIONS

    recovery_table = build_default_recovery_table()
    for stage, hierarchy in recovery_table.hierarchies.items():
        classification = STAGE_CLASSIFICATIONS[stage].value
        actions = ", ".join(a.action_type.value for a in hierarchy.actions)
        print(f"  {stage.value} ({classification}): {actions}")
    print("")
    print("Recovery Table JSON:")
    print(recovery_table.to_json())

    print("")
    print("=" * 60)
    print("")
    print("To run research, remove --dry-run flag")
    return 0


def _handle_generate_vendor(config: CLIConfig) -> int:
    """Handle generate-vendor command."""
    from primr.core.vendor_research import generate_vendor_research_sync

    console.banner("Vendor AI Research Generation")

    if config.generate_vendor == "all":
        vendors = ["azure", "aws", "gcp", "agnostic"]
    else:
        vendors = [config.generate_vendor] if config.generate_vendor else []

    for vendor in vendors:
        console.step(f"Generating {vendor.upper()} research")
        result = generate_vendor_research_sync(vendor)
        if result:
            console.ok(f"Saved: {result}")
        else:
            console.error(f"Failed to generate {vendor} research")

    return 0


def _handle_enrich(config: CLIConfig) -> int:
    """Handle batch enrich command."""
    if not config.batch_file:
        console.error("No batch file specified")
        console.info('Usage: primr --batch "file.xlsx" --enrich')
        return 1

    return enrich_batch(
        config.batch_file,
        industry=config.industry,
        limit=config.limit,
        mode=config.mode,
    )


def _handle_batch(config: CLIConfig) -> int:
    """Handle batch processing (Excel or CSV)."""
    # New --batch flag takes priority
    if config.batch_file:
        return process_batch(
            config.batch_file,
            mode=config.mode,
            citation_style=config.citation_style,
            ai_strategy=config.ai_strategy,
            platforms=config.cloud_vendors,
            industry=config.industry,
            limit=config.limit,
            skip_confirm=config.skip_confirm,
        )

    # Legacy --csv path
    if not config.csv_file:
        console.error("No file specified")
        console.info('Usage: primr --batch "file.xlsx" --mode scrape')
        return 1

    process_csv(
        config.csv_file,
        mode=config.mode,
        citation_style=config.citation_style,
        ai_strategy=config.ai_strategy,
        platforms=config.cloud_vendors,
    )
    return 0


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
        console.ok("No sections needed regeneration — report left unchanged")
    return 0


def _handle_calibrate(config: CLIConfig) -> int:
    """Handle the label-calibration audit: primr calibrate "Company"."""
    from primr.qa.calibration_runner import (
        aggregate_per_label,
        aggregate_precision,
        compare_judges,
        estimate_cost_usd,
        resolve_judge,
        resolve_reports,
        run_calibration,
    )

    try:
        reports = resolve_reports(config.calibrate_target, recent=config.calibrate_recent)
    except FileNotFoundError as e:
        console.error(str(e))
        console.info('Usage: primr calibrate "Company Name" [--dry-run] [--max-per-label 10]')
        console.info("   or: primr calibrate path/to/report.md")
        console.info("   or: primr calibrate --calibrate-recent 10")
        return 1

    console.banner("Label Calibration")
    console.info(f"Reports: {len(reports)}")

    if config.calibrate_judge_compare:
        # Compare mode needs a working local judge alongside the cloud one.
        try:
            local_selection = resolve_judge("local", model=config.calibrate_judge_model)
        except RuntimeError as e:
            console.error(str(e))
            return 1
        console.info(f"Judges: cloud (fast-tier) vs local ({local_selection.model})")
        if config.calibrate_dry_run:
            outcomes = run_calibration(
                reports, max_per_label=config.calibrate_max_per_label, dry_run=True
            )
            total_calls = sum(o.estimated_judge_calls for o in outcomes)
            console.info(
                f"Dry run: ~{total_calls} cloud judge calls (${estimate_cost_usd(total_calls):.2f})"
                f" + ~{total_calls} local judge calls ($0.00)"
            )
            return 0
        outcomes, agreement = compare_judges(
            reports,
            local_selection=local_selection,
            max_per_label=config.calibrate_max_per_label,
        )
        if agreement.agreement is None:
            console.warn("No claims were decidable by both judges — agreement not measurable")
        else:
            console.info(
                f"Judge agreement: {agreement.agreement:.0%} "
                f"({agreement.agreed}/{agreement.compared} decidable claims, "
                f"local={agreement.local_model})"
            )
    else:
        try:
            judge_selection = resolve_judge(
                config.calibrate_judge, model=config.calibrate_judge_model
            )
        except (RuntimeError, ValueError) as e:
            console.error(str(e))
            return 1
        console.info(f"Judge: {judge_selection.kind} ({judge_selection.model})")
        outcomes = run_calibration(
            reports,
            max_per_label=config.calibrate_max_per_label,
            dry_run=config.calibrate_dry_run,
            judge_selection=judge_selection,
        )
        if judge_selection.cloud_fallbacks:
            console.warn(
                f"Local judge fell back to cloud on {judge_selection.cloud_fallbacks} call(s)"
            )

    failures = [o for o in outcomes if o.error]
    for outcome in failures:
        console.warn(f"{outcome.report_path.name}: {outcome.error}")

    if config.calibrate_dry_run:
        total_calls = sum(o.estimated_judge_calls for o in outcomes)
        for outcome in outcomes:
            console.info(
                f"  {outcome.report_path.name}: {outcome.claims_sampled} claims, "
                f"{outcome.judgeable_claims} judgeable, "
                f"~{outcome.estimated_judge_calls} judge calls"
            )
        console.info(
            f"Dry run: ~{total_calls} judge calls, estimated ${estimate_cost_usd(total_calls):.2f}"
        )
        return 0

    totals = aggregate_per_label(outcomes)
    for label in ("Confirmed", "Reported"):
        stats = totals.get(label)
        if not stats:
            continue
        precision = aggregate_precision(totals, label)
        shown = f"{precision:.0%}" if precision is not None else "n/a (no decidable claims)"
        console.info(
            f"  {label}: traceability {shown} "
            f"(traceable {stats['traceable']}, untraceable {stats['untraceable']}, "
            f"no-source {stats['no_source']}, unfetchable {stats['unfetchable']})"
        )
    sidecars = [o for o in outcomes if o.sidecar_path]
    if sidecars:
        console.ok(f"Calibration sidecars written: {len(sidecars)}")
    return 0 if not failures else 1


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
    """Handle strategy generation using existing report as context."""
    import re
    from pathlib import Path

    from primr.core.research_agent import _generate_strategy_section

    report_path = config.ai_strategy_only_path
    if not report_path:
        console.error("Report path is required for --ai-strategy-only")
        console.info(
            'Usage: primr --ai-strategy-only "path/to/report.md" --strategy-type customer_experience'
        )
        return 1

    # Validate file exists and lives under a trusted root. Without root
    # containment, an attacker who can pass --ai-strategy-only arguments
    # (e.g. via shared automation) could upload arbitrary readable files
    # as Deep Research context.
    path = Path(report_path).expanduser()
    if not path.exists():
        console.error(f"Report file not found: {report_path}")
        return 1
    try:
        from primr.config.config import OUTPUT_DIR, WORKING_DIR

        allowed_roots = [Path(OUTPUT_DIR).resolve(), Path(WORKING_DIR).resolve()]
        if config.output_dir:
            allowed_roots.append(Path(config.output_dir).resolve())
        resolved_path = path.resolve()
        if not any(
            resolved_path == root or resolved_path.is_relative_to(root) for root in allowed_roots
        ):
            console.error(
                f"Report file is outside allowed roots (output/, working/): {resolved_path}"
            )
            return 1
    except Exception:
        # Defensive: if containment check itself fails, fall through to
        # filename derivation but log it.
        logger.warning("Could not enforce report-root containment for %s", path)

    # Get strategy type (default to 'ai' if not specified)
    strategy_type = getattr(config, "strategy_type", "ai")

    # Map strategy types to display names
    strategy_names = {
        "ai": "AI Strategy",
        "customer_experience": "Customer Experience Strategy",
        "modern_security_compliance": "Security & Compliance Strategy",
        "data_fabric_strategy": "Data Fabric Strategy",
    }
    strategy_display = strategy_names.get(strategy_type, strategy_type)

    # Extract company name from filename or content.
    company_name = config.company_name
    if not company_name:
        filename = path.stem
        # Try to extract from filename pattern
        match = re.match(
            r"^(.+?)_(?:Strategic_Overview|AI_Strategy|Customer_Experience|Security|Data_Fabric)",
            filename,
        )
        if match:
            company_name = match.group(1).replace("_", " ")
        else:
            # Fallback: use filename without extension
            company_name = filename.replace("_", " ")

    # Always run company_name through the path-traversal-aware validator
    # before it reaches output-path construction in _generate_strategy_section.
    try:
        from primr.utils.validators import (
            InputValidationError,
            validate_company_name,
        )

        company_name = validate_company_name(company_name)
    except InputValidationError as e:
        console.error(f"Invalid company name: {e.reason}")
        return 1

    console.banner(f"{strategy_display} Generation")
    console.info(f"Company: {company_name}")
    console.info(f"Context: {path.name}")
    if strategy_type == "ai":
        vendor_names = ", ".join(v.upper() for v in config.cloud_vendors)
        console.info(f"Cloud Vendor(s): {vendor_names}")
    console.blank()

    # For AI strategy, loop over each vendor; others run once
    vendors = list(config.cloud_vendors) if strategy_type == "ai" else ["agnostic"]
    result_paths: list[str] = []
    diagnostics_dir = Path(config.output_dir) / "_diagnostics" if config.output_dir else None

    for vendor in vendors:
        result_path = _generate_strategy_section(
            strategy_name=strategy_type,
            company_name=company_name,
            platform=vendor,
            company_research_path=str(path),
            force_refresh_vendor=config.refresh_vendor_research,
            discovery_notes_content=None,  # TODO: Add discovery notes support
            lite_strategy=config.lite_strategy,
            output_dir=config.output_dir,
            diagnostics_dir=diagnostics_dir,
            write_txt=config.output_dir is None,
        )

        if result_path:
            vendor_label = (
                f" ({vendor.upper()})" if strategy_type == "ai" and len(vendors) > 1 else ""
            )
            console.blank()
            console.success_box(f"{strategy_display}{vendor_label} generated", result_path)
            result_paths.append(result_path)

    if result_paths:
        # Open last generated file if requested
        if config.open_after:
            open_file(result_paths[-1])
        return 0
    else:
        console.error(f"{strategy_display} generation failed")
        return 1


# =============================================================================
# AGENTIC ARCHITECTURE HANDLERS
# =============================================================================


def _handle_memory(config: CLIConfig) -> int:
    """Handle research memory commands."""
    from pathlib import Path

    from primr.agentic.memory import ResearchMemory

    # Default memory path
    memory_path = Path("./logs/research_memory")

    try:
        memory = ResearchMemory(storage_path=memory_path)
    except Exception as e:
        console.error(f"Failed to initialize research memory: {e}")
        return 1

    # List all companies
    if config.memory_list:
        console.banner("Research Memory")
        companies = memory.list_companies()
        if not companies:
            console.info("No research memory found.")
            console.info("Run research to start tracking hypotheses.")
            return 0

        console.info(f"Found {len(companies)} company/companies with research memory:")
        console.blank()
        for company in sorted(companies):
            hypotheses = memory.get_hypotheses(company)
            console.ok(f"  {company}: {len(hypotheses)} hypothesis/hypotheses")
        return 0

    # Show hypotheses for a specific company
    company = config.memory_company
    if not company:
        # Check if company was passed as positional arg (website position when 'memory' is company)
        if config.website:
            company = config.website
        elif config.company_name and config.company_name.lower() != "memory":
            company = config.company_name
        else:
            console.error("Company name required")
            console.info('Usage: primr memory "Company Name"')
            console.info('   or: primr --memory "Company Name"')
            console.info("   or: primr --memory-list")
            return 1

    console.banner(f"Research Memory: {company}")

    hypotheses = memory.get_hypotheses(company)
    if not hypotheses:
        console.info(f"No hypotheses found for {company}")
        console.info("Run research to generate hypotheses.")
        return 0

    console.info(f"Found {len(hypotheses)} hypothesis/hypotheses:")
    console.blank()

    # Group by confidence level
    by_confidence: dict[str, list] = {}
    for h in hypotheses:
        level = h.confidence.value
        if level not in by_confidence:
            by_confidence[level] = []
        by_confidence[level].append(h)

    # Display in order: validated, high, medium, low
    order = ["validated", "high", "medium", "low"]
    for level in order:
        if level in by_confidence:
            console.step(f"{level.upper()} confidence ({len(by_confidence[level])})")
            for h in by_confidence[level]:
                console.info(f"  • {h.statement}")
                if h.evidence:
                    console.info(f"    Evidence: {h.evidence[:100]}...")
                if h.topic:
                    console.info(f"    Topic: {h.topic}")
            console.blank()

    return 0


def _handle_orchestrate(config: CLIConfig) -> int:
    """Handle orchestrated research command."""
    import asyncio
    from pathlib import Path

    from primr.agentic.hooks import CostGuardHook, HookSystem, SSRFGuardHook
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
    memory_path = Path("./logs/research_memory")
    output_path = Path("./output")

    memory = ResearchMemory(storage_path=memory_path)
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
    from primr.core.local_stage_eval import (
        find_latest_website_summary_eval_inputs,
        run_local_website_summary_stage_eval,
        write_website_summary_stage_eval_markdown,
        write_website_summary_stage_eval_report,
        write_website_summary_stage_eval_summary,
    )
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

    # Validate every profile name is a registered slot. argparse no longer
    # restricts to the legacy three; cross-provider eval slots are accepted
    # via runtime registration. See ROADMAP "v1.24.0 — Sub-$1 default eval".
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
                # Consult the slot registry first — registered slots may declare
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
                # space-preserving names (Acme Corp Inc.) — primr's actual
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

    if config.eval_local_stage == "website-summary":
        console.blank()
        console.step("Local Stage Eval")
        judge_models, missing_models = _resolve_local_judge_models(config)
        if config.eval_judge_model_list:
            console.info(f"Local stage model list: {config.eval_judge_model_list}")
        if missing_models:
            console.warn(
                "Skipping local stage models not installed in Ollama: " + ", ".join(missing_models)
            )
        if not judge_models:
            console.error(
                "No local models available for stage eval after resolving the requested list."
            )
            return 1
        target_companies = (
            [config.eval_company]
            if config.eval_company
            else sorted({m.company for m in eval_result.metrics})
        )
        inputs = find_latest_website_summary_eval_inputs(
            Path(config.eval_working_root),
            companies=target_companies or None,
        )
        if not inputs:
            console.warn(
                "No working folders with scraped_content.txt and scraped_website_summary.txt found for local stage eval."
            )
        else:
            console.info(
                f"Stage=website-summary, Companies={', '.join(row.company for row in inputs)}, "
                f"Models={', '.join(judge_models)}"
            )
            stage_root = Path(config.eval_root) / config.eval_id / "website_summary_stage"
            stage_results: list[tuple[str, list[Any]]] = []
            for model_name in judge_models:
                console.info(f"Running local website-summary stage model: {model_name}")
                stage_rows = run_local_website_summary_stage_eval(
                    inputs=inputs,
                    model=model_name,
                    output_root=stage_root,
                    base_url=config.eval_judge_base_url,
                    api_key_env=config.eval_judge_api_key_env,
                )
                stage_results.append((model_name, stage_rows))
                model_slug = re.sub(r"[^a-zA-Z0-9]+", "-", model_name).strip("-").lower() or "model"
                report_path = stage_root / f"website_summary_stage.{model_slug}.json"
                write_website_summary_stage_eval_report(
                    report_path,
                    model=model_name,
                    rows=stage_rows,
                    base_url=config.eval_judge_base_url,
                    api_key_env=config.eval_judge_api_key_env,
                )
                console.info(f"  companies: {len(stage_rows)}")
                console.info(f"  output: {report_path}")
            summary_json = stage_root / "website_summary_stage_summary.json"
            summary_md = stage_root / "website_summary_stage_summary.md"
            write_website_summary_stage_eval_summary(
                summary_json,
                eval_id=config.eval_id,
                results=stage_results,
            )
            write_website_summary_stage_eval_markdown(
                summary_md,
                eval_id=config.eval_id,
                results=stage_results,
            )
            console.info(f"Local stage eval summary: {summary_json}")
            console.info(f"Local stage eval markdown: {summary_md}")

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


def _run_preflight_checks(mode: str) -> tuple[bool, list[str]]:
    """
    Run preflight checks before starting research pipeline.

    Validates critical dependencies upfront to fail fast rather than
    failing 30 minutes into a long pipeline.

    Returns:
        (success, errors) - True if all checks pass, list of error messages if not
    """
    errors = []

    # 1. Check GEMINI_API_KEY (required for all modes)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key or len(gemini_key) < 10:
        errors.append(
            "GEMINI_API_KEY not configured. Run 'primr keys set gemini' "
            "or get a key at https://aistudio.google.com/apikey"
        )

    # 2. Check Playwright browsers (required for scrape and full modes)
    if mode in ("scrape-only", "complete", "hybrid", "structured"):
        try:
            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            try:
                # Try to launch browser - this will fail if browsers aren't installed
                browser = pw.chromium.launch(headless=True)
                browser.close()
            finally:
                pw.stop()
        except Exception as e:
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg or "playwright install" in error_msg.lower():
                errors.append("Playwright browsers not installed. Run: playwright install chromium")
            else:
                errors.append(f"Playwright check failed: {error_msg}")

    # 3. Quick API connectivity check (validates key is valid)
    if gemini_key and len(gemini_key) >= 10:
        try:
            from google import genai

            client = genai.Client(api_key=gemini_key, http_options=default_genai_http_options())
            # Minimal test - just check we can connect
            _ = client.models.generate_content(
                model=PrimrModels.FAST_MODEL,
                contents="Reply with: ok",
            )
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                errors.append("Gemini API quota exceeded - wait and retry later")
            elif "invalid" in error_str or "api key" in error_str:
                errors.append("Gemini API key is invalid - check your .env file")
            else:
                errors.append(f"Gemini API connection failed: {e}")

    # 4. Check search provider (Google requires API keys; DDG needs nothing)
    search_provider = os.environ.get("SEARCH_PROVIDER", "auto").lower().strip()
    if search_provider == "google":
        search_key = os.environ.get("SEARCH_API_KEY", "")
        search_engine_id = os.environ.get("SEARCH_ENGINE_ID", "")

        if not search_key or len(search_key) < 10:
            errors.append(
                "SEARCH_API_KEY not configured. Get your key at: https://console.cloud.google.com/apis/credentials"
            )
        elif not search_engine_id or len(search_engine_id) < 10:
            errors.append(
                "SEARCH_ENGINE_ID not configured or invalid. Get it at: https://programmablesearchengine.google.com/controlpanel/all"
            )
        else:
            # Actually test the Search API with a simple query
            try:
                import requests

                test_url = "https://www.googleapis.com/customsearch/v1"
                params: dict[str, str | int] = {
                    "q": "test",
                    "key": search_key,
                    "cx": search_engine_id,
                    "num": 1,
                }
                search_response = requests.get(test_url, params=params, timeout=10)
                if search_response.status_code == 400:
                    error_detail = (
                        search_response.json().get("error", {}).get("message", "Bad Request")
                    )
                    errors.append(f"Google Search API config invalid: {error_detail}")
                elif search_response.status_code == 403:
                    errors.append("Google Search API key invalid or quota exceeded")
                elif search_response.status_code != 200:
                    errors.append(f"Google Search API error: HTTP {search_response.status_code}")
            except requests.exceptions.Timeout:
                errors.append("Google Search API timeout - check your internet connection")
            except Exception as e:
                errors.append(f"Google Search API check failed: {e}")

    return (len(errors) == 0, errors)


def _handle_research(config: CLIConfig) -> int:
    """Handle research command."""
    from primr.core.research_agent import perform_research
    from primr.core.workspace import consolidate_working_folder, validate_context_files
    from primr.utils.validators import InputValidationError, validate_company_name, validate_url

    # Validate inputs
    if not config.company_name or not config.website:
        console.error("Both company name and website are required")
        console.info("")
        console.info('Usage: primr "Company Name" https://company.com')
        console.info("")
        console.info("Run 'primr doctor' to check system configuration")
        return 1

    # Validate company name
    try:
        company_name = validate_company_name(config.company_name)
    except InputValidationError as e:
        console.error(f"Invalid company name: {e.reason}")
        return 1

    # Normalize and validate website
    website = _ensure_valid_url(config.website)
    try:
        website = validate_url(website)
    except InputValidationError as e:
        console.error(f"Invalid website URL: {e.reason}")
        return 1

    # Run preflight checks before starting the pipeline
    console.step("Preflight checks")
    preflight_ok, preflight_errors = _run_preflight_checks(config.mode)
    if not preflight_ok:
        for error in preflight_errors:
            console.error(error)
        console.blank()
        console.info("Run 'primr doctor' for detailed diagnostics")
        return 1

    # Resolve mode: --premium vs --fast vs auto-detect via XAI_API_KEY
    if config.premium_mode and config.fast_mode:
        console.error("Cannot use both --fast and --premium. Choose one.")
        return 1

    # Determine effective fast_mode for this run
    use_fast_mode = config.fast_mode
    use_premium_mode = config.premium_mode

    if (
        not use_fast_mode
        and not use_premium_mode
        and config.mode in ("complete", "structured", "hybrid")
    ):
        # Auto-detect: if XAI_API_KEY is set, default to fast mode
        if os.environ.get("XAI_API_KEY"):
            use_fast_mode = True
            tier_label = {
                "fast": "Grok 4.3 (low-effort)",
                "hybrid": "Grok 4.3 hybrid",
                "max": "Grok 4.3 max",
            }
            console.info(
                f"Using {tier_label.get(config.grok_tier, 'Grok')} · for deeper research add --premium"
            )
        else:
            console.info("Using standard mode (Gemini). Set XAI_API_KEY for faster, cheaper runs.")

    if use_premium_mode:
        if config.mode not in ("complete", "structured", "hybrid"):
            console.error(f"--premium only works with full mode, not --mode {config.mode}")
            return 1

    # Fast mode preflight: verify XAI_API_KEY and openai package
    if use_fast_mode:
        if config.mode not in ("complete", "structured", "hybrid"):
            console.error(f"--fast only works with full mode, not --mode {config.mode}")
            console.info('Usage: primr "Company" https://url --fast [--platform aws azure]')
            return 1
        if not os.environ.get("XAI_API_KEY"):
            console.error("Fast mode requires XAI_API_KEY in your .env or environment")
            console.info("Set it with: primr keys set xai")
            console.info("Get a key at https://console.x.ai/")
            return 1
        try:
            import openai  # noqa: F401
        except ImportError:
            console.error("Fast mode requires the 'openai' package")
            console.info("Install with: pip install 'primr[fast]' or pip install openai")
            return 1
        if config.lite_strategy:
            console.warn("--lite is ignored with --fast (fast mode uses Grok for all calls)")

    console.ok("All systems ready")

    # Build context files list
    context_files = list(config.context_files)

    # Handle context folder
    if config.context_folder:
        try:
            consolidated_file = consolidate_working_folder(config.context_folder)
            context_files = [consolidated_file, *context_files]
        except Exception as e:
            console.error(f"Failed to consolidate context folder: {e}")
            return 1

    # Validate context files
    if context_files:
        # Cast to satisfy mypy - list[str] is compatible with list[str | Path]
        validation_result = validate_context_files(list(context_files))  # type: ignore[arg-type]
        for warning in validation_result.warnings:
            console.warn(warning)
        if validation_result.invalid_files:
            for file_path, reason in validation_result.invalid_files:
                console.error(f"Invalid context file: {file_path} - {reason}")
            return 1
        context_files = [str(p) for p in validation_result.valid_files]

    # Build strategy types list from --strategy-type (non-AI strategies for Grok/DR)
    strategy_types = None
    if config.strategy_type and config.strategy_type != "ai":
        strategy_types = [config.strategy_type]

    os.environ["PRIMR_BROWSER_SESSION_MODE"] = config.browser_session_mode
    if config.browser_headed:
        os.environ["PRIMR_BROWSER_HEADED"] = "1"
    else:
        os.environ.pop("PRIMR_BROWSER_HEADED", None)

    # --budget pre-flight gate: refuse to start a run whose estimate already
    # exceeds the ceiling, then activate the run budget so the pipeline can
    # skip optional stages once actual spend reaches it.
    run_budget_active = False
    if config.budget_usd is not None:
        from primr.utils.cost_estimator import estimate_cost
        from primr.utils.run_budget import set_run_budget

        if config.budget_usd <= 0:
            console.error(f"--budget must be positive, got {config.budget_usd}")
            return 1

        budget_estimate = estimate_cost(
            config.mode,
            config.ai_strategy,
            num_vendors=len(config.cloud_vendors),
            lite_strategy=config.lite_strategy,
            fast_mode=use_fast_mode,
            premium_mode=use_premium_mode,
            grok_tier=config.grok_tier,
        )
        if budget_estimate.total_cost > config.budget_usd:
            console.error(
                f"Estimated cost ${budget_estimate.total_cost:.2f} exceeds "
                f"--budget ${config.budget_usd:.2f}. Not starting."
            )
            console.info(
                "Raise --budget, or use a cheaper mode (--mode scrape ~$0.10, "
                "--dry-run for the full breakdown)."
            )
            return 1

        set_run_budget(config.budget_usd)
        run_budget_active = True
        console.info(
            f"Run budget: ${config.budget_usd:.2f} (estimated ${budget_estimate.total_cost:.2f})"
        )

    # Run research
    try:
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
            lite_strategy=config.lite_strategy,
            fast_mode=use_fast_mode,
            premium_mode=use_premium_mode,
            skip_scrape_validation=config.skip_scrape_validation,
            resume_local=config.resume_local,
            verify=config.verify,
            grok_tier=config.grok_tier,
            skip_recon=config.skip_recon,
            continuous_reasoning=config.continuous_reasoning,
        )
    finally:
        if run_budget_active:
            from primr.utils.run_budget import clear_run_budget

            clear_run_budget()

    # Open report if requested
    if config.open_after and result_path:
        open_file(result_path)

    return 0 if result_path else 1


# =============================================================================
# INTERNAL FUNCTIONS - Doctor Checks
# =============================================================================


def list_recent_outputs() -> None:
    """List recent research outputs from the output directory."""
    import glob
    from datetime import datetime

    output_files = glob.glob(os.path.join(OUTPUT_DIR, "*.docx"))
    if not output_files:
        print("No recent outputs found.")
        return

    output_files.sort(key=os.path.getmtime, reverse=True)

    print("\nRECENT RESEARCH OUTPUTS")
    print("-" * 60)
    for i, filepath in enumerate(output_files[:20], 1):
        filename = os.path.basename(filepath)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        size_kb = os.path.getsize(filepath) / 1024
        print(f"{i:2}. {filename}")
        print(f"    {mtime.strftime('%Y-%m-%d %H:%M')} | {size_kb:.1f} KB")
    if len(output_files) > 20:
        print(f"... and {len(output_files) - 20} more files")
    print("-" * 60)


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


def check_pending_jobs() -> None:
    """Check pending research jobs."""
    from primr.ai.deep_research import get_deep_research_client, get_pending_jobs

    console.banner("Pending Research Jobs")
    jobs = get_pending_jobs()

    if not jobs:
        console.info("No pending jobs found.")
        return

    console.info(f"Found {len(jobs)} pending job(s)")
    client = get_deep_research_client()

    for interaction_id, job_info in jobs.items():
        console.step(f"Checking: {job_info.get('description', 'Unknown')[:60]}...")
        console.info(f"  ID: {interaction_id}")
        console.info(f"  Started: {job_info.get('started', 'Unknown')}")

        result = client.check_job(interaction_id)
        status = result.get("status", "unknown")
        error = result.get("error")
        error_source = result.get("error_source")
        is_terminal = bool(result.get("terminal", False))

        if status == "completed":
            console.ok("  Status: COMPLETED")
            content = result.get("content", "")
            if content:
                try:
                    outputs = _save_recovered_outputs(interaction_id, job_info, content)
                    console.ok(f"  Finalized MD: {outputs['md']}")
                    console.ok(f"  Finalized DOCX: {outputs['docx']}")
                except Exception as e:
                    job_type = job_info.get("type", "research")
                    output_file = os.path.join(
                        OUTPUT_DIR, f"recovered_{job_type}_{interaction_id[:8]}.txt"
                    )
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    console.warn(f"  Canonical finalize failed: {e}")
                    console.ok(f"  Saved fallback TXT: {output_file}")
        elif status in {"failed", "error", "cancelled", "canceled", "expired"}:
            console.error("  Status: FAILED")
            if error_source == "provider":
                console.error("  Source: Cloud provider reported terminal failure")
            console.error(f"  Error: {error or 'Unknown'}")
        elif status == "check_error":
            console.error("  Status: CHECK ERROR")
            if error_source == "local":
                console.error("  Source: Local API connectivity/status check")
            console.error(f"  Error: {error or 'Unknown'}")
            console.info("  Job may still be running in the cloud. Re-run `primr --check-jobs`.")
        elif status == "in_progress":
            console.info("  Status: IN PROGRESS (still running)")
        else:
            console.info(f"  Status: {status}")
            if error:
                console.info(f"  Detail: {error}")
            if is_terminal:
                console.info("  Terminal state reached; job removed from pending list.")


def _handle_list_strategies(config: CLIConfig) -> int:
    """List available strategy documents (dynamically from YAML configs)."""
    from pathlib import Path

    import yaml  # type: ignore[import-untyped]

    console.banner("Available Strategy Documents")

    console.info("Strategy documents are research tools to help you show up prepared")
    console.info("for discovery conversations. They're NOT deliverables to hand over.")
    console.blank()

    strategies_dir = Path(__file__).parent.parent / "prompts" / "strategies"

    # Separate active vs placeholder strategies
    active: list[dict[str, str]] = []
    placeholders: list[dict[str, str]] = []

    # AI Strategy is always first (built-in)
    active.append(
        {
            "name": "ai",
            "display_name": "AI Strategy",
            "description": "Agentic AI transformation roadmap with vendor-specific recommendations (Azure/AWS/GCP)",
            "usage": 'primr "Company" https://example.com --platform azure',
            "standalone": 'primr --ai-strategy-only "report.md" --platform azure',
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
                    "standalone": f'primr --ai-strategy-only "report.md" --strategy-type {stem}',
                }
                if status == "placeholder":
                    placeholders.append(entry)
                else:
                    active.append(entry)
            except Exception as e:
                logger.warning("Failed to load strategy %s: %s", yaml_path.name, e)
                continue

    console.step(f"Available Strategies ({len(active)} active)")
    console.blank()

    for s in active:
        console.ok(f"  {s['display_name']} ({s['name']})")
        if s.get("description"):
            # Wrap long descriptions
            desc = s["description"]
            console.info(f"    {desc}")
        if s.get("expected_pages"):
            console.muted(f"    Expected: {s['expected_pages']} pages")
        console.info(f"    In research run:  {s['usage']}")
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
    console.info(
        '  2. Standalone:        primr --ai-strategy-only "report.md" --strategy-type customer_experience'
    )
    console.info(
        '  3. With notes:        primr --ai-strategy-only "report.md" --strategy-type ai --discovery-notes "notes.md"'
    )
    console.info('  4. Multi-vendor AI:   primr "Company" https://example.com --platform aws azure')
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
) -> int:
    """
    Enrich a batch file: detect columns, filter by industry, look up websites,
    save enriched CSV. Does NOT run research.

    Returns:
        Exit code (0 for success)
    """
    import os as _os

    from primr.data.search_utils import lookup_company_website

    console.banner("Batch Enrich")
    console.info(f"File: {file_path}")
    if industry:
        console.info(f"Industry filter: {industry}")
    console.blank()

    df, col_map = _prepare_batch_df(file_path, industry=industry, limit=limit)

    total = len(df)
    console.info(f"Found {total} companies")
    console.blank()

    # Build enriched rows (deduplicate by company name, case-insensitive)
    enriched = []
    seen_companies: set[str] = set()
    for idx, (_, row) in enumerate(df.iterrows(), 1):
        company_name = str(row[col_map.company]).strip()
        if not company_name or company_name.lower() == "nan":
            continue
        if company_name.lower() in seen_companies:
            logger.debug(f"Skipping duplicate company: {company_name}")
            continue
        seen_companies.add(company_name.lower())

        # Use existing website if available, otherwise look up
        website = None
        if col_map.website and str(row.get(col_map.website, "")).strip().lower() not in ("", "nan"):
            website = str(row[col_map.website]).strip()
        else:
            console.info(f"  [{idx}/{total}] Looking up {company_name}...")
            # Pass only LLM-selected context columns
            row_context = {
                k: str(row[k]).strip()
                for k in col_map.context
                if str(row.get(k, "")).strip().lower() not in ("", "nan")
            }
            website = lookup_company_website(company_name, context=row_context)

        ind_value = ""
        if col_map.industry and str(row.get(col_map.industry, "")).strip().lower() != "nan":
            ind_value = str(row[col_map.industry]).strip()

        enriched.append(
            {
                "company_name": company_name,
                "website": website or "",
                "industry": ind_value,
            }
        )

    # Display table
    console.blank()
    console.info(f"  {'#':>3}  {'Company':<35} {'Website':<35} {'Industry'}")
    console.info(f"  {'---':>3}  {'-' * 35} {'-' * 35} {'-' * 20}")
    for i, row in enumerate(enriched, 1):
        w = row["website"][:33] + ".." if len(row["website"]) > 35 else row["website"]
        c = (
            row["company_name"][:33] + ".."
            if len(row["company_name"]) > 35
            else row["company_name"]
        )
        console.info(f"  {i:>3}  {c:<35} {w:<35} {row['industry']}")

    found = sum(1 for r in enriched if r["website"])
    missing = len(enriched) - found
    console.blank()
    console.info(f"Websites found: {found}/{len(enriched)}")
    if missing:
        console.warn(f"Missing websites: {missing} (edit the CSV to add them manually)")

    # Save enriched CSV. Sanitize formula-leading cells before export so
    # Excel/Sheets/LibreOffice won't evaluate hostile content (e.g. a
    # company_name like `=WEBSERVICE("https://attacker/")` injected via
    # the input spreadsheet). Prefixing with a single quote is the
    # standard CSV-injection mitigation: spreadsheet apps render the
    # value as a string instead of a formula. See OWASP "CSV Injection".
    import pandas as pd

    _DANGEROUS_LEAD_CHARS = ("=", "+", "-", "@", "\t", "\r")

    def _csv_safe(value: object) -> object:
        if isinstance(value, str) and value and value[0] in _DANGEROUS_LEAD_CHARS:
            return "'" + value
        return value

    safe_rows = [{k: _csv_safe(v) for k, v in row.items()} for row in enriched]

    base = _os.path.splitext(_os.path.basename(file_path))[0]
    suffix = f"_{industry.lower().replace(' ', '_')}" if industry else ""
    out_name = f"{base}{suffix}_enriched.csv"
    out_path = _os.path.join(".", out_name)

    pd.DataFrame(safe_rows).to_csv(out_path, index=False, encoding="utf-8")
    console.blank()
    console.ok(f"Saved: {out_path}")

    # Cost estimates (from cost_estimator)
    from primr.utils.cost_estimator import estimate_cost

    count = len(enriched)
    scrape_est = estimate_cost("scrape-only", use_historical=False)
    deep_est = estimate_cost("deep-research", use_historical=False)
    full_est = estimate_cost("complete", use_historical=False)
    console.blank()
    console.info("Cost estimates:")
    console.info(
        f"  scrape mode: {count} x ${scrape_est.total_cost:.2f} = ~${count * scrape_est.total_cost:.2f}"
    )
    console.info(
        f"  deep mode:   {count} x ${deep_est.total_cost:.2f} = ~${count * deep_est.total_cost:.2f}"
    )
    console.info(
        f"  full mode:   {count} x ${full_est.total_cost:.2f} = ~${count * full_est.total_cost:.2f}"
    )
    console.blank()
    console.info(f'Next step: primr --batch "{out_path}" --mode scrape')

    return 0


def process_batch(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    platforms: tuple[str, ...] = ("azure",),
    industry: str | None = None,
    limit: int | None = None,
    skip_confirm: bool = True,
) -> int:
    """
    Process a batch file (Excel or CSV) for research.

    Handles smart column detection, optional industry filtering,
    auto website lookup, and sequential research execution.

    Returns:
        Exit code (0 for success)
    """
    from primr.core.research_agent import perform_research
    from primr.data.search_utils import lookup_company_website

    console.banner("Batch Research")
    console.info(f"File: {file_path}")
    console.info(f"Mode: {mode}")
    if industry:
        console.info(f"Industry filter: {industry}")
    console.blank()

    df, col_map = _prepare_batch_df(file_path, industry=industry, limit=limit)

    # Build company list with row context for disambiguation (deduplicate by name)
    companies: list[tuple[str, str | None, dict]] = []
    seen_companies: set[str] = set()
    for _, row in df.iterrows():
        company_name = str(row[col_map.company]).strip()
        if not company_name or company_name.lower() == "nan":
            continue
        if company_name.lower() in seen_companies:
            logger.debug(f"Skipping duplicate company: {company_name}")
            continue
        seen_companies.add(company_name.lower())

        website = None
        if col_map.website and str(row.get(col_map.website, "")).strip().lower() not in ("", "nan"):
            website = str(row[col_map.website]).strip()

        row_context = {
            k: str(row[k]).strip()
            for k in col_map.context
            if str(row.get(k, "")).strip().lower() not in ("", "nan")
        }
        companies.append((company_name, website, row_context))

    if not companies:
        console.error("No companies found in file")
        return 1

    total = len(companies)

    # Show preview
    console.info(f"Companies to research: {total}")
    for i, (name, url, _ctx) in enumerate(companies[:10], 1):
        console.info(f"  {i}. {name} — {url or '(website TBD)'}")
    if total > 10:
        console.info(f"  ... and {total - 10} more")

    # Cost estimate
    mode_costs = {"scrape-only": 0.10, "deep-research": 1.00, "complete": 1.50, "hybrid": 1.50}
    per_cost = mode_costs.get(mode, 1.50)
    console.blank()
    console.info(f"Estimated cost: {total} x ${per_cost:.2f} = ~${total * per_cost:.2f}")

    # Confirmation
    if not skip_confirm:
        console.blank()
        response = input("Proceed? [y/N] ").strip().lower()
        if response not in ("y", "yes"):
            console.info("Cancelled.")
            return 0

    # Defensive thresholds
    max_consecutive_failures = 3
    min_report_size_kb = 5  # Reports under 5KB are suspiciously small
    max_retries_per_company = 2
    retry_wait_minutes = [0, 2, 5]  # Progressive backoff: immediate, 2min, 5min
    billing_wait_minutes = 10  # How long to pause when billing/credits exhausted

    # Check for existing reports (enables resume)
    import glob
    import time as _time
    from datetime import datetime

    from primr.config.config import OUTPUT_DIR

    today_str = datetime.now().strftime("%m-%d-%Y")

    def _find_existing_report(company: str) -> str | None:
        """Check if a report already exists for this company (today)."""
        # Try both raw name and underscore-sanitized name for broader matching
        candidates = {company, company.replace(" ", "_").replace("/", "_")}
        for name in candidates:
            # glob.escape the company-name fragment so glob metacharacters in
            # the name (e.g. brackets in "Acme [Holdings]", "?", "*") are
            # matched literally — without this, resume silently misses the
            # existing report and re-runs the (paid) research.
            pattern = os.path.join(OUTPUT_DIR, f"{glob.escape(name)}*Overview*{today_str}*")
            matches = glob.glob(pattern)
            if matches:
                # Prefer .docx > .md > .txt > anything else
                for ext in (".docx", ".md", ".txt"):
                    for m in matches:
                        if m.endswith(ext):
                            return m
                return matches[0]
        return None

    # Run research sequentially with defensive checks
    console.blank()
    results: list[dict] = []  # {company, status, path, size_kb, error}
    consecutive_failures = 0
    skipped_existing = 0

    for i, (company_name, website, row_ctx) in enumerate(companies, 1):
        # Resume: skip companies that already have reports from today
        existing = _find_existing_report(company_name)
        if existing:
            size_kb = os.path.getsize(existing) / 1024
            console.info(f"[{i}/{total}] {company_name} — already done ({size_kb:.0f}KB), skipping")
            results.append(
                {
                    "company": company_name,
                    "status": "ok",
                    "path": existing,
                    "size_kb": size_kb,
                    "error": None,
                }
            )
            skipped_existing += 1
            continue

        console.step(f"[{i}/{total}] Researching {company_name}...")

        # Look up website if missing
        if not website:
            console.info(f"  Looking up website for {company_name}...")
            website = lookup_company_website(company_name, context=row_ctx)
            if not website:
                console.warn(f"  No website found for {company_name}, skipping")
                results.append(
                    {
                        "company": company_name,
                        "status": "skipped",
                        "path": None,
                        "size_kb": 0,
                        "error": "no website found",
                    }
                )
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    console.error(f"  {max_consecutive_failures} consecutive failures — pausing")
                    resp = input("  Continue? [y/N] ").strip().lower()
                    if resp not in ("y", "yes"):
                        console.info("  Batch stopped by user.")
                        break
                    consecutive_failures = 0
                continue

        # Research with retry and progressive backoff
        results_len_before = len(results)
        for attempt in range(max_retries_per_company + 1):
            # Progressive backoff: wait before retries (not before first attempt)
            wait_min = retry_wait_minutes[attempt] if attempt < len(retry_wait_minutes) else 5
            if attempt > 0 and wait_min > 0:
                console.warn(
                    f"  Retrying in {wait_min}min "
                    f"(attempt {attempt + 1}/{max_retries_per_company + 1})..."
                )
                _time.sleep(wait_min * 60)

            try:
                result_path = perform_research(
                    company_name,
                    _ensure_valid_url(website),
                    mode=mode,
                    citation_style=citation_style,
                    ai_strategy=ai_strategy,
                    platforms=platforms,
                )

                if result_path:
                    size_kb = (
                        os.path.getsize(result_path) / 1024 if os.path.exists(result_path) else 0
                    )
                    if size_kb < min_report_size_kb:
                        console.warn(f"  Report is only {size_kb:.1f}KB — may be incomplete")
                        results.append(
                            {
                                "company": company_name,
                                "status": "warning",
                                "path": result_path,
                                "size_kb": size_kb,
                                "error": "small report",
                            }
                        )
                    else:
                        console.ok(f"  Done — {size_kb:.0f}KB")
                        results.append(
                            {
                                "company": company_name,
                                "status": "ok",
                                "path": result_path,
                                "size_kb": size_kb,
                                "error": None,
                            }
                        )
                    consecutive_failures = 0
                    break
                else:
                    # No report returned — not transient, don't retry
                    console.error(f"  No report generated for {company_name}")
                    results.append(
                        {
                            "company": company_name,
                            "status": "failed",
                            "path": None,
                            "size_kb": 0,
                            "error": "no report returned",
                        }
                    )
                    consecutive_failures += 1
                    break

            except Exception as e:
                error_str = str(e).lower()

                # Billing exhaustion — pause immediately, don't burn retries
                is_billing = any(
                    s in error_str
                    for s in (
                        "credits exhausted",
                        "spending limit",
                        "available credits",
                        "insufficient credits",
                    )
                )
                if is_billing:
                    console.error("  xAI credits exhausted — add credits at https://console.x.ai/")
                    if skip_confirm:
                        console.info(f"  Pausing {billing_wait_minutes}min then retrying...")
                        _time.sleep(billing_wait_minutes * 60)
                        continue  # Retry same company
                    console.info(f"  [w] Wait {billing_wait_minutes} minutes and retry")
                    console.info("  [s] Stop batch (re-run to resume)")
                    resp = input("  Choice [w/s]: ").strip().lower()
                    if resp == "w":
                        console.info(f"  Waiting {billing_wait_minutes}min...")
                        _time.sleep(billing_wait_minutes * 60)
                        continue  # Retry same company
                    else:
                        console.info("  Batch stopped. Re-run the same command to resume.")
                        results.append(
                            {
                                "company": company_name,
                                "status": "failed",
                                "path": None,
                                "size_kb": 0,
                                "error": "billing exhausted — stopped by user",
                            }
                        )
                        break

                is_quota = any(
                    s in error_str for s in ("quota", "rate", "429", "resource_exhausted")
                )

                if is_quota and attempt < max_retries_per_company:
                    continue  # Will wait at top of next iteration

                console.error(f"  Failed: {company_name} — {e}")
                results.append(
                    {
                        "company": company_name,
                        "status": "failed",
                        "path": None,
                        "size_kb": 0,
                        "error": str(e)[:80],
                    }
                )
                consecutive_failures += 1
                break

        # If the retry loop exited without recording any terminal result for
        # this company — e.g. skip_confirm billing exhaustion kept `continue`-ing
        # until the bounded attempts ran out — record a failure. Otherwise the
        # company is silently dropped and the batch summary can report success
        # (failed_count == 0) despite producing no report for it.
        if len(results) == results_len_before:
            console.error(
                f"  {company_name}: exhausted retries without completing — recording failure"
            )
            results.append(
                {
                    "company": company_name,
                    "status": "failed",
                    "path": None,
                    "size_kb": 0,
                    "error": "exhausted retries (billing/quota not recovered)",
                }
            )
            consecutive_failures += 1

        # Billing stop — the inner loop broke because user chose to stop
        last_result = results[-1] if results else None
        if last_result and last_result.get("error") == "billing exhausted — stopped by user":
            break

        # Consecutive failure handling — likely quota exhaustion
        if consecutive_failures >= max_consecutive_failures:
            console.error(
                f"\n  {max_consecutive_failures} consecutive failures — possible API quota exhaustion."
            )
            if skip_confirm:
                console.info(f"  Auto-waiting {billing_wait_minutes}min before continuing...")
                _time.sleep(billing_wait_minutes * 60)
                consecutive_failures = 0
            else:
                console.info(f"  [w] Wait {billing_wait_minutes} minutes and continue")
                console.info("  [s] Stop batch and show summary")
                resp = input("  Choice [w/s]: ").strip().lower()
                if resp == "w":
                    console.info(f"  Waiting {billing_wait_minutes}min for quota recovery...")
                    _time.sleep(billing_wait_minutes * 60)
                    consecutive_failures = 0
                else:
                    console.info("  Batch stopped by user.")
                    console.info("  Re-run the same command to retry failed companies.")
                    break

        # Check overall error rate (after at least 3 new attempts). Count all
        # failures rather than slicing results[skipped_existing:] — resumed and
        # freshly-processed companies interleave in company order, so the slice
        # miscounted. Resumed entries are always status "ok", so every "failed"
        # entry is a new attempt.
        new_attempted = len(results) - skipped_existing
        new_failed = sum(1 for r in results if r["status"] == "failed")
        if new_attempted >= 3 and new_failed > new_attempted / 2:
            console.warn(f"  High failure rate: {new_failed}/{new_attempted} failed so far")

        # Cooldown between companies after any completed attempt (ok or warning)
        # Scale cooldown by mode: scrape is lighter on APIs than deep/full
        completed = any(
            r["company"] == company_name and r["status"] in ("ok", "warning") for r in results
        )
        if completed and i < total:
            cooldown = 10 if mode == "scrape-only" else 60
            remaining = total - i
            console.info(
                f"  Cooling down {cooldown}s before next company ({remaining} remaining)..."
            )
            _time.sleep(cooldown)

    # Summary
    succeeded = sum(1 for r in results if r["status"] == "ok")
    warnings_count = sum(1 for r in results if r["status"] == "warning")
    failed_count = sum(1 for r in results if r["status"] in ("failed", "skipped"))

    console.blank()
    console.banner("Batch Summary")
    if skipped_existing:
        console.info(f"  ({skipped_existing} already completed, resumed from where we left off)")
        console.blank()
    console.info(f"  {'#':>3}  {'Company':<35} {'Status':<10} {'Size':>8}  Notes")
    console.info(f"  {'---':>3}  {'-' * 35} {'-' * 10} {'-' * 8}  {'-' * 20}")
    for i, r in enumerate(results, 1):
        status_icon = {"ok": "ok", "warning": "!!", "failed": "FAIL", "skipped": "SKIP"}[
            r["status"]
        ]
        size_str = f"{r['size_kb']:.0f}KB" if r["size_kb"] else "-"
        note = r["error"] or ""
        c = r["company"][:33] + ".." if len(r["company"]) > 35 else r["company"]
        console.info(f"  {i:>3}  {c:<35} {status_icon:<10} {size_str:>8}  {note}")

    console.blank()
    if failed_count == 0:
        console.success_box(f"All {succeeded} reports generated", "Batch complete")
    else:
        console.success_box(
            f"Batch complete: {succeeded} ok, {warnings_count} warnings, {failed_count} failed",
            f"{succeeded + warnings_count}/{len(results)} usable reports",
        )
    if failed_count > 0:
        console.info("Re-run the same command to retry failed companies.")

    return 0 if failed_count == 0 else 1


def process_csv(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    platforms: tuple[str, ...] = ("azure",),
) -> None:
    """Process a CSV file for batch research."""
    import csv

    from primr.core.research_agent import perform_research

    console.header("Batch Processing", file_path)
    console.info(f"Mode: {mode}")

    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = row.get("company_name", "").strip()
            website = row.get("website", "").strip()
            if company or website:
                try:
                    perform_research(
                        company,
                        _ensure_valid_url(website) if website else None,
                        mode=mode,
                        citation_style=citation_style,
                        ai_strategy=ai_strategy,
                        platforms=platforms,
                    )
                except Exception as e:
                    console.error(f"Failed: {company or website} - {e}")


def open_file(filepath: str) -> None:
    """Open a file with the system default application."""
    from primr.utils.files import open_with_default_app

    try:
        open_with_default_app(filepath)
    except Exception as e:
        console.warn(f"Could not open file: {e}")
