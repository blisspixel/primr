"""Runtime bridge from production stage declarations to the capability router."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from primr.ai.capability_routing import (
    BackendCapabilities,
    BackendKind,
    BillingMode,
    InferenceProfile,
    ReasoningDepth,
    RoutingPolicy,
    TrustSensitivity,
    route_stage,
)
from primr.ai.routing import Role, pick_model_for_legacy_type
from primr.config.model_registry import ModelConfig
from primr.config.models import PrimrModels
from primr.core.stage_inventory import get_production_stage

INFERENCE_PROFILE_ENV = "PRIMR_INFERENCE_PROFILE"
DEFAULT_INFERENCE_PROFILE = InferenceProfile.CLOUD


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
    routed: bool
    reasons: tuple[str, ...]
    rejections: tuple[str, ...]

    def log_metadata(self) -> dict[str, Any]:
        """Return safe structured-log metadata for this route."""

        data: dict[str, Any] = {
            "stage_id": self.stage_id,
            "inference_profile": self.profile.value,
            "backend_id": self.backend_id,
            "backend_kind": self.backend_kind,
            "billing_mode": self.billing_mode,
            "routed": self.routed,
            "route_reasons": list(self.reasons),
        }
        if self.estimated_cost_usd is not None:
            data["estimated_cost_usd"] = round(self.estimated_cost_usd, 6)
        if self.rejections:
            data["fallback_rejections"] = list(self.rejections)
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
) -> StageModelRoute:
    """Resolve the model for a production stage through the capability router.

    The first production slice is intentionally conservative: it routes the
    legacy role-selected backend through ``route_stage()`` and then executes the
    returned model through existing provider seams. If the declared stage and
    selected profile reject that backend, the route object records the rejection
    but still returns the legacy model so current runs do not regress.
    """

    stage = get_production_stage(stage_id)
    selected_profile = (
        _coerce_profile(profile) if profile is not None else current_inference_profile()
    )
    legacy_model = pick_model_for_legacy_type(legacy_model_type)
    backend = _backend_for_model(legacy_model, stage.role)
    if backend is None:
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name=legacy_model,
            backend_id=legacy_model,
            backend_kind="unknown",
            billing_mode=BillingMode.UNKNOWN.value,
            estimated_cost_usd=None,
            routed=False,
            reasons=("legacy_model_unregistered",),
            rejections=("legacy_model_unregistered",),
        )

    plan = route_stage(
        stage.to_requirements(),
        (backend,),
        RoutingPolicy(profile=selected_profile),
    )
    if plan.primary is not None:
        primary = plan.primary
        return StageModelRoute(
            stage_id=stage.stage_id,
            profile=selected_profile,
            model_name=primary.backend.backend_id,
            backend_id=primary.backend.backend_id,
            backend_kind=BackendKind(primary.backend.kind).value,
            billing_mode=BillingMode(primary.backend.billing_mode).value,
            estimated_cost_usd=primary.estimated_cost_usd,
            routed=True,
            reasons=primary.reasons,
            rejections=(),
        )

    rejection_reasons = tuple(reason for item in plan.rejections for reason in item.reasons)
    return StageModelRoute(
        stage_id=stage.stage_id,
        profile=selected_profile,
        model_name=legacy_model,
        backend_id=backend.backend_id,
        backend_kind=BackendKind(backend.kind).value,
        billing_mode=BillingMode(backend.billing_mode).value,
        estimated_cost_usd=None,
        routed=False,
        reasons=("legacy_fallback",),
        rejections=rejection_reasons,
    )


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
