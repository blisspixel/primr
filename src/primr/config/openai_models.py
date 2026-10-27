"""OpenAI standard API rates and context tiers, verified 2026-10-22.

Shutdown dates and replacements verified 2026-10-27.

https://developers.openai.com/api/docs/pricing
https://developers.openai.com/api/docs/models
https://developers.openai.com/api/docs/deprecations
"""

from dataclasses import replace
from datetime import date

from primr.config.model_config import ModelConfig


def build_openai_models() -> dict[str, ModelConfig]:
    """Build priced records without changing evaluated production defaults."""
    models: dict[str, ModelConfig] = {}
    models["OPENAI_GPT_5_6_SOL"] = ModelConfig(
        name="gpt-5.6-sol",
        display_name="GPT-5.6 Sol",
        provider="openai",
        cost_per_1m_input_tokens=4.0,
        cost_per_1m_output_tokens=20.0,
        max_input_tokens=922000,
        max_output_tokens=128000,
        cost_per_1m_input_tokens_cached=0.4,
        cost_per_1m_input_tokens_high=8.0,
        cost_per_1m_output_tokens_high=30.0,
        cost_per_1m_input_tokens_cached_high=0.8,
        tier_threshold_tokens=272000,
    )
    models["OPENAI_GPT_5_6"] = replace(
        models["OPENAI_GPT_5_6_SOL"], name="gpt-5.6", display_name="GPT-5.6 (Sol alias)"
    )
    models["OPENAI_GPT_5_6_TERRA"] = replace(
        models["OPENAI_GPT_5_6_SOL"],
        name="gpt-5.6-terra",
        display_name="GPT-5.6 Terra",
        cost_per_1m_input_tokens=2.0,
        cost_per_1m_output_tokens=12.0,
        cost_per_1m_input_tokens_cached=0.2,
        cost_per_1m_input_tokens_high=4.0,
        cost_per_1m_output_tokens_high=18.0,
        cost_per_1m_input_tokens_cached_high=0.4,
    )
    models["OPENAI_GPT_5_6_LUNA"] = replace(
        models["OPENAI_GPT_5_6_SOL"],
        name="gpt-5.6-luna",
        display_name="GPT-5.6 Luna",
        cost_per_1m_input_tokens=0.2,
        cost_per_1m_output_tokens=1.2,
        cost_per_1m_input_tokens_cached=0.02,
        cost_per_1m_input_tokens_high=0.4,
        cost_per_1m_output_tokens_high=1.8,
        cost_per_1m_input_tokens_cached_high=0.04,
    )
    models["OPENAI_GPT_5_5"] = ModelConfig(
        name="gpt-5.5",
        display_name="GPT-5.5",
        provider="openai",
        cost_per_1m_input_tokens=5.0,
        cost_per_1m_output_tokens=30.0,
        max_input_tokens=1050000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.5,
        cost_per_1m_input_tokens_high=10.0,
        cost_per_1m_output_tokens_high=45.0,
        cost_per_1m_input_tokens_cached_high=1.0,
        tier_threshold_tokens=272000,
    )
    models["OPENAI_GPT_5_4"] = ModelConfig(
        name="gpt-5.4",
        display_name="GPT-5.4",
        provider="openai",
        cost_per_1m_input_tokens=2.5,
        cost_per_1m_output_tokens=15.0,
        max_input_tokens=1050000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.25,
        cost_per_1m_input_tokens_high=5.0,
        cost_per_1m_output_tokens_high=22.5,
        cost_per_1m_input_tokens_cached_high=0.5,
        tier_threshold_tokens=272000,
    )
    models["OPENAI_GPT_5_4_MINI"] = ModelConfig(
        name="gpt-5.4-mini",
        display_name="GPT-5.4 Mini",
        provider="openai",
        cost_per_1m_input_tokens=0.75,
        cost_per_1m_output_tokens=4.5,
        max_input_tokens=400000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.075,
    )
    models["OPENAI_GPT_5_4_NANO"] = ModelConfig(
        name="gpt-5.4-nano",
        display_name="GPT-5.4 Nano",
        provider="openai",
        cost_per_1m_input_tokens=0.2,
        cost_per_1m_output_tokens=1.25,
        max_input_tokens=400000,
        max_output_tokens=128000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=True,
        cost_per_1m_input_tokens_cached=0.02,
        expiration_date=date(2027, 4, 1),
        replacement_model="gpt-6-luna",
    )
    models["OPENAI_O4_MINI"] = ModelConfig(
        name="o4-mini",
        display_name="o4-mini",
        provider="openai",
        cost_per_1m_input_tokens=1.1,
        cost_per_1m_output_tokens=4.4,
        max_input_tokens=200000,
        max_output_tokens=100000,
        supports_thinking=True,
        supports_tools=True,
        supports_multimodal=False,
        cost_per_1m_input_tokens_cached=0.275,
        deprecated=True,
        expiration_date=date(2026, 10, 23),
        replacement_model="gpt-5.6-terra",
    )
    # Standard USD rates; >272K prompts reprice the full request.
    for key, name, display, input_rate, output_rate, cached_rate in (
        ("OPENAI_GPT_6_ASTRA", "gpt-6-astra", "GPT-6 Astra", 10.0, 50.0, 1.0),
        ("OPENAI_GPT_6_SOL", "gpt-6-sol", "GPT-6 Sol", 2.0, 10.0, 0.2),
        ("OPENAI_GPT_6_1_SOL", "gpt-6.1-sol", "GPT-6.1 Sol", 2.0, 10.0, 0.1),
        ("OPENAI_GPT_6_LUNA", "gpt-6-luna", "GPT-6 Luna", 0.1, 0.5, 0.01),
    ):
        models[key] = ModelConfig(
            name=name,
            display_name=display,
            provider="openai",
            cost_per_1m_input_tokens=input_rate,
            cost_per_1m_output_tokens=output_rate,
            cost_per_1m_input_tokens_cached=cached_rate,
            max_input_tokens=922_000,
            max_output_tokens=128_000,
            cost_per_1m_input_tokens_high=input_rate * 2,
            cost_per_1m_output_tokens_high=output_rate * 1.5,
            cost_per_1m_input_tokens_cached_high=cached_rate * 2,
            tier_threshold_tokens=272_000,
        )
    for model in models.values():
        if model.name in OPENAI_PAID_CACHE_WRITE_MODELS:
            model.cost_per_1m_input_tokens_write_ceiling = model.cost_per_1m_input_tokens * 2.5
            if model.cost_per_1m_input_tokens_high is not None:
                model.cost_per_1m_input_tokens_write_ceiling_high = (
                    model.cost_per_1m_input_tokens_high * 2.5
                )
    return models


OPENAI_PAID_CACHE_WRITE_MODELS = frozenset(
    {
        "gpt-5.6",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-6-astra",
        "gpt-6-sol",
        "gpt-6.1-sol",
        "gpt-6-luna",
    }
)
