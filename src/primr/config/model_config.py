"""Shared model pricing and provider lifecycle contracts."""

from dataclasses import dataclass
from datetime import UTC, date, datetime


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
    cost_per_1m_input_tokens_high: float | None = None
    cost_per_1m_output_tokens_high: float | None = None
    tier_threshold_tokens: int | None = None
    cost_per_1m_input_tokens_cached: float | None = None
    cost_per_1m_input_tokens_cached_high: float | None = None
    tier_threshold_inclusive: bool = False
    price_change_date: date | None = None
    cost_per_1m_input_tokens_after: float | None = None
    cost_per_1m_output_tokens_after: float | None = None
    cost_per_1m_input_tokens_cached_after: float | None = None
    deprecated: bool = False
    expiration_date: date | None = None
    replacement_model: str | None = None

    def require_available(self, on_date: date | None = None) -> None:
        """Reject new requests on or after a provider's published retirement date."""
        effective_date = on_date if on_date is not None else datetime.now(UTC).date()
        if self.expiration_date is not None and effective_date >= self.expiration_date:
            replacement = (
                f" Select {self.replacement_model} explicitly." if self.replacement_model else ""
            )
            raise ValueError(
                f"Model {self.name} expired on {self.expiration_date}.{replacement} Re-estimate before running."
            )

    @property
    def has_tiered_pricing(self) -> bool:
        """Whether this model uses tiered pricing based on prompt size."""
        return (
            self.cost_per_1m_input_tokens_high is not None
            and self.cost_per_1m_output_tokens_high is not None
            and self.tier_threshold_tokens is not None
        )

    def standard_rates(self, pricing_date: date | None = None) -> tuple[float, float, float | None]:
        """Return flat input, output, and cache rates effective on a date."""
        effective_date = pricing_date or date.today()
        if self.price_change_date is not None and effective_date >= self.price_change_date:
            if (
                self.cost_per_1m_input_tokens_after is None
                or self.cost_per_1m_output_tokens_after is None
            ):
                raise ValueError(f"Model {self.name} has an incomplete scheduled price change")
            return (
                self.cost_per_1m_input_tokens_after,
                self.cost_per_1m_output_tokens_after,
                self.cost_per_1m_input_tokens_cached_after,
            )
        return (
            self.cost_per_1m_input_tokens,
            self.cost_per_1m_output_tokens,
            self.cost_per_1m_input_tokens_cached,
        )
