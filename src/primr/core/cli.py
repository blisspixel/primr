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
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from primr.config.config import LOGS_DIR, OUTPUT_DIR, WORKING_DIR
from primr.config.models import PrimrModels
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("cli")


# =============================================================================
# ENUMS
# =============================================================================

class Command(Enum):
    """CLI commands."""
    RESEARCH = "research"
    DOCTOR = "doctor"
    LIST_RECENT = "list-recent"
    CLEAN_TEMP = "clean-temp"
    CHECK_QUOTA = "check-quota"
    CHECK_JOBS = "check-jobs"
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
    # Agentic architecture commands
    MEMORY = "memory"
    ORCHESTRATE = "orchestrate"
    ROADMAP = "roadmap"


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
    cloud_vendors: tuple[str, ...] = ("azure",)
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
    lite_strategy: bool = False  # Use Pro model instead of Deep Research for strategy
    fast_mode: bool = False  # Use Grok 4.1 for fast research (~10 min, ~$0.30)
    # Agentic architecture options
    memory_company: str | None = None
    memory_list: bool = False
    orchestrate_max_cost: float | None = None
    roadmap_version: str | None = None

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
    if getattr(parsed, 'no_ai_strategy', False):
        ai_strategy = False
    elif mode in ("scrape-only",):
        ai_strategy = False  # Scrape mode doesn't need AI strategy
    else:
        ai_strategy = True

    # Build context files tuple
    context_files = tuple(getattr(parsed, 'context', None) or [])

    # Batch commands default to requiring confirmation; everything else skips it.
    # --skip-confirm explicitly skips confirmation for any command.
    is_batch = bool(getattr(parsed, 'batch', None) or parsed.csv)
    skip_confirm_flag = getattr(parsed, 'skip_confirm', False)
    skip_confirm = skip_confirm_flag if is_batch else True

    return CLIConfig(
        command=command,
        company_name=parsed.company,
        website=parsed.website,
        mode=mode,
        citation_style=getattr(parsed, 'citation_style', 'numbered'),
        ai_strategy=ai_strategy,
        cloud_vendors=tuple(dict.fromkeys(getattr(parsed, 'cloud_vendor', ['azure']))),
        skip_confirm=skip_confirm,
        context_files=context_files,
        context_folder=getattr(parsed, 'context_folder', None),
        refresh_vendor_research=getattr(parsed, 'refresh_vendor_research', False),
        generate_vendor=getattr(parsed, 'generate_vendor_research', None),
        csv_file=parsed.csv,
        batch_file=getattr(parsed, 'batch', None),
        industry=getattr(parsed, 'industry', None),
        limit=getattr(parsed, 'limit', None),
        enrich=getattr(parsed, 'enrich', False),
        output_dir=getattr(parsed, 'output_dir', None),
        open_after=getattr(parsed, 'open', False),
        quiet=parsed.quiet,
        verbose=parsed.verbose,
        test_accordion_topic=getattr(parsed, 'test_accordion', None),
        test_accordion_pages=getattr(parsed, 'accordion_pages', 50),
        analyze_report_path=getattr(parsed, 'analyze_report', None),
        qa_company=getattr(parsed, 'qa', None),
        qa_recent_count=getattr(parsed, 'qa_recent', None),
        max_scrape_time=getattr(parsed, 'max_scrape_time', None),
        ai_strategy_only_path=getattr(parsed, 'ai_strategy_only', None),
        discovery_notes_path=getattr(parsed, 'discovery_notes', None),
        strategy_type=getattr(parsed, 'strategy_type', 'ai'),
        lite_strategy=getattr(parsed, 'lite_strategy', False),
        fast_mode=getattr(parsed, 'fast_mode', False),
        # Agentic architecture options
        memory_company=getattr(parsed, 'memory', None),
        memory_list=getattr(parsed, 'memory_list', False),
        orchestrate_max_cost=getattr(parsed, 'max_cost', None),
        roadmap_version=getattr(parsed, 'roadmap_version', None),
    )


