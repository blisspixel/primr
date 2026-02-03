"""
Centralized Model Configuration for Primr
==========================================

THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL AI MODELS.
UPDATE HERE TO CHANGE MODELS GLOBALLY.

AVAILABLE MODELS (January 2026):
--------------------------------
GEMINI 3 SERIES (Latest Flagship - GA):
1. gemini-3-pro-preview    - PRO: Deep reasoning, 65k output, 2M context ($2/$12 per 1M)
2. gemini-3-flash-preview  - FLASH: Speed + intelligence, 65k output, 1M context ($0.60/$2.50 per 1M)

GEMINI 2.5 SERIES (Stable Workhorses):
3. gemini-2.5-pro          - Stable production, 8k output, 2M context ($1.25/$10 per 1M)
4. gemini-2.5-flash        - High-volume, 8k output, 1M context ($0.30/$1.25 per 1M)
5. gemini-2.5-flash-lite   - Ultra-cheap simple tasks ($0.10/$0.40 per 1M)

SPECIALIZED:
6. deep-research-pro-preview-12-2025 - Autonomous 12+ page research reports

WHEN TO USE EACH:
-----------------
- FLASH (3): Smart chatbots, general assistance, scraping summaries, QA checks
- PRO (3): Complex coding, reasoning, analysis, report writing (65k output!)
- 2.5 FLASH: High-volume data processing where cost matters more than latest features
- 2.5 FLASH-LITE: Simple classification, extraction, categorizing

KEY UPGRADE: Gemini 3 has 65k max output tokens (vs 8k for 2.5) - can write entire files!

PRICING (January 2026):
-----------------------
Gemini 3 Pro:    $2.00 input / $12.00 output per 1M tokens (includes thinking tokens)
Gemini 3 Flash:  $0.60 input / $2.50 output per 1M tokens
Gemini 2.5 Pro:  $1.25 input / $10.00 output per 1M tokens
Gemini 2.5 Flash: $0.30 input / $1.25 output per 1M tokens
"""

from dataclasses import dataclass
from enum import Enum


class ModelType(Enum):
    """Types of AI tasks - maps to appropriate model."""
    SCRAPING = "scraping"           # Flash - summarizing scraped content
    LINK_SELECTION = "link_selection"  # Flash - intelligent link prioritization (which pages to scrape)
    QA = "qa"                       # Flash - quality checks
    SECTION_WRITING = "section_writing"  # Pro - writing report sections
    ANALYSIS = "analysis"           # Pro - complex analysis
    DEEP_RESEARCH = "deep_research"      # Deep Research Agent - 12+ page reports
    IMAGE = "image"                 # Image generation


@dataclass
class ModelConfig:
    """Configuration for a specific AI model."""
    name: str
    display_name: str
    provider: str
    cost_per_1m_input_tokens: float
    cost_per_1m_output_tokens: float
    max_input_tokens: int
    max_output_tokens: int
    supports_thinking: bool = True
    supports_tools: bool = True
    supports_multimodal: bool = True

    def __post_init__(self):
        pass


