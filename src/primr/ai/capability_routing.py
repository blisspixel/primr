"""Pure capability router for per-stage inference backends.

This module is the next layer above the legacy role router in
``primr.ai.routing``. It does not call providers, inspect environment
variables, launch host agents, or mutate circuit-breaker state. Callers provide
stage requirements and available backend capability rows; the router returns an
ordered plan plus explicit rejection reasons.

The boundary is important for agentic balance: Primr chooses the stage, packet,
budget policy, and allowed backend class. A model or host agent only exercises
judgment inside that bounded stage.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from primr.ai.routing import Role

if TYPE_CHECKING:
    from primr.config.model_registry import ModelConfig


class ReasoningDepth(str, Enum):
    """Coarse reasoning tier required by a stage or offered by a backend."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PREMIUM = "premium"


class TrustSensitivity(str, Enum):
    """How sensitive a stage is to model quality and provenance risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyClass(str, Enum):
    """Expected latency class for a backend or accepted by a stage."""

    INTERACTIVE = "interactive"
    STANDARD = "standard"
    LONG_RUNNING = "long_running"


class BackendKind(str, Enum):
    """Inference backend families the capability router can rank."""

    CLOUD_API = "cloud_api"
    GATEWAY = "gateway"
    HOST_AGENT = "host_agent"
    LOCAL = "local"


class BillingMode(str, Enum):
    """Cost-reporting category for a candidate backend."""

    API_DOLLARS = "api_dollars"
    API_CREDITS = "api_credits"
    HOST_PLAN_USAGE = "host_plan_usage"
    ZERO_API_RUNTIME = "zero_api_runtime"
    UNKNOWN = "unknown"


class InferenceProfile(str, Enum):
    """Operator-selected inference profile."""

    CLOUD = "cloud"
    AGENT = "agent"
    HYBRID = "hybrid"
    LOCAL = "local"


_REASONING_RANK: Mapping[ReasoningDepth, int] = {
    ReasoningDepth.LOW: 0,
    ReasoningDepth.MEDIUM: 1,
    ReasoningDepth.HIGH: 2,
    ReasoningDepth.PREMIUM: 3,
}

_TRUST_RANK: Mapping[TrustSensitivity, int] = {
    TrustSensitivity.LOW: 0,
    TrustSensitivity.MEDIUM: 1,
    TrustSensitivity.HIGH: 2,
}

_LATENCY_RANK: Mapping[LatencyClass, int] = {
    LatencyClass.INTERACTIVE: 0,
    LatencyClass.STANDARD: 1,
    LatencyClass.LONG_RUNNING: 2,
}


@dataclass(frozen=True)
class StageRequirements:
    """Backend requirements for one bounded pipeline stage."""

    stage_id: str
    role: Role | str
    min_reasoning: ReasoningDepth | str = ReasoningDepth.LOW
    trust_sensitivity: TrustSensitivity | str = TrustSensitivity.MEDIUM
    min_context_tokens: int = 0
    expected_input_tokens: int = 0
    expected_output_tokens: int = 0
    requires_web_search: bool = False
    requires_deep_research: bool = False
    requires_structured_output: bool = False
    accepts_host_agent: bool = False
    accepts_local: bool = False
    accepts_gateway: bool = True
    acceptable_latency: LatencyClass | str = LatencyClass.STANDARD
    allowed_backend_ids: Iterable[str] = field(default_factory=tuple)
    blocked_backend_ids: Iterable[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.stage_id.strip():
            raise ValueError("stage_id is required")
        object.__setattr__(self, "role", Role(self.role))
        object.__setattr__(self, "min_reasoning", ReasoningDepth(self.min_reasoning))
        object.__setattr__(self, "trust_sensitivity", TrustSensitivity(self.trust_sensitivity))
        object.__setattr__(self, "acceptable_latency", LatencyClass(self.acceptable_latency))
        if self.min_context_tokens < 0:
            raise ValueError("min_context_tokens must be non-negative")
        if self.expected_input_tokens < 0:
            raise ValueError("expected_input_tokens must be non-negative")
        if self.expected_output_tokens < 0:
            raise ValueError("expected_output_tokens must be non-negative")
        object.__setattr__(
            self,
            "allowed_backend_ids",
            frozenset(str(item).strip() for item in self.allowed_backend_ids if str(item).strip()),
        )
        object.__setattr__(
            self,
            "blocked_backend_ids",
            frozenset(str(item).strip() for item in self.blocked_backend_ids if str(item).strip()),
        )


@dataclass(frozen=True)
class BackendCapabilities:
    """Static capability row for one model, gateway, local server, or host runner."""

    backend_id: str
    kind: BackendKind | str
    roles: Iterable[Role | str]
    reasoning_depth: ReasoningDepth | str = ReasoningDepth.LOW
    max_trust_sensitivity: TrustSensitivity | str = TrustSensitivity.MEDIUM
    max_context_tokens: int = 128_000
    supports_web_search: bool = False
    supports_deep_research: bool = False
    supports_structured_output: bool = True
    latency_class: LatencyClass | str = LatencyClass.STANDARD
    billing_mode: BillingMode | str = BillingMode.UNKNOWN
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    available: bool = True
    official_host_runner: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.backend_id.strip():
            raise ValueError("backend_id is required")
        object.__setattr__(self, "kind", BackendKind(self.kind))
        roles = frozenset(Role(role) for role in self.roles)
        if not roles:
            raise ValueError("roles must not be empty")
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "reasoning_depth", ReasoningDepth(self.reasoning_depth))
        object.__setattr__(
            self,
            "max_trust_sensitivity",
            TrustSensitivity(self.max_trust_sensitivity),
        )
        object.__setattr__(self, "latency_class", LatencyClass(self.latency_class))
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")
        if self.input_cost_per_million is not None and self.input_cost_per_million < 0:
            raise ValueError("input_cost_per_million must be non-negative")
        if self.output_cost_per_million is not None and self.output_cost_per_million < 0:
            raise ValueError("output_cost_per_million must be non-negative")
        billing_mode = BillingMode(self.billing_mode)
        if billing_mode is BillingMode.UNKNOWN:
            billing_mode = _default_billing_mode(BackendKind(self.kind))
        object.__setattr__(self, "billing_mode", billing_mode)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_model_config(
        cls,
        model: ModelConfig,
        *,
        roles: Iterable[Role | str],
        available: bool = True,
        reasoning_depth: ReasoningDepth | str = ReasoningDepth.MEDIUM,
        max_trust_sensitivity: TrustSensitivity | str = TrustSensitivity.MEDIUM,
        supports_web_search: bool = False,
        supports_deep_research: bool = False,
        supports_structured_output: bool = True,
        latency_class: LatencyClass | str = LatencyClass.STANDARD,
    ) -> BackendCapabilities:
        """Build a capability row from the existing model registry metadata."""

        kind = BackendKind.LOCAL if model.provider == "ollama" else BackendKind.CLOUD_API
        return cls(
            backend_id=model.name,
            kind=kind,
            roles=roles,
            reasoning_depth=reasoning_depth,
            max_trust_sensitivity=max_trust_sensitivity,
            max_context_tokens=model.max_input_tokens,
            supports_web_search=supports_web_search,
            supports_deep_research=supports_deep_research,
            supports_structured_output=supports_structured_output,
            latency_class=latency_class,
            input_cost_per_million=model.cost_per_1m_input_tokens,
            output_cost_per_million=model.cost_per_1m_output_tokens,
            available=available and not model.deprecated,
            metadata={"provider": model.provider, "display_name": model.display_name},
        )


@dataclass(frozen=True)
class RoutingPolicy:
    """Operator policy applied while ranking compatible backends."""

    profile: InferenceProfile | str = InferenceProfile.CLOUD
    allow_profile_fallback: bool = False
    require_official_host_runner: bool = True
    allow_api_credit_handoff: bool = False
    prefer_zero_api_runtime: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile", InferenceProfile(self.profile))


@dataclass(frozen=True)
class RouteCandidate:
    """One compatible backend in ranked order."""

    backend: BackendCapabilities
    estimated_cost_usd: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RejectedCandidate:
    """One rejected backend and the reason codes that removed it."""

    backend_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RoutePlan:
    """Pure routing result for one stage."""

    requirements: StageRequirements
    policy: RoutingPolicy
    candidates: tuple[RouteCandidate, ...]
    rejections: tuple[RejectedCandidate, ...]

    @property
    def primary(self) -> RouteCandidate | None:
        """Return the first compatible backend, if one exists."""

        return self.candidates[0] if self.candidates else None

    @property
    def is_routable(self) -> bool:
        """Whether at least one backend met the requirements."""

        return bool(self.candidates)


def route_stage(
    requirements: StageRequirements,
    backends: Iterable[BackendCapabilities],
    policy: RoutingPolicy | None = None,
) -> RoutePlan:
    """Return an ordered backend plan for a stage.

    The function is deterministic and side-effect free. It consumes only the
    supplied dataclasses and returns compatible candidates plus explicit
    rejection reasons for every incompatible backend.
    """

    policy = policy or RoutingPolicy()
    candidates: list[RouteCandidate] = []
    rejections: list[RejectedCandidate] = []

    for backend in backends:
        ok, reasons = backend_meets_requirements(backend, requirements, policy)
        if ok:
            candidates.append(
                RouteCandidate(
                    backend=backend,
                    estimated_cost_usd=estimate_stage_cost(requirements, backend),
                    reasons=reasons,
                )
            )
        else:
            rejections.append(RejectedCandidate(backend.backend_id, reasons))

    candidates.sort(key=lambda candidate: _candidate_sort_key(candidate, requirements, policy))
    rejections.sort(key=lambda rejected: rejected.backend_id)
    return RoutePlan(
        requirements=requirements,
        policy=policy,
        candidates=tuple(candidates),
        rejections=tuple(rejections),
    )


def backend_meets_requirements(
    backend: BackendCapabilities,
    requirements: StageRequirements,
    policy: RoutingPolicy | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Return whether a backend qualifies, with reason codes."""

    policy = policy or RoutingPolicy()
    rejections: list[str] = []
    backend_kind = BackendKind(backend.kind)
    backend_reasoning = ReasoningDepth(backend.reasoning_depth)
    backend_trust = TrustSensitivity(backend.max_trust_sensitivity)
    backend_latency = LatencyClass(backend.latency_class)
    billing_mode = BillingMode(backend.billing_mode)
    required_reasoning = ReasoningDepth(requirements.min_reasoning)
    required_trust = TrustSensitivity(requirements.trust_sensitivity)
    acceptable_latency = LatencyClass(requirements.acceptable_latency)

    if not backend.available:
        rejections.append("unavailable")
    if (
        requirements.allowed_backend_ids
        and backend.backend_id not in requirements.allowed_backend_ids
    ):
        rejections.append("backend_not_allowed")
    if backend.backend_id in requirements.blocked_backend_ids:
        rejections.append("backend_blocked")
    if requirements.role not in backend.roles:
        rejections.append("role_not_supported")
    if _REASONING_RANK[backend_reasoning] < _REASONING_RANK[required_reasoning]:
        rejections.append("reasoning_too_shallow")
    if _TRUST_RANK[backend_trust] < _TRUST_RANK[required_trust]:
        rejections.append("trust_too_sensitive")
    if backend.max_context_tokens < requirements.min_context_tokens:
        rejections.append("context_too_small")
    if requirements.requires_web_search and not backend.supports_web_search:
        rejections.append("web_search_required")
    if requirements.requires_deep_research and not backend.supports_deep_research:
        rejections.append("deep_research_required")
    if requirements.requires_structured_output and not backend.supports_structured_output:
        rejections.append("structured_output_required")
    if _LATENCY_RANK[backend_latency] > _LATENCY_RANK[acceptable_latency]:
        rejections.append("latency_too_slow")
    if backend_kind is BackendKind.HOST_AGENT:
        if not requirements.accepts_host_agent:
            rejections.append("host_agent_not_allowed_for_stage")
        if policy.require_official_host_runner and not backend.official_host_runner:
            rejections.append("unofficial_host_runner")
    if backend_kind is BackendKind.LOCAL and not requirements.accepts_local:
        rejections.append("local_not_allowed_for_stage")
    if backend_kind is BackendKind.GATEWAY and not requirements.accepts_gateway:
        rejections.append("gateway_not_allowed_for_stage")
    if billing_mode is BillingMode.API_CREDITS and not policy.allow_api_credit_handoff:
        rejections.append("api_credit_handoff_not_approved")

    profile_rank = _profile_rank(backend_kind, requirements, policy)
    if profile_rank is None:
        rejections.append("profile_disallows_backend")

    if rejections:
        return False, tuple(rejections)

    reasons = [
        "available",
        "role_match",
        "meets_reasoning",
        "meets_context",
        "profile_primary" if profile_rank == 0 else "profile_fallback",
    ]
    if billing_mode in (BillingMode.HOST_PLAN_USAGE, BillingMode.ZERO_API_RUNTIME):
        reasons.append(billing_mode.value)
    if requirements.requires_web_search:
        reasons.append("supports_web_search")
    if requirements.requires_deep_research:
        reasons.append("supports_deep_research")
    if requirements.requires_structured_output:
        reasons.append("supports_structured_output")
    return True, tuple(reasons)


