# config.py
"""
Configuration module with lazy API key validation.

API keys are loaded at import time but NOT validated until accessed.
This allows modules to be imported and tested without requiring API keys.

Usage:
    # For code that needs API keys:
    from primr.config.config import get_gemini_api_key
    api_key = get_gemini_api_key()  # Raises ConfigurationError if not set

    # For startup validation (e.g., in main() or doctor command):
    from primr.config.config import validate_config, require_valid_config
    result = validate_config()
    if not result.valid:
        print(result.errors)
"""

from dataclasses import dataclass
import os
from pathlib import Path

from primr.config.env import load_primr_env

# Load environment variables (safe, no validation)
load_primr_env()


# =============================================================================
# PROJECT ROOT DETECTION
# =============================================================================


def get_project_root() -> Path:
    """
    Returns the project root directory.
    Works whether running from package or directly.
    """
    current = Path(__file__).resolve()
    # Go up: config.py -> config/ -> primr/ -> src/ -> project_root
    for _ in range(4):
        current = current.parent
        if (current / ".env").exists() or (current / "pyproject.toml").exists():
            return current
    return Path.cwd()


PROJECT_ROOT = get_project_root()


# =============================================================================
# LAZY API KEY ACCESS
# =============================================================================

# Private storage (loaded but not validated at import time)
_gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
_search_api_key: str | None = os.getenv("SEARCH_API_KEY")
_search_engine_id: str | None = os.getenv("SEARCH_ENGINE_ID")
_xai_api_key: str | None = os.getenv("XAI_API_KEY")


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid.

    Note: This is a separate class from primr.utils.errors.ConfigurationError
    due to circular import constraints (config <- utils <- config). Code that
    catches ConfigurationError should import from whichever module raised it.
    """

    def __init__(self, message: str, guidance: str | None = None):
        super().__init__(message)
        self.message = message
        self.guidance = guidance

    def __str__(self) -> str:
        if self.guidance:
            return f"{self.message}\n  Guidance: {self.guidance}"
        return self.message


def get_gemini_api_key() -> str:
    """
    Get Gemini API key, raising if not configured.

    Raises:
        ConfigurationError: If GEMINI_API_KEY is not set in environment or .env
    """
    if not _gemini_api_key:
        raise ConfigurationError(
            "GEMINI_API_KEY not configured",
            guidance="Run 'primr keys set gemini' or add GEMINI_API_KEY to .env/environment",
        )
    return _gemini_api_key


def get_search_api_key() -> str:
    """
    Get Google Search API key, raising if not configured.

    Raises:
        ConfigurationError: If SEARCH_API_KEY is not set
    """
    if not _search_api_key:
        raise ConfigurationError(
            "SEARCH_API_KEY not configured",
            guidance="Add SEARCH_API_KEY=your_key to your .env file or environment",
        )
    return _search_api_key


def get_search_engine_id() -> str:
    """
    Get Google Search Engine ID, raising if not configured.

    Raises:
        ConfigurationError: If SEARCH_ENGINE_ID is not set
    """
    if not _search_engine_id:
        raise ConfigurationError(
            "SEARCH_ENGINE_ID not configured",
            guidance="Add SEARCH_ENGINE_ID=your_id to your .env file or environment",
        )
    return _search_engine_id


# =============================================================================
# EXPLICIT VALIDATION
# =============================================================================


@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""

    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_config(include_optional: bool = False) -> ConfigValidationResult:
    """
    Explicitly validate all required configuration.

    Call this at application startup (e.g., in main() or doctor command)
    to fail fast with clear error messages.

    Args:
        include_optional: If True, also check optional config values

    Returns:
        ConfigValidationResult with validation status and any errors
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Required API keys
    if not _gemini_api_key:
        errors.append("GEMINI_API_KEY not set")
    if not _xai_api_key:
        warnings.append("XAI_API_KEY not set (recommended for Grok standard mode)")
    if not _search_api_key:
        warnings.append("SEARCH_API_KEY not set (optional, for Google Search)")
    if not _search_engine_id:
        warnings.append("SEARCH_ENGINE_ID not set (optional, for Google Search)")

    # Check directories are writable (actually test writing)
    for dir_name, dir_path in [
        ("OUTPUT_DIR", OUTPUT_DIR),
        ("WORKING_DIR", WORKING_DIR),
        ("LOGS_DIR", LOGS_DIR),
    ]:
        path = Path(dir_path)
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"{dir_name} cannot be created: {e}")
                continue

        # Symlink-safe writability probe — see fs_safety for rationale.
        from primr.utils.fs_safety import check_dir_writable

        ok, why = check_dir_writable(path)
        if not ok:
            errors.append(f"{dir_name} is not writable: {path} - {why}")

    return ConfigValidationResult(
        valid=len(errors) == 0, errors=tuple(errors), warnings=tuple(warnings)
    )


