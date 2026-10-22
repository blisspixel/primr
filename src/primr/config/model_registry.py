"""Volatile model data behind the ``config.models`` selection and cost facade."""

from dataclasses import replace
from enum import Enum

from primr.config.anthropic_models import build_anthropic_models
from primr.config.bedrock_models import build_current_bedrock_models
from primr.config.gemini_models import build_gemini_models
from primr.config.model_config import ModelConfig
from primr.config.openai_models import build_openai_models
from primr.config.openrouter_models import build_openrouter_models


class GrokTier(str, Enum):
    """Grok model tier — controls quality/cost tradeoff in fast mode."""

    FAST = "fast"  # 4.3 (reasoning_effort=low) + 4.20-nr (~$5.09 xAI-only base)
    HYBRID = "hybrid"  # 4.3 + 4.20-nr (~$5.09 xAI-only base) - DEFAULT
    MAX = "max"  # 4.5 evaluated pin; 4.6 is registered but promotion is eval-gated


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


_OPENAI_MODELS = build_openai_models()
_ANTHROPIC_MODELS = build_anthropic_models()
_GEMINI_MODELS = build_gemini_models()
_OPENROUTER_MODELS = build_openrouter_models(ModelConfig)


class ModelRegistry:
    """Registry of available and historical model configurations."""

    GEMINI_4_ARGON = _GEMINI_MODELS["GEMINI_4_ARGON"]
    GEMINI_NANO_BANANA_2_1 = _GEMINI_MODELS["GEMINI_NANO_BANANA_2_1"]
    GEMINI_3_PRO_IMAGE_STABLE = _GEMINI_MODELS["GEMINI_3_PRO_IMAGE_STABLE"]
    GEMINI_3_FLASH = _GEMINI_MODELS["GEMINI_3_FLASH"]
    GEMINI_3_PRO = _GEMINI_MODELS["GEMINI_3_PRO"]
    GEMINI_3_1_FLASH_LITE = _GEMINI_MODELS["GEMINI_3_1_FLASH_LITE"]
    GEMINI_3_5_FLASH_LITE = _GEMINI_MODELS["GEMINI_3_5_FLASH_LITE"]
    GEMINI_3_1_PRO = _GEMINI_MODELS["GEMINI_3_1_PRO"]
    GEMINI_3_1_PRO_CUSTOMTOOLS = _GEMINI_MODELS["GEMINI_3_1_PRO_CUSTOMTOOLS"]
    GEMINI_3_5_FLASH = _GEMINI_MODELS["GEMINI_3_5_FLASH"]
    GEMINI_3_6_FLASH = _GEMINI_MODELS["GEMINI_3_6_FLASH"]
    GEMINI_3_7_FLASH = _GEMINI_MODELS["GEMINI_3_7_FLASH"]
    GEMINI_3_8_FLASH = _GEMINI_MODELS["GEMINI_3_8_FLASH"]
    GEMINI_2_5_PRO = _GEMINI_MODELS["GEMINI_2_5_PRO"]
    GEMINI_2_5_FLASH = _GEMINI_MODELS["GEMINI_2_5_FLASH"]
    GEMINI_2_5_FLASH_LITE = _GEMINI_MODELS["GEMINI_2_5_FLASH_LITE"]
    GEMINI_3_PRO_IMAGE = _GEMINI_MODELS["GEMINI_3_PRO_IMAGE"]

    # GROK 4.1 FAST REASONING - xAI fast reasoning model
    # USE FOR: Analytical tasks (gap analysis, workbook, cross-validation)
    # $0.20 input / $0.50 output per 1M tokens (+ reasoning tokens at output rate)
    # Context: 2M tokens, Output: 128k tokens
    # OpenAI-compatible API at https://api.x.ai/v1
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

    # GROK 4.1 FAST NON-REASONING - xAI fast model without reasoning overhead
    # USE FOR: Writing tasks (report batches, section regen, trust polish, AI strategy)
    # Same per-token pricing as reasoning variant, but no reasoning token overhead
    # → strictly faster and cheaper for prose generation
    # Context: 2M tokens, Output: 128k tokens
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

    # GROK 4.3 - xAI value reasoning model (released 2026-04-30)
    # USE FOR: Default hybrid/fast reasoning stages (sub-$1 measured recipe).
    # Pricing (docs.x.ai, Aug 2026): $1.25/$2.50 below 200k prompt tokens;
    # $2.50/$5.00 at or above 200k. Cached input is $0.20 below and $0.40 at or
    # above the boundary.
    # Context: 1M tokens. Output cap: not published (131k is a conservative
    # carry-over from the 4.1 line).
    # reasoning_effort: none/low/medium/high (default low) — not always-on.
    # Grok 4.6 is the newer coding/agent flagship; keep 4.3 as the default
    # cost/quality balance until an eval promotes a change.
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
        cost_per_1m_input_tokens_high=2.50,
        cost_per_1m_output_tokens_high=5.00,
        tier_threshold_tokens=200_000,
        cost_per_1m_input_tokens_cached=0.20,
        cost_per_1m_input_tokens_cached_high=0.40,
        tier_threshold_inclusive=True,
    )

    # GROK 4.5 - xAI previous flagship (released 2026-07; coding/agentic focus)
    # USE FOR: Opt-in MAX tier (`--grok-tier max`). Not the hybrid default —
    # ~2x input / ~2.4x output vs 4.3 and 500k context (vs 1M on 4.3).
    # Pricing (docs.x.ai, Aug 2026): $2.00/$6.00 below 200k; $4.00/$12.00 at
    # or above 200k. Cached input is $0.30 below and $0.60 at or above the
    # boundary.
    # reasoning_effort: low/medium/high (default high).
    GROK_4_5 = ModelConfig(
        name="grok-4.5",
        display_name="Grok 4.5",
        provider="xai",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=6.00,
        max_input_tokens=500_000,
        max_output_tokens=131_072,  # Unconfirmed — xAI does not publish a cap
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_high=4.00,
        cost_per_1m_output_tokens_high=12.00,
        tier_threshold_tokens=200_000,
        cost_per_1m_input_tokens_cached=0.30,
        cost_per_1m_input_tokens_cached_high=0.60,
        tier_threshold_inclusive=True,
    )

    # GROK 4.6 - xAI current flagship (released 2026-08-12)
    # USE FOR: Registered promotion candidate only. It is not silently routed
    # into Standard or MAX until a bounded quality and cost evaluation passes.
    # Pricing: $2.00/$0.50 cached/$6.00 below 200k prompt tokens;
    # $4.00/$1.00 cached/$12.00 at or above 200k. Context: 500k tokens.
    # xAI publishes no text output limit; 131k remains Primr's conservative cap.
    # reasoning_effort: low/medium/high/xhigh (default high).
    GROK_4_6 = ModelConfig(
        name="grok-4.6",
        display_name="Grok 4.6",
        provider="xai",
        cost_per_1m_input_tokens=2.00,
        cost_per_1m_output_tokens=6.00,
        max_input_tokens=500_000,
        max_output_tokens=131_072,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_high=4.00,
        cost_per_1m_output_tokens_high=12.00,
        tier_threshold_tokens=200_000,
        cost_per_1m_input_tokens_cached=0.50,
        cost_per_1m_input_tokens_cached_high=1.00,
        tier_threshold_inclusive=True,
    )

    # Grok 4.7 is selectable; the MAX routing pin remains evaluated Grok 4.5.
    GROK_4_7 = replace(GROK_4_6, name="grok-4.7", display_name="Grok 4.7")

    # GROK 4.20 REASONING - dated canonical ID retained for compatibility
    # Pricing: $1.25/$0.20 cached/$2.50 below 200k prompt tokens;
    # $2.50/$0.40 cached/$5.00 at or above 200k. Context: 1M tokens.
    GROK_4_20_REASONING = ModelConfig(
        name="grok-4.20-0309-reasoning",
        display_name="Grok 4.20 Reasoning",
        provider="xai",
        cost_per_1m_input_tokens=1.25,
        cost_per_1m_output_tokens=2.50,
        max_input_tokens=1_000_000,
        max_output_tokens=131_072,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
        cost_per_1m_input_tokens_high=2.50,
        cost_per_1m_output_tokens_high=5.00,
        tier_threshold_tokens=200_000,
        cost_per_1m_input_tokens_cached=0.20,
        cost_per_1m_input_tokens_cached_high=0.40,
        tier_threshold_inclusive=True,
    )

    GROK_4_20 = replace(
        GROK_4_20_REASONING,
        name="grok-4.20",
        display_name="Grok 4.20",
    )

    # GROK 4.20 NON-REASONING - dated canonical ID retained for compatibility
    # ⚠️  LEGACY — kept only for resume of in-flight runs started before v1.23.
    # DO NOT USE in new code. Use GROK_4_20_NR_NEW ("grok-4.20-non-reasoning").
    GROK_4_20_NR = replace(
        GROK_4_20_REASONING,
        name="grok-4.20-0309-non-reasoning",
        display_name="Grok 4.20",
        supports_thinking=False,
    )

    GROK_4_20_NR_NEW = replace(
        GROK_4_20_NR,
        name="grok-4.20-non-reasoning",
        display_name="Grok 4.20 Non-Reasoning",
    )

    # GROK 4.20 MULTI-AGENT - dated canonical ID with tool optimizations
    # Registered but not wired — superseded by Grok 4.3's reasoning-intensity
    # parameter (3 levels) which delivers the same value via runtime control.
    GROK_4_20_MULTI_AGENT = replace(
        GROK_4_20_NR,
        name="grok-4.20-multi-agent-0309",
        display_name="Grok 4.20 Multi-Agent",
        deprecated=True,  # Superseded by Grok 4.3 reasoning-intensity parameter
    )

    # Direct OpenAI catalog includes current candidates and historical records.
    # Registration does not repoint production defaults.
    OPENAI_GPT_6_ASTRA = _OPENAI_MODELS["OPENAI_GPT_6_ASTRA"]
    OPENAI_GPT_6_SOL = _OPENAI_MODELS["OPENAI_GPT_6_SOL"]
    OPENAI_GPT_6_1_SOL = _OPENAI_MODELS["OPENAI_GPT_6_1_SOL"]
    OPENAI_GPT_6_LUNA = _OPENAI_MODELS["OPENAI_GPT_6_LUNA"]
    OPENAI_MODELS = tuple(_OPENAI_MODELS.values())
    OPENAI_GPT_5_6_SOL = _OPENAI_MODELS["OPENAI_GPT_5_6_SOL"]
    OPENAI_GPT_5_6 = _OPENAI_MODELS["OPENAI_GPT_5_6"]
    OPENAI_GPT_5_6_TERRA = _OPENAI_MODELS["OPENAI_GPT_5_6_TERRA"]
    OPENAI_GPT_5_6_LUNA = _OPENAI_MODELS["OPENAI_GPT_5_6_LUNA"]
    OPENAI_GPT_5_5 = _OPENAI_MODELS["OPENAI_GPT_5_5"]
    OPENAI_GPT_5_4 = _OPENAI_MODELS["OPENAI_GPT_5_4"]
    OPENAI_GPT_5_4_MINI = _OPENAI_MODELS["OPENAI_GPT_5_4_MINI"]
    OPENAI_GPT_5_4_NANO = _OPENAI_MODELS["OPENAI_GPT_5_4_NANO"]
    OPENAI_O4_MINI = _OPENAI_MODELS["OPENAI_O4_MINI"]

    # Gateway-qualified names keep routing and accounting at the billing boundary.
    OPENROUTER_MODELS = _OPENROUTER_MODELS
    OPENROUTER_GEMINI_2_5_FLASH_LITE = _OPENROUTER_MODELS[0]
    OPENROUTER_GPT_4_1_MINI = _OPENROUTER_MODELS[1]
    OPENROUTER_DEEPSEEK_V3_2 = _OPENROUTER_MODELS[2]
    OPENROUTER_GEMINI_3_1_FLASH_LITE = next(
        model for model in _OPENROUTER_MODELS if model.name == "google/gemini-3.1-flash-lite"
    )

    # Direct Anthropic records preserve the evaluated routing constants.
    ANTHROPIC_FABLE_5_1 = _ANTHROPIC_MODELS["ANTHROPIC_FABLE_5_1"]
    ANTHROPIC_OPUS_5_5 = _ANTHROPIC_MODELS["ANTHROPIC_OPUS_5_5"]
    ANTHROPIC_SONNET_5_5 = _ANTHROPIC_MODELS["ANTHROPIC_SONNET_5_5"]
    ANTHROPIC_HAIKU_5_5 = _ANTHROPIC_MODELS["ANTHROPIC_HAIKU_5_5"]
    ANTHROPIC_MODELS = tuple(_ANTHROPIC_MODELS.values())
    ANTHROPIC_OPUS = _ANTHROPIC_MODELS["ANTHROPIC_OPUS"]
    ANTHROPIC_SONNET = _ANTHROPIC_MODELS["ANTHROPIC_SONNET"]
    ANTHROPIC_SONNET_4_6 = _ANTHROPIC_MODELS["ANTHROPIC_SONNET_4_6"]
    ANTHROPIC_HAIKU = _ANTHROPIC_MODELS["ANTHROPIC_HAIKU"]
    ANTHROPIC_HAIKU_3_5 = _ANTHROPIC_MODELS["ANTHROPIC_HAIKU_3_5"]

    # OLLAMA QWEN3 CODER 30B - Local inference, agentic-friendly
    # Zero cost (local), 131k context
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

    # OLLAMA QWEN 2.5 32B - Local reasoning model
    # Zero cost (local), 131k context
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

    # OLLAMA DEEPSEEK R1 32B - Local open reasoning model
    # Zero cost (local), 131k context
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

    # OLLAMA QWEN3 7B - Small local model for consumer GPUs
    # Zero cost (local), 131k context
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

    # OLLAMA QWEN3 32B - Dense daily-driver candidate for 24GB GPUs
    # Zero cost (local), 40k context, ~20GB VRAM at Q4
    # ADDED: May 2026 — RTX 4090 top-tier candidate for v1.24.0 eval matrix
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

    # OLLAMA QWEN3.6 35B-A3B - MoE, 35B total / 3B active (released Apr 16, 2026)
    # Zero cost (local), 262K native context expandable to ~1M, fast tok/s on 24GB
    # ADDED: May 2026 — fast agentic tier for v1.24.0 eval matrix
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

    # OLLAMA GEMMA3 27B - Dense, multimodal, 128K context, ~17GB VRAM at Q4
    # Zero cost (local), native multimodal text+image (relevant for vision tier)
    # ADDED: May 2026 — multimodal-capable writing tier for v1.24.0 eval matrix
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

    # OLLAMA LLAMA 4 SCOUT - 109B MoE / 17B active, 10M token context, multimodal
    # Zero cost (local), ~22-24GB VRAM at Q4, unique 10M context window
    # ADDED: May 2026 — long-context reasoning tier (full corpus + workbook +
    # cross-validation could fit in one window)
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

    # OLLAMA GLM-4.6 - 200K context, strong agentic / tool-use benchmarks
    # Zero cost (local), competitive with DeepSeek-V3.1 / Sonnet 4 per provider
    # ADDED: May 2026 — reasoning candidate for v1.24.0 eval matrix
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

    # OLLAMA PHI-4 14B - Microsoft, beats many 30-70B models on STEM/structured logic
    # Zero cost (local), 14B params, fits comfortably under 24GB even at higher quant
    # ADDED: May 2026 — small-footprint utility tier for v1.24.0 eval matrix
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

    # AMAZON BEDROCK - Amazon Nova family via the boto3 converse API.
    # Model ids are cross-region inference-profile ids (the `us.` prefix is
    # required for on-demand invocation). Prices verified July 2026 against the
    # AWS Bedrock pricing page. Cached-input (Bedrock prompt caching, ~75% off)
    # is left unset so the estimate gate assumes no cache discount (conservative).
    # Bedrock routing is MAIN-PROCESS ONLY — see providers/registry.py; the
    # supervised-worker credential boundary (config/env.py) is not crossed.
    BEDROCK_NOVA_MICRO = ModelConfig(
        name="us.amazon.nova-micro-v1:0",
        display_name="Amazon Nova Micro (Bedrock)",
        provider="bedrock",
        cost_per_1m_input_tokens=0.035,
        cost_per_1m_output_tokens=0.14,
        max_input_tokens=128_000,
        max_output_tokens=5_120,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=False,
    )

    BEDROCK_NOVA_LITE = ModelConfig(
        name="us.amazon.nova-lite-v1:0",
        display_name="Amazon Nova Lite (Bedrock)",
        provider="bedrock",
        cost_per_1m_input_tokens=0.06,
        cost_per_1m_output_tokens=0.24,
        max_input_tokens=300_000,
        max_output_tokens=5_120,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=True,
    )

    BEDROCK_NOVA_PRO = ModelConfig(
        name="us.amazon.nova-pro-v1:0",
        display_name="Amazon Nova Pro (Bedrock)",
        provider="bedrock",
        cost_per_1m_input_tokens=0.80,
        cost_per_1m_output_tokens=3.20,
        max_input_tokens=300_000,
        max_output_tokens=5_120,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=True,
    )

    BEDROCK_CURRENT_MODELS = build_current_bedrock_models()

    # Local-only library tags. 16K is a conservative configured generation cap;
    # the advertised context windows require matching local runtime settings.
    OLLAMA_CURRENT_MODELS = tuple(
        ModelConfig(
            name=name,
            display_name=display,
            provider="ollama",
            cost_per_1m_input_tokens=0.0,
            cost_per_1m_output_tokens=0.0,
            max_input_tokens=262_144,
            max_output_tokens=16_384,
        )
        for name, display in (
            ("qwen3.8:27b", "Qwen 3.8 27B (Local)"),
            ("gemma4:12b", "Gemma 4 12B (Local)"),
            ("gemma4:26b", "Gemma 4 26B (Local)"),
            ("gemma4:31b", "Gemma 4 31B (Local)"),
        )
    )

    # DEEP RESEARCH AGENT - Autonomous research producing 12+ page reports
    # This is a SEPARATE API (Interactions API), not generate_content
    # June 2026 audit: slug refreshed deep-research-pro-preview-12-2025 ->
    # deep-research-preview-04-2026 (the 12-2025 preview is superseded). A
    # heavier deep-research-max-preview-04-2026 variant also exists.
    DEEP_RESEARCH_AGENT = "deep-research-preview-04-2026"


# Runtime defaults live with the registry data so settings and pricing can
# depend on one leaf module without depending on each other.
DEFAULT_FLASH_MODEL = ModelRegistry.GEMINI_3_FLASH.name
DEFAULT_PRO_MODEL = ModelRegistry.GEMINI_3_1_PRO.name
