"""
Centralized Model Configuration for Primr
==========================================

THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL AI MODELS.
UPDATE HERE TO CHANGE MODELS GLOBALLY.

AVAILABLE MODELS (December 2025):
---------------------------------
1. gemini-3-flash-preview  - FLASH: Fast, cheap ($0.50/$3 per 1M tokens)
2. gemini-3-pro-preview    - PRO: Complex reasoning ($2/$12 per 1M tokens)  
3. deep-research-pro-preview-12-2025 - DEEP RESEARCH: Autonomous 12+ page reports

WHEN TO USE EACH:
-----------------
- FLASH: Scraping summaries, link selection (which pages to scrape), QA checks
- PRO: Report section writing, complex analysis, reasoning tasks
- DEEP RESEARCH: Autonomous multi-step research producing 12+ page reports

TASK-SPECIFIC MODEL ASSIGNMENTS:
--------------------------------
SCRAPING_MODEL       = Flash - Summarizing scraped website content
LINK_SELECTION_MODEL = Flash - Intelligent link prioritization (which pages to scrape)
                              Acts like a human consultant deciding what to read
QA_MODEL             = Flash - Quality assurance checks
SECTION_WRITING_MODEL = Pro  - Writing report sections with analysis
ANALYSIS_MODEL        = Pro  - Complex analysis, reasoning tasks

UPDATING FOR NEW MODELS:
------------------------
When Gemini 3.2 or 4.0 comes out:
1. Update ModelRegistry with new model configs
2. Update FLASH_MODEL and PRO_MODEL in PrimrModels
3. That's it - all code uses these constants

PRICING (December 2025):
------------------------
Flash:  $0.50 input / $3.00 output per 1M tokens
Pro:    $2.00 input / $12.00 output per 1M tokens (<200k context)
        $4.00 input / $18.00 output per 1M tokens (>200k context)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


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
    # GEMINI 3 FLASH - Fast, cheap, good for simple tasks
    # USE FOR: Scraping summaries, link filtering, QA checks
    # $0.50 input / $3.00 output per 1M tokens
    # =========================================================================
    GEMINI_3_FLASH = ModelConfig(
        name="gemini-3-flash-preview", 
        display_name="Gemini 3 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.50,
        cost_per_1m_output_tokens=3.00,
        max_input_tokens=1_048_576,      # 1M tokens
        max_output_tokens=65_536,        # 64k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )
    
    # =========================================================================
    # GEMINI 3 PRO - Complex reasoning, expensive but smart
    # USE FOR: Report section writing, complex analysis
    # $2.00 input / $12.00 output per 1M tokens (<200k context)
    # $4.00 input / $18.00 output per 1M tokens (>200k context)
    # =========================================================================
    GEMINI_3_PRO = ModelConfig(
        name="gemini-3-pro-preview",
        display_name="Gemini 3 Pro",
        provider="google",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=12.00,
        max_input_tokens=1_048_576,      # 1M tokens
        max_output_tokens=65_536,        # 64k tokens
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
    def get_model_config(cls, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for a specific model."""
        return cls.ALL_MODELS.get(model_name)
    
    @classmethod
    def get_fallback_models(cls, model_name: str) -> List[str]:
        """Get fallback models for a given model. Returns empty - we fail fast."""
        return cls.FALLBACK_MODELS.get(model_name, [])
    
    @classmethod
    def is_latest_model(cls, model_name: str) -> bool:
        """Check if a model is one of the latest Gemini 3 models."""
        latest_models = {
            ModelRegistry.GEMINI_3_PRO.name,
            ModelRegistry.GEMINI_3_FLASH.name, 
            ModelRegistry.GEMINI_3_PRO_IMAGE.name,
            ModelRegistry.DEEP_RESEARCH_AGENT
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
