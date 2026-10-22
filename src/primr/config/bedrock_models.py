"""Current Bedrock Converse candidates and AWS prices, verified 2026-10-22.

https://aws.amazon.com/bedrock/pricing/
AWS's pricing-table metered-unit maps verify global and 10% higher US geo
rates separately. These rows do not imply access to mantle-only APIs.
"""

from primr.config.model_config import ModelConfig


def build_current_bedrock_models() -> tuple[ModelConfig, ...]:
    """Return explicitly selectable standard-tier candidates, without route promotion."""
    models: list[ModelConfig] = []
    for prefix, multiplier in (("global", 1.0), ("us", 1.1)):
        models.append(
            ModelConfig(
                name=f"{prefix}.amazon.nova-2-lite-v1:0",
                display_name=f"Amazon Nova 2 Lite (Bedrock {prefix})",
                provider="bedrock",
                cost_per_1m_input_tokens=round(0.3 * multiplier, 6),
                cost_per_1m_output_tokens=round(2.5 * multiplier, 6),
                max_input_tokens=1_000_000,
                max_output_tokens=65_535,
            )
        )
        for name, display, input_rate, output_rate, cache in (
            ("claude-fable-5-1", "Claude Fable 5.1", 10.0, 50.0, 0.25),
            ("claude-opus-5-5", "Claude Opus 5.5", 4.0, 20.0, 0.2),
            ("claude-sonnet-5-5", "Claude Sonnet 5.5", 2.0, 10.0, 0.1),
            ("claude-haiku-5-5", "Claude Haiku 5.5", 0.1, 0.5, 0.01),
        ):
            models.append(
                ModelConfig(
                    name=f"{prefix}.anthropic.{name}",
                    display_name=f"{display} (Bedrock {prefix})",
                    provider="bedrock",
                    cost_per_1m_input_tokens=round(input_rate * multiplier, 6),
                    cost_per_1m_output_tokens=round(output_rate * multiplier, 6),
                    cost_per_1m_input_tokens_cached=round(cache * multiplier, 6),
                    max_input_tokens=1_000_000,
                    max_output_tokens=128_000,
                    cost_per_1m_input_tokens_high=round(0.5 * multiplier, 6)
                    if name == "claude-haiku-5-5"
                    else None,
                    cost_per_1m_output_tokens_high=round(2.5 * multiplier, 6)
                    if name == "claude-haiku-5-5"
                    else None,
                    cost_per_1m_input_tokens_cached_high=round(0.05 * multiplier, 6)
                    if name == "claude-haiku-5-5"
                    else None,
                    tier_threshold_tokens=100_000 if name == "claude-haiku-5-5" else None,
                )
            )
    for model in models:
        if ".anthropic." in model.name:
            model.cost_per_1m_input_tokens_write_ceiling = round(
                model.cost_per_1m_input_tokens * 2, 6
            )
            if model.cost_per_1m_input_tokens_high is not None:
                model.cost_per_1m_input_tokens_write_ceiling_high = round(
                    model.cost_per_1m_input_tokens_high * 2, 6
                )
    return tuple(models)
