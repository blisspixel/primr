"""Anthropic API rates and lifecycle data, verified 2026-10-22.

https://platform.claude.com/docs/en/about-claude/pricing
https://platform.claude.com/docs/en/about-claude/model-deprecations
"""

from datetime import date

from primr.config.model_config import ModelConfig


def build_anthropic_models() -> dict[str, ModelConfig]:
    """Build priced records without changing evaluated production defaults."""
    models: dict[str, ModelConfig] = {}
    models["ANTHROPIC_OPUS"] = ModelConfig(
        name="claude-opus-4-8",
        display_name="Claude Opus 4.8",
        provider="anthropic",
        cost_per_1m_input_tokens=5.0,
        cost_per_1m_output_tokens=25.0,
        max_input_tokens=1000000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.5,
    )
    models["ANTHROPIC_SONNET"] = ModelConfig(
        name="claude-sonnet-5",
        display_name="Claude Sonnet 5",
        provider="anthropic",
        cost_per_1m_input_tokens=2.0,
        cost_per_1m_output_tokens=10.0,
        max_input_tokens=1000000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.2,
    )
    models["ANTHROPIC_SONNET_4_6"] = ModelConfig(
        name="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        provider="anthropic",
        cost_per_1m_input_tokens=3.0,
        cost_per_1m_output_tokens=15.0,
        max_input_tokens=1000000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.3,
    )
    models["ANTHROPIC_HAIKU"] = ModelConfig(
        name="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        provider="anthropic",
        cost_per_1m_input_tokens=1.0,
        cost_per_1m_output_tokens=5.0,
        max_input_tokens=200000,
        max_output_tokens=64000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.1,
    )
    models["ANTHROPIC_HAIKU_3_5"] = ModelConfig(
        name="claude-haiku-3-5",
        display_name="Claude Haiku 3.5",
        provider="anthropic",
        cost_per_1m_input_tokens=0.8,
        cost_per_1m_output_tokens=4.0,
        max_input_tokens=200000,
        max_output_tokens=8192,
        supports_thinking=False,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.08,
        deprecated=True,
        expiration_date=date(2026, 2, 19),
        replacement_model="claude-haiku-4-5",
    )
    for key, name, display, input_rate, output_rate, cached_rate in (
        ("ANTHROPIC_FABLE_5_1", "claude-fable-5-1", "Claude Fable 5.1", 10.0, 50.0, 0.25),
        ("ANTHROPIC_OPUS_5_5", "claude-opus-5-5", "Claude Opus 5.5", 4.0, 20.0, 0.2),
        ("ANTHROPIC_SONNET_5_5", "claude-sonnet-5-5", "Claude Sonnet 5.5", 2.0, 10.0, 0.1),
        ("ANTHROPIC_HAIKU_5_5", "claude-haiku-5-5", "Claude Haiku 5.5", 0.1, 0.5, 0.01),
    ):
        models[key] = ModelConfig(
            name=name,
            display_name=display,
            provider="anthropic",
            cost_per_1m_input_tokens=input_rate,
            cost_per_1m_output_tokens=output_rate,
            cost_per_1m_input_tokens_cached=cached_rate,
            max_input_tokens=1_000_000,
            max_output_tokens=128_000,
        )
    haiku = models["ANTHROPIC_HAIKU_5_5"]
    haiku.cost_per_1m_input_tokens_high = 0.5
    haiku.cost_per_1m_output_tokens_high = 2.5
    haiku.cost_per_1m_input_tokens_cached_high = 0.05
    haiku.tier_threshold_tokens = 100_000
    for model in models.values():
        model.cost_per_1m_input_tokens_write_ceiling = model.cost_per_1m_input_tokens * 2
        if model.cost_per_1m_input_tokens_high is not None:
            model.cost_per_1m_input_tokens_write_ceiling_high = (
                model.cost_per_1m_input_tokens_high * 2
            )
    return models


# Current Claude API and Bedrock models that removed manual sampling and thinking.
CLAUDE_ADAPTIVE_ONLY_FAMILIES = (
    "opus-4-7",
    "opus-4-8",
    "opus-5",
    "sonnet-5",
    "haiku-5-5",
    "fable-5",
    "mythos-5",
)


def rejects_claude_sampling(model: str) -> bool:
    """Recognize direct, gateway and Bedrock spellings of the same Claude family."""
    normalized = model.replace(".", "-")
    return any(marker in normalized for marker in CLAUDE_ADAPTIVE_ONLY_FAMILIES)


CLAUDE_ALWAYS_THINKING_FAMILIES = ("opus-5", "fable-5", "mythos-5")


def uses_modern_claude_tokenizer(model: str) -> bool:
    """Recognize verified newer Claude tokenizers across direct and gateway IDs."""
    normalized = model.replace(".", "-")
    return any(marker in normalized for marker in CLAUDE_ADAPTIVE_ONLY_FAMILIES)
