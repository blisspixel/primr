"""Direct Gemini catalog, including historical prices and provider retirements.

Sources checked 2026-10-22:
https://ai.google.dev/gemini-api/docs/models
https://ai.google.dev/gemini-api/docs/pricing
https://ai.google.dev/gemini-api/docs/deprecations

Registration does not promote production reasoning or writing defaults.
"""

from datetime import date

from primr.config.model_config import ModelConfig

# Preserve the first observed accounting cutover when rechecking the catalog.
GEMINI_ALIASES_VERIFIED_ON = date(2026, 10, 20)
GEMINI_MODEL_ALIASES = {
    "gemini-3.5-flash": "gemini-3.6-flash",
    "gemini-3.7-flash": "gemini-3.8-flash",
}


def build_gemini_models() -> dict[str, ModelConfig]:
    """Build current candidates and retained historical lookup identities."""
    models: dict[str, ModelConfig] = {}
    # Active preview: Google has not announced a shutdown date (2026-10-20).
    # USE FOR: Smart chatbots, scraping summaries, link filtering, QA checks
    # $0.50 input / $3.00 output per 1M tokens
    # Context: 1M tokens, Output: 65k tokens
    models["GEMINI_3_FLASH"] = ModelConfig(
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

    # GEMINI 3 PRO - Deep reasoning, complex tasks (GA January 2026)
    # RETIRED March 9, 2026: replaced by gemini-3.1-pro-preview.
    # $2.00 input / $12.00 output per 1M tokens. Context: 2M tokens, Output: 65k tokens.
    models["GEMINI_3_PRO"] = ModelConfig(
        name="gemini-3-pro-preview",
        display_name="Gemini 3 Pro",
        provider="google",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=12.00,
        max_input_tokens=2_000_000,
        max_output_tokens=65_536,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        deprecated=True,
        expiration_date=date(2026, 3, 9),
        replacement_model="gemini-3.1-pro-preview",
    )

    # GEMINI 3.1 FLASH-LITE - GA May 7, 2026; shutdown May 7, 2027.
    # $0.25 input / $1.50 output per 1M tokens, $0.025 cached. Context: 1M, Output: 65k.
    models["GEMINI_3_1_FLASH_LITE"] = ModelConfig(
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
        expiration_date=date(2027, 5, 7),
        replacement_model="gemini-3.5-flash-lite",
    )

    # GEMINI 3.5 FLASH-LITE - Successor to 3.1 Flash-Lite (GA July 21, 2026)
    # USE FOR: bulk writing / utility. Outperforms 3.1 Flash-Lite and exceeds
    # Gemini 3 Flash on several benchmarks (SWE-Bench Pro 54.2% vs 49.6%,
    # OSWorld-Verified 74.0% vs 65.1%); ~350 output tokens/sec.
    # $0.30 input / $2.50 output per 1M tokens. Context: 1M, Output: 65k.
    # Registered as AVAILABLE; NOT a default. Output is dearer than
    # gemini-3.1-flash-lite ($1.50), so a writing-tier repoint is eval-gated.
    # Standard cached input is $0.03 per 1M tokens.
    models["GEMINI_3_5_FLASH_LITE"] = ModelConfig(
        name="gemini-3.5-flash-lite",
        display_name="Gemini 3.5 Flash-Lite",
        provider="google",
        cost_per_1m_input_tokens=0.30,
        cost_per_1m_output_tokens=2.50,
        max_input_tokens=1_048_576,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.03,
    )

    # GEMINI 3.1 PRO - Improved reasoning, token efficiency (Preview Feb 2026)
    # DEFAULT PRO MODEL - better thinking, token efficiency, factual consistency
    # TIERED PRICING: $2/$12 (prompts <=200k) | $4/$18 (prompts >200k)
    # Context: 1M tokens, Output: 65k tokens
    models["GEMINI_3_1_PRO"] = ModelConfig(
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

    # GEMINI 3.1 PRO CUSTOMTOOLS - Optimized for agentic/tool-heavy workflows
    # Better at prioritizing custom tools (view_file, search_code) over bash
    # Same pricing as 3.1 Pro
    models["GEMINI_3_1_PRO_CUSTOMTOOLS"] = ModelConfig(
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

    # GEMINI 3.5 FLASH - Frontier agentic/coding Flash (GA May 19, 2026, I/O '26)
    # Historical candidate, now a provider alias of 3.6 Flash. Retain its
    # original record; current alias prices resolve through the pricing facade.
    # $1.50 input / $9.00 output per 1M tokens, cached input $0.15. No tiered
    # (>200k) pricing. Context: 1M tokens, Output: 65k tokens.
    models["GEMINI_3_5_FLASH"] = ModelConfig(
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

    # GEMINI 3.6 FLASH - Successor to 3.5 Flash (GA July 21, 2026)
    # Introductory through-2026 pricing is half the original launch rates and ~17%
    # fewer output tokens (Artificial Analysis Index), plus stronger coding/agent
    # scores (DeepSWE 49% vs 37%, MLE Bench 63.9% vs 49.7%, OSWorld 83.0% vs
    # 78.4%). Supersedes gemini-3.5-flash as the Pro-tier-replacement candidate.
    # $0.75 input / $0.075 cached / $3.75 output per 1M tokens through 2026;
    # $1.50 / $0.15 / $7.50 starting January 1, 2027. Context: 1M, output: 65k.
    # Registered as AVAILABLE; NOT a default. A PRO-tier repoint from
    # gemini-3.1-pro-preview ($2/$12) is eval-gated.
    models["GEMINI_3_6_FLASH"] = ModelConfig(
        name="gemini-3.6-flash",
        display_name="Gemini 3.6 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.75,
        cost_per_1m_output_tokens=3.75,
        max_input_tokens=1_048_576,  # 1M tokens
        max_output_tokens=65_536,  # 65k tokens
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.075,
        price_change_date=date(2027, 1, 1),
        cost_per_1m_input_tokens_after=1.50,
        cost_per_1m_output_tokens_after=7.50,
        cost_per_1m_input_tokens_cached_after=0.15,
    )

    # GEMINI 3.7 FLASH - Historical workhorse, now a provider alias of 3.8.
    # Registered evaluation candidate. 1M context, 65k output, native thinking.
    models["GEMINI_3_7_FLASH"] = ModelConfig(
        name="gemini-3.7-flash",
        display_name="Gemini 3.7 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.75,
        cost_per_1m_output_tokens=3.75,
        max_input_tokens=1_048_576,
        max_output_tokens=65_536,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.075,
        price_change_date=date(2027, 1, 1),
        cost_per_1m_input_tokens_after=1.50,
        cost_per_1m_output_tokens_after=7.50,
        cost_per_1m_input_tokens_cached_after=0.15,
    )

    # GEMINI 3.8 FLASH - Latest frontier workhorse (GA September 2, 2026)
    # Registered evaluation candidate. 1M context, 65k output, native thinking.
    models["GEMINI_3_8_FLASH"] = ModelConfig(
        name="gemini-3.8-flash",
        display_name="Gemini 3.8 Flash",
        provider="google",
        cost_per_1m_input_tokens=0.75,
        cost_per_1m_output_tokens=3.75,
        max_input_tokens=1_048_576,
        max_output_tokens=65_536,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.075,
        price_change_date=date(2027, 1, 1),
        cost_per_1m_input_tokens_after=1.50,
        cost_per_1m_output_tokens_after=7.50,
        cost_per_1m_input_tokens_cached_after=0.15,
    )

    # GEMINI 2.5 PRO - Stable production workhorse
    # USE FOR: Stable production apps where predictability > newest features
    # $1.25 input / $10.00 output per 1M tokens
    # Context: 1M tokens, Output: 8k tokens
    # June 2026 audit: context is 1M (1,048,576), NOT 2M - the 2M figure belongs
    # to the unreleased Gemini 3.5 Pro. Developer API access is limited to
    # prior users; no shutdown date is announced (checked 2026-10-13).
    # Vertex/OpenRouter retirement dates do not apply to this direct API row.
    models["GEMINI_2_5_PRO"] = ModelConfig(
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
    )

    # GEMINI 2.5 FLASH - High-volume workhorse
    # USE FOR: High-volume data processing, cost-sensitive applications
    # $0.30 input / $2.50 output per 1M tokens
    # PRICING UPDATED: May 2026 audit - output rate moved from $1.25 to $2.50.
    # Context: 1M tokens, Output: 8k tokens
    models["GEMINI_2_5_FLASH"] = ModelConfig(
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
        # Developer API: prior users only; no announced shutdown (2026-10-13).
    )

    # GEMINI 2.5 FLASH-LITE - Ultra-cheap utility tier
    # USE FOR: Simple classification, extraction, categorizing
    # $0.10 input / $0.40 output per 1M tokens
    # Context: 1M tokens, Output: 8k tokens
    # REGISTERED: May 2026 audit - was documented in module docstring but never
    # registered as a ModelConfig. Now registered for inclusion in v1.24.0 eval.
    models["GEMINI_2_5_FLASH_LITE"] = ModelConfig(
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
        # Developer API: prior users only; no announced shutdown (2026-10-13).
    )

    # GEMINI 3 PRO IMAGE - Image generation
    # $2.00 input (text) / $0.134 per image output
    models["GEMINI_3_PRO_IMAGE"] = ModelConfig(
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
        deprecated=True,
        expiration_date=date(2026, 6, 25),
        replacement_model="gemini-3-pro-image",
    )

    models["GEMINI_4_ARGON"] = ModelConfig(
        name="gemini-4-argon",
        display_name="Gemini 4 Argon",
        provider="google",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=10.00,
        # Input, thinking, and output share this window. The synchronous API
        # has a 65,536-token output ceiling; long decode is a separate mode.
        max_input_tokens=1_048_576,
        max_output_tokens=65_536,
        cost_per_1m_input_tokens_cached=0.10,
        price_change_date=date(2026, 12, 1),
        cost_per_1m_input_tokens_after=4.00,
        cost_per_1m_output_tokens_after=20.00,
        cost_per_1m_input_tokens_cached_after=0.20,
    )
    models["GEMINI_3_PRO_IMAGE_STABLE"] = ModelConfig(
        name="gemini-3-pro-image",
        display_name="Gemini 3 Pro Image",
        provider="google",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=120.00,  # Image output; text uses $12/M.
        max_input_tokens=65_536,
        max_output_tokens=32_768,
    )
    models["GEMINI_NANO_BANANA_2_1"] = ModelConfig(
        name="gemini-nano-banana-2.1",
        display_name="Gemini Nano Banana 2.1",
        provider="google",
        cost_per_1m_input_tokens=1.50,
        cost_per_1m_output_tokens=30.00,  # Image output; text uses $7.50/M.
        max_input_tokens=131_072,
        max_output_tokens=32_768,
        supports_tools=False,
    )

    return models