class ModelRegistry:
    """
    Registry of all available Gemini models.

    UPDATE THESE WHEN NEW MODELS ARE RELEASED.
    """

    # =========================================================================
    # GEMINI 3 FLASH - Speed + Intelligence balance (GA January 2026)
    # USE FOR: Smart chatbots, scraping summaries, link filtering, QA checks
    # $0.60 input / $2.50 output per 1M tokens
    # Context: 1M tokens, Output: 65k tokens
    # =========================================================================
    GEMINI_3_FLASH = ModelConfig(
        name="gemini-3-flash-preview",
        display_name="Gemini 3 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.60,
        cost_per_1m_output_tokens=2.50,
        max_input_tokens=1_000_000,      # 1M tokens
        max_output_tokens=65_536,        # 65k tokens (major upgrade from 2.5!)
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # GEMINI 3 PRO - Deep reasoning, complex tasks (GA January 2026)
    # USE FOR: Complex coding, reasoning, analysis, report writing
    # $2.00 input / $12.00 output per 1M tokens (includes thinking tokens)
    # Context: 2M tokens, Output: 65k tokens
    # =========================================================================
    GEMINI_3_PRO = ModelConfig(
        name="gemini-3-pro-preview",
        display_name="Gemini 3 Pro",
        provider="google",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=12.00,
        max_input_tokens=2_000_000,      # 2M tokens
        max_output_tokens=65_536,        # 65k tokens (can write entire files!)
        supports_thinking=True,          # Native Chain-of-Thought
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # GEMINI 2.5 PRO - Stable production workhorse
    # USE FOR: Stable production apps where predictability > newest features
    # $1.25 input / $10.00 output per 1M tokens
    # Context: 2M tokens, Output: 8k tokens
    # =========================================================================
    GEMINI_2_5_PRO = ModelConfig(
        name="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        provider="google",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=10.00,
        max_input_tokens=2_000_000,      # 2M tokens
        max_output_tokens=8_192,         # 8k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # GEMINI 2.5 FLASH - High-volume workhorse
    # USE FOR: High-volume data processing, cost-sensitive applications
    # $0.30 input / $1.25 output per 1M tokens
    # Context: 1M tokens, Output: 8k tokens
    # =========================================================================
    GEMINI_2_5_FLASH = ModelConfig(
        name="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.30,
        cost_per_1m_output_tokens=1.25,
        max_input_tokens=1_000_000,      # 1M tokens
        max_output_tokens=8_192,         # 8k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # GEMINI 3 PRO IMAGE - Image generation
    # $2.00 input (text) / $0.134 per image output
    # =========================================================================
    GEMINI_3_PRO_IMAGE = ModelConfig(
        name="gemini-3-pro-image-preview",
        display_name="Gemini 3 Pro Image",
        provider="google",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=120.00,  # Images are expensive
        max_input_tokens=65_536,
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # DEEP RESEARCH AGENT - Autonomous research producing 12+ page reports
    # This is a SEPARATE API (Interactions API), not generate_content
    # Uses Gemini 3 Pro under the hood
    # =========================================================================
    DEEP_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"


class PrimrModels:
    """
    CENTRALIZED MODEL ASSIGNMENTS FOR PRIMR
    =======================================

    THIS IS WHERE YOU CHANGE MODELS GLOBALLY.

    When Gemini 3.2 or 4.0 comes out:
    1. Add new model to ModelRegistry above
    2. Update FLASH_MODEL and/or PRO_MODEL below
    3. Done - all code uses these constants

    CURRENT ASSIGNMENTS (December 2025):
    ------------------------------------
    FLASH_MODEL = gemini-3-flash-preview  (cheap, fast - for scraping/filtering)
    PRO_MODEL   = gemini-3-pro-preview    (expensive, smart - for report writing)
    DEEP_RESEARCH_AGENT = deep-research-pro-preview-12-2025 (autonomous 12+ page reports)
    """

    # =========================================================================
    # PRIMARY MODELS - UPDATE THESE TO CHANGE MODELS GLOBALLY
    # =========================================================================
    FLASH_MODEL = ModelRegistry.GEMINI_3_FLASH.name    # Cheap - $0.50/$3 per 1M
    PRO_MODEL = ModelRegistry.GEMINI_3_PRO.name        # Expensive - $2/$12 per 1M
    DEEP_RESEARCH_AGENT = ModelRegistry.DEEP_RESEARCH_AGENT  # Autonomous 12+ page reports

    # =========================================================================
    # TASK-SPECIFIC ALIASES
    # Maps specific tasks to the appropriate model
    # =========================================================================

    # --- FLASH MODEL TASKS (cheap, fast) ---
    SCRAPING_MODEL = FLASH_MODEL          # Summarizing scraped website content
    LINK_SELECTION_MODEL = FLASH_MODEL    # Intelligent link prioritization - decides which pages to scrape
                                          # (acts like a human consultant choosing what to read)
    QA_MODEL = FLASH_MODEL                # Quality assurance checks

    # --- PRO MODEL TASKS (expensive, smart) ---
    SECTION_WRITING_MODEL = PRO_MODEL     # Writing report sections
    ANALYSIS_MODEL = PRO_MODEL            # Complex analysis, reasoning

    # --- IMAGE MODEL ---
    IMAGE_MODEL = ModelRegistry.GEMINI_3_PRO_IMAGE.name

    # =========================================================================
    # LEGACY ALIASES - For backward compatibility only
    # DO NOT USE IN NEW CODE - use the task-specific names above
    # =========================================================================
    FAST_MODEL = FLASH_MODEL              # Legacy alias
    REASONING_MODEL = PRO_MODEL           # Legacy alias
    FILTERING_MODEL = FLASH_MODEL         # DEPRECATED - use LINK_SELECTION_MODEL
    RESEARCH_MODEL = FLASH_MODEL          # DEPRECATED - confusing name, use SCRAPING_MODEL
    REPORT_MODEL = PRO_MODEL              # Legacy alias for SECTION_WRITING_MODEL

    # =========================================================================
    # NO FALLBACKS - If model fails, FAIL IMMEDIATELY
    # Don't silently switch to a different model
    # =========================================================================
    FALLBACK_MODELS: dict = {}  # Empty - no fallbacks

    # Model registry for lookups
    ALL_MODELS = {
        ModelRegistry.GEMINI_3_PRO.name: ModelRegistry.GEMINI_3_PRO,
        ModelRegistry.GEMINI_3_FLASH.name: ModelRegistry.GEMINI_3_FLASH,
        ModelRegistry.GEMINI_3_PRO_IMAGE.name: ModelRegistry.GEMINI_3_PRO_IMAGE,
        ModelRegistry.GEMINI_2_5_PRO.name: ModelRegistry.GEMINI_2_5_PRO,
        ModelRegistry.GEMINI_2_5_FLASH.name: ModelRegistry.GEMINI_2_5_FLASH,
    }

    @classmethod
    def get_model_for_type(cls, model_type: ModelType) -> str:
        """Get the recommended model for a specific task type."""
        type_mapping = {
            ModelType.SCRAPING: cls.SCRAPING_MODEL,
            ModelType.LINK_SELECTION: cls.LINK_SELECTION_MODEL,
            ModelType.QA: cls.QA_MODEL,
            ModelType.SECTION_WRITING: cls.SECTION_WRITING_MODEL,
            ModelType.ANALYSIS: cls.ANALYSIS_MODEL,
            ModelType.IMAGE: cls.IMAGE_MODEL,
            ModelType.DEEP_RESEARCH: cls.DEEP_RESEARCH_AGENT,
        }
        return type_mapping.get(model_type, cls.FLASH_MODEL)

    @classmethod
    def get_model_config(cls, model_name: str) -> ModelConfig | None:
        """Get configuration for a specific model."""
        return cls.ALL_MODELS.get(model_name)

    @classmethod
    def get_fallback_models(cls, model_name: str) -> list[str]:
        """Get fallback models for a given model. Returns empty - we fail fast."""
        return cls.FALLBACK_MODELS.get(model_name, [])

    @classmethod
    def is_latest_model(cls, model_name: str) -> bool:
        """Check if a model is one of the latest Gemini 3 models."""
        latest_models = {
            ModelRegistry.GEMINI_3_PRO.name,
            ModelRegistry.GEMINI_3_FLASH.name,
            ModelRegistry.GEMINI_3_PRO_IMAGE.name,
            ModelRegistry.DEEP_RESEARCH_AGENT,
            ModelRegistry.GEMINI_2_5_PRO.name,
            ModelRegistry.GEMINI_2_5_FLASH.name,
        }
        return model_name in latest_models


# =============================================================================
# CONVENIENCE CONSTANTS - Import these directly
# =============================================================================

# Primary models
FLASH_MODEL = PrimrModels.FLASH_MODEL
PRO_MODEL = PrimrModels.PRO_MODEL
DEEP_RESEARCH_AGENT = PrimrModels.DEEP_RESEARCH_AGENT

# Task-specific (preferred)
SCRAPING_MODEL = PrimrModels.SCRAPING_MODEL
LINK_SELECTION_MODEL = PrimrModels.LINK_SELECTION_MODEL
QA_MODEL = PrimrModels.QA_MODEL
SECTION_WRITING_MODEL = PrimrModels.SECTION_WRITING_MODEL
ANALYSIS_MODEL = PrimrModels.ANALYSIS_MODEL

# Legacy aliases (backward compatible - avoid in new code)
FAST_MODEL = PrimrModels.FAST_MODEL
REASONING_MODEL = PrimrModels.REASONING_MODEL
FILTERING_MODEL = PrimrModels.FILTERING_MODEL  # DEPRECATED - use LINK_SELECTION_MODEL
RESEARCH_MODEL = PrimrModels.RESEARCH_MODEL  # DEPRECATED
REPORT_MODEL = PrimrModels.REPORT_MODEL
