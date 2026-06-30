"""Model registry data: AI model configs and the registry of all models.

Extracted from ``config/models.py`` (the single source of truth and audit
log) so the volatile per-model data block stays separate from the cost and
selection logic. Update model entries HERE when providers release or retire
models; see ``config/models.py`` for the audit history and the ``PrimrModels``
selection facade. Symbols are re-exported from ``config.models`` so existing
``from primr.config.models import ModelRegistry`` imports keep working.
"""

from dataclasses import dataclass
from enum import Enum


class GrokTier(str, Enum):
    """Grok model tier — controls quality/cost tradeoff in fast mode."""

    FAST = "fast"  # 4.3 (reasoning_effort=low) + 4.20-nr (~$4.36 base)
    HYBRID = "hybrid"  # 4.3 + 4.20-nr (~$4.36 base, same models, default effort) - DEFAULT
    MAX = "max"  # 4.3 everywhere (~$3.75)


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
    # Cached input pricing (optional) — discount rate for cache hits
    cost_per_1m_input_tokens_cached: float | None = None
    # Deprecation flag — model is retiring and should not be used in new routing
    deprecated: bool = False

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
    # ⚠️ DEPRECATED March 9, 2026 — replaced by gemini-3.1-pro-preview.
    # Kept registered for historical eval comparison and back-compat only.
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
        deprecated=True,  # Replaced by gemini-3.1-pro-preview on 2026-03-09
    )

    # =========================================================================
    # GEMINI 3.1 FLASH-LITE - Cheapest Gemini-3-era model (released March 3, 2026)
    # USE FOR: Bulk writing — leading writing-tier candidate for v1.24.0 sub-$1 default.
    # $0.25 input / $1.50 output per 1M tokens (half the price of Gemini 3 Flash).
    # Batch mode: $0.125 / $0.75 (50% off, currently unmodeled in cost estimator).
    # Context: 1M tokens, Output: 65k tokens.
    # ADDED: May 2026 audit — was missing from registry; this is the model that
    # didn't exist when v1.22.0 was designed. With Grok 4.3 (cached) for reasoning,
    # this brings the default pipeline back under $1.
    # =========================================================================
    GEMINI_3_1_FLASH_LITE = ModelConfig(
        name="gemini-3.1-flash-lite",
        display_name="Gemini 3.1 Flash-Lite",
        provider="google",
        cost_per_1m_input_tokens=0.25,
        cost_per_1m_output_tokens=1.50,
        max_input_tokens=1_048_576,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.025,  # Confirmed June 2026 (docs)
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
    # GEMINI 3.5 FLASH - Frontier agentic/coding Flash (GA May 19, 2026, I/O '26)
    # Google's strongest agentic + coding model in the Flash line; benchmarks
    # above Gemini 3.1 Pro at lower cost. Registered as AVAILABLE; NOT yet wired
    # as a default tier — switching the PRO tier (gemini-3.1-pro-preview, $2/$12)
    # to this ($1.50/$9, cheaper AND stronger) is eval-gated. See ROADMAP
    # "Engineering Standards" / "Model Adaptability". NOTE: this is dearer than
    # gemini-3.1-flash-lite ($0.25/$1.50), so it is a Pro-tier replacement
    # candidate, NOT a sub-$1 writing-tier swap.
    # $1.50 input / $9.00 output per 1M tokens, cached input $0.15. No tiered
    # (>200k) pricing. Context: 1M tokens, Output: 65k tokens.
    # Sibling models from the same launch not yet GA on the API: Gemini 3.5 Pro
    # (rolling out June 2026) and Gemini Omni (multimodal video, weeks out) —
    # register them once their API slugs go live.
    # =========================================================================
    GEMINI_3_5_FLASH = ModelConfig(
        name="gemini-3.5-flash",
        display_name="Gemini 3.5 Flash",
        provider="google",
        cost_per_1m_input_tokens=1.50,
        cost_per_1m_output_tokens=9.00,
        max_input_tokens=1_048_576,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.15,
    )

    # =========================================================================
    # GEMINI 2.5 PRO - Stable production workhorse
    # USE FOR: Stable production apps where predictability > newest features
    # $1.25 input / $10.00 output per 1M tokens
    # Context: 1M tokens, Output: 8k tokens
    # June 2026 audit: context is 1M (1,048,576), NOT 2M — the 2M figure belongs
    # to the unreleased Gemini 3.5 Pro. Now DEPRECATED (earliest shutdown
    # Oct 16, 2026) → migrate to gemini-3.1-pro-preview.
    # =========================================================================
    GEMINI_2_5_PRO = ModelConfig(
        name="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        provider="google",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=10.00,
        max_input_tokens=1_048_576,  # 1M tokens (was wrongly 2M)
        max_output_tokens=8_192,  # 8k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.125,  # Confirmed June 2026 (docs)
        deprecated=True,  # Earliest shutdown 2026-10-16 → gemini-3.1-pro-preview
    )

    # =========================================================================
    # GEMINI 2.5 FLASH - High-volume workhorse
    # USE FOR: High-volume data processing, cost-sensitive applications
    # $0.30 input / $2.50 output per 1M tokens
    # PRICING UPDATED: May 2026 audit — output rate moved from $1.25 to $2.50.
    # Context: 1M tokens, Output: 8k tokens
    # =========================================================================
    GEMINI_2_5_FLASH = ModelConfig(
        name="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.30,
        cost_per_1m_output_tokens=2.50,
        max_input_tokens=1_000_000,  # 1M tokens
        max_output_tokens=8_192,  # 8k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.03,  # Confirmed June 2026 (docs)
        deprecated=True,  # June 2026 audit: shutdown ~2026-10-16 → gemini-3.5-flash
    )

    # =========================================================================
    # GEMINI 2.5 FLASH-LITE - Ultra-cheap utility tier
    # USE FOR: Simple classification, extraction, categorizing
    # $0.10 input / $0.40 output per 1M tokens
    # Context: 1M tokens, Output: 8k tokens
    # REGISTERED: May 2026 audit — was documented in module docstring but never
    # registered as a ModelConfig. Now registered for inclusion in v1.24.0 eval.
    # =========================================================================
    GEMINI_2_5_FLASH_LITE = ModelConfig(
        name="gemini-2.5-flash-lite",
        display_name="Gemini 2.5 Flash-Lite",
        provider="google",
        cost_per_1m_input_tokens=0.10,
        cost_per_1m_output_tokens=0.40,
        max_input_tokens=1_000_000,  # 1M tokens
        max_output_tokens=8_192,  # 8k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.01,  # Confirmed June 2026 (docs)
        deprecated=True,  # June 2026 audit: shutdown ~2026-10-16 → gemini-3.1-flash-lite
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
        deprecated=True,  # Retiring May 15, 2026 — use grok-4.3 instead
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
        deprecated=True,  # Retiring May 15, 2026 — use grok-4.20-non-reasoning instead
    )

    # =========================================================================
    # GROK 4.3 - xAI flagship (released 2026-04-30)
    # USE FOR: All reasoning stages; replaces 4.20 in HYBRID and MAX tiers.
    # $1.25 input / $2.50 output / $0.20 cached input per 1M tokens — flat rate.
    # Context: 1M tokens. Output cap: not published by xAI (131k below is a
    # conservative carry-over from the 4.1 line, unconfirmed for 4.3).
    # June 2026 audit: reasoning_effort has FOUR levels (none/low/medium/high,
    # default low) and `none` disables reasoning — so it is NOT "always-on".
    # The GrokTier mapping selects effort at the caller; supports_thinking stays
    # True because reasoning is available, not because it's forced.
    # NOTE: xAI publishes no >200K input tier — 4.3 is flat-rate.
    # =========================================================================
    GROK_4_3 = ModelConfig(
        name="grok-4.3",
        display_name="Grok 4.3",
        provider="xai",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=2.50,
        max_input_tokens=1_000_000,
        max_output_tokens=131_072,  # Unconfirmed — xAI does not publish a cap
        supports_thinking=True,  # Reasoning available (effort: none/low/medium/high)
        supports_tools=True,
        supports_multimodal=True,  # Image input supported
        cost_per_1m_input_tokens_cached=0.20,
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
    # ⚠️  LEGACY — kept only for resume of in-flight runs started before v1.23.
    # DO NOT USE in new code. Use GROK_4_20_NR_NEW ("grok-4.20-non-reasoning").
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
    # GROK 4.20 NON-REASONING (NEW) - xAI recommended replacement for NR workloads
    # USE FOR: Writing tasks replacing grok-4-1-fast-non-reasoning after retirement
    # $2.00 input / $6.00 output per 1M tokens
    # Context: 2M tokens, Output: 131k tokens
    # NOTE: Distinct from GROK_4_20_NR which uses the dated "0309" model ID
    # =========================================================================
    GROK_4_20_NR_NEW = ModelConfig(
        name="grok-4.20-non-reasoning",
        display_name="Grok 4.20 Non-Reasoning",
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
    # Registered but not wired — superseded by Grok 4.3's reasoning-intensity
    # parameter (3 levels) which delivers the same value via runtime control.
    # Kept registered for back-compat; flagged for removal once tests are updated.
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
        deprecated=True,  # Superseded by Grok 4.3 reasoning-intensity parameter
    )

    # =========================================================================
    # OPENAI GPT-5.5 - Flagship reasoning + coding (released April 24, 2026)
    # $5.00 input / $30.00 output per 1M tokens, cached input $0.50
    # Long-context surcharge: 2x input / 1.5x output above 270K input tokens
    # Context: 1M tokens, Output: 128k tokens
    # PRICING UPDATED: May 2026 audit — Feb 2026 registry had $2.00/$10.00 (wrong).
    # =========================================================================
    OPENAI_GPT_5_5 = ModelConfig(
        name="gpt-5.5",
        display_name="GPT-5.5",
        provider="openai",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_output_tokens=30.00,
        max_input_tokens=1_000_000,
        max_output_tokens=128_000,  # June 2026 audit: docs list 128k (was 100k)
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.50,
        cost_per_1m_input_tokens_high=10.00,  # 2x base above 270K input
        cost_per_1m_output_tokens_high=45.00,  # 1.5x base above 270K input
        tier_threshold_tokens=270_000,
    )

    # =========================================================================
    # OPENAI GPT-5.4 - Affordable flagship
    # $2.50 input / $15.00 output per 1M tokens, cached input $0.25
    # Long-context surcharge: 2x input / 1.5x output above 270K input tokens
    # Context: 1M tokens, Output: 128k tokens
    # PRICING UPDATED: May 2026 audit — output was $10.00, cached was $0.625.
    # =========================================================================
    OPENAI_GPT_5_4 = ModelConfig(
        name="gpt-5.4",
        display_name="GPT-5.4",
        provider="openai",
        cost_per_1m_input_tokens=2.50,
        cost_per_1m_output_tokens=15.00,
        max_input_tokens=1_000_000,  # June 2026 audit: ~1.05M, not 200K
        max_output_tokens=128_000,  # June 2026 audit: 128k (was 100k)
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.25,
        # June 2026 audit: context is ~1M (not 200K), so the gpt-5.x long-context
        # surcharge (2x input / 1.5x output above 270K input) CAN trigger here.
        cost_per_1m_input_tokens_high=5.00,  # 2x base above 270K input
        cost_per_1m_output_tokens_high=22.50,  # 1.5x base above 270K input
        tier_threshold_tokens=270_000,
    )

    # =========================================================================
    # OPENAI GPT-5.4 MINI - Utility tier candidate
    # $0.75 input / $4.50 output per 1M tokens
    # Long-context surcharge: 2x input / 1.5x output above 270K input tokens
    # Context: 400k tokens, Output: 128k tokens
    # PRICING UPDATED: May 2026 audit — was $0.40/$1.60 (wrong).
    # Cached rate not separately published — OpenAI's general 90%-off cache
    # rule would imply ~$0.075 cached input.
    # =========================================================================
    OPENAI_GPT_5_4_MINI = ModelConfig(
        name="gpt-5.4-mini",
        display_name="GPT-5.4 Mini",
        provider="openai",
        cost_per_1m_input_tokens=0.75,
        cost_per_1m_output_tokens=4.50,
        max_input_tokens=400_000,  # June 2026 audit: 400K (was 200K)
        max_output_tokens=128_000,  # June 2026 audit: 128k (was 100k)
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.075,  # Confirmed June 2026 (docs)
        cost_per_1m_input_tokens_high=1.50,
        cost_per_1m_output_tokens_high=6.75,
        tier_threshold_tokens=270_000,
    )

    # =========================================================================
    # OPENAI GPT-5.4 NANO - Ultra-cheap utility tier
    # $0.20 input / $1.25 output per 1M tokens
    # Long-context surcharge: 2x input / 1.5x output above 270K input tokens
    # Context: 400k tokens, Output: 128k tokens
    # PRICING UPDATED: May 2026 audit — was $0.10/$0.40 (wrong).
    # =========================================================================
    OPENAI_GPT_5_4_NANO = ModelConfig(
        name="gpt-5.4-nano",
        display_name="GPT-5.4 Nano",
        provider="openai",
        cost_per_1m_input_tokens=0.20,
        cost_per_1m_output_tokens=1.25,
        max_input_tokens=400_000,  # June 2026 audit: 400K (was 200K)
        max_output_tokens=128_000,  # June 2026 audit: 128k (was a wrong 16k cap)
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.02,  # Confirmed June 2026 (docs)
        cost_per_1m_input_tokens_high=0.40,
        cost_per_1m_output_tokens_high=1.875,
        tier_threshold_tokens=270_000,
    )

    # =========================================================================
    # OPENAI O4-MINI - Reasoning model (faster than o3-mini, same price)
    # $1.10 input / $4.40 output per 1M tokens
    # Strong reasoning candidate for v1.24.0 eval — cheaper output than Grok 4.3.
    # Context: 200K tokens (typical OpenAI tier; verify before relying), Output: 100K.
    # ADDED: May 2026 audit — was missing from registry entirely.
    # =========================================================================
    OPENAI_O4_MINI = ModelConfig(
        name="o4-mini",
        display_name="o4-mini",
        provider="openai",
        cost_per_1m_input_tokens=1.10,
        cost_per_1m_output_tokens=4.40,
        max_input_tokens=200_000,
        max_output_tokens=100_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,  # Reasoning models typically text-only
        cost_per_1m_input_tokens_cached=0.11,  # Inferred from 90% cache rule
    )

    # =========================================================================
    # ANTHROPIC CLAUDE OPUS 4.8 - Most capable (GA May 28, 2026)
    # $5.00 input / $25.00 output per 1M tokens, cached input $0.50 (identical
    # pricing to Opus 4.7 — drop-in replacement). Context: 1M tokens, Output: 128k.
    # Over 4.7: sharper judgement, more honesty about its own progress, longer
    # autonomous runs, and ~4x less likely to let flaws in generated code pass.
    # NOTE: shares the Opus 4.7 tokenizer profile (up to ~35% more tokens for the
    # same input vs Opus 4.6) — pre-run cost estimates may under-count for long
    # inputs until the cost estimator's tokenizer is updated.
    # =========================================================================
    ANTHROPIC_OPUS = ModelConfig(
        name="claude-opus-4-8",
        display_name="Claude Opus 4.8",
        provider="anthropic",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_output_tokens=25.00,
        max_input_tokens=1_000_000,
        max_output_tokens=128_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.50,
    )

    # =========================================================================
    # ANTHROPIC CLAUDE SONNET 5 - Best speed/intelligence balance
    # Conservative estimator rate: $3.00 input / $15.00 output per 1M tokens,
    # cached input $0.30. Anthropic's launch rate is lower ($2/$10) through Aug
    # 31, 2026, then returns to Sonnet 4.6 pricing. Use the post-intro rate here
    # so pre-run estimates do not become stale underestimates after the promo
    # window. Context: 1M tokens, Output: 128k tokens. Uses adaptive thinking by
    # default; manual output_config.effort is handled in ai/providers/anthropic.py.
    # =========================================================================
    ANTHROPIC_SONNET = ModelConfig(
        name="claude-sonnet-5",
        display_name="Claude Sonnet 5",
        provider="anthropic",
        cost_per_1m_input_tokens=3.00,
        cost_per_1m_output_tokens=15.00,
        max_input_tokens=1_000_000,
        max_output_tokens=128_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.30,
    )

    # =========================================================================
    # ANTHROPIC CLAUDE SONNET 4.6 - Previous balanced tier
    # Kept registered for explicit eval recipes and back-compat. New routing uses
    # ANTHROPIC_SONNET (Claude Sonnet 5).
    # $3.00 input / $15.00 output per 1M tokens, cached input $0.30
    # Context: 1M tokens, Output: 64k tokens
    # =========================================================================
    ANTHROPIC_SONNET_4_6 = ModelConfig(
        name="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        provider="anthropic",
        cost_per_1m_input_tokens=3.00,
        cost_per_1m_output_tokens=15.00,
        max_input_tokens=1_000_000,
        max_output_tokens=64_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.30,
    )

    # =========================================================================
    # ANTHROPIC CLAUDE HAIKU 4.5 - Fastest, utility tier candidate
    # $1.00 input / $5.00 output per 1M tokens, cached input $0.10
    # Batch API: $0.50 / $2.50 (50% off, currently unmodeled in cost estimator)
    # Context: 200k tokens, Output: 64k tokens
    # =========================================================================
    ANTHROPIC_HAIKU = ModelConfig(
        name="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        provider="anthropic",
        cost_per_1m_input_tokens=1.00,
        cost_per_1m_output_tokens=5.00,
        max_input_tokens=200_000,
        max_output_tokens=65_536,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.10,
    )

    # =========================================================================
    # ANTHROPIC CLAUDE HAIKU 3.5 - RETIRED Feb 19, 2026
    # June 2026 audit: claude-3-5-haiku was retired on 2026-02-19 and now 404s.
    # The canonical slug was always the dated claude-3-5-haiku-20241022; the
    # bare "claude-haiku-3-5" alias is gone too. Kept registered + deprecated
    # for historical eval comparison only — DO NOT route to it. Use Haiku 4.5.
    # =========================================================================
    ANTHROPIC_HAIKU_3_5 = ModelConfig(
        name="claude-haiku-3-5",
        display_name="Claude Haiku 3.5",
        provider="anthropic",
        cost_per_1m_input_tokens=0.80,
        cost_per_1m_output_tokens=4.00,
        max_input_tokens=200_000,
        max_output_tokens=8_192,
        supports_thinking=False,  # Pre-Claude-4 era, no extended thinking
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.08,
        deprecated=True,  # Retired 2026-02-19 (404) → claude-haiku-4-5
    )

    # =========================================================================
    # OLLAMA QWEN3 CODER 30B - Local inference, agentic-friendly
    # Zero cost (local), 131k context
    # =========================================================================
    OLLAMA_QWEN3_CODER_30B = ModelConfig(
        name="qwen3-coder:30b",
        display_name="Qwen3 Coder 30B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=131_072,
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA QWEN 2.5 32B - Local reasoning model
    # Zero cost (local), 131k context
    # =========================================================================
    OLLAMA_QWEN2_5_32B = ModelConfig(
        name="qwen2.5:32b",
        display_name="Qwen 2.5 32B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=131_072,
        max_output_tokens=32_768,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA DEEPSEEK R1 32B - Local open reasoning model
    # Zero cost (local), 131k context
    # =========================================================================
    OLLAMA_DEEPSEEK_R1_32B = ModelConfig(
        name="deepseek-r1:32b",
        display_name="DeepSeek R1 32B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=131_072,
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=False,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA QWEN3 7B - Small local model for consumer GPUs
    # Zero cost (local), 131k context
    # =========================================================================
    OLLAMA_QWEN3_7B = ModelConfig(
        name="qwen3:7b",
        display_name="Qwen3 7B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=131_072,
        max_output_tokens=16_384,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA QWEN3 32B - Dense daily-driver candidate for 24GB GPUs
    # Zero cost (local), 40k context, ~20GB VRAM at Q4
    # ADDED: May 2026 — RTX 4090 top-tier candidate for v1.24.0 eval matrix
    # =========================================================================
    OLLAMA_QWEN3_32B = ModelConfig(
        name="qwen3:32b",
        display_name="Qwen3 32B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=40_960,
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA QWEN3.6 35B-A3B - MoE, 35B total / 3B active (released Apr 16, 2026)
    # Zero cost (local), 262K native context expandable to ~1M, fast tok/s on 24GB
    # ADDED: May 2026 — fast agentic tier for v1.24.0 eval matrix
    # =========================================================================
    OLLAMA_QWEN3_6_35B_A3B = ModelConfig(
        name="qwen3.6:35b-a3b",
        display_name="Qwen3.6 35B-A3B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=262_144,
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA GEMMA3 27B - Dense, multimodal, 128K context, ~17GB VRAM at Q4
    # Zero cost (local), native multimodal text+image (relevant for vision tier)
    # ADDED: May 2026 — multimodal-capable writing tier for v1.24.0 eval matrix
    # =========================================================================
    OLLAMA_GEMMA3_27B = ModelConfig(
        name="gemma3:27b",
        display_name="Gemma3 27B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=131_072,
        max_output_tokens=8_192,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # OLLAMA LLAMA 4 SCOUT - 109B MoE / 17B active, 10M token context, multimodal
    # Zero cost (local), ~22-24GB VRAM at Q4, unique 10M context window
    # ADDED: May 2026 — long-context reasoning tier (full corpus + workbook +
    # cross-validation could fit in one window)
    # =========================================================================
    OLLAMA_LLAMA4_SCOUT = ModelConfig(
        name="llama4:scout",
        display_name="Llama 4 Scout (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=10_485_760,  # 10M tokens — uniquely large for local
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
    )

    # =========================================================================
    # OLLAMA GLM-4.6 - 200K context, strong agentic / tool-use benchmarks
    # Zero cost (local), competitive with DeepSeek-V3.1 / Sonnet 4 per provider
    # ADDED: May 2026 — reasoning candidate for v1.24.0 eval matrix
    # =========================================================================
    OLLAMA_GLM_4_6 = ModelConfig(
        name="glm-4.6",
        display_name="GLM-4.6 (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=200_000,
        max_output_tokens=32_768,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # OLLAMA PHI-4 14B - Microsoft, beats many 30-70B models on STEM/structured logic
    # Zero cost (local), 14B params, fits comfortably under 24GB even at higher quant
    # ADDED: May 2026 — small-footprint utility tier for v1.24.0 eval matrix
    # =========================================================================
    OLLAMA_PHI4_14B = ModelConfig(
        name="phi4:14b",
        display_name="Phi-4 14B (Local)",
        provider="ollama",
        cost_per_1m_input_tokens=0.0,
        cost_per_1m_output_tokens=0.0,
        max_input_tokens=16_384,
        max_output_tokens=16_384,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
    )

    # =========================================================================
    # DEEP RESEARCH AGENT - Autonomous research producing 12+ page reports
    # This is a SEPARATE API (Interactions API), not generate_content
    # June 2026 audit: slug refreshed deep-research-pro-preview-12-2025 ->
    # deep-research-preview-04-2026 (the 12-2025 preview is superseded). A
    # heavier deep-research-max-preview-04-2026 variant also exists.
    # =========================================================================
    DEEP_RESEARCH_AGENT = "deep-research-preview-04-2026"
