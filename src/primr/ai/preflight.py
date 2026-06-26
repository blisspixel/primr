"""
Pre-flight validation for Primr research pipelines.

This module validates ALL dependencies before starting expensive, long-running
research operations. A 40-minute pipeline should not fail at minute 35 because
of a missing API key.

Usage:
    from primr.ai.preflight import PreflightValidator, PreflightResult

    validator = PreflightValidator()
    result = await validator.validate(
        mode="full",
        website_url="https://example.com",
    )

    if not result.success:
        print(result.summary())
        sys.exit(1)

    # Safe to proceed with pipeline

Design Principles:
    - Fail fast: Check everything before starting expensive operations
    - Clear errors: Tell user exactly what's wrong and how to fix it
    - Mode-aware: Only check dependencies needed for the selected mode
    - No side effects: Validation should not modify state
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from primr.ai.genai_factory import default_genai_http_options
from primr.config.settings import get_settings
from primr.utils.logging_config import get_logger

logger = get_logger("ai.preflight")


@dataclass
class PreflightResult:
    """Result of pre-flight validation."""

    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, dict] = field(default_factory=dict)
    estimated_duration: str = ""
    estimated_cost: str = ""

    def summary(self, verbose: bool = False) -> str:
        """
        Generate human-readable summary.

        Args:
            verbose: Include all check details, not just errors
        """
        lines = []

        if self.success:
            lines.append("+ Pre-flight validation passed")
            lines.append(f"  Duration: {self.estimated_duration}")
            lines.append(f"  Est. cost: {self.estimated_cost}")
        else:
            lines.append("x Pre-flight validation FAILED")
            lines.append("")
            lines.append("Errors (must fix before proceeding):")
            for err in self.errors:
                lines.append(f"  x {err}")

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warn in self.warnings:
                lines.append(f"  ! {warn}")

        if verbose:
            lines.append("")
            lines.append("Check details:")
            for name, check in self.checks.items():
                status = "+" if check.get("passed") else "x"
                lines.append(f"  {status} {name}: {check.get('status', 'unknown')}")
                if check.get("detail"):
                    lines.append(f"      {check['detail']}")

        return "\n".join(lines)


class PreflightValidator:
    """
    Validates all prerequisites before starting research pipelines.

    Checks are mode-aware:
    - full: All checks (scraping + search + Deep Research + section writing)
    - deep: Deep Research + Gemini only
    - scrape: Scraping + search + Gemini only
    """

    # Import centralized model config
    from primr.config.models import PrimrModels

    # Model identifiers - USE CENTRALIZED CONFIG
    DEEP_RESEARCH_AGENT = PrimrModels.DEEP_RESEARCH_AGENT
    SECTION_MODEL = PrimrModels.FLASH_MODEL

    # Estimates by mode
    ESTIMATES = {
        "full": {"duration": "35-50 minutes", "cost": "~$0.50-1.00"},
        "deep": {"duration": "10-15 minutes", "cost": "~$0.10-0.20"},
        "scrape": {"duration": "2-5 minutes", "cost": "~$0.01"},  # Scrape-only is cheap
    }

    def __init__(self):
        """Initialize validator."""
        self._settings = get_settings()

    async def validate(
        self,
        mode: str = "full",
        website_url: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> PreflightResult:
        """
        Run all pre-flight checks for the specified mode.

        Args:
            mode: Research mode - "full", "deep", or "scrape"
            website_url: Target website URL (for reachability check)
            on_progress: Optional callback for progress updates

        Returns:
            PreflightResult with success status and any errors/warnings
        """
        errors = []
        warnings = []
        checks = {}

        def progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        progress(f"Pre-flight validation (mode: {mode})...")

        # 1. API Keys
        self._check_api_keys(mode, errors, warnings, checks, progress)

        # 2. YAML Configuration
        self._check_yaml_config(errors, warnings, checks, progress)

        # 3. Model Connectivity (async)
        await self._check_models(mode, errors, warnings, checks, progress)

        # 4. Playwright (for scraping modes)
        if mode in ("full", "scrape"):
            await self._check_playwright(errors, warnings, checks, progress)

        # 5. Website Reachability
        if website_url and mode in ("full", "scrape"):
            await self._check_website(website_url, errors, warnings, checks, progress)

        # 6. Output Directory
        self._check_output_dir(errors, warnings, checks, progress)

        # Build result
        estimates = self.ESTIMATES.get(mode, self.ESTIMATES["full"])

        result = PreflightResult(
            success=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            checks=checks,
            estimated_duration=estimates["duration"],
            estimated_cost=estimates["cost"],
        )

        if result.success:
            progress("+ All checks passed")
        else:
            progress(f"x {len(errors)} error(s) found")

        return result

    def _check_api_keys(
        self,
        mode: str,
        errors: list,
        warnings: list,
        checks: dict,
        progress: Callable,
    ) -> None:
        """Check required API keys are configured."""

        # This legacy validator backs the Gemini Deep Research helper, so its
        # model checks are Gemini-specific even though the main CLI can run the
        # XAI standard path without Gemini.
        gemini_key = self._settings.api.gemini_key
        if not gemini_key:
            errors.append("GEMINI_API_KEY not configured in .env")
            checks["gemini_api_key"] = {"passed": False, "status": "missing"}
        else:
            checks["gemini_api_key"] = {"passed": True, "status": "configured"}
            progress("  + GEMINI_API_KEY")

        # Search provider - check based on active provider
        if mode in ("full", "scrape"):
            search_provider = os.environ.get("SEARCH_PROVIDER", "auto").lower().strip()
            if search_provider == "google":
                # Google requires API keys
                search_key = getattr(self._settings.api, "search_key", None) or os.environ.get(
                    "SEARCH_API_KEY"
                )
                if not search_key:
                    errors.append(
                        "SEARCH_API_KEY not configured (required when SEARCH_PROVIDER=google)"
                    )
                    checks["search_api_key"] = {"passed": False, "status": "missing"}
                else:
                    checks["search_api_key"] = {"passed": True, "status": "configured"}
                    progress("  + SEARCH_API_KEY")

                search_engine_id = getattr(
                    self._settings.api, "search_engine_id", None
                ) or os.environ.get("SEARCH_ENGINE_ID")
                if not search_engine_id:
                    errors.append(
                        "SEARCH_ENGINE_ID not configured (required when SEARCH_PROVIDER=google)"
                    )
                    checks["search_engine_id"] = {"passed": False, "status": "missing"}
                else:
                    checks["search_engine_id"] = {"passed": True, "status": "configured"}
                    progress("  + SEARCH_ENGINE_ID")
            else:
                # DuckDuckGo - no keys needed
                checks["search_provider"] = {"passed": True, "status": "DuckDuckGo (no key needed)"}
                progress("  + Search: DuckDuckGo (no key needed)")

    def _check_yaml_config(
        self,
        errors: list,
        warnings: list,
        checks: dict,
        progress: Callable,
    ) -> None:
        """Check YAML configuration loads correctly."""
        try:
            from primr.prompts.composer import PromptComposer

            composer = PromptComposer()
            config = composer._load_config("company_overview")

            section_count = len(config.sections)
            if section_count < 10:
                warnings.append(f"Only {section_count} sections in config (expected 21)")

            # Check accordion prompts
            accordion = config.raw_config.get("accordion_method", {})
            if not accordion.get("research_dossier_prompt"):
                errors.append("research_dossier_prompt missing from company_overview.yaml")
            if not accordion.get("section_writing_prompt"):
                errors.append("section_writing_prompt missing from company_overview.yaml")

            checks["yaml_config"] = {
                "passed": True,
                "status": f"{section_count} sections",
                "detail": "company_overview.yaml loaded successfully",
            }
            progress(f"  + YAML config ({section_count} sections)")

        except Exception as e:
            errors.append(f"YAML configuration error: {e}")
            checks["yaml_config"] = {"passed": False, "status": "error", "detail": str(e)}

    async def _check_models(
        self,
        mode: str,
        errors: list,
        warnings: list,
        checks: dict,
        progress: Callable,
    ) -> None:
        """Check model connectivity."""
        gemini_key = self._settings.api.gemini_key
        if not gemini_key:
            return  # Already reported in API key check

        try:
            from google import genai
        except ImportError:
            errors.append(
                "google-genai package not installed. Install with: pip install google-genai"
            )
            checks["gemini_sdk"] = {"passed": False, "status": "missing"}
            return

        client = genai.Client(api_key=gemini_key, http_options=default_genai_http_options())

        # Gemini 3 Flash - required for section writing (full, scrape modes)
        if mode in ("full", "scrape"):
            try:
                response = client.models.generate_content(
                    model=self.SECTION_MODEL,
                    contents="Respond with exactly: OK",
                )
                if response.text:
                    checks["gemini_flash"] = {
                        "passed": True,
                        "status": "accessible",
                        "detail": self.SECTION_MODEL,
                    }
                    progress(f"  ✓ {self.SECTION_MODEL}")
                else:
                    errors.append(f"{self.SECTION_MODEL} returned empty response")
                    checks["gemini_flash"] = {"passed": False, "status": "empty_response"}
            except Exception as e:
                error_str = str(e).lower()
                if "not found" in error_str or "does not exist" in error_str:
                    errors.append(
                        f"Model {self.SECTION_MODEL} not available - check model name in docs"
                    )
                elif "quota" in error_str or "429" in error_str:
                    errors.append("Gemini API quota exhausted - wait or check billing")
                elif "api key" in error_str or "authentication" in error_str:
                    errors.append("Gemini API key invalid")
                else:
                    errors.append(f"Gemini connectivity error: {e}")
                checks["gemini_flash"] = {"passed": False, "status": "error", "detail": str(e)}

        # Deep Research agent - required for full and deep modes
        if mode in ("full", "deep"):
            try:
                interaction = client.interactions.create(
                    input="Connectivity test",
                    agent=self.DEEP_RESEARCH_AGENT,
                    background=True,
                )
                if interaction.id:
                    checks["deep_research"] = {
                        "passed": True,
                        "status": "accessible",
                        "detail": f"ID: {interaction.id[:16]}...",
                    }
                    progress("  ✓ Deep Research agent")
            except Exception as e:
                error_str = str(e).lower()
                if "not found" in error_str or "invalid" in error_str:
                    errors.append("Deep Research agent not available - check agent ID")
                    checks["deep_research"] = {"passed": False, "status": "not_found"}
                elif "quota" in error_str or "429" in error_str:
                    # Rate limit is a warning for Deep Research (we have fallback)
                    warnings.append(
                        "Deep Research may be rate limited - will use fallback if needed"
                    )
                    checks["deep_research"] = {"passed": True, "status": "rate_limited"}
                    progress("  ⚠ Deep Research (rate limited, fallback available)")
                else:
                    errors.append(f"Deep Research connectivity error: {e}")
                    checks["deep_research"] = {"passed": False, "status": "error", "detail": str(e)}

    async def _check_playwright(
        self,
        errors: list,
        warnings: list,
        checks: dict,
        progress: Callable,
    ) -> None:
        """Check Playwright browsers are installed."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                await browser.close()

            checks["playwright"] = {"passed": True, "status": "installed"}
            progress("  ✓ Playwright browsers")

        except Exception as e:
            error_str = str(e).lower()
            if "executable doesn't exist" in error_str or "not found" in error_str:
                errors.append("Playwright browsers not installed. Run: playwright install chromium")
                checks["playwright"] = {
                    "passed": False,
                    "status": "not_installed",
                    "detail": "Run: playwright install chromium",
                }
            else:
                warnings.append(f"Playwright check failed: {e}")
                checks["playwright"] = {"passed": False, "status": "unknown", "detail": str(e)}

    async def _check_website(
        self,
        website_url: str,
        errors: list,
        warnings: list,
        checks: dict,
        progress: Callable,
    ) -> None:
        """Check target website is reachable."""
        try:
            from primr.data.safe_http import async_safe_http_head
            from primr.utils.security import is_safe_url

            # Normalize URL
            if not website_url.startswith(("http://", "https://")):
                website_url = f"https://{website_url}"

            is_safe, initial_error = is_safe_url(website_url)
            if not is_safe:
                if initial_error == "DNS resolution failed":
                    warnings.append(f"Could not reach website: {initial_error}")
                    checks["website"] = {
                        "passed": False,
                        "status": "unreachable",
                        "detail": initial_error,
                    }
                    return
                errors.append(f"Website URL is unsafe: {initial_error}")
                checks["website"] = {
                    "passed": False,
                    "status": "unsafe_url",
                    "detail": f"Blocked before request: {initial_error}",
                }
                return

            status_code, final_url, blocked_by_guard = await async_safe_http_head(
                website_url,
                timeout=10.0,
                log_prefix="preflight-website",
            )
            if blocked_by_guard:
                errors.append("Website redirects to unsafe URL")
                checks["website"] = {
                    "passed": False,
                    "status": "unsafe_redirect",
                    "detail": f"Redirects to blocked address: {final_url or website_url}",
                }
                return
            if status_code is None:
                warnings.append("Could not reach website: no response")
                checks["website"] = {
                    "passed": False,
                    "status": "unreachable",
                    "detail": website_url,
                }
                return
            if status_code < 400:
                checks["website"] = {
                    "passed": True,
                    "status": f"HTTP {status_code}",
                    "detail": final_url or website_url,
                }
                progress("  ✓ Website reachable")
            else:
                warnings.append(f"Website returned HTTP {status_code}")
                checks["website"] = {
                    "passed": True,  # Warning, not error
                    "status": f"HTTP {status_code}",
                }

        except Exception as e:
            warnings.append(f"Could not reach website: {e}")
            checks["website"] = {"passed": False, "status": "unreachable", "detail": str(e)}

    def _check_output_dir(
        self,
        errors: list,
        warnings: list,
        checks: dict,
        progress: Callable,
    ) -> None:
        """Check output directory is writable."""
        try:
            from primr.config.config import OUTPUT_DIR

            os.makedirs(OUTPUT_DIR, exist_ok=True)

            # Test write permission
            test_file = os.path.join(OUTPUT_DIR, ".preflight_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)

            checks["output_dir"] = {
                "passed": True,
                "status": "writable",
                "detail": OUTPUT_DIR,
            }
            progress("  ✓ Output directory")

        except Exception as e:
            errors.append(f"Output directory not writable: {e}")
            checks["output_dir"] = {"passed": False, "status": "not_writable", "detail": str(e)}


async def run_preflight(
    mode: str = "full",
    website_url: str | None = None,
    verbose: bool = False,
) -> PreflightResult:
    """
    Convenience function to run pre-flight validation.

    Args:
        mode: Research mode
        website_url: Target website
        verbose: Show detailed progress

    Returns:
        PreflightResult
    """
    validator = PreflightValidator()

    def progress(msg: str) -> None:
        if verbose:
            print(msg)

    return await validator.validate(
        mode=mode,
        website_url=website_url,
        on_progress=progress if verbose else None,
    )
