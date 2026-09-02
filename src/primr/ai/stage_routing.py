"""Runtime bridge from production stage declarations to the capability router."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from primr.ai.capability_routing import (
    BackendCapabilities,
    BackendKind,
    BillingMode,
    InferenceProfile,
    LatencyClass,
    ReasoningDepth,
    RoutingPolicy,
    TrustSensitivity,
    backends_with_availability,
    route_stage,
    sanitized_availability_metadata,
)
from primr.ai.provider_availability import LocalCapacityBusyError
from primr.ai.provider_availability_collectors import (
    LOCAL_OPENAI_COMPATIBLE_PROVIDER,
    collect_provider_availability_snapshots,
)
from primr.ai.routing import Role, pick_model_for_legacy_type
from primr.config.inference import INFERENCE_PROFILE_ENV, host_agent_may_bill_acknowledged
from primr.config.model_registry import ModelConfig
from primr.config.models import PrimrModels
from primr.core.stage_inventory import get_production_stage
from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from primr.ai.provider_availability import ProviderQuotaSnapshot

logger = get_logger(__name__)
DEFAULT_INFERENCE_PROFILE = InferenceProfile.CLOUD
StageUsageByModel = dict[str, dict[str, int | float]]


@dataclass(frozen=True)
class StageModelRoute:
    """Resolved runtime route for a stage that still executes through ``llm``."""

    stage_id: str
    profile: InferenceProfile
    model_name: str
    backend_id: str
    backend_kind: str
    billing_mode: str
    estimated_cost_usd: float | None
    expected_input_tokens: int
    expected_output_tokens: int
    routed: bool
    reasons: tuple[str, ...]
    rejections: tuple[str, ...]
    availability: dict[str, Any] | None = None
    execution_mode: str = "llm"
    host_agent_kind: str | None = None
    billing_acknowledged: bool = False
    promotion_status: str | None = None

    def log_metadata(self) -> dict[str, Any]:
        """Return safe structured-log metadata for this route."""

        data: dict[str, Any] = {
            "stage_id": self.stage_id,
            "inference_profile": self.profile.value,
            "backend_id": self.backend_id,
            "backend_kind": self.backend_kind,
            "billing_mode": self.billing_mode,
            "routed": self.routed,
            "execution_mode": self.execution_mode,
            "route_reasons": list(self.reasons),
            "expected_input_tokens": self.expected_input_tokens,
            "expected_output_tokens": self.expected_output_tokens,
        }
        if self.host_agent_kind:
            data["host_agent_kind"] = self.host_agent_kind
        if self.billing_acknowledged:
            data["billing_acknowledged"] = True
        if self.promotion_status:
            data["promotion_status"] = self.promotion_status
        if self.estimated_cost_usd is not None:
            data["estimated_cost_usd"] = round(self.estimated_cost_usd, 6)
        if self.rejections:
            data["fallback_rejections"] = list(self.rejections)
        if self.availability is not None:
            data["availability"] = dict(self.availability)
        return data


def current_inference_profile() -> InferenceProfile:
    """Return the operator-selected inference profile from the runtime environment."""

    raw = os.getenv(INFERENCE_PROFILE_ENV, DEFAULT_INFERENCE_PROFILE.value)
    return _coerce_profile(raw)


def resolve_stage_model(
    stage_id: str,
    *,
    legacy_model_type: str,
    profile: InferenceProfile | str | None = None,
    availability_snapshots: Iterable[ProviderQuotaSnapshot] | None = None,
    require_availability_snapshot: bool = False,
) -> StageModelRoute:
    """Resolve the model for a production stage through the capability router.

    Runtime routing remains conservative: cloud/local-compatible selections
    execute through existing provider seams, while official host-agent
    selections return an explicit ``host_agent`` execution mode for bounded
    stage-specific delegation.
    """

    stage = get_production_stage(stage_id)
    selected_profile = (
        _coerce_profile(profile) if profile is not None else current_inference_profile()
    )
    legacy_model = pick_model_for_legacy_type(legacy_model_type)
    legacy_backend = _backend_for_model(legacy_model, stage.role)
    candidate_backends = [
        backend
        for backend in (
            *_supported_host_agent_backends(stage.stage_id),
            *_supported_deep_research_backends(stage),
            legacy_backend,
        )
        if backend is not None
    ]
    if not candidate_backends:
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name=legacy_model,
            backend_id=legacy_model,
            backend_kind="unknown",
            billing_mode=BillingMode.UNKNOWN.value,
            estimated_cost_usd=None,
            expected_input_tokens=stage.expected_input_tokens,
            expected_output_tokens=stage.expected_output_tokens,
            routed=False,
            reasons=("legacy_model_unregistered",),
            rejections=("legacy_model_unregistered",),
        )
    snapshots = (
        tuple(availability_snapshots)
        if availability_snapshots is not None
        else _default_provider_availability_snapshots(
            include_local=selected_profile is InferenceProfile.LOCAL
        )
    )
    if snapshots:
        candidate_backends = list(
            backends_with_availability(
                candidate_backends,
                snapshots,
                require_snapshot=require_availability_snapshot,
            )
        )

    plan = route_stage(
        stage.to_requirements(),
        candidate_backends,
        RoutingPolicy(
            profile=selected_profile,
            allow_potentially_metered_handoff=host_agent_may_bill_acknowledged(),
        ),
    )
    rejection_reasons = tuple(reason for item in plan.rejections for reason in item.reasons)
    if plan.primary is not None:
        return _route_from_candidate(
            stage,
            selected_profile,
            plan.primary.backend,
            plan.primary.estimated_cost_usd,
            plan.primary.reasons,
            rejection_reasons if selected_profile is InferenceProfile.HYBRID else (),
        )

    # Premium deep-research stages must not fall through to a non-deep-research
    # legacy model; that would mis-advertise the backend and spend incorrectly.
    if stage.requires_deep_research:
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name="",
            backend_id="deep-research-unavailable",
            backend_kind=BackendKind.CLOUD_API.value,
            billing_mode=BillingMode.API_DOLLARS.value,
            estimated_cost_usd=None,
            expected_input_tokens=stage.expected_input_tokens,
            expected_output_tokens=stage.expected_output_tokens,
            routed=False,
            reasons=("deep_research_backend_unavailable",),
            rejections=rejection_reasons,
            execution_mode="unavailable",
        )

    if selected_profile is InferenceProfile.AGENT:
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name="",
            backend_id="agent-profile-unavailable",
            backend_kind=BackendKind.HOST_AGENT.value,
            billing_mode=BillingMode.UNKNOWN.value,
            estimated_cost_usd=None,
            expected_input_tokens=stage.expected_input_tokens,
            expected_output_tokens=stage.expected_output_tokens,
            routed=False,
            reasons=("agent_profile_unavailable",),
            rejections=rejection_reasons,
            execution_mode="unavailable",
        )

    if selected_profile is InferenceProfile.LOCAL:
        local_availability = _local_profile_availability(snapshots)
        backend_id, unavailable_reason = _local_unavailable_route_state(local_availability)
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name="",
            backend_id=backend_id,
            backend_kind=BackendKind.LOCAL.value,
            billing_mode=BillingMode.ZERO_API_RUNTIME.value,
            estimated_cost_usd=0.0,
            expected_input_tokens=stage.expected_input_tokens,
            expected_output_tokens=stage.expected_output_tokens,
            routed=False,
            reasons=(unavailable_reason, "no_paid_fallback"),
            rejections=rejection_reasons,
            availability=local_availability,
            execution_mode="unavailable",
        )

    if legacy_backend is None:
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name=legacy_model,
            backend_id=legacy_model,
            backend_kind="unknown",
            billing_mode=BillingMode.UNKNOWN.value,
            estimated_cost_usd=None,
            expected_input_tokens=stage.expected_input_tokens,
            expected_output_tokens=stage.expected_output_tokens,
            routed=False,
            reasons=("legacy_model_unregistered",),
            rejections=("legacy_model_unregistered",),
        )
    legacy_backend_for_log = next(
        (
            backend
            for backend in candidate_backends
            if backend.backend_id == legacy_backend.backend_id
        ),
        legacy_backend,
    )
    return StageModelRoute(
        stage_id=stage.stage_id,
        profile=selected_profile,
        model_name=legacy_model,
        backend_id=legacy_backend_for_log.backend_id,
        backend_kind=BackendKind(legacy_backend_for_log.kind).value,
        billing_mode=BillingMode(legacy_backend_for_log.billing_mode).value,
        estimated_cost_usd=None,
        expected_input_tokens=stage.expected_input_tokens,
        expected_output_tokens=stage.expected_output_tokens,
        routed=False,
        reasons=("legacy_fallback",),
        rejections=rejection_reasons,
        availability=_availability_metadata(legacy_backend_for_log),
    )


def _supported_host_agent_backends(stage_id: str) -> tuple[BackendCapabilities, ...]:
    """Return host-agent backends without making routing import heavy."""

    if stage_id != "fast.source_relevance":
        return ()
    try:
        from primr.ai.host_agent_cli import supported_host_agent_backends

        return supported_host_agent_backends()
    except Exception as exc:
        logger.debug("Host-agent backend discovery skipped: %s", exc, exc_info=True)
        return ()


def _supported_deep_research_backends(stage: Any) -> tuple[BackendCapabilities, ...]:
    """Return cloud Deep Research agent backends for premium stages.

    The Deep Research agent slug is not a full chat ModelConfig row, so it is
    constructed explicitly with supports_deep_research=True. Availability is
    gated on GEMINI_API_KEY only; no live probe runs here.
    """

    if not getattr(stage, "requires_deep_research", False):
        return ()
    try:
        from primr.config.models import PrimrModels

        agent_id = PrimrModels.DEEP_RESEARCH_AGENT
        available = bool(os.getenv("GEMINI_API_KEY"))
        return (
            BackendCapabilities(
                backend_id=agent_id,
                kind=BackendKind.CLOUD_API,
                roles=(Role.REASONING,),
                reasoning_depth=ReasoningDepth.PREMIUM,
                max_trust_sensitivity=TrustSensitivity.HIGH,
                max_context_tokens=max(
                    1_000_000, int(getattr(stage, "min_context_tokens", 1_000_000) or 1_000_000)
                ),
                supports_web_search=True,
                supports_deep_research=True,
                supports_structured_output=True,
                latency_class=LatencyClass.LONG_RUNNING,
                billing_mode=BillingMode.API_DOLLARS,
                available=available,
                metadata={
                    "provider": "google",
                    "display_name": "Gemini Deep Research",
                    "deep_research_agent": True,
                },
            ),
        )
    except Exception as exc:
        logger.debug("Deep research backend discovery skipped: %s", exc, exc_info=True)
        return ()


def _route_from_candidate(
    stage: Any,
    selected_profile: InferenceProfile,
    backend: BackendCapabilities,
    estimated_cost_usd: float | None,
    reasons: tuple[str, ...],
    rejections: tuple[str, ...],
) -> StageModelRoute:
    backend_kind = BackendKind(backend.kind)
    execution_mode = "host_agent" if backend_kind is BackendKind.HOST_AGENT else "llm"
    host_agent_kind = _host_agent_kind(backend) if execution_mode == "host_agent" else None
    return StageModelRoute(
        stage_id=stage.stage_id,
        profile=selected_profile,
        model_name=backend.backend_id,
        backend_id=backend.backend_id,
        backend_kind=backend_kind.value,
        billing_mode=BillingMode(backend.billing_mode).value,
        estimated_cost_usd=estimated_cost_usd,
        expected_input_tokens=stage.expected_input_tokens,
        expected_output_tokens=stage.expected_output_tokens,
        routed=True,
        reasons=reasons,
        rejections=rejections,
        availability=_availability_metadata(backend),
        execution_mode=execution_mode,
        host_agent_kind=host_agent_kind,
        billing_acknowledged=backend.metadata.get("billing_acknowledged") is True,
        promotion_status=_optional_backend_metadata_text(backend, "promotion_status"),
    )


def _host_agent_kind(backend: BackendCapabilities) -> str | None:
    runner = backend.metadata.get("runner")
    if isinstance(runner, str) and runner.strip():
        return runner.strip()
    return None


def _optional_backend_metadata_text(
    backend: BackendCapabilities,
    key: str,
) -> str | None:
    value = backend.metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def record_stage_route_usage(
    folder_path: str | os.PathLike[str] | None,
    route: StageModelRoute,
    *,
    outcome: str,
    input_items: int | None = None,
    output_items: int | None = None,
    duration_seconds: float | None = None,
    failure_class: str | None = None,
    failure: Exception | None = None,
    usage_delta: dict[str, Any] | None = None,
) -> None:
    """Append body-free route usage metadata to the per-run state file."""

    if folder_path is None:
        return

    from primr.core.run_state_io import _mutate_run_state

    record = {
        "ts": datetime.now().isoformat(),
        "outcome": outcome,
        **route.log_metadata(),
    }
    if input_items is not None:
        record["input_items"] = input_items
    if output_items is not None:
        record["output_items"] = output_items
    if duration_seconds is not None:
        record["duration_seconds"] = round(max(0.0, duration_seconds), 3)
    if failure_class:
        record["failure_class"] = failure_class
    if isinstance(failure, LocalCapacityBusyError):
        record["capacity_failure"] = failure.as_metadata()
    if usage_delta:
        _apply_usage_delta(record, usage_delta)

    def append_route(state: dict[str, Any]) -> None:
        routes = state.get("stage_routes", [])
        if not isinstance(routes, list):
            routes = []
        routes.append(record)
        state["stage_routes"] = routes[-200:]

    _mutate_run_state(str(folder_path), append_route)


def stage_route_failure_class(
    route: StageModelRoute | Any,
    error: Exception | None = None,
) -> str:
    """Return a stable body-free failure code for route records."""

    if isinstance(error, LocalCapacityBusyError):
        return "local_capacity_busy"

    metadata = route.log_metadata()
    reasons = getattr(route, "reasons", ())
    if not reasons:
        raw_reasons = metadata.get("route_reasons", ())
        reasons = tuple(raw_reasons) if isinstance(raw_reasons, list | tuple) else ()
    known_unavailable = {
        "agent_profile_unavailable",
        "local_adapter_unavailable",
        "local_capacity_busy",
        "local_capacity_unavailable",
        "local_capacity_unknown",
        "local_profile_unavailable",
        "deep_research_backend_unavailable",
    }
    for reason in reasons:
        if reason in known_unavailable:
            return reason

    if getattr(route, "execution_mode", "llm") == "unavailable":
        profile = metadata.get("inference_profile")
        if profile == InferenceProfile.AGENT.value:
            return "agent_profile_unavailable"
        if profile == InferenceProfile.LOCAL.value:
            availability = metadata.get("availability", {})
            if isinstance(availability, dict) and availability.get("state") == "busy":
                return "local_capacity_busy"
            return "local_profile_unavailable"
        return "route_unavailable"
    if error is not None:
        return type(error).__name__
    return "route_failure"


def capture_stage_usage() -> StageUsageByModel:
    """Return cumulative provider token usage by model for stage delta accounting."""

    usage: StageUsageByModel = {}
    try:
        from primr.ai.client import get_ai_client_usage_by_model

        _merge_usage_by_model(usage, get_ai_client_usage_by_model())
    except Exception as exc:
        logger.debug("Legacy AI client usage snapshot skipped: %s", exc, exc_info=True)

    try:
        from primr.ai.grok_client import get_grok_session_usage_by_model

        _merge_usage_by_model(usage, get_grok_session_usage_by_model())
    except Exception as exc:
        logger.debug("Grok session usage snapshot skipped: %s", exc, exc_info=True)

    try:
        from primr.ai.llm import get_llm_provider_usage_by_model

        _merge_usage_by_model(usage, get_llm_provider_usage_by_model())
    except Exception as exc:
        logger.debug("LLM provider usage snapshot skipped: %s", exc, exc_info=True)

    return usage


def stage_usage_delta(
    before: StageUsageByModel,
    after: StageUsageByModel | None = None,
) -> dict[str, Any]:
    """Return body-free token/cache/cost deltas between two usage snapshots."""

    current = capture_stage_usage() if after is None else after
    models: dict[str, dict[str, int | float | None]] = {}
    total_input = 0
    total_output = 0
    total_cached = 0
    total_cost = 0.0
    unpriced = False
    for model_name in sorted(set(before) | set(current)):
        prior = before.get(model_name, {})
        latest = current.get(model_name, {})
        input_tokens = max(
            0,
            _usage_int(latest, "input_tokens") - _usage_int(prior, "input_tokens"),
        )
        output_tokens = max(
            0,
            _usage_int(latest, "output_tokens") - _usage_int(prior, "output_tokens"),
        )
        cached_input_tokens = max(
            0,
            _usage_int(latest, "cached_input_tokens") - _usage_int(prior, "cached_input_tokens"),
        )
        actual_cost_usd = max(
            0.0,
            _usage_float(latest, "actual_cost_usd") - _usage_float(prior, "actual_cost_usd"),
        )
        actual_cost_calls = max(
            0,
            _usage_int(latest, "actual_cost_calls") - _usage_int(prior, "actual_cost_calls"),
        )
        call_count = max(
            0,
            _usage_int(latest, "call_count") - _usage_int(prior, "call_count"),
        )
        if not (
            input_tokens or output_tokens or cached_input_tokens or actual_cost_usd or call_count
        ):
            continue
        if call_count > 0 and actual_cost_calls == call_count:
            priced_cost: float | None = actual_cost_usd
        else:
            priced_cost = _actual_usage_cost(
                model_name, input_tokens, output_tokens, cached_input_tokens
            )
        models[model_name] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "actual_cost_usd": None if priced_cost is None else round(priced_cost, 8),
        }
        total_input += input_tokens
        total_output += output_tokens
        total_cached += cached_input_tokens
        if priced_cost is None:
            unpriced = True
        else:
            total_cost += priced_cost

    if not models:
        return {}
    return {
        "actual_input_tokens": total_input,
        "actual_output_tokens": total_output,
        "actual_cached_input_tokens": total_cached,
        "actual_cost_usd": None if unpriced else round(total_cost, 8),
        "actual_usage_by_model": models,
    }


def _backend_for_model(model_name: str, role: Role) -> BackendCapabilities | None:
    config = PrimrModels.get_model_config(model_name)
    if config is None:
        return None
    return BackendCapabilities.from_model_config(
        config,
        roles=(role,),
        available=_provider_configured(config) and not config.deprecated,
        reasoning_depth=_reasoning_depth_for_model(config, role),
        max_trust_sensitivity=_trust_for_role(role),
        supports_structured_output=True,
    )


def _availability_metadata(backend: BackendCapabilities) -> dict[str, Any] | None:
    value = backend.metadata.get("availability")
    if not isinstance(value, dict):
        return None
    return dict(value)


def _default_provider_availability_snapshots(
    *,
    include_local: bool = False,
) -> tuple[ProviderQuotaSnapshot, ...]:
    """Collect routing availability, probing local only for an explicit local profile."""

    try:
        return tuple(collect_provider_availability_snapshots(include_local=include_local))
    except Exception as exc:
        logger.debug("Provider availability collection skipped: %s", exc, exc_info=True)
        return ()


def _local_profile_availability(
    snapshots: Iterable[ProviderQuotaSnapshot],
) -> dict[str, Any]:
    for snapshot in snapshots:
        if snapshot.provider in {LOCAL_OPENAI_COMPATIBLE_PROVIDER, "ollama"}:
            return sanitized_availability_metadata(snapshot)
    return {
        "available": False,
        "error": "missing_local_availability_snapshot",
        "provider": LOCAL_OPENAI_COMPATIBLE_PROVIDER,
        "quota_source": "not_collected",
        "retryable": False,
        "stale": False,
        "state": "unavailable",
    }


def _local_unavailable_route_state(availability: dict[str, Any]) -> tuple[str, str]:
    if availability.get("available") is True:
        return "local-adapter-unavailable", "local_adapter_unavailable"
    if availability.get("state") == "busy":
        return "local-capacity-busy", "local_capacity_busy"
    if availability.get("error") == "missing_local_availability_snapshot":
        return "local-capacity-unknown", "local_capacity_unknown"
    if availability.get("state") == "unavailable":
        return "local-capacity-unavailable", "local_capacity_unavailable"
    return "local-profile-unavailable", "local_profile_unavailable"


def _merge_usage_by_model(
    target: StageUsageByModel,
    source: dict[str, dict[str, int]] | dict[str, dict[str, int | float]],
) -> None:
    for model_name, values in source.items():
        if not isinstance(model_name, str) or not isinstance(values, dict):
            continue
        bucket = target.setdefault(
            model_name,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "actual_cost_usd": 0.0,
                "actual_cost_calls": 0,
                "call_count": 0,
            },
        )
        bucket["input_tokens"] += _usage_int(values, "input_tokens")
        bucket["output_tokens"] += _usage_int(values, "output_tokens")
        bucket["cached_input_tokens"] += _usage_int(values, "cached_input_tokens")
        bucket["actual_cost_usd"] += _usage_float(values, "actual_cost_usd")
        bucket["actual_cost_calls"] += _usage_int(values, "actual_cost_calls")
        bucket["call_count"] += _usage_int(values, "call_count")


def _usage_int(values: dict[str, int] | dict[str, int | float], key: str) -> int:
    value = values.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _usage_float(values: dict[str, int] | dict[str, int | float], key: str) -> float:
    value = values.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return max(0.0, float(value))


def _actual_usage_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
) -> float | None:
    try:
        return PrimrModels.calculate_cost(
            model_name,
            input_tokens,
            output_tokens,
            cached_input_tokens=cached_input_tokens,
            prompt_tokens=input_tokens,
        )
    except KeyError:
        return None


def _apply_usage_delta(record: dict[str, Any], usage_delta: dict[str, Any]) -> None:
    for key in (
        "actual_input_tokens",
        "actual_output_tokens",
        "actual_cached_input_tokens",
    ):
        value = usage_delta.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            record[key] = value
    cost = usage_delta.get("actual_cost_usd")
    if isinstance(cost, int | float) and not isinstance(cost, bool) and cost >= 0:
        record["actual_cost_usd"] = round(float(cost), 8)
    models = usage_delta.get("actual_usage_by_model")
    if isinstance(models, dict) and models:
        record["actual_usage_by_model"] = models


def _coerce_profile(profile: InferenceProfile | str) -> InferenceProfile:
    try:
        return InferenceProfile(profile)
    except ValueError:
        return DEFAULT_INFERENCE_PROFILE


def _provider_configured(config: ModelConfig) -> bool:
    provider = config.provider
    if provider == "google":
        return bool(os.getenv("GEMINI_API_KEY"))
    if provider == "xai":
        return bool(os.getenv("XAI_API_KEY"))
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if provider == "openrouter":
        from primr.ai.providers.openrouter import openrouter_routing_ready

        return openrouter_routing_ready()
    if provider == "bedrock":
        return bool(
            os.getenv("AWS_BEARER_TOKEN_BEDROCK")
            or os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_PROFILE")
        )
    if provider == "foundry":
        return bool(os.getenv("AZURE_OPENAI_API_KEY"))
    return provider == "ollama"


def _reasoning_depth_for_model(config: ModelConfig, role: Role) -> ReasoningDepth:
    if role is Role.REASONING or role is Role.PRO:
        return ReasoningDepth.HIGH
    if role is Role.WRITING:
        return ReasoningDepth.MEDIUM if config.supports_thinking else ReasoningDepth.LOW
    return ReasoningDepth.MEDIUM if config.supports_thinking else ReasoningDepth.LOW


def _trust_for_role(role: Role) -> TrustSensitivity:
    if role in (Role.REASONING, Role.PRO, Role.WRITING):
        return TrustSensitivity.HIGH
    return TrustSensitivity.MEDIUM