def estimate_stage_cost(
    requirements: StageRequirements,
    backend: BackendCapabilities,
) -> float | None:
    """Estimate direct API cost for a stage, or 0 for non-API-dollar modes."""

    if backend.billing_mode in (BillingMode.HOST_PLAN_USAGE, BillingMode.ZERO_API_RUNTIME):
        return 0.0
    if backend.input_cost_per_million is None or backend.output_cost_per_million is None:
        return None
    return (requirements.expected_input_tokens / 1_000_000) * backend.input_cost_per_million + (
        requirements.expected_output_tokens / 1_000_000
    ) * backend.output_cost_per_million


def _default_billing_mode(kind: BackendKind) -> BillingMode:
    if kind is BackendKind.LOCAL:
        return BillingMode.ZERO_API_RUNTIME
    if kind is BackendKind.HOST_AGENT:
        return BillingMode.HOST_PLAN_USAGE
    if kind in (BackendKind.CLOUD_API, BackendKind.GATEWAY):
        return BillingMode.API_DOLLARS
    return BillingMode.UNKNOWN


def _profile_rank(
    kind: BackendKind,
    requirements: StageRequirements,
    policy: RoutingPolicy,
) -> int | None:
    if policy.profile is InferenceProfile.CLOUD:
        return 0 if kind in (BackendKind.CLOUD_API, BackendKind.GATEWAY) else None

    if policy.profile is InferenceProfile.AGENT:
        if kind is BackendKind.HOST_AGENT:
            return 0
        if policy.allow_profile_fallback and kind in (BackendKind.CLOUD_API, BackendKind.GATEWAY):
            return 1
        return None

    if policy.profile is InferenceProfile.HYBRID:
        required_trust = TrustSensitivity(requirements.trust_sensitivity)
        if kind in (BackendKind.CLOUD_API, BackendKind.GATEWAY):
            if required_trust is TrustSensitivity.HIGH:
                return 0
            if requirements.requires_web_search or requirements.requires_deep_research:
                return 0
            return 1
        if kind in (BackendKind.HOST_AGENT, BackendKind.LOCAL):
            return 1 if required_trust is TrustSensitivity.HIGH else 0
        return None

    if policy.profile is InferenceProfile.LOCAL:
        if kind is BackendKind.LOCAL:
            return 0
        if policy.allow_profile_fallback and kind in (BackendKind.CLOUD_API, BackendKind.GATEWAY):
            return 1
        return None

    return None


