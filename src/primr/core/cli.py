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
    config = parse_args(["Tesla", "https://tesla.com", "--mode", "deep"])
"""
import argparse
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from primr.config.models import PrimrModels

from primr.config.config import LOGS_DIR, OUTPUT_DIR, WORKING_DIR
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
    SHOW_USAGE = "show-usage"
    DRY_RUN = "dry-run"
    GENERATE_VENDOR = "generate-vendor"
    BATCH = "batch"
    TEST_ACCORDION = "test-accordion"
    ANALYZE_REPORT = "analyze-report"
    QA = "qa"
    QA_RECENT = "qa-recent"


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
    cloud_vendor: str = "azure"
    skip_confirm: bool = True
    context_files: tuple[str, ...] = ()
    context_folder: str | None = None
    refresh_vendor_research: bool = False
    generate_vendor: str | None = None
    csv_file: str | None = None
    output_dir: str | None = None
    open_after: bool = False
    quiet: bool = False
    verbose: bool = False
    test_accordion_topic: str | None = None
    test_accordion_pages: int = 50
    analyze_report_path: str | None = None
    qa_company: str | None = None
    qa_recent_count: int | None = None

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
    "scrape": "scrape-only",  # NEW: scrape-only mode (just scraping + insights)
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
    elif mode == "scrape-only":
        ai_strategy = False  # Scrape-only doesn't need AI strategy
    else:
        ai_strategy = True

    # Build context files tuple
    context_files = tuple(getattr(parsed, 'context', None) or [])

    return CLIConfig(
        command=command,
        company_name=parsed.company,
        website=parsed.website,
        mode=mode,
        citation_style=getattr(parsed, 'citation_style', 'numbered'),
        ai_strategy=ai_strategy,
        cloud_vendor=getattr(parsed, 'cloud_vendor', 'azure'),
        skip_confirm=not getattr(parsed, 'confirm', False),
        context_files=context_files,
        context_folder=getattr(parsed, 'context_folder', None),
        refresh_vendor_research=getattr(parsed, 'refresh_vendor_research', False),
        generate_vendor=getattr(parsed, 'generate_vendor_research', None),
        csv_file=parsed.csv,
        output_dir=getattr(parsed, 'output_dir', None),
        open_after=getattr(parsed, 'open', False),
        quiet=parsed.quiet,
        verbose=parsed.verbose,
        test_accordion_topic=getattr(parsed, 'test_accordion', None),
        test_accordion_pages=getattr(parsed, 'accordion_pages', 50),
        analyze_report_path=getattr(parsed, 'analyze_report', None),
        qa_company=getattr(parsed, 'qa', None),
        qa_recent_count=getattr(parsed, 'qa_recent', None),
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
    from primr.utils.logging_config import setup_logging
    
    config = parse_args(args)

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
        Command.SHOW_USAGE: _handle_show_usage,
        Command.DRY_RUN: _handle_dry_run,
        Command.GENERATE_VENDOR: _handle_generate_vendor,
        Command.BATCH: _handle_batch,
        Command.TEST_ACCORDION: _handle_test_accordion,
        Command.ANALYZE_REPORT: _handle_analyze_report,
        Command.QA: _handle_qa,
        Command.QA_RECENT: _handle_qa_recent,
        Command.RESEARCH: _handle_research,
    }

    handler = handlers.get(config.command, _handle_research)
    return handler(config)


def run_doctor() -> int:
    """
    Run system diagnostics.

    Returns:
        Exit code (0 if all checks pass, 1 otherwise)
    """
    from primr.utils.type_guards import ConfigSchema, validate_config

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
  primr "Tesla" https://tesla.com
  primr "Tesla" tesla.com --mode deep
  primr "Tesla" tesla.com --mode scrape     # Quick scrape + insights only
  primr doctor                              # System diagnostics
  primr --qa "Tesla"                        # Show detailed QA analysis
  primr --qa-recent 5                       # Show QA summary for recent reports
  
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

    # Research options
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["scrape", "deep", "full", "parallel", "structured", "deep-research", "complete", "hybrid"],
        default="full",
        help="Research mode (default: full)"
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
        choices=["azure", "aws", "gcp", "agnostic"],
        default="azure",
        help="Cloud vendor for AI recommendations"
    )
    parser.add_argument("--confirm", action="store_true", help="Ask for confirmation")
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
    parser.add_argument("--check-quota", action="store_true", help="Check API quota")
    
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

    return parser


def _determine_command(args: argparse.Namespace) -> Command:
    """Determine which command to run based on parsed args."""
    # Check for 'doctor' as first positional arg
    if args.company and args.company.lower() == "doctor":
        return Command.DOCTOR

    # Check utility flags
    if getattr(args, 'qa_recent', None) is not None:
        return Command.QA_RECENT
    if getattr(args, 'qa', None):
        return Command.QA
    if getattr(args, 'analyze_report', None):
        return Command.ANALYZE_REPORT
    if getattr(args, 'test_accordion', None):
        return Command.TEST_ACCORDION
    if getattr(args, 'show_usage', False):
        return Command.SHOW_USAGE
    if getattr(args, 'list_recent', False):
        return Command.LIST_RECENT
    if getattr(args, 'clean_temp', False):
        return Command.CLEAN_TEMP
    if getattr(args, 'check_quota', False):
        return Command.CHECK_QUOTA
    if getattr(args, 'check_jobs', False):
        return Command.CHECK_JOBS
    if getattr(args, 'dry_run', False):
        return Command.DRY_RUN
    if getattr(args, 'generate_vendor_research', None):
        return Command.GENERATE_VENDOR
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


def _handle_show_usage(config: CLIConfig) -> int:
    """Handle show-usage command."""
    from primr.utils.usage_tracker import get_usage_tracker
    tracker = get_usage_tracker()
    print(tracker.display_usage_history())
    return 0


def _handle_dry_run(config: CLIConfig) -> int:
    """Handle dry-run command."""
    from primr.utils.cost_estimator import estimate_cost

    print("")
    print("=" * 60)
    print(f"COST ESTIMATE: {config.mode} mode")
    if config.ai_strategy:
        print("(includes AI Strategy analysis)")
    print("=" * 60)
    print("")

    estimate = estimate_cost(config.mode, config.ai_strategy)
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


def _handle_batch(config: CLIConfig) -> int:
    """Handle batch CSV processing."""
    if not config.csv_file:
        console.error("No CSV file specified")
        return 1

    process_csv(
        config.csv_file,
        mode=config.mode,
        citation_style=config.citation_style,
        ai_strategy=config.ai_strategy,
        cloud_vendor=config.cloud_vendor
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
        from report_analyzer import ReportAnalyzer
        analyzer = ReportAnalyzer(config.analyze_report_path)
        report = analyzer.generate_report()
        print(report)
        return 0
    except Exception as e:
        console.error(f"Analysis failed: {e}")
        return 1


def _handle_qa(config: CLIConfig) -> int:
    """Handle QA review command."""
    print(f"DEBUG: _handle_qa called with qa_company: '{config.qa_company}'")
    
    if not config.qa_company:
        console.error("Company name or file path is required for QA review")
        console.info("Usage: primr --qa \"Company Name\"")
        console.info("   or: primr --qa \"path/to/report.docx\"")
        return 1
    
    try:
        from primr.qa.command import QACommand
        from pathlib import Path
        
        qa_command = QACommand()
        
        print(f"DEBUG: Received argument: '{config.qa_company}'")
        
        # Check if the argument is a file path by checking if it exists as a file
        potential_path = Path(config.qa_company)
        print(f"DEBUG: Path object created: {potential_path}")
        print(f"DEBUG: Path exists: {potential_path.exists()}")
        if potential_path.exists():
            print(f"DEBUG: Is file: {potential_path.is_file()}")
        
        if potential_path.exists() and potential_path.is_file():
            # Treat as file path
            print(f"DEBUG: File exists, calling analyze_report_file with: {config.qa_company}")
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

    # Build context files list
    context_files = list(config.context_files)

    # Handle context folder
    if config.context_folder:
        try:
            consolidated_file = consolidate_working_folder(config.context_folder)
            context_files = [consolidated_file] + context_files
        except Exception as e:
            console.error(f"Failed to consolidate context folder: {e}")
            return 1

    # Validate context files
    if context_files:
        valid_files, invalid_files, warnings = validate_context_files(context_files)
        for warning in warnings:
            console.warn(warning)
        if invalid_files:
            for file_path, reason in invalid_files:
                console.error(f"Invalid context file: {file_path} - {reason}")
            return 1
        context_files = valid_files

    # Run research
    result_path = perform_research(
        company_name,
        website,
        mode=config.mode,
        citation_style=config.citation_style,
        ai_strategy=config.ai_strategy,
        cloud_vendor=config.cloud_vendor,
        skip_confirm=config.skip_confirm,
        context_files=context_files if context_files else None,
        refresh_vendor_research=config.refresh_vendor_research
    )

    # Open report if requested
    if config.open_after and result_path:
        open_file(result_path)

    return 0 if result_path else 1


# =============================================================================
# INTERNAL FUNCTIONS - Doctor Checks
# =============================================================================

def _check_api_keys(all_passed: bool, warnings_count: int) -> tuple[bool, int]:
    """Check API key configuration."""
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

    search_key = os.environ.get("SEARCH_API_KEY", "")
    if search_key and len(search_key) >= 10:
        console.ok("SEARCH_API_KEY configured")
    else:
        console.warn("SEARCH_API_KEY not set (optional, for Google Search)")
        warnings_count += 1

    search_engine = os.environ.get("SEARCH_ENGINE_ID", "")
    if search_engine:
        console.ok("SEARCH_ENGINE_ID configured")
    else:
        console.warn("SEARCH_ENGINE_ID not set (optional, for Google Search)")
        warnings_count += 1

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
                pass

    for f in temp_files:
        try:
            os.remove(f)
            cleaned += 1
        except Exception:
            pass

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


def process_csv(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    cloud_vendor: str = "azure"
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
                        cloud_vendor=cloud_vendor
                    )
                except Exception as e:
                    console.error(f"Failed: {company or website} - {e}")


def open_file(filepath: str) -> None:
    """Open a file with the system default application."""
    import platform
    import subprocess

    try:
        if platform.system() == 'Windows':
            os.startfile(filepath)
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