def main(args: list[str] | None = None) -> int:
    """
    Main CLI entry point.

    Args:
        args: Optional list of arguments (for testing)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    from pathlib import Path

    from primr.utils.config_validation import validate_config
    from primr.utils.logging_config import setup_logging

    config = parse_args(args)

    # Validate configuration early (skip API key check for utility commands)
    utility_commands = {
        Command.DOCTOR, Command.LIST_RECENT, Command.CLEAN_TEMP,
        Command.CHECK_JOBS, Command.CLEAR_JOBS, Command.LIST_STRATEGIES,
        Command.SHOW_USAGE, Command.ENRICH,
    }
    include_api_keys = config.command not in utility_commands

    validation_result = validate_config(include_api_keys=include_api_keys)
    if not validation_result.valid:
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

    # Dispatch to appropriate handler
    handlers = {
        Command.DOCTOR: _handle_doctor,
        Command.LIST_RECENT: _handle_list_recent,
        Command.CLEAN_TEMP: _handle_clean_temp,
        Command.CHECK_QUOTA: _handle_check_quota,
        Command.CHECK_JOBS: _handle_check_jobs,
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
        Command.RESEARCH: _handle_research,
        # Agentic architecture handlers
        Command.MEMORY: _handle_memory,
        Command.ORCHESTRATE: _handle_orchestrate,
        Command.ROADMAP: _handle_roadmap,
    }

    handler = handlers.get(config.command, _handle_research)
    return handler(config)


def run_doctor() -> int:
    """
    Run system diagnostics.

    Returns:
        Exit code (0 if all checks pass, 1 otherwise)
    """

    console.banner("Primr Doctor")
    console.blank()

    all_passed = True
    warnings_count = 0

    # 1. Python version
    console.step("Environment")
    py_version = sys.version_info
    if py_version >= (3, 10):
        console.ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        console.error(f"Python {py_version.major}.{py_version.minor} (need 3.10+)")
        all_passed = False

    # 2. API Keys
    console.step("API Configuration")
    all_passed, warnings_count = _check_api_keys(all_passed, warnings_count)

    # 3. Dependencies
    console.step("Dependencies")
    warnings_count = _check_dependencies(warnings_count)

    # 4. File System
    console.step("File System")
    all_passed, warnings_count = _check_filesystem(all_passed, warnings_count)

    # 5. API Connectivity
    console.step("API Connectivity")
    all_passed, warnings_count = _check_api_connectivity(all_passed, warnings_count)

    # 6. Gemini Resource Cleanup Check
    console.step("Gemini Resources")
    all_passed, warnings_count = _check_gemini_resources(all_passed, warnings_count)

    # Summary
    console.blank()
    if all_passed and warnings_count == 0:
        console.success_box("All checks passed", "Primr is ready to use")
    elif all_passed:
        console.success_box(f"Ready with {warnings_count} warning(s)", "Primr can run, but some features may be limited")
    else:
        console.error("Some checks failed - fix issues above before running research")

    return 0 if all_passed else 1


# =============================================================================
# INTERNAL FUNCTIONS - Parser
# =============================================================================

def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="primr",
        description="Primr - AI-powered company research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Research Modes:
  full     Two-step pipeline: scrape then deep research (~30-40 min) [DEFAULT]
  scrape   Scrape website + extract insights only (~2-5 min)
  deep     Autonomous AI web research, 8 sections (~10-15 min)
  parallel Both engines in parallel (legacy, ~25 min)

Examples:
  primr "Acme Corp" https://acme.example
  primr "Acme Corp" acme.example --mode deep
  primr "Acme Corp" acme.example --mode scrape       # Build Site Corpus + Extract Insights
  primr doctor                                       # System diagnostics
  primr --qa "Acme Corp"                             # Show detailed QA analysis
  primr --qa-recent 5                                # Show QA summary for recent reports

AI Strategy Retry (when main report succeeded but AI strategy failed):
  primr --ai-strategy-only "output/Company_Strategic_Overview_01-09-2026.md"
  primr --ai-strategy-only "output/report.md" --cloud-vendor aws

Agentic Architecture (v1.7.0):
  primr memory "Acme Corp"                           # View hypotheses for a company
  primr --memory-list                                # List all companies with memory
  primr orchestrate "Acme Corp" https://acme.com    # Run orchestrated research
  primr --orchestrate --max-cost 5.0                 # With cost budget
  primr roadmap                                      # Show roadmap overview
  primr --roadmap-version v1.7.0                     # Show version details

Accordion Method Test (for development):
  primr --test-accordion "Oceanography 2026-2030"
  primr --test-accordion "Topic" --accordion-pages 30
"""
    )

    # Positional arguments
    parser.add_argument("company", nargs="?", type=str, help="Company name")
    parser.add_argument("website", nargs="?", type=str, help="Company website URL")

    # Batch mode
    parser.add_argument("--csv", type=str, help="CSV file for batch processing")
    parser.add_argument(
        "--batch",
        type=str,
        metavar="FILE",
        help="Excel (.xlsx) or CSV file for batch research"
    )
    parser.add_argument(
        "--industry",
        type=str,
        help="Filter batch rows by industry column value"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Max number of companies to process in batch"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich mode: look up websites, save CSV, don't run research"
    )
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="Skip confirmation prompt for batch research"
    )

    # Research options
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["scrape", "deep", "full", "parallel", "structured", "deep-research", "complete", "hybrid"],
        default="full",
        help="Research mode: scrape (corpus + insights), deep, full (default)"
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed output")
    parser.add_argument(
        "--citation-style",
        type=str,
        choices=["numbered", "inline", "sidecar"],
        default="numbered",
        help="Citation style (default: numbered)"
    )
    parser.add_argument("--ai-strategy", action="store_true", default=True, help="Generate AI recommendations")
    parser.add_argument("--no-ai-strategy", action="store_true", help="Disable AI strategy")
    parser.add_argument("--no-qa", action="store_true", help="Disable automatic quality assessment")
    parser.add_argument(
        "--cloud-vendor",
        type=str,
        nargs="+",
        choices=["azure", "aws", "gcp", "agnostic"],
        default=["azure"],
        help="Cloud vendor(s) for AI recommendations (can specify multiple)"
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        dest="lite_strategy",
        help="Use Pro model instead of Deep Research for AI strategy (faster, cheaper, less depth)"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        dest="fast_mode",
        help="Fast mode: Grok 4.1 one-shot report (~10 min, ~$0.30). Requires XAI_API_KEY"
    )
    parser.add_argument(
        "--discovery-notes",
        type=str,
        help="Path to discovery notes file (freeform meeting insights)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show cost estimate only")
    parser.add_argument("--show-usage", action="store_true", help="Display usage statistics")
    parser.add_argument("--context", type=str, nargs="+", help="Context files for deep mode")
    parser.add_argument("--context-folder", type=str, help="Use working folder as context")
    parser.add_argument("--open", action="store_true", help="Open report after generation")
    parser.add_argument("--output-dir", type=str, help="Custom output directory")
    parser.add_argument("--list-recent", action="store_true", help="List recent outputs")
    parser.add_argument("--clean-temp", action="store_true", help="Clean temporary files")
    parser.add_argument("--refresh-vendor-research", action="store_true", help="Force refresh vendor research")
    parser.add_argument("--generate-vendor-research", type=str, choices=["azure", "aws", "gcp", "agnostic", "all"])
    parser.add_argument("--check-jobs", action="store_true", help="Check pending research jobs")
    parser.add_argument("--clear-jobs", action="store_true", help="Clear stale pending jobs")
    parser.add_argument("--list-strategies", action="store_true", help="List available strategy documents")
    parser.add_argument("--check-quota", action="store_true", help="Check API quota")
    parser.add_argument(
        "--max-scrape-time",
        type=int,
        default=None,
        help="Max minutes for scraping phase (default: 10, env: PRIMR_MAX_SCRAPE_TIME)"
    )

    # Accordion Method test
    parser.add_argument(
        "--test-accordion",
        type=str,
        metavar="TOPIC",
        help="Test Accordion Method with a standalone topic (e.g., 'Oceanography 2026-2030')"
    )
    parser.add_argument(
        "--accordion-pages",
        type=int,
        default=50,
        help="Target pages for Accordion test (default: 50)"
    )

    # Report analysis
    parser.add_argument(
        "--analyze-report",
        type=str,
        metavar="PATH",
        help="Analyze quality of an existing report file"
    )

    # QA review
    parser.add_argument(
        "--qa",
        type=str,
        metavar="COMPANY_OR_PATH",
        help="Show detailed QA analysis for a company report or analyze a specific file path"
    )
    parser.add_argument(
        "--qa-recent",
        type=int,
        nargs='?',
        const=5,
        metavar="N",
        help="Show QA summary for N most recent reports (default: 5)"
    )

    # AI Strategy retry/resume
    parser.add_argument(
        "--ai-strategy-only",
        type=str,
        metavar="REPORT_PATH",
        help="Generate AI strategy using an existing report as context (retry failed AI strategy)"
    )

    # Strategy type selection
    parser.add_argument(
        "--strategy-type",
        type=str,
        choices=["ai", "customer_experience", "modern_security_compliance", "data_fabric_strategy"],
        default="ai",
        help="Strategy document type: 'ai' (AI transformation), 'customer_experience' (CX strategy), 'modern_security_compliance' (security/compliance), 'data_fabric_strategy' (data platform). Use with --ai-strategy-only."
    )

    # Agentic architecture commands
    parser.add_argument(
        "--memory",
        type=str,
        metavar="COMPANY",
        help="View research memory (hypotheses) for a company"
    )
    parser.add_argument(
        "--memory-list",
        action="store_true",
        help="List all companies with research memory"
    )
    parser.add_argument(
        "--orchestrate",
        action="store_true",
        help="Run orchestrated research with subagent coordination (experimental)"
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        help="Maximum cost budget for orchestrated research (USD)"
    )
    parser.add_argument(
        "--roadmap",
        action="store_true",
        help="Show roadmap information"
    )
    parser.add_argument(
        "--roadmap-version",
        type=str,
        metavar="VERSION",
        help="Show details for a specific roadmap version (e.g., 'v1.7.0')"
    )

    return parser


