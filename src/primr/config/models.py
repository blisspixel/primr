"""
Centralized Model Configuration for Primr
==========================================

THIS IS THE SINGLE SOURCE OF TRUTH FOR ALL AI MODELS.
UPDATE HERE TO CHANGE MODELS GLOBALLY.

Last audited: May 30, 2026 (refresh of the May 8 "Model Landscape Audit").
Pricing checked against provider docs the same day. Re-audit before each major
eval — see ROADMAP "Model Adaptability".

AVAILABLE MODELS (May 2026):
-----------------------------
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
  deep-research-pro-preview-12-2025 - Autonomous 12+ page research reports

OPENAI:
  gpt-5.5                    - Flagship, $5.00/$30.00 + $0.50 cached, 1M ctx
  gpt-5.4                    - Affordable flagship, $2.50/$15.00 + $0.25 cached, 200k ctx
  gpt-5.4-mini               - Utility candidate, $0.75/$4.50, 200k ctx
  gpt-5.4-nano               - Ultra-cheap, $0.20/$1.25, 200k ctx, 16k out cap
  o4-mini                    - Reasoning, $1.10/$4.40, alternative to Grok 4.3
  All gpt-5.x: 2x input / 1.5x output above 272K input tokens.

ANTHROPIC:
  claude-opus-4-8            - Most capable (GA May 28, 2026), $5.00/$25.00 + $0.50 cached,
                               1M ctx, 128k out. Drop-in over 4.7 (identical pricing).
  claude-sonnet-4-6          - Balance, $3.00/$15.00 + $0.30 cached, 1M ctx, 64k out
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
from enum import Enum


class GrokTier(str, Enum):
    """Grok model tier — controls quality/cost tradeoff in fast mode."""

    FAST = "fast"  # 4.3 (reasoning_effort=low) + 4.20-nr (~$4.27)
    HYBRID = "hybrid"  # 4.3 + 4.20-nr (~$4.27, same models, default effort) — DEFAULT
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
    # GROK 4.3 - xAI flagship (released 2026-04-30), always-on reasoning
    # USE FOR: All reasoning stages; replaces 4.20 in HYBRID and MAX tiers.
    # $1.25 input / $2.50 output / $0.20 cached input per 1M tokens — flat rate.
    # Context: 1M tokens, Output: 131k tokens.
    # No non-reasoning variant — reasoning cannot be disabled.
    # Reasoning intensity is a runtime parameter (3 levels) — see GrokTier mapping.
    # Multimodal input (text + image), text output.
    # NOTE: xAI publishes no >200K input tier — 4.3 launched as flat-rate.
    # The high-tier placeholder fields from v1.22.0 were removed in May 2026 audit.
    # =========================================================================
    GROK_4_3 = ModelConfig(
        name="grok-4.3",
        display_name="Grok 4.3",
        provider="xai",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=2.50,
        max_input_tokens=1_000_000,
        max_output_tokens=131_072,
        supports_thinking=True,  # Always-on, cannot be disabled
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
    # Long-context surcharge: 2x input / 1.5x output above 272K input tokens
    # Context: 1M tokens, Output: 100k tokens
    # PRICING UPDATED: May 2026 audit — Feb 2026 registry had $2.00/$10.00 (wrong).
    # =========================================================================
    OPENAI_GPT_5_5 = ModelConfig(
        name="gpt-5.5",
        display_name="GPT-5.5",
        provider="openai",
        cost_per_1m_input_tokens=5.00,
        cost_per_1m_output_tokens=30.00,
        max_input_tokens=1_000_000,
        max_output_tokens=100_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.50,
        cost_per_1m_input_tokens_high=10.00,  # 2x base above 272K input
        cost_per_1m_output_tokens_high=45.00,  # 1.5x base above 272K input
        tier_threshold_tokens=272_000,
    )

    # =========================================================================
    # OPENAI GPT-5.4 - Affordable flagship
    # $2.50 input / $15.00 output per 1M tokens, cached input $0.25
    # Long-context surcharge: 2x input / 1.5x output above 272K input tokens
    # Context: 200k tokens, Output: 100k tokens
    # PRICING UPDATED: May 2026 audit — output was $10.00, cached was $0.625.
    # =========================================================================
    OPENAI_GPT_5_4 = ModelConfig(
        name="gpt-5.4",
        display_name="GPT-5.4",
        provider="openai",
        cost_per_1m_input_tokens=2.50,
        cost_per_1m_output_tokens=15.00,
        max_input_tokens=200_000,
        max_output_tokens=100_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.25,
        # Note: gpt-5.4 context cap is 200K; long-context surcharge above 272K
        # would never trigger for this model. Tier fields omitted.
    )

    # =========================================================================
    # OPENAI GPT-5.4 MINI - Utility tier candidate
    # $0.75 input / $4.50 output per 1M tokens
    # Context: 200k tokens, Output: 100k tokens
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
        max_input_tokens=200_000,
        max_output_tokens=100_000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.075,  # Inferred from 90% cache rule
    )

    # =========================================================================
    # OPENAI GPT-5.4 NANO - Ultra-cheap utility tier
    # $0.20 input / $1.25 output per 1M tokens
    # Context: 200k tokens, Output: 16k tokens (output cap may force per-section sizing)
    # PRICING UPDATED: May 2026 audit — was $0.10/$0.40 (wrong).
    # =========================================================================
    OPENAI_GPT_5_4_NANO = ModelConfig(
        name="gpt-5.4-nano",
        display_name="GPT-5.4 Nano",
        provider="openai",
        cost_per_1m_input_tokens=0.20,
        cost_per_1m_output_tokens=1.25,
        max_input_tokens=200_000,
        max_output_tokens=16_384,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.02,  # Inferred from 90% cache rule
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
    # ANTHROPIC CLAUDE SONNET 4.6 - Best speed/intelligence balance
    # $3.00 input / $15.00 output per 1M tokens, cached input $0.30
    # Context: 1M tokens, Output: 64k tokens
    # =========================================================================
    ANTHROPIC_SONNET = ModelConfig(
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
    # ANTHROPIC CLAUDE HAIKU 3.5 - Cheaper utility tier alternative
    # $0.80 input / $4.00 output per 1M tokens, cached input $0.08
    # Batch API: $0.40 / $2.00 (50% off, currently unmodeled)
    # Context: 200k tokens, Output: 8k tokens (Claude 3 era)
    # ADDED: May 2026 audit — useful as a cheap alternative to Haiku 4.5
    # for utility-tier roles where Haiku 4.5's full capability isn't needed.
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
        """Calculate cost in USD for given token counts using model pricing.

        For tiered models, uses the high tier when prompt_tokens exceeds the
        tier threshold. When prompt_tokens is None, uses standard (low) tier.

        cached_input_tokens are billed at the model's cached rate when the
        config exposes one; otherwise they fall through to the standard input
        rate. Non-cached input is (input_tokens - cached_input_tokens).

        All token counts are clamped to non-negative values defensively.
        """
        config = cls.ALL_MODELS.get(model_name)
        if config is None:
            raise KeyError(f"Unknown model: {model_name}")

        # Defensive: clamp all token counts to non-negative
        input_tokens = max(0, input_tokens)
        output_tokens = max(0, output_tokens)
        cached_input_tokens = max(0, min(cached_input_tokens, input_tokens))

        if (
            config.has_tiered_pricing
            and prompt_tokens is not None
            and config.tier_threshold_tokens is not None
            and prompt_tokens > config.tier_threshold_tokens
        ):
            inp_price = config.cost_per_1m_input_tokens_high
            out_price = config.cost_per_1m_output_tokens_high
            if inp_price is None or out_price is None:  # pragma: no cover
                raise ValueError(
                    f"Model {model_name} has tiered pricing but missing high-tier rates"
                )
        else:
            inp_price = config.cost_per_1m_input_tokens
            out_price = config.cost_per_1m_output_tokens

        live_input_tokens = input_tokens - cached_input_tokens
        cache_price = config.cost_per_1m_input_tokens_cached
        cached_cost = (
            (cached_input_tokens / 1_000_000) * cache_price
            if cache_price is not None
            else (cached_input_tokens / 1_000_000) * inp_price
        )

        return (
            (live_input_tokens / 1_000_000) * inp_price
            + cached_cost
            + (output_tokens / 1_000_000) * out_price
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

        if config.has_tiered_pricing:
            inp_price = config.cost_per_1m_input_tokens_high
            out_price = config.cost_per_1m_output_tokens_high
            if inp_price is None or out_price is None:  # pragma: no cover
                raise ValueError(
                    f"Model {model_name} has tiered pricing but missing high-tier rates"
                )
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
