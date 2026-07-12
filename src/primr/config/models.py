"""
Centralized Model Configuration for Primr
==========================================

THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL AI MODELS.
UPDATE HERE TO CHANGE MODELS GLOBALLY.

Last audited: July 1, 2026 (refresh of the June 29 audit), checked against
current provider docs (developers.openai.com, ai.google.dev, docs.x.ai) and the
Anthropic model catalog. Re-audit before each major eval — see ROADMAP "Model
Adaptability".

KEY CHANGES (June 29, 2026 audit):
- OpenAI context/output corrected: gpt-5.4 is ~1M ctx (not 200K) and now carries
  the >270K long-context surcharge; gpt-5.4-mini/-nano are 400K ctx; all gpt-5.x
  max-output is 128k (gpt-5.4-nano's 16k cap was wrong). Prices unchanged.
- GPT-5.4 mini/nano now carry the same >270K long-context surcharge metadata
  as the flagship GPT-5.x entries so estimates surface the selected tier.
- Gemini: gemini-2.5-pro is 1M ctx (the 2M figure belongs to the unreleased 3.5
  Pro); the whole Gemini 2.5 family is now deprecated (~Oct 16, 2026 shutdown);
  Deep Research slug refreshed to deep-research-preview-04-2026; cached-input
  rates filled in for the 3.x/2.5 entries.
- Anthropic: claude-haiku-3-5 retired Feb 19, 2026 (404) — marked deprecated.
  Sonnet 5 is the balanced default; Opus 4.7+/Sonnet 5/Fable-5 reject
  temperature, current effort values include max/xhigh, and adaptive-thinking
  tiers reject manual thinking budgets (handled in ai/providers/anthropic.py).
- xAI Grok 4.3 reasoning is NOT always-on — reasoning_effort has four levels
  (none/low/medium/high, default low); published output cap is unverified.

AVAILABLE MODELS (June 2026):
------------------------------
xAI / GROK:
  grok-4.3                   - Flagship reasoning, $1.25/$2.50 + $0.20 cached, 1M context
                               No published >200K tier (flat rate)
  grok-4.20-non-reasoning    - Bulk writing replacement after 4.1 retirement, $2/$6
  grok-4.1-fast-*            - DEPRECATED, retired May 15, 2026

GOOGLE / GEMINI:
  gemini-3.5-flash           - NEW (GA May 19, 2026, I/O '26), $1.50/$9.00 + $0.15 cached,
                               1M ctx, 65k out. Beats 3.1 Pro on benchmarks at lower cost.
                               AVAILABLE but not yet a default tier — Pro-tier replacement
                               candidate (eval-gated). 3.5 Pro (June) + Omni (weeks) pending.
  gemini-3.1-pro-preview     - PRO default, $2/$12 (<=200k) | $4/$18 (>200k), 1M ctx, 65k out
  gemini-3.1-flash-lite      - $0.25/$1.50, 1M ctx, 65k out
                               Leading writing-tier candidate for v1.24.0 sub-$1 default
  gemini-3-flash-preview     - $0.50/$3.00, 1M ctx, 65k out
  gemini-3-pro-preview       - DEPRECATED Mar 9, 2026 (replaced by 3.1 Pro)
  gemini-2.5-flash-lite      - Ultra-cheap, $0.10/$0.40
  gemini-2.5-flash           - $0.30/$2.50, 1M ctx (output rate updated May 2026)
  gemini-2.5-pro             - Stable workhorse, $1.25/$10, 2M ctx, 8k out
  deep-research-preview-04-2026 - Autonomous 12+ page research reports

OPENAI:
  gpt-5.5                    - Flagship, $5.00/$30.00 + $0.50 cached, 1M ctx
  gpt-5.4                    - Affordable flagship, $2.50/$15.00 + $0.25 cached, 200k ctx
  gpt-5.4-mini               - Utility candidate, $0.75/$4.50, 400k ctx
  gpt-5.4-nano               - Ultra-cheap, $0.20/$1.25, 400k ctx, 128k out cap
  o4-mini                    - Reasoning, $1.10/$4.40, alternative to Grok 4.3
  All gpt-5.x: 2x input / 1.5x output above 270K input tokens.

ANTHROPIC:
  claude-opus-4-8            - Most capable (GA May 28, 2026), $5.00/$25.00 + $0.50 cached,
                               1M ctx, 128k out. Drop-in over 4.7 (identical pricing).
  claude-sonnet-5            - Balance, $3.00/$15.00 + $0.30 cached estimate,
                               1M ctx, 128k out. Actual launch pricing is
                               $2/$10 through Aug 31, 2026, then returns to
                               Sonnet 4.6 pricing per Anthropic.
  claude-sonnet-4-6          - Previous balance tier, $3.00/$15.00 + $0.30 cached,
                               1M ctx, 64k out. Registered for explicit back-compat.
  claude-haiku-4-5           - Utility candidate, $1.00/$5.00 + $0.10 cached, 200k ctx
  claude-haiku-3-5           - Cheaper utility option, $0.80/$4.00 + $0.08 cached, 200k ctx

OLLAMA (zero marginal cost):
  qwen3-coder:30b, qwen2.5:32b, deepseek-r1:32b, qwen3:7b — 24GB VRAM compatible

WHEN TO USE EACH (post-v1.24.0 eval-driven defaults will refine these):
-----------------------------------------------------------------------
- UTILITY tier (scraping summaries, link selection, QA): Gemini 3 Flash or Flash-Lite
- WRITING tier (bulk section generation): Gemini 3.1 Flash-Lite (cheapest sub-$1 candidate)
- REASONING tier (gap analysis, workbook, cross-validation): Grok 4.3 with cache
- PREMIUM tier (Deep Research): Gemini Deep Research Agent

KEY CHANGES (May 30, 2026 refresh):
- Claude Opus 4.7 -> 4.8 (`claude-opus-4-8`, GA May 28). Identical pricing; the
  canonical Anthropic flagship slug swapped repo-wide (registry, fallback chain,
  routing tests). Historical CHANGELOG references to 4.7 left intact.
- Gemini 3.5 Flash (`gemini-3.5-flash`, GA May 19) REGISTERED as available, not
  yet a default tier. Stronger than 3.1 Pro at lower cost ($1.50/$9 vs $2/$12) —
  a Pro-tier replacement candidate, NOT a sub-$1 writing-tier swap. Default
  repoint is eval-gated. Gemini 3.5 Pro (June) + Omni (weeks) not yet on the API.
- xAI Grok 4.3 remains flagship; new Grok Build 0.1 is coding-specialized and not
  relevant to primr's research/writing pipeline. OpenAI GPT-5.5 remains latest.

KEY CHANGES SINCE v1.22.0:
- Grok 4.1 line retired May 15, 2026 — `deprecated=True` on legacy entries
- Grok 4.3 high-tier (>200K) placeholder REMOVED (xAI publishes no such tier)
- Every gpt-5.x price updated (May 2026 audit found Feb registry prices stale)
- Gemini 3.1 Flash-Lite added (Mar 2026 release, primary writing-tier candidate)
- Gemini 3 Pro Preview marked deprecated (replaced by 3.1 Pro)
- Gemini 2.5 Flash-Lite registered as ModelConfig (was only in module docstring)
- o4-mini added as Grok 4.3 reasoning alternative
- Haiku 3.5 added as alternate utility-tier candidate
"""