_POSITIONAL_COMMANDS: dict[str, Command] = {
    "doctor": Command.DOCTOR,
    "memory": Command.MEMORY,
    "orchestrate": Command.ORCHESTRATE,
    "roadmap": Command.ROADMAP,
}

# (attr_name, command) — checked with getattr(args, attr, None) for truthiness
_FLAG_COMMANDS: list[tuple[str, Command]] = [
    ("memory", Command.MEMORY),
    ("memory_list", Command.MEMORY),
    ("orchestrate", Command.ORCHESTRATE),
    ("roadmap", Command.ROADMAP),
    ("roadmap_version", Command.ROADMAP),
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
    ("clear_jobs", Command.CLEAR_JOBS),
    ("list_strategies", Command.LIST_STRATEGIES),
    ("dry_run", Command.DRY_RUN),
    ("generate_vendor_research", Command.GENERATE_VENDOR),
]


def _determine_command(args: argparse.Namespace) -> Command:
    """Determine which command to run based on parsed args."""
    # Check for positional command words (e.g. "primr doctor")
    if args.company:
        cmd = _POSITIONAL_COMMANDS.get(args.company.lower())
        if cmd is not None:
            return cmd

    # Check flag-based commands
    for attr, cmd in _FLAG_COMMANDS:
        if getattr(args, attr, None):
            return cmd

    # qa_recent uses `is not None` (0 is a valid value)
    if getattr(args, 'qa_recent', None) is not None:
        return Command.QA_RECENT

    if getattr(args, 'enrich', False) and getattr(args, 'batch', None):
        return Command.ENRICH

    if getattr(args, 'batch', None):
        return Command.BATCH

    if args.csv:
        return Command.BATCH

    return Command.RESEARCH


# =============================================================================
# INTERNAL FUNCTIONS - Command Handlers
# =============================================================================

def _handle_doctor(config: CLIConfig) -> int:
    """Handle doctor command."""
    return run_doctor()


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
    with open(jobs_file, 'w', encoding='utf-8') as f:
        json.dump({}, f)

    console.ok(f"Cleared {len(jobs)} pending jobs")
    return 0


def _handle_show_usage(config: CLIConfig) -> int:
    """Handle show-usage command."""
    from primr.utils.usage_tracker import get_usage_tracker
    tracker = get_usage_tracker()
    print(tracker.display_usage_history())
    return 0


def _handle_dry_run(config: CLIConfig) -> int:
    """Handle dry-run command."""
    from primr.utils.cost_estimator import estimate_cost

    mode_label = "fast (Grok 4.1)" if config.fast_mode else config.mode
    print("")
    print("=" * 60)
    print(f"COST ESTIMATE: {mode_label} mode")
    if config.ai_strategy and not config.fast_mode:
        strategy_label = "AI Strategy (Pro mode)" if config.lite_strategy else "AI Strategy analysis"
        print(f"(includes {strategy_label})")
    elif config.fast_mode and config.ai_strategy:
        print("(includes AI Strategy via Grok)")
    print("=" * 60)
    print("")

    estimate = estimate_cost(
        config.mode,
        config.ai_strategy,
        num_vendors=len(config.cloud_vendors),
        lite_strategy=config.lite_strategy,
        fast_mode=config.fast_mode,
    )
    print(str(estimate))

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
        console.info("Usage: primr --batch \"file.xlsx\" --enrich")
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
            cloud_vendors=config.cloud_vendors,
            industry=config.industry,
            limit=config.limit,
            skip_confirm=config.skip_confirm,
        )

    # Legacy --csv path
    if not config.csv_file:
        console.error("No file specified")
        console.info("Usage: primr --batch \"file.xlsx\" --mode scrape")
        return 1

    process_csv(
        config.csv_file,
        mode=config.mode,
        citation_style=config.citation_style,
        ai_strategy=config.ai_strategy,
        cloud_vendors=config.cloud_vendors
    )
    return 0


def _handle_test_accordion(config: CLIConfig) -> int:
    """Handle test-accordion command."""
    from primr.ai.accordion_test import run_accordion_test

    if not config.test_accordion_topic:
        console.error("No topic specified for Accordion test")
        console.info("Usage: primr --test-accordion \"Oceanography 2026-2030\"")
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
            f"Test completed: {result.page_estimate:.1f} pages",
            f"Output: {result.output_path}"
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
        from report_analyzer import ReportAnalyzer  # type: ignore[import-not-found]
        analyzer = ReportAnalyzer(config.analyze_report_path)
        report = analyzer.generate_report()
        print(report)
        return 0
    except Exception as e:
        console.error(f"Analysis failed: {e}")
        return 1


