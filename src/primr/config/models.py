"""
Centralized Model Configuration for Primr
==========================================

THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL AI MODELS.
UPDATE HERE TO CHANGE MODELS GLOBALLY.

AVAILABLE MODELS (February 2026):
----------------------------------
GEMINI 3.1 SERIES (Preview - February 2026 — CURRENT DEFAULT PRO):
1. gemini-3.1-pro-preview  - Improved reasoning, token efficiency, factual consistency
   - Also: gemini-3.1-pro-preview-customtools (optimized for agentic/tool-heavy workflows)
   - TIERED PRICING: $2/$12 (prompts <=200k) | $4/$18 (prompts >200k) per 1M tokens

GEMINI 3 SERIES (GA January 2026):
2. gemini-3-pro-preview    - PRO: Deep reasoning, 65k output, 1M context ($2/$12 per 1M)
3. gemini-3-flash-preview  - FLASH: Speed + intelligence, 65k output, 1M context ($0.50/$3.00 per 1M)

GEMINI 2.5 SERIES (Stable Workhorses):
4. gemini-2.5-pro          - Stable production, 8k output, 2M context ($1.25/$10 per 1M)
5. gemini-2.5-flash        - High-volume, 8k output, 1M context ($0.30/$1.25 per 1M)
6. gemini-2.5-flash-lite   - Ultra-cheap simple tasks ($0.10/$0.40 per 1M)

SPECIALIZED:
7. deep-research-pro-preview-12-2025 - Autonomous 12+ page research reports

WHEN TO USE EACH:
-----------------
- FLASH (3): Smart chatbots, general assistance, scraping summaries, QA checks
- PRO (3): Complex coding, reasoning, analysis, report writing (65k output!)
- PRO (3.1): Same tasks as 3 Pro but with better thinking — use to validate before promoting
- 2.5 FLASH: High-volume data processing where cost matters more than latest features
- 2.5 FLASH-LITE: Simple classification, extraction, categorizing

KEY UPGRADE: Gemini 3 has 65k max output tokens (vs 8k for 2.5) - can write entire files!

PRICING (February 2026):
-------------------------
Gemini 3.1 Pro:  $2.00/$12.00 (prompts <=200k) | $4.00/$18.00 (prompts >200k) per 1M tokens
Gemini 3 Pro:    $2.00 input / $12.00 output per 1M tokens (includes thinking tokens)
Gemini 3 Flash:  $0.50 input / $3.00 output per 1M tokens
Gemini 2.5 Pro:  $1.25 input / $10.00 output per 1M tokens
Gemini 2.5 Flash: $0.30 input / $1.25 output per 1M tokens
"""

from dataclasses import dataclass
from enum import Enum


class GrokTier(str, Enum):
    """Grok model tier — controls quality/cost tradeoff in fast mode."""

    FAST = "fast"  # 4.1-fast everywhere (~$0.47)
    HYBRID = "hybrid"  # 4.20 reasoning + 4.1-fast writing (~$0.67) — DEFAULT
    MAX = "max"  # 4.20 everywhere (~$4.29)


class ModelType(Enum):
    """Types of AI tasks - maps to appropriate model."""

    SCRAPING = "scraping"  # Flash - summarizing scraped content
    LINK_SELECTION = (
        "link_selection"  # Flash - intelligent link prioritization (which pages to scrape)
    )
    QA = "qa"  # Flash - quality checks
    SECTION_WRITING = "section_writing"  # Pro - writing report sections
    ANALYSIS = "analysis"  # Pro - complex analysis
    DEEP_RESEARCH = "deep_research"  # Deep Research Agent - 12+ page reports
    IMAGE = "image"  # Image generation


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
    # Tiered pricing (optional) — higher rates when prompt exceeds threshold
    cost_per_1m_input_tokens_high: float | None = None
    cost_per_1m_output_tokens_high: float | None = None
    tier_threshold_tokens: int | None = None

    @property
    def has_tiered_pricing(self) -> bool:
        """Whether this model uses tiered pricing based on prompt size."""
        return (
            self.cost_per_1m_input_tokens_high is not None
            and self.cost_per_1m_output_tokens_high is not None
            and self.tier_threshold_tokens is not None
        )