from dataclasses import dataclass

from primr.config.model_registry import (
    GrokTier,
    ModelConfig,
    ModelRegistry,
    ModelType,
)


@dataclass
class DeepResearchCost:
    """Planning estimates for variable token-and-tool Deep Research billing."""

    standard_task_cost: float = 2.50  # Conservative point in Google's typical ~$1-$3 range
    complex_task_cost: float = 4.00  # Planning point in the documented ~$3-$7 Max range


@dataclass(frozen=True)
class TokenCostBreakdown:
    """Detailed token-cost math for one model call or estimate bucket."""

    model_name: str
    input_tokens: int
    output_tokens: int
    live_input_tokens: int
    cached_input_tokens: int
    input_cost: float
    live_input_cost: float
    cached_input_cost: float
    output_cost: float
    total_cost: float
    input_rate_per_million: float
    cached_input_rate_per_million: float
    output_rate_per_million: float
    tier_applied: bool
    tier_threshold_tokens: int | None
    long_context_surcharge_cost: float


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

    CURRENT ASSIGNMENTS (July 2026):
    ------------------------------------
    FLASH_MODEL = gemini-3-flash-preview       (cheap, fast - for scraping/filtering)
    PRO_MODEL   = gemini-3.1-pro-preview       (smart - for report writing, tiered pricing)
    DEEP_RESEARCH_AGENT = deep-research-preview-04-2026 (autonomous 12+ page reports)

    OTHER REGISTRY ENTRIES:
    -----------------------
    gemini-3-pro-preview               - Deprecated; replaced by 3.1 Pro
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
    GROK_MODEL = ModelRegistry.GROK_4_3.name  # 4.3 reasoning — replaces retired 4.1-fast
    GROK_MODEL_WRITING = (
        ModelRegistry.GROK_4_20_NR_NEW.name
    )  # 4.20 non-reasoning — replaces retired 4.1-fast-nr
    GROK_MODEL_43 = ModelRegistry.GROK_4_3.name  # 4.3 — current flagship for hybrid/max tier
    # Legacy 4.20 constants — kept for back-compat and resume of in-flight runs.
    # New code should use GROK_MODEL_43.
    GROK_MODEL_420 = ModelRegistry.GROK_4_20_REASONING.name
    GROK_MODEL_420_WRITING = ModelRegistry.GROK_4_20_NR.name

    # Model registry for lookups
    ALL_MODELS = {
        # Google / Gemini
        ModelRegistry.GEMINI_3_5_FLASH.name: ModelRegistry.GEMINI_3_5_FLASH,
        ModelRegistry.GEMINI_3_1_PRO.name: ModelRegistry.GEMINI_3_1_PRO,
        ModelRegistry.GEMINI_3_1_PRO_CUSTOMTOOLS.name: ModelRegistry.GEMINI_3_1_PRO_CUSTOMTOOLS,
        ModelRegistry.GEMINI_3_1_FLASH_LITE.name: ModelRegistry.GEMINI_3_1_FLASH_LITE,
        ModelRegistry.GEMINI_3_PRO.name: ModelRegistry.GEMINI_3_PRO,
        ModelRegistry.GEMINI_3_FLASH.name: ModelRegistry.GEMINI_3_FLASH,
        ModelRegistry.GEMINI_3_PRO_IMAGE.name: ModelRegistry.GEMINI_3_PRO_IMAGE,
        ModelRegistry.GEMINI_2_5_PRO.name: ModelRegistry.GEMINI_2_5_PRO,
        ModelRegistry.GEMINI_2_5_FLASH.name: ModelRegistry.GEMINI_2_5_FLASH,
        ModelRegistry.GEMINI_2_5_FLASH_LITE.name: ModelRegistry.GEMINI_2_5_FLASH_LITE,
        # xAI / Grok
        ModelRegistry.GROK_4_1_FAST.name: ModelRegistry.GROK_4_1_FAST,
        ModelRegistry.GROK_4_1_FAST_NR.name: ModelRegistry.GROK_4_1_FAST_NR,
        ModelRegistry.GROK_4_3.name: ModelRegistry.GROK_4_3,
        ModelRegistry.GROK_4_20_REASONING.name: ModelRegistry.GROK_4_20_REASONING,
        ModelRegistry.GROK_4_20_NR.name: ModelRegistry.GROK_4_20_NR,
        ModelRegistry.GROK_4_20_NR_NEW.name: ModelRegistry.GROK_4_20_NR_NEW,
        ModelRegistry.GROK_4_20_MULTI_AGENT.name: ModelRegistry.GROK_4_20_MULTI_AGENT,
        # OpenAI
        ModelRegistry.OPENAI_GPT_5_5.name: ModelRegistry.OPENAI_GPT_5_5,
        ModelRegistry.OPENAI_GPT_5_4.name: ModelRegistry.OPENAI_GPT_5_4,
        ModelRegistry.OPENAI_GPT_5_4_MINI.name: ModelRegistry.OPENAI_GPT_5_4_MINI,
        ModelRegistry.OPENAI_GPT_5_4_NANO.name: ModelRegistry.OPENAI_GPT_5_4_NANO,
        ModelRegistry.OPENAI_O4_MINI.name: ModelRegistry.OPENAI_O4_MINI,
        # Anthropic
        ModelRegistry.ANTHROPIC_OPUS.name: ModelRegistry.ANTHROPIC_OPUS,
        ModelRegistry.ANTHROPIC_SONNET.name: ModelRegistry.ANTHROPIC_SONNET,
        ModelRegistry.ANTHROPIC_SONNET_4_6.name: ModelRegistry.ANTHROPIC_SONNET_4_6,
        ModelRegistry.ANTHROPIC_HAIKU.name: ModelRegistry.ANTHROPIC_HAIKU,
        ModelRegistry.ANTHROPIC_HAIKU_3_5.name: ModelRegistry.ANTHROPIC_HAIKU_3_5,
        # Ollama (local, zero cost) — original four
        ModelRegistry.OLLAMA_QWEN3_CODER_30B.name: ModelRegistry.OLLAMA_QWEN3_CODER_30B,
        ModelRegistry.OLLAMA_QWEN2_5_32B.name: ModelRegistry.OLLAMA_QWEN2_5_32B,
        ModelRegistry.OLLAMA_DEEPSEEK_R1_32B.name: ModelRegistry.OLLAMA_DEEPSEEK_R1_32B,
        ModelRegistry.OLLAMA_QWEN3_7B.name: ModelRegistry.OLLAMA_QWEN3_7B,
        # Ollama — May 2026 RTX 4090 candidates added for v1.24.0 eval matrix
        ModelRegistry.OLLAMA_QWEN3_32B.name: ModelRegistry.OLLAMA_QWEN3_32B,
        ModelRegistry.OLLAMA_QWEN3_6_35B_A3B.name: ModelRegistry.OLLAMA_QWEN3_6_35B_A3B,
        ModelRegistry.OLLAMA_GEMMA3_27B.name: ModelRegistry.OLLAMA_GEMMA3_27B,
        ModelRegistry.OLLAMA_LLAMA4_SCOUT.name: ModelRegistry.OLLAMA_LLAMA4_SCOUT,
        ModelRegistry.OLLAMA_GLM_4_6.name: ModelRegistry.OLLAMA_GLM_4_6,
        ModelRegistry.OLLAMA_PHI4_14B.name: ModelRegistry.OLLAMA_PHI4_14B,
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
        """Return (reasoning_model, writing_model) for the given Grok tier.

        Post-retirement tier mapping (May 2026):
        FAST: grok-4.3 (reasoning_effort=low) + grok-4.20-non-reasoning
        HYBRID: grok-4.3 + grok-4.20-non-reasoning
        MAX: grok-4.3 + grok-4.3

        FAST and HYBRID now use the same models; the difference is in
        reasoning_effort parameter (low for FAST, default/high for HYBRID)
        which is a runtime concern handled by the caller.
        """
        if tier == GrokTier.FAST:
            return (cls.GROK_MODEL_43, cls.GROK_MODEL_WRITING)
        if tier == GrokTier.HYBRID:
            return (cls.GROK_MODEL_43, cls.GROK_MODEL_WRITING)
        # GrokTier.MAX
        return (cls.GROK_MODEL_43, cls.GROK_MODEL_43)

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
        cached_input_tokens: int = 0,
    ) -> float:
        """Calculate cost in USD for given token counts using model pricing."""
        return cls.calculate_cost_breakdown(
            model_name,
            input_tokens,
            output_tokens,
            prompt_tokens=prompt_tokens,
            cached_input_tokens=cached_input_tokens,
        ).total_cost

    @classmethod
    def calculate_cost_breakdown(
        cls,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        prompt_tokens: int | None = None,
        cached_input_tokens: int = 0,
        force_high_tier: bool = False,
    ) -> TokenCostBreakdown:
        """Calculate detailed token costs for one model.

        For tiered models, the high tier applies when ``prompt_tokens`` exceeds
        the model threshold or when ``force_high_tier`` is true. Cached input
        tokens are billed at the model's cached rate when one is configured;
        otherwise they fall through to the selected live-input rate.

        The long-context surcharge is reported as the delta between the
        selected tier and the base tier for the same live-input, cached-input,
        and output counts. It is zero for flat-priced models and for standard
        tier calls.
        """
        config = cls.ALL_MODELS.get(model_name)
        if config is None:
            raise KeyError(f"Unknown model: {model_name}")

        input_tokens = max(0, input_tokens)
        output_tokens = max(0, output_tokens)
        cached_input_tokens = max(0, min(cached_input_tokens, input_tokens))
        live_input_tokens = input_tokens - cached_input_tokens

        tier_applied = (
            config.has_tiered_pricing
            and config.tier_threshold_tokens is not None
            and (
                force_high_tier
                or (prompt_tokens is not None and prompt_tokens > config.tier_threshold_tokens)
            )
        )
        if tier_applied:
            input_rate = config.cost_per_1m_input_tokens_high
            output_rate = config.cost_per_1m_output_tokens_high
            if input_rate is None or output_rate is None:  # pragma: no cover
                raise ValueError(
                    f"Model {model_name} has tiered pricing but missing high-tier rates"
                )
        else:
            input_rate = config.cost_per_1m_input_tokens
            output_rate = config.cost_per_1m_output_tokens

        cache_rate = config.cost_per_1m_input_tokens_cached
        selected_cache_rate = cache_rate if cache_rate is not None else input_rate
        live_input_cost = (live_input_tokens / 1_000_000) * input_rate
        cached_input_cost = (cached_input_tokens / 1_000_000) * selected_cache_rate
        output_cost = (output_tokens / 1_000_000) * output_rate
        total_cost = live_input_cost + cached_input_cost + output_cost

        base_cache_rate = cache_rate if cache_rate is not None else config.cost_per_1m_input_tokens
        base_total = (
            (live_input_tokens / 1_000_000) * config.cost_per_1m_input_tokens
            + (cached_input_tokens / 1_000_000) * base_cache_rate
            + (output_tokens / 1_000_000) * config.cost_per_1m_output_tokens
        )
        surcharge = max(0.0, total_cost - base_total)

        return TokenCostBreakdown(
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            live_input_tokens=live_input_tokens,
            cached_input_tokens=cached_input_tokens,
            input_cost=live_input_cost + cached_input_cost,
            live_input_cost=live_input_cost,
            cached_input_cost=cached_input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            input_rate_per_million=input_rate,
            cached_input_rate_per_million=selected_cache_rate,
            output_rate_per_million=output_rate,
            tier_applied=tier_applied,
            tier_threshold_tokens=config.tier_threshold_tokens,
            long_context_surcharge_cost=surcharge,
        )

    @classmethod
    def calculate_cost_conservative(
        cls, model_name: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost using the highest tier for tiered models.

        For flat-pricing models this is identical to calculate_cost().
        Use this for **pre-run estimates** where we don't know prompt sizes.
        All token counts are clamped to non-negative values defensively.
        """
        config = cls.ALL_MODELS.get(model_name)
        if config is None:
            raise KeyError(f"Unknown model: {model_name}")

        # Defensive: clamp to non-negative
        input_tokens = max(0, input_tokens)
        output_tokens = max(0, output_tokens)

        return cls.calculate_cost_breakdown(
            model_name,
            input_tokens,
            output_tokens,
            force_high_tier=config.has_tiered_pricing,
        ).total_cost

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
    cached_input_tokens: int = 0,
) -> float:
    """Calculate cost in USD for given token counts."""
    return PrimrModels.calculate_cost(
        model_name,
        input_tokens,
        output_tokens,
        prompt_tokens=prompt_tokens,
        cached_input_tokens=cached_input_tokens,
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
GROK_MODEL_43 = PrimrModels.GROK_MODEL_43
GROK_MODEL_420 = PrimrModels.GROK_MODEL_420  # legacy, keep for back-compat
GROK_MODEL_420_WRITING = PrimrModels.GROK_MODEL_420_WRITING  # legacy

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