def _handle_qa(config: CLIConfig) -> int:
    """Handle QA review command."""
    if not config.qa_company:
        console.error("Company name or file path is required for QA review")
        console.info("Usage: primr --qa \"Company Name\"")
        console.info("   or: primr --qa \"path/to/report.docx\"")
        return 1

    try:
        from pathlib import Path

        from primr.qa.command import QACommand

        qa_command = QACommand()
        potential_path = Path(config.qa_company)

        if potential_path.exists() and potential_path.is_file():
            return qa_command.analyze_report_file(config.qa_company)
        elif (config.qa_company.endswith(('.docx', '.pdf')) or
              '\\' in config.qa_company or
              '/' in config.qa_company):
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
        console.info("Usage: primr --ai-strategy-only \"path/to/report.md\" --strategy-type customer_experience")
        return 1

    # Validate file exists
    path = Path(report_path)
    if not path.exists():
        console.error(f"Report file not found: {report_path}")
        return 1

    # Get strategy type (default to 'ai' if not specified)
    strategy_type = getattr(config, 'strategy_type', 'ai')

    # Map strategy types to display names
    strategy_names = {
        "ai": "AI Strategy",
        "customer_experience": "Customer Experience Strategy",
        "modern_security_compliance": "Security & Compliance Strategy",
        "data_fabric_strategy": "Data Fabric Strategy"
    }
    strategy_display = strategy_names.get(strategy_type, strategy_type)

    # Extract company name from filename or content
    # Filename pattern: "Company Name_Strategic_Overview_MM-DD-YYYY.md"
    company_name = config.company_name
    if not company_name:
        filename = path.stem
        # Try to extract from filename pattern
        match = re.match(r'^(.+?)_(?:Strategic_Overview|AI_Strategy|Customer_Experience|Security|Data_Fabric)', filename)
        if match:
            company_name = match.group(1).replace('_', ' ')
        else:
            # Fallback: use filename without extension
            company_name = filename.replace('_', ' ')

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

    for vendor in vendors:
        result_path = _generate_strategy_section(
            strategy_name=strategy_type,
            company_name=company_name,
            cloud_vendor=vendor,
            company_research_path=str(path),
            force_refresh_vendor=config.refresh_vendor_research,
            discovery_notes_content=None,  # TODO: Add discovery notes support
            lite_strategy=config.lite_strategy,
        )

        if result_path:
            vendor_label = f" ({vendor.upper()})" if strategy_type == "ai" and len(vendors) > 1 else ""
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
            console.info("Usage: primr memory \"Company Name\"")
            console.info("   or: primr --memory \"Company Name\"")
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
        console.info("Usage: primr orchestrate \"Company Name\" https://company.com")
        console.info("   or: primr \"Company Name\" https://company.com --orchestrate")
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
        result = asyncio.run(orchestrator.research(
            company_name=company_name,
            company_url=website,
            mode="full",
        ))

        console.blank()

        if result.is_success:
            console.success_box(
                "Research completed",
                f"Duration: {result.duration_seconds:.1f}s"
            )
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
        errors.append("GEMINI_API_KEY not configured. Get your key at: https://ai.google.dev/")

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
            client = genai.Client(api_key=gemini_key)
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
            errors.append("SEARCH_API_KEY not configured. Get your key at: https://console.cloud.google.com/apis/credentials")
        elif not search_engine_id or len(search_engine_id) < 10:
            errors.append("SEARCH_ENGINE_ID not configured or invalid. Get it at: https://programmablesearchengine.google.com/controlpanel/all")
        else:
            # Actually test the Search API with a simple query
            try:
                import requests
                test_url = "https://www.googleapis.com/customsearch/v1"
                params: dict[str, str | int] = {
                    "q": "test",
                    "key": search_key,
                    "cx": search_engine_id,
                    "num": 1
                }
                search_response = requests.get(test_url, params=params, timeout=10)
                if search_response.status_code == 400:
                    error_detail = search_response.json().get("error", {}).get("message", "Bad Request")
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
        console.info("Usage: primr \"Company Name\" https://company.com")
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

    # Fast mode preflight: verify XAI_API_KEY and openai package
    if config.fast_mode:
        if not os.environ.get("XAI_API_KEY"):
            console.error("--fast requires XAI_API_KEY in your .env or environment")
            console.info("Get a key at https://console.x.ai/")
            return 1
        try:
            import openai  # noqa: F401
        except ImportError:
            console.error("--fast requires the 'openai' package")
            console.info("Install with: pip install 'primr[fast]' or pip install openai")
            return 1

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

    # Run research
    result_path = perform_research(
        company_name,
        website,
        mode=config.mode,
        citation_style=config.citation_style,
        ai_strategy=config.ai_strategy,
        cloud_vendors=config.cloud_vendors,
        skip_confirm=config.skip_confirm,
        context_files=context_files if context_files else None,
        refresh_vendor_research=config.refresh_vendor_research,
        max_scrape_time=config.max_scrape_time,
        discovery_notes_path=config.discovery_notes_path,
        lite_strategy=config.lite_strategy,
        fast_mode=config.fast_mode,
    )

    # Open report if requested
    if config.open_after and result_path:
        open_file(result_path)

    return 0 if result_path else 1


# =============================================================================
# INTERNAL FUNCTIONS - Doctor Checks
# =============================================================================