def require_valid_config() -> None:
    """
    Require valid configuration, raising if invalid.

    Use this as a guard at the start of operations that need config.
    """
    result = validate_config()
    if not result.valid:
        raise ConfigurationError(
            "Configuration validation failed",
            guidance="Errors:\n  - " + "\n  - ".join(result.errors),
        )


# =============================================================================
# BACKWARD COMPATIBLE CONSTANTS
# =============================================================================

# These are still available for backward compatibility.
# Code should migrate to using get_*() functions for API keys.

# Expose API keys as module-level constants for backward compatibility
# WARNING: These will be None if not configured. Use get_*() functions instead.
GEMINI_API_KEY = _gemini_api_key
SEARCH_API_KEY = _search_api_key
SEARCH_ENGINE_ID = _search_engine_id
XAI_API_KEY = _xai_api_key

### **Search & Scraping Configuration** ###
NUM_SEARCH_RESULTS = 10
PARALLEL_SEARCH_LIMIT = 2
INITIAL_RETRY_DELAY = 5
MAX_EXTERNAL_SEARCH_QUERIES = int(os.getenv("MAX_EXTERNAL_SEARCH_QUERIES", "5"))
MAX_EXTERNAL_SOURCES = int(os.getenv("MAX_EXTERNAL_SOURCES", "8"))
MIN_SCRAPED_PAGES = int(os.getenv("MIN_SCRAPED_PAGES", "3"))
MIN_SCRAPED_CHARS = int(os.getenv("MIN_SCRAPED_CHARS", "6000"))
SCRAPE_PILOT_COUNT = int(os.getenv("SCRAPE_PILOT_COUNT", "10"))
SCRAPE_PILOT_MIN_SUCCESS_RATE = float(os.getenv("SCRAPE_PILOT_MIN_SUCCESS_RATE", "0.70"))
SCRAPE_PILOT_MIN_CHARS = int(os.getenv("SCRAPE_PILOT_MIN_CHARS", "700"))

# Scraping Settings
MAX_SCRAPE_RETRIES = 2
SCRAPE_TIMEOUT = 15
SCRAPE_MAX_DEPTH = 2
EXCLUDED_SITES = ["login", "captcha", "privacy-policy", "terms-of-service"]

### **AI Model Configuration** ###
# Import centralized model configuration - UPDATE PrimrModels TO CHANGE MODELS GLOBALLY
from primr.config.models import PrimrModels

# Model assignments - these are backward compatible aliases
# Use PrimrModels.FAST_MODEL or PrimrModels.REASONING_MODEL directly in new code
AI_RESEARCH_MODEL = os.getenv("AI_RESEARCH_MODEL", PrimrModels.FAST_MODEL)  # Flash - cheap/fast
AI_REPORT_MODEL = os.getenv("AI_REPORT_MODEL", PrimrModels.PRO_MODEL)  # Pro - matches settings.py

MAX_RETRIES = 3
GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT = 70

### **File Handling & Output Settings** ###
OUTPUT_DIR = str(PROJECT_ROOT / "output")
WORKING_DIR = str(PROJECT_ROOT / "working")
LOGS_DIR = str(PROJECT_ROOT / "logs" / "chat_history")
FAST_FEEDBACK_RULES_PATH = str(PROJECT_ROOT / "output" / "evals" / "_fast_feedback_current.md")

# Ensure necessary directories exist (safe operation)
for directory in [OUTPUT_DIR, WORKING_DIR, LOGS_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True)

### **Document Processing Settings** ###
SUPPORTED_FILE_TYPES = [".pdf", ".docx", ".txt", ".xlsx"]
CONVERT_TO_PDF = True
