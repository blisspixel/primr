"""
Config module - Configuration and settings.
"""

# Legacy exports from config.py for backward compatibility
from primr.config.config import (
    AI_REPORT_MODEL,
    AI_RESEARCH_MODEL,
    EXCLUDED_SITES,
    GEMINI_API_KEY,
    GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT,
    LOGS_DIR,
    MAX_RETRIES,
    MAX_SCRAPE_RETRIES,
    NUM_SEARCH_RESULTS,
    OUTPUT_DIR,
    PROJECT_ROOT,
    SCRAPE_MAX_DEPTH,
    SCRAPE_TIMEOUT,
    SEARCH_API_KEY,
    SEARCH_ENGINE_ID,
    WORKING_DIR,
)
from primr.config.sections_config import SECTION_KEY_MAP
from primr.config.settings import (
    AIConfig,
    APIConfig,
    CacheConfig,
    OutputConfig,
    PathConfig,
    PricingConfig,
    ScrapingConfig,
    SearchConfig,
    Settings,
    TimeoutConfig,
    configure,
    get_settings,
    reset_settings,
)

__all__ = [
    # New settings system
    "Settings",
    "APIConfig",
    "ScrapingConfig",
    "AIConfig",
    "SearchConfig",
    "PathConfig",
    "OutputConfig",
    "TimeoutConfig",
    "CacheConfig",
    "PricingConfig",
    "get_settings",
    "reset_settings",
    "configure",
    "SECTION_KEY_MAP",
    # Legacy exports
    "GEMINI_API_KEY",
    "SEARCH_API_KEY",
    "SEARCH_ENGINE_ID",
    "NUM_SEARCH_RESULTS",
    "MAX_SCRAPE_RETRIES",
    "SCRAPE_TIMEOUT",
    "SCRAPE_MAX_DEPTH",
    "EXCLUDED_SITES",
    "AI_RESEARCH_MODEL",
    "AI_REPORT_MODEL",
    "MAX_RETRIES",
    "GRADE_THRESHOLD_FOR_RESEARCH_REFINEMENT",
    "OUTPUT_DIR",
    "WORKING_DIR",
    "LOGS_DIR",
    "PROJECT_ROOT",
]