def _check_api_keys(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check API key configuration and actually test connectivity."""
    import requests

    # Check Gemini API key
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key and len(gemini_key) >= 10:
        if gemini_key.startswith("AI"):
            console.ok("GEMINI_API_KEY configured (valid format)")
        else:
            console.ok("GEMINI_API_KEY configured")
            console.warn("  Key format unusual (expected to start with 'AI')")
            warnings_count += 1
    else:
        console.error("GEMINI_API_KEY not set or invalid")
        console.info("  Get your key at: https://ai.google.dev/")
        all_passed = False

    # Check search provider
    search_provider = os.environ.get("SEARCH_PROVIDER", "auto").lower().strip()
    search_key = os.environ.get("SEARCH_API_KEY", "")
    search_engine_id = os.environ.get("SEARCH_ENGINE_ID", "")

    if search_provider == "google":
        # Google Custom Search mode - require keys and test API
        if not search_key or len(search_key) < 10:
            console.error("SEARCH_API_KEY not set or invalid (required for SEARCH_PROVIDER=google)")
            console.info("  Get your key at: https://console.cloud.google.com/apis/credentials")
            all_passed = False
        elif not search_engine_id or len(search_engine_id) < 10:
            console.error("SEARCH_ENGINE_ID not set or invalid (required for SEARCH_PROVIDER=google)")
            console.info("  Get it at: https://programmablesearchengine.google.com/controlpanel/all")
            all_passed = False
        else:
            try:
                test_url = "https://www.googleapis.com/customsearch/v1"
                params: dict[str, str | int] = {
                    "q": "test",
                    "key": search_key,
                    "cx": search_engine_id,
                    "num": 1
                }
                response = requests.get(test_url, params=params, timeout=10)
                if response.status_code == 200:
                    console.ok("Google Search API working")
                elif response.status_code == 400:
                    error_detail = response.json().get("error", {}).get("message", "Bad Request")
                    console.error(f"Google Search API config invalid: {error_detail}")
                    console.info("  Check SEARCH_ENGINE_ID at: https://programmablesearchengine.google.com/controlpanel/all")
                    all_passed = False
                elif response.status_code == 403:
                    console.error("Google Search API key invalid or quota exceeded")
                    all_passed = False
                else:
                    console.error(f"Google Search API error: HTTP {response.status_code}")
                    all_passed = False
            except requests.exceptions.Timeout:
                console.error("Google Search API timeout")
                all_passed = False
            except Exception as e:
                console.error(f"Google Search API check failed: {e}")
                all_passed = False
    else:
        # DuckDuckGo mode (default) - test connectivity
        try:
            from ddgs import DDGS
            results = DDGS().text("test", max_results=1)
            if results:
                console.ok("DuckDuckGo search working (no API key needed)")
            else:
                console.warn("DuckDuckGo returned no results for test query")
                warnings_count += 1
        except Exception as e:
            console.error(f"DuckDuckGo search check failed: {e}")
            all_passed = False

    # Check xAI API key (optional — for --fast mode)
    xai_key = os.environ.get("XAI_API_KEY", "")
    if xai_key and len(xai_key) >= 10:
        console.ok("XAI_API_KEY configured (enables --fast mode)")
    else:
        console.info("XAI_API_KEY not set (optional — needed for --fast mode)")

    return all_passed, warnings_count


def _check_dependencies(warnings_count: int) -> int:
    """Check required dependencies."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright():
            console.ok("Playwright browsers available")
    except Exception as e:
        console.warn(f"Playwright not ready: {e}")
        console.info("  Run: playwright install chromium")
        warnings_count += 1
    return warnings_count


def _check_filesystem(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check filesystem access."""
    # Output directory
    try:
        test_file = os.path.join(OUTPUT_DIR, ".primr_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        console.ok("Output directory writable")
    except Exception as e:
        console.error(f"Cannot write to output directory: {e}")
        all_passed = False

    # Working directory
    try:
        os.makedirs(WORKING_DIR, exist_ok=True)
        test_file = os.path.join(WORKING_DIR, ".primr_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        console.ok("Working directory writable")
    except Exception as e:
        console.error(f"Cannot write to working directory: {e}")
        all_passed = False

    # Cache directory
    try:
        cache_path = os.path.join(LOGS_DIR, "cache.db")
        if os.path.exists(cache_path):
            cache_size = os.path.getsize(cache_path) / (1024 * 1024)
            console.ok(f"Cache accessible ({cache_size:.1f} MB)")
        else:
            console.ok("Cache directory ready")
    except Exception as e:
        console.warn(f"Cache check failed: {e}")
        warnings_count += 1

    return all_passed, warnings_count


def _check_api_connectivity(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check API connectivity."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=PrimrModels.FAST_MODEL,
                contents="Reply with exactly: hello",
            )
            # Check if we got any response at all (connection works)
            if response and (response.text or response.candidates):
                console.ok("Gemini API responding")
            else:
                # Still connected, just empty - not a failure
                console.ok("Gemini API connected")
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str:
                console.error("Gemini API quota exceeded - wait and retry")
                all_passed = False
            elif "invalid" in error_str and "key" in error_str:
                console.error("Gemini API key is invalid")
                all_passed = False
            else:
                console.warn(f"Gemini API test failed: {e}")
                warnings_count += 1
    else:
        console.warn("Skipping API test (no key configured)")
        warnings_count += 1

    return all_passed, warnings_count


def _check_gemini_resources(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check for orphaned Gemini resources that could be incurring costs.

    Checks for:
    - Explicit context caches ($1-4.50/M tokens/hour storage)
    - File search stores (persist until manually deleted)
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        console.warn("Skipping Gemini resource check (no API key)")
        warnings_count += 1
        return all_passed, warnings_count

    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)

        # Check for explicit caches
        try:
            caches = list(client.caches.list())
            if caches:
                console.warn(f"Found {len(caches)} orphaned cache(s) - costing money!")
                console.info("  Run: python scripts/check_gemini_resources.py --delete-caches")
                warnings_count += 1
            else:
                console.ok("No orphaned caches")
        except Exception as e:
            # Don't fail the whole check if cache listing fails
            logger.debug(f"Could not list caches: {e}")

        # Check for file search stores
        try:
            stores = list(client.file_search_stores.list())
            if stores:
                console.warn(f"Found {len(stores)} orphaned file search store(s)")
                console.info("  Run: python scripts/check_gemini_resources.py --delete-stores --force-empty")
                warnings_count += 1
            else:
                console.ok("No orphaned file search stores")
        except Exception as e:
            # Don't fail the whole check if store listing fails
            logger.debug(f"Could not list file search stores: {e}")

    except ImportError:
        console.warn("google-genai not installed, skipping resource check")
        warnings_count += 1
    except Exception as e:
        console.warn(f"Gemini resource check failed: {e}")
        warnings_count += 1

    return all_passed, warnings_count


# =============================================================================
# UTILITY FUNCTIONS
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
        client = genai.Client(api_key=settings.api.gemini_key)
        response = client.models.generate_content(
            model=PrimrModels.FAST_MODEL,
            contents="Say 'OK' in one word."
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
        status = result.get('status', 'unknown')

        if status == "completed":
            console.ok("  Status: COMPLETED")
            content = result.get('content', '')
            if content:
                job_type = job_info.get('type', 'research')
                output_file = os.path.join(OUTPUT_DIR, f"recovered_{job_type}_{interaction_id[:8]}.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                console.ok(f"  Saved to: {output_file}")
        elif status == "failed":
            console.error("  Status: FAILED")
            console.error(f"  Error: {result.get('error', 'Unknown')}")
        elif status == "in_progress":
            console.info("  Status: IN PROGRESS (still running)")
        else:
            console.info(f"  Status: {status}")


def _handle_list_strategies(config: CLIConfig) -> int:
    """List available strategy documents."""
    console.banner("Available Strategy Documents")

    console.info("Strategy documents are research tools to help you show up prepared")
    console.info("for discovery conversations. They're NOT deliverables to hand over.")
    console.blank()

    console.step("Tier 1: External Research (No Discovery Required)")
    console.info("  These can be generated from public information:")
    console.blank()

    console.ok("  AI Strategy (ai)")
    console.info("    - Agentic AI transformation roadmap")
    console.info("    - Cloud vendor recommendations (Azure/AWS/GCP)")
    console.info("    - ROAI framework and superagency enablement")
    console.info("    Usage: primr --ai-strategy-only \"report.md\" --cloud-vendor azure")
    console.blank()

    console.ok("  Customer Experience Strategy (customer_experience)")
    console.info("    - CX transformation and digital experience")
    console.info("    - Journey mapping and personalization")
    console.info("    Usage: primr --ai-strategy-only \"report.md\" --strategy-type customer_experience")
    console.blank()

    console.ok("  Security & Compliance Strategy (modern_security_compliance)")
    console.info("    - Zero Trust architecture and identity management")
    console.info("    - Compliance frameworks and risk management")
    console.info("    Usage: primr --ai-strategy-only \"report.md\" --strategy-type modern_security_compliance")
    console.blank()

    console.ok("  Data Fabric Strategy (data_fabric_strategy)")
    console.info("    - Semantic layers and zero-copy architecture")
    console.info("    - Agent enablement and data mesh patterns")
    console.info("    Usage: primr --ai-strategy-only \"report.md\" --strategy-type data_fabric_strategy")
    console.blank()

    console.step("Tier 2: Discovery-Informed (Requires Meeting Insights)")
    console.info("  These require discovery notes from client conversations:")
    console.blank()

    console.warn("  Cloud Migration Strategy (cloud_migration)")
    console.info("    - Status: Placeholder only")
    console.info("    - Requires: Discovery notes about current infrastructure")
    console.blank()

    console.warn("  Application Modernization (placeholder)")
    console.info("    - Status: Not yet defined")
    console.info("    - Requires: Discovery notes about application portfolio")
    console.blank()

    console.step("How to Generate Strategies")
    console.info("  1. Run full research: primr \"Company\" https://example.com --mode full")
    console.info("  2. Generate specific strategy: primr --ai-strategy-only \"report.md\" --strategy-type customer_experience")
    console.info("  3. With discovery notes: primr --ai-strategy-only \"report.md\" --discovery-notes \"notes.md\"")
    console.blank()

    console.info("See docs/STRATEGY_PORTFOLIO.md for detailed information")

    return 0


# =============================================================================
# BATCH / ENRICH FUNCTIONS
# =============================================================================

@dataclass(frozen=True)
class _ColumnMap:
    """Result of LLM-based column classification."""
    company: str          # Column name for company name (required)
    website: str | None   # Column name for website URL
    industry: str | None  # Column name for industry/sector
    context: list[str]    # Columns useful for company disambiguation


def _classify_columns(df) -> _ColumnMap:
    """
    Use LLM to classify spreadsheet columns into roles.

    Shows the column names + a few sample rows so the LLM understands
    what each column actually contains.
    """
    import json

    from primr.ai.llm import llm

    columns = list(df.columns)
    if not columns:
        raise ValueError("Spreadsheet has no columns — cannot classify an empty file")

    # Build sample rows (up to 3) for context
    sample_lines = []
    for _, row in df.head(3).iterrows():
        vals = {col: str(row[col]).strip() for col in columns if str(row[col]).strip().lower() != 'nan'}
        sample_lines.append(json.dumps(vals, ensure_ascii=False))
    samples_text = "\n".join(sample_lines)

    prompt = f"""Classify these spreadsheet columns for a company research tool.

Columns: {json.dumps(columns)}

Sample rows:
{samples_text}

Classify each column into exactly ONE role:
- "company_name": the column containing the company/organization name (exactly one)
- "website": the column containing the company website URL (if any)
- "industry": the column containing industry, sector, or vertical (if any)
- "context": columns useful for identifying the company (region, country, revenue, employees, HQ, etc.)
- "skip": internal CRM fields not useful for identifying the company (owner, sales team, dates, internal IDs, etc.)

Return JSON only, no explanation:
{{"company_name": "column_name", "website": "column_name_or_null", "industry": "column_name_or_null", "context": ["col1", "col2"], "skip": ["col1", "col2"]}}"""

    response = llm(prompt, model_type="fast", streaming=False).strip()

    # Parse JSON from response (handle markdown code fences)
    if response.startswith("```"):
        parts = response.split("\n", 1)
        if len(parts) > 1:
            response = parts[1].rsplit("```", 1)[0].strip()
        else:
            # No newline after opening fences (e.g. ```{...}```)
            response = response[3:].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        logger.warning("LLM column classification failed to parse, falling back")
        console.warn(f"Column detection fell back to '{columns[0]}' — verify this is the company name column")
        return _ColumnMap(company=columns[0], website=None, industry=None, context=[])

    company_col = result.get("company_name")
    if not company_col or company_col not in columns:
        # Fallback: try common names
        for candidate in ["Account Name", "Company", "company_name", "Name"]:
            if candidate in columns:
                company_col = candidate
                break
        if not company_col:
            company_col = columns[0]

    website_col = result.get("website")
    if website_col and website_col not in columns:
        website_col = None

    industry_col = result.get("industry")
    if industry_col and industry_col not in columns:
        industry_col = None

    context_cols = [c for c in result.get("context", []) if c in columns]

    mapping = _ColumnMap(
        company=company_col,
        website=website_col,
        industry=industry_col,
        context=context_cols,
    )

    logger.debug(f"Column mapping: {mapping}")
    return mapping


def _read_batch_file(file_path: str):
    """Read an Excel or CSV file into a pandas DataFrame."""
    import pandas as pd

    if file_path.lower().endswith(('.xlsx', '.xls')):
        return pd.read_excel(file_path, engine='openpyxl')
    return pd.read_csv(file_path, encoding='utf-8')


def _prepare_batch_df(
    file_path: str,
    industry: str | None = None,
    limit: int | None = None,
) -> tuple:
    """
    Read batch file, classify columns with LLM, filter, and limit.

    Returns:
        (df, column_map: _ColumnMap)
    """
    df = _read_batch_file(file_path)

    # LLM classifies columns
    console.info("Analyzing columns...")
    col_map = _classify_columns(df)
    console.info(f"  Company: {col_map.company}")
    if col_map.website:
        console.info(f"  Website: {col_map.website}")
    if col_map.industry:
        console.info(f"  Industry: {col_map.industry}")
    if col_map.context:
        console.info(f"  Context: {', '.join(col_map.context)}")
    console.blank()

    # Filter by industry if requested
    if industry and col_map.industry:
        df = df[df[col_map.industry].astype(str).str.lower() == industry.lower()]
        if df.empty:
            df_full = _read_batch_file(file_path)
            unique = sorted(df_full[col_map.industry].dropna().unique())
            console.error(f"No rows match industry '{industry}'.")
            console.info(f"Available industries: {', '.join(str(v) for v in unique[:20])}")
            raise SystemExit(1)
    elif industry and not col_map.industry:
        console.error(f"--industry specified but no industry column found in {file_path}")
        console.info(f"Available columns: {', '.join(list(df.columns))}")
        raise SystemExit(1)

    # Apply limit
    if limit and limit > 0:
        df = df.head(limit)

    return df, col_map


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

    df, col_map = _prepare_batch_df(
        file_path, industry=industry, limit=limit
    )

    total = len(df)
    console.info(f"Found {total} companies")
    console.blank()

    # Build enriched rows (deduplicate by company name, case-insensitive)
    enriched = []
    seen_companies: set[str] = set()
    for idx, (_, row) in enumerate(df.iterrows(), 1):
        company_name = str(row[col_map.company]).strip()
        if not company_name or company_name.lower() == 'nan':
            continue
        if company_name.lower() in seen_companies:
            logger.debug(f"Skipping duplicate company: {company_name}")
            continue
        seen_companies.add(company_name.lower())

        # Use existing website if available, otherwise look up
        website = None
        if col_map.website and str(row.get(col_map.website, '')).strip().lower() not in ('', 'nan'):
            website = str(row[col_map.website]).strip()
        else:
            console.info(f"  [{idx}/{total}] Looking up {company_name}...")
            # Pass only LLM-selected context columns
            row_context = {
                k: str(row[k]).strip() for k in col_map.context
                if str(row.get(k, '')).strip().lower() not in ('', 'nan')
            }
            website = lookup_company_website(company_name, context=row_context)

        ind_value = ''
        if col_map.industry and str(row.get(col_map.industry, '')).strip().lower() != 'nan':
            ind_value = str(row[col_map.industry]).strip()

        enriched.append({
            'company_name': company_name,
            'website': website or '',
            'industry': ind_value,
        })

    # Display table
    console.blank()
    console.info(f"  {'#':>3}  {'Company':<35} {'Website':<35} {'Industry'}")
    console.info(f"  {'---':>3}  {'-'*35} {'-'*35} {'-'*20}")
    for i, row in enumerate(enriched, 1):
        w = row['website'][:33] + '..' if len(row['website']) > 35 else row['website']
        c = row['company_name'][:33] + '..' if len(row['company_name']) > 35 else row['company_name']
        console.info(f"  {i:>3}  {c:<35} {w:<35} {row['industry']}")

    found = sum(1 for r in enriched if r['website'])
    missing = len(enriched) - found
    console.blank()
    console.info(f"Websites found: {found}/{len(enriched)}")
    if missing:
        console.warn(f"Missing websites: {missing} (edit the CSV to add them manually)")

    # Save enriched CSV
    import pandas as pd

    base = _os.path.splitext(_os.path.basename(file_path))[0]
    suffix = f"_{industry.lower().replace(' ', '_')}" if industry else ""
    out_name = f"{base}{suffix}_enriched.csv"
    out_path = _os.path.join('.', out_name)

    pd.DataFrame(enriched).to_csv(out_path, index=False, encoding='utf-8')
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
    console.info(f"  scrape mode: {count} x ${scrape_est.total_cost:.2f} = ~${count * scrape_est.total_cost:.2f}")
    console.info(f"  deep mode:   {count} x ${deep_est.total_cost:.2f} = ~${count * deep_est.total_cost:.2f}")
    console.info(f"  full mode:   {count} x ${full_est.total_cost:.2f} = ~${count * full_est.total_cost:.2f}")
    console.blank()
    console.info(f"Next step: primr --batch \"{out_path}\" --mode scrape")

    return 0


def process_batch(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    cloud_vendors: tuple[str, ...] = ("azure",),
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

    df, col_map = _prepare_batch_df(
        file_path, industry=industry, limit=limit
    )

    # Build company list with row context for disambiguation (deduplicate by name)
    companies: list[tuple[str, str | None, dict]] = []
    seen_companies: set[str] = set()
    for _, row in df.iterrows():
        company_name = str(row[col_map.company]).strip()
        if not company_name or company_name.lower() == 'nan':
            continue
        if company_name.lower() in seen_companies:
            logger.debug(f"Skipping duplicate company: {company_name}")
            continue
        seen_companies.add(company_name.lower())

        website = None
        if col_map.website and str(row.get(col_map.website, '')).strip().lower() not in ('', 'nan'):
            website = str(row[col_map.website]).strip()

        row_context = {
            k: str(row[k]).strip() for k in col_map.context
            if str(row.get(k, '')).strip().lower() not in ('', 'nan')
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
        if response not in ('y', 'yes'):
            console.info("Cancelled.")
            return 0

    # Defensive thresholds
    max_consecutive_failures = 3
    min_report_size_kb = 5    # Reports under 5KB are suspiciously small
    max_retries_per_company = 2
    retry_wait_minutes = [0, 2, 5]  # Progressive backoff: immediate, 2min, 5min

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
            pattern = os.path.join(OUTPUT_DIR, f"{name}*Overview*{today_str}*")
            matches = glob.glob(pattern)
            if matches:
                # Prefer .docx > .md > .txt > anything else
                for ext in ('.docx', '.md', '.txt'):
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
            results.append({"company": company_name, "status": "ok",
                            "path": existing, "size_kb": size_kb, "error": None})
            skipped_existing += 1
            continue

        console.step(f"[{i}/{total}] Researching {company_name}...")

        # Look up website if missing
        if not website:
            console.info(f"  Looking up website for {company_name}...")
            website = lookup_company_website(company_name, context=row_ctx)
            if not website:
                console.warn(f"  No website found for {company_name}, skipping")
                results.append({"company": company_name, "status": "skipped",
                                "path": None, "size_kb": 0, "error": "no website found"})
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    console.error(f"  {max_consecutive_failures} consecutive failures — pausing")
                    resp = input("  Continue? [y/N] ").strip().lower()
                    if resp not in ('y', 'yes'):
                        console.info("  Batch stopped by user.")
                        break
                    consecutive_failures = 0
                continue

        # Research with retry and progressive backoff
        for attempt in range(max_retries_per_company + 1):
            # Progressive backoff: wait before retries (not before first attempt)
            wait_min = retry_wait_minutes[attempt] if attempt < len(retry_wait_minutes) else 5
            if attempt > 0 and wait_min > 0:
                console.warn(f"  Retrying in {wait_min}min "
                             f"(attempt {attempt + 1}/{max_retries_per_company + 1})...")
                _time.sleep(wait_min * 60)

            try:
                result_path = perform_research(
                    company_name,
                    _ensure_valid_url(website),
                    mode=mode,
                    citation_style=citation_style,
                    ai_strategy=ai_strategy,
                    cloud_vendors=cloud_vendors,
                )

                if result_path:
                    size_kb = os.path.getsize(result_path) / 1024 if os.path.exists(result_path) else 0
                    if size_kb < min_report_size_kb:
                        console.warn(f"  Report is only {size_kb:.1f}KB — may be incomplete")
                        results.append({"company": company_name, "status": "warning",
                                        "path": result_path, "size_kb": size_kb, "error": "small report"})
                    else:
                        console.ok(f"  Done — {size_kb:.0f}KB")
                        results.append({"company": company_name, "status": "ok",
                                        "path": result_path, "size_kb": size_kb, "error": None})
                    consecutive_failures = 0
                    break
                else:
                    # No report returned — not transient, don't retry
                    console.error(f"  No report generated for {company_name}")
                    results.append({"company": company_name, "status": "failed",
                                    "path": None, "size_kb": 0, "error": "no report returned"})
                    consecutive_failures += 1
                    break

            except Exception as e:
                error_str = str(e).lower()
                is_quota = any(s in error_str for s in ("quota", "rate", "429", "resource_exhausted"))

                if is_quota and attempt < max_retries_per_company:
                    continue  # Will wait at top of next iteration

                console.error(f"  Failed: {company_name} — {e}")
                results.append({"company": company_name, "status": "failed",
                                "path": None, "size_kb": 0, "error": str(e)[:80]})
                consecutive_failures += 1
                break

        # Consecutive failure handling — likely quota exhaustion
        if consecutive_failures >= max_consecutive_failures:
            console.error(f"\n  {max_consecutive_failures} consecutive failures — possible API quota exhaustion.")
            console.info("  [w] Wait 10 minutes and continue")
            console.info("  [s] Stop batch and show summary")
            resp = input("  Choice [w/s]: ").strip().lower()
            if resp == 'w':
                console.info("  Waiting 10 minutes for quota recovery...")
                _time.sleep(10 * 60)
                consecutive_failures = 0
            else:
                console.info("  Batch stopped by user.")
                console.info("  Re-run the same command to retry failed companies.")
                break

        # Check overall error rate (after at least 3 new attempts)
        new_attempted = len(results) - skipped_existing
        new_failed = sum(1 for r in results[skipped_existing:] if r["status"] == "failed")
        if new_attempted >= 3 and new_failed > new_attempted / 2:
            console.warn(f"  High failure rate: {new_failed}/{new_attempted} failed so far")

        # Cooldown between companies after any completed attempt (ok or warning)
        # Scale cooldown by mode: scrape is lighter on APIs than deep/full
        completed = any(r["company"] == company_name and r["status"] in ("ok", "warning")
                        for r in results)
        if completed and i < total:
            cooldown = 10 if mode == "scrape-only" else 60
            remaining = total - i
            console.info(f"  Cooling down {cooldown}s before next company ({remaining} remaining)...")
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
    console.info(f"  {'---':>3}  {'-'*35} {'-'*10} {'-'*8}  {'-'*20}")
    for i, r in enumerate(results, 1):
        status_icon = {"ok": "ok", "warning": "!!", "failed": "FAIL", "skipped": "SKIP"}[r["status"]]
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
    cloud_vendors: tuple[str, ...] = ("azure",),
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
                        cloud_vendors=cloud_vendors
                    )
                except Exception as e:
                    console.error(f"Failed: {company or website} - {e}")


def open_file(filepath: str) -> None:
    """Open a file with the system default application."""
    import platform
    import subprocess

    try:
        if platform.system() == 'Windows':
            os.startfile(filepath)  # type: ignore[attr-defined]  # Windows-only
        elif platform.system() == 'Darwin':
            subprocess.run(['open', filepath], check=True)
        else:
            subprocess.run(['xdg-open', filepath], check=True)
    except Exception as e:
        console.warn(f"Could not open file: {e}")


def _ensure_valid_url(website: str | None) -> str | None:
    """Ensure URL has proper scheme."""
    if not website:
        return None
    website = website.strip()
    if website.startswith(("http://", "https://")):
        return website
    if website.startswith("www."):
        return f"https://{website}"
    return f"https://{website}"


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())