def _candidate_sort_key(
    candidate: RouteCandidate,
    requirements: StageRequirements,
    policy: RoutingPolicy,
) -> tuple[int, int, float, int, int, str]:
    backend = candidate.backend
    backend_kind = BackendKind(backend.kind)
    backend_reasoning = ReasoningDepth(backend.reasoning_depth)
    backend_latency = LatencyClass(backend.latency_class)
    required_reasoning = ReasoningDepth(requirements.min_reasoning)
    billing_mode = BillingMode(backend.billing_mode)
    profile_rank = _profile_rank(backend_kind, requirements, policy)
    if profile_rank is None:  # pragma: no cover
        profile_rank = 99
    zero_runtime_rank = 0
    if policy.prefer_zero_api_runtime:
        zero_runtime_rank = 0 if billing_mode is BillingMode.ZERO_API_RUNTIME else 1
    cost = candidate.estimated_cost_usd
    cost_rank = cost if cost is not None else float("inf")
    reasoning_surplus = _REASONING_RANK[backend_reasoning] - _REASONING_RANK[required_reasoning]
    latency_rank = _LATENCY_RANK[backend_latency]
    return (
        profile_rank,
        zero_runtime_rank,
        cost_rank,
        reasoning_surplus,
        latency_rank,
        backend.backend_id,
    )
