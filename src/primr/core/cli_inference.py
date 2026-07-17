"""CLI policy for capability-routed and host-agent inference stages."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Protocol

from primr.config.inference import (
    EXPERIMENTAL_HOST_PROMOTION_STATUS,
    configure_inference_environment,
)


class _InferenceConfig(Protocol):
    @property
    def inference_profile(self) -> str:
        raise NotImplementedError

    @property
    def acknowledge_host_agent_may_bill(self) -> bool:
        raise NotImplementedError


class _CostEstimate(Protocol):
    notes: list[str]


POTENTIALLY_METERED_HOST_STAGES = ("fast.source_relevance",)
HOST_AGENT_ESTIMATE_NOTE = (
    "Experimental host-agent usage is acknowledged for fast.source_relevance when "
    "an installed Codex CLI qualifies. This route has not cleared its promotion eval. "
    "Host charges are unknown and excluded from Estimated Total and --budget."
)
HOST_AGENT_RUNTIME_WARNING = (
    "Experimental, potentially metered host-agent use acknowledged. Primr may route "
    "fast.source_relevance through an installed Codex CLI. The route is not promoted, "
    "and any host charge is outside Primr's dollar estimate and --budget."
)


class _Console(Protocol):
    def error(self, message: str) -> None:
        raise NotImplementedError

    def warn(self, message: str) -> None:
        raise NotImplementedError


def validate_inference_options(
    inference_profile: str,
    acknowledge_host_agent_may_bill: bool,
) -> str | None:
    """Return a user-facing error for an unsafe or meaningless option pair."""

    if acknowledge_host_agent_may_bill and inference_profile != "hybrid":
        return "--acknowledge-host-agent-may-bill requires --inference hybrid"
    return None


def configure_inference_runtime(
    inference_profile: str,
    acknowledge_host_agent_may_bill: bool,
    *,
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Apply one run's inference policy without leaving stale acknowledgment state."""

    configure_inference_environment(
        inference_profile,
        acknowledge_host_agent_may_bill,
        environment=environment,
    )


def prepare_inference_runtime(config: _InferenceConfig, console: _Console) -> bool:
    """Validate, apply, and visibly disclose the runtime inference policy."""

    error = validate_inference_options(
        config.inference_profile,
        config.acknowledge_host_agent_may_bill,
    )
    if error:
        console.error(error)
        return False
    configure_inference_runtime(
        config.inference_profile,
        config.acknowledge_host_agent_may_bill,
    )
    if config.acknowledge_host_agent_may_bill:
        console.warn(HOST_AGENT_RUNTIME_WARNING)
    return True


def prepare_batch_inference_runtime(config: _InferenceConfig, console: _Console) -> bool:
    """Apply batch inference policy while rejecting uncapped experimental fan-out."""

    if config.acknowledge_host_agent_may_bill:
        console.error("--acknowledge-host-agent-may-bill is limited to single-company research")
        return False
    configure_inference_runtime(config.inference_profile, False)
    return True


def append_inference_estimate_note(
    config: _InferenceConfig,
    estimate: _CostEstimate,
) -> None:
    """Disclose unpriced host billing on every estimate and budget surface."""

    acknowledged = getattr(config, "acknowledge_host_agent_may_bill", False)
    if acknowledged and HOST_AGENT_ESTIMATE_NOTE not in estimate.notes:
        estimate.notes.append(HOST_AGENT_ESTIMATE_NOTE)


def inference_estimate_metadata(config: _InferenceConfig) -> dict[str, object]:
    """Return body-free inference and billing metadata for JSON estimates."""

    acknowledged = config.acknowledge_host_agent_may_bill
    return {
        "profile": config.inference_profile,
        "host_agent": {
            "enabled": acknowledged,
            "runner": "codex_cli" if acknowledged else None,
            "billing_mode": "potentially_metered" if acknowledged else "unknown",
            "billing_acknowledged": acknowledged,
            "promotion_status": EXPERIMENTAL_HOST_PROMOTION_STATUS if acknowledged else None,
            "eligible_stages": list(POTENTIALLY_METERED_HOST_STAGES) if acknowledged else [],
            "cost_included_in_estimate": False if acknowledged else None,
            "covered_by_budget": False if acknowledged else None,
        },
    }