class ModelRegistry:
    """
    Registry of all available Gemini models.

    UPDATE THESE WHEN NEW MODELS ARE RELEASED.
    """

    # =========================================================================
    # GEMINI 3 FLASH - Speed + Intelligence balance (GA January 2026)
    # USE FOR: Smart chatbots, scraping summaries, link filtering, QA checks
    # $0.50 input / $3.00 output per 1M tokens
    # Context: 1M tokens, Output: 65k tokens
    # =========================================================================
    GEMINI_3_FLASH = ModelConfig(
        name="gemini-3-flash-preview",
        display_name="Gemini 3 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.50,
        cost_per_1m_output_tokens=3.00,
        max_input_tokens=1_000_000,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens (major upgrade from 2.5!)
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
        max_input_tokens=2_000_000,  # 2M tokens
        max_output_tokens=65_536,  # 65k tokens (can write entire files!)
        supports_thinking=True,  # Native Chain-of-Thought
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # GEMINI 3.1 PRO - Improved reasoning, token efficiency (Preview Feb 2026)
    # DEFAULT PRO MODEL — better thinking, token efficiency, factual consistency
    # TIERED PRICING: $2/$12 (prompts <=200k) | $4/$18 (prompts >200k)
    # Context: 1M tokens, Output: 65k tokens
    # =========================================================================
    GEMINI_3_1_PRO = ModelConfig(
        name="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro Preview",
        provider="google",
        cost_per_1m_input_tokens=2.00,  # <=200k prompts
        cost_per_1m_output_tokens=12.00,  # <=200k prompts
        max_input_tokens=1_048_576,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_high=4.00,  # >200k prompts
        cost_per_1m_output_tokens_high=18.00,  # >200k prompts
        tier_threshold_tokens=200_000,
    )

    # =========================================================================
    # GEMINI 3.1 PRO CUSTOMTOOLS - Optimized for agentic/tool-heavy workflows
    # Better at prioritizing custom tools (view_file, search_code) over bash
    # Same pricing as 3.1 Pro
    # =========================================================================
    GEMINI_3_1_PRO_CUSTOMTOOLS = ModelConfig(
        name="gemini-3.1-pro-preview-customtools",
        display_name="Gemini 3.1 Pro Preview (Custom Tools)",
        provider="google",
        cost_per_1m_input_tokens=2.00,  # <=200k prompts
        cost_per_1m_output_tokens=12.00,  # <=200k prompts
        max_input_tokens=1_048_576,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_high=4.00,  # >200k prompts
        cost_per_1m_output_tokens_high=18.00,  # >200k prompts
        tier_threshold_tokens=200_000,
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
        max_input_tokens=2_000_000,  # 2M tokens
        max_output_tokens=8_192,  # 8k tokens
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
        max_input_tokens=1_000_000,  # 1M tokens
        max_output_tokens=8_192,  # 8k tokens
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
    # GROK 4.1 FAST REASONING - xAI fast reasoning model
    # USE FOR: Analytical tasks (gap analysis, workbook, cross-validation)
    # $0.20 input / $0.50 output per 1M tokens (+ reasoning tokens at output rate)
    # Context: 2M tokens, Output: 128k tokens
    # OpenAI-compatible API at https://api.x.ai/v1
    # =========================================================================
    GROK_4_1_FAST = ModelConfig(
        name="grok-4-1-fast-reasoning",
        display_name="Grok 4.1 Fast Reasoning",
        provider="xai",
        cost_per_1m_input_tokens=0.20,
        cost_per_1m_output_tokens=0.50,
        max_input_tokens=2_000_000,  # 2M tokens
        max_output_tokens=131_072,  # 128k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # GROK 4.1 FAST NON-REASONING - xAI fast model without reasoning overhead
    # USE FOR: Writing tasks (report batches, section regen, trust polish, AI strategy)
    # Same per-token pricing as reasoning variant, but no reasoning token overhead
    # → strictly faster and cheaper for prose generation
    # Context: 2M tokens, Output: 128k tokens
    # =========================================================================
    GROK_4_1_FAST_NR = ModelConfig(
        name="grok-4-1-fast-non-reasoning",
        display_name="Grok 4.1 Fast",
        provider="xai",
        cost_per_1m_input_tokens=0.20,
        cost_per_1m_output_tokens=0.50,
        max_input_tokens=2_000_000,  # 2M tokens
        max_output_tokens=131_072,  # 128k tokens
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # GROK 4.20 REASONING - xAI flagship model, lowest hallucination rate
    # USE FOR: High-leverage reasoning stages (gap analysis, workbook, cross-val)
    # $2.00 input / $6.00 output per 1M tokens
    # Context: 2M tokens, Output: 131k tokens
    # =========================================================================
    GROK_4_20_REASONING = ModelConfig(
        name="grok-4.20-0309-reasoning",
        display_name="Grok 4.20 Reasoning",
        provider="xai",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=6.00,
        max_input_tokens=2_000_000,
        max_output_tokens=131_072,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # GROK 4.20 NON-REASONING - xAI flagship without reasoning overhead
    # USE FOR: Writing tasks in max tier (report sections, strategy, polish)
    # $2.00 input / $6.00 output per 1M tokens
    # Context: 2M tokens, Output: 131k tokens
    # =========================================================================
    GROK_4_20_NR = ModelConfig(
        name="grok-4.20-0309-non-reasoning",
        display_name="Grok 4.20",
        provider="xai",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=6.00,
        max_input_tokens=2_000_000,
        max_output_tokens=131_072,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # GROK 4.20 MULTI-AGENT - xAI flagship with tool calling optimizations
    # Registered but not wired — no pipeline stage currently needs tool calling
    # $2.00 input / $6.00 output per 1M tokens
    # Context: 2M tokens, Output: 131k tokens
    # =========================================================================
    GROK_4_20_MULTI_AGENT = ModelConfig(
        name="grok-4.20-multi-agent-0309",
        display_name="Grok 4.20 Multi-Agent",
        provider="xai",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=6.00,
        max_input_tokens=2_000_000,
        max_output_tokens=131_072,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # DEEP RESEARCH AGENT - Autonomous research producing 12+ page reports
    # This is a SEPARATE API (Interactions API), not generate_content
    # Uses Gemini 3 Pro under the hood
    # =========================================================================
    DEEP_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"


@dataclass
class DeepResearchCost:
    """Per-task cost estimates. API doesn't expose tokens — these are approximate."""

    standard_task_cost: float = 2.50  # $2-3 typical (midpoint)
    complex_task_cost: float = 4.00  # $3-5 typical (midpoint)


DEEP_RESEARCH_COST = DeepResearchCost()
SEARCH_COST_PER_QUERY = 0.035  # $35/1000 queries


class PrimrModels:
    """
    CENTRALIZED MODEL ASSIGNMENTS FOR PRIMR
    =======================================

    THIS IS WHERE YOU CHANGE MODELS GLOBALLY.

    To upgrade to a new model:
    1. Add new model to ModelRegistry above
    2. Update FLASH_MODEL and/or PRO_MODEL below
    3. Done - all code uses these constants

    CURRENT ASSIGNMENTS (February 2026):
    ------------------------------------
    FLASH_MODEL = gemini-3-flash-preview       (cheap, fast - for scraping/filtering)
    PRO_MODEL   = gemini-3.1-pro-preview       (smart - for report writing, tiered pricing)
    DEEP_RESEARCH_AGENT = deep-research-pro-preview-12-2025 (autonomous 12+ page reports)

    ALSO AVAILABLE:
    ---------------
    gemini-3-pro-preview               - Previous default, flat $2/$12 pricing
    gemini-3.1-pro-preview-customtools - Same as 3.1 Pro + optimized for custom tool prioritization
    Override via AI_REASONING_MODEL env var in .env
    """

    # =========================================================================
    # PRIMARY MODELS - UPDATE THESE TO CHANGE MODELS GLOBALLY
    # =========================================================================
    FLASH_MODEL = ModelRegistry.GEMINI_3_FLASH.name  # Cheap - $0.50/$3 per 1M
    PRO_MODEL = ModelRegistry.GEMINI_3_1_PRO.name  # Smart - $2/$12 (≤200k) | $4/$18 (>200k)
    DEEP_RESEARCH_AGENT = ModelRegistry.DEEP_RESEARCH_AGENT  # Autonomous 12+ page reports

    # =========================================================================
    # TASK-SPECIFIC ALIASES
    # Maps specific tasks to the appropriate model
    # =========================================================================

    # --- FLASH MODEL TASKS (cheap, fast) ---
    SCRAPING_MODEL = FLASH_MODEL  # Summarizing scraped website content
    LINK_SELECTION_MODEL = (
        FLASH_MODEL  # Intelligent link prioritization - decides which pages to scrape
    )
    # (acts like a human consultant choosing what to read)
    QA_MODEL = FLASH_MODEL  # Quality assurance checks

    # --- PRO MODEL TASKS (expensive, smart) ---
    SECTION_WRITING_MODEL = PRO_MODEL  # Writing report sections
    ANALYSIS_MODEL = PRO_MODEL  # Complex analysis, reasoning

    # --- IMAGE MODEL ---
    IMAGE_MODEL = ModelRegistry.GEMINI_3_PRO_IMAGE.name

    # =========================================================================
    # LEGACY ALIASES - For backward compatibility only
    # DO NOT USE IN NEW CODE - use the task-specific names above
    # =========================================================================
    FAST_MODEL = FLASH_MODEL  # Legacy alias
    REASONING_MODEL = PRO_MODEL  # Legacy alias
    FILTERING_MODEL = FLASH_MODEL  # DEPRECATED - use LINK_SELECTION_MODEL
    RESEARCH_MODEL = FLASH_MODEL  # DEPRECATED - confusing name, use SCRAPING_MODEL
    REPORT_MODEL = PRO_MODEL  # Legacy alias for SECTION_WRITING_MODEL

    # =========================================================================
    # NO FALLBACKS - If model fails, FAIL IMMEDIATELY
    # Don't silently switch to a different model
    # =========================================================================
    FALLBACK_MODELS: dict = {}  # Empty - no fallbacks

    # --- GROK MODELS (xAI - for fast mode) ---
    GROK_MODEL = ModelRegistry.GROK_4_1_FAST.name  # Reasoning — analytical tasks
    GROK_MODEL_WRITING = ModelRegistry.GROK_4_1_FAST_NR.name  # Non-reasoning — writing tasks
    GROK_MODEL_420 = ModelRegistry.GROK_4_20_REASONING.name  # 4.20 reasoning — hybrid/max tier
    GROK_MODEL_420_WRITING = ModelRegistry.GROK_4_20_NR.name  # 4.20 non-reasoning — max tier

    # Model registry for lookups
    ALL_MODELS = {
        ModelRegistry.GEMINI_3_1_PRO.name: ModelRegistry.GEMINI_3_1_PRO,
        ModelRegistry.GEMINI_3_1_PRO_CUSTOMTOOLS.name: ModelRegistry.GEMINI_3_1_PRO_CUSTOMTOOLS,
        ModelRegistry.GEMINI_3_PRO.name: ModelRegistry.GEMINI_3_PRO,
        ModelRegistry.GEMINI_3_FLASH.name: ModelRegistry.GEMINI_3_FLASH,
        ModelRegistry.GEMINI_3_PRO_IMAGE.name: ModelRegistry.GEMINI_3_PRO_IMAGE,
        ModelRegistry.GEMINI_2_5_PRO.name: ModelRegistry.GEMINI_2_5_PRO,
        ModelRegistry.GEMINI_2_5_FLASH.name: ModelRegistry.GEMINI_2_5_FLASH,
        ModelRegistry.GROK_4_1_FAST.name: ModelRegistry.GROK_4_1_FAST,
        ModelRegistry.GROK_4_1_FAST_NR.name: ModelRegistry.GROK_4_1_FAST_NR,
        ModelRegistry.GROK_4_20_REASONING.name: ModelRegistry.GROK_4_20_REASONING,
        ModelRegistry.GROK_4_20_NR.name: ModelRegistry.GROK_4_20_NR,
        ModelRegistry.GROK_4_20_MULTI_AGENT.name: ModelRegistry.GROK_4_20_MULTI_AGENT,
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
    def get_grok_models(cls, tier: GrokTier) -> tuple[str, str]:
        """Return (reasoning_model, writing_model) for the given Grok tier."""
        if tier == GrokTier.HYBRID:
            return (cls.GROK_MODEL_420, cls.GROK_MODEL_WRITING)
        if tier == GrokTier.MAX:
            return (cls.GROK_MODEL_420, cls.GROK_MODEL_420_WRITING)
        # GrokTier.FAST (default)
        return (cls.GROK_MODEL, cls.GROK_MODEL_WRITING)

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
            ModelRegistry.GEMINI_3_1_PRO.name,
            ModelRegistry.GEMINI_3_1_PRO_CUSTOMTOOLS.name,
            ModelRegistry.GEMINI_3_PRO.name,
            ModelRegistry.GEMINI_3_FLASH.name,
            ModelRegistry.GEMINI_3_PRO_IMAGE.name,
            ModelRegistry.DEEP_RESEARCH_AGENT,
            ModelRegistry.GEMINI_2_5_PRO.name,
            ModelRegistry.GEMINI_2_5_FLASH.name,
        }
        return model_name in latest_models

    @classmethod
    def get_price(cls, model_name: str) -> tuple[float, float]:
        """Look up (input_price, output_price) per 1M tokens from ALL_MODELS."""
        config = cls.ALL_MODELS.get(model_name)
        if config is None:
            raise KeyError(f"Unknown model: {model_name}")
        return (config.cost_per_1m_input_tokens, config.cost_per_1m_output_tokens)

    @classmethod
    def calculate_cost(
        cls,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        prompt_tokens: int | None = None,
    ) -> float:
        """Calculate cost in USD for given token counts using model pricing.

        For tiered models, uses the high tier when prompt_tokens exceeds the
        tier threshold. When prompt_tokens is None, uses standard (low) tier.
        """
        config = cls.ALL_MODELS.get(model_name)
        if config is None:
            raise KeyError(f"Unknown model: {model_name}")

        if (
            config.has_tiered_pricing
            and prompt_tokens is not None
            and prompt_tokens > config.tier_threshold_tokens  # type: ignore[operator]
        ):
            inp_price = config.cost_per_1m_input_tokens_high  # type: ignore[assignment]
            out_price = config.cost_per_1m_output_tokens_high  # type: ignore[assignment]
        else:
            inp_price = config.cost_per_1m_input_tokens
            out_price = config.cost_per_1m_output_tokens

        return (input_tokens / 1_000_000) * inp_price + (output_tokens / 1_000_000) * out_price

    @classmethod
    def calculate_cost_conservative(
        cls, model_name: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost using the highest tier for tiered models.

        For flat-pricing models this is identical to calculate_cost().
        Use this for **pre-run estimates** where we don't know prompt sizes.
        """
        config = cls.ALL_MODELS.get(model_name)
        if config is None:
            raise KeyError(f"Unknown model: {model_name}")

        if config.has_tiered_pricing:
            inp_price = config.cost_per_1m_input_tokens_high  # type: ignore[assignment]
            out_price = config.cost_per_1m_output_tokens_high  # type: ignore[assignment]
        else:
            inp_price = config.cost_per_1m_input_tokens
            out_price = config.cost_per_1m_output_tokens

        return (input_tokens / 1_000_000) * inp_price + (output_tokens / 1_000_000) * out_price

    @classmethod
    def get_active_pro_model(cls) -> ModelConfig:
        """Return the ModelConfig for the active Pro model from settings.

        Reads ``get_settings().ai.pro_model`` (which honours the
        ``AI_REASONING_MODEL`` env-var) and falls back to the default
        GEMINI_3_PRO config when the resolved name isn't in ALL_MODELS.
        """
        from primr.config.settings import get_settings

        active_name = get_settings().ai.pro_model
        config = cls.ALL_MODELS.get(active_name)
        if config is not None:
            return config
        # Unknown model name — default to GEMINI_3_PRO
        return cls.ALL_MODELS[cls.PRO_MODEL]

    @classmethod
    def calculate_active_pro_cost(cls, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost using the active Pro model (standard tier)."""
        cfg = cls.get_active_pro_model()
        return cls.calculate_cost(cfg.name, input_tokens, output_tokens)

    @classmethod
    def calculate_active_pro_cost_conservative(cls, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost using the active Pro model at highest tier."""
        cfg = cls.get_active_pro_model()
        return cls.calculate_cost_conservative(cfg.name, input_tokens, output_tokens)

    @classmethod
    def calculate_flash_cost(cls, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost using Flash model pricing."""
        return cls.calculate_cost(cls.FLASH_MODEL, input_tokens, output_tokens)

    @classmethod
    def calculate_pro_cost(cls, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost using Pro model pricing."""
        return cls.calculate_cost(cls.PRO_MODEL, input_tokens, output_tokens)

    @classmethod
    def calculate_search_cost(cls, num_queries: int) -> float:
        """Calculate search cost at $0.035/query."""
        return num_queries * SEARCH_COST_PER_QUERY


# Module-level convenience functions
def get_price(model_name: str) -> tuple[float, float]:
    """Look up (input_price, output_price) per 1M tokens."""
    return PrimrModels.get_price(model_name)


def calculate_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    prompt_tokens: int | None = None,
) -> float:
    """Calculate cost in USD for given token counts."""
    return PrimrModels.calculate_cost(
        model_name, input_tokens, output_tokens, prompt_tokens=prompt_tokens
    )


def calculate_flash_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost using Flash model pricing."""
    return PrimrModels.calculate_flash_cost(input_tokens, output_tokens)


def calculate_pro_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost using Pro model pricing."""
    return PrimrModels.calculate_pro_cost(input_tokens, output_tokens)


def calculate_search_cost(num_queries: int) -> float:
    """Calculate search cost at $0.035/query."""
    return PrimrModels.calculate_search_cost(num_queries)


# =============================================================================
# CONVENIENCE CONSTANTS - Import these directly
# =============================================================================

# Primary models
FLASH_MODEL = PrimrModels.FLASH_MODEL
PRO_MODEL = PrimrModels.PRO_MODEL
DEEP_RESEARCH_AGENT = PrimrModels.DEEP_RESEARCH_AGENT
GROK_MODEL = PrimrModels.GROK_MODEL
GROK_MODEL_WRITING = PrimrModels.GROK_MODEL_WRITING
GROK_MODEL_420 = PrimrModels.GROK_MODEL_420
GROK_MODEL_420_WRITING = PrimrModels.GROK_MODEL_420_WRITING

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
