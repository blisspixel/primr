from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from primr.ai.capability_routing import (
    BackendCapabilities,
    BackendKind,
    BillingMode,
    InferenceProfile,
    ReasoningDepth,
    RoutingPolicy,
    StageRequirements,
    TrustSensitivity,
    backend_meets_requirements,
    backend_with_availability,
    backends_with_availability,
    route_stage,
)
from primr.ai.provider_availability import ProviderQuotaSnapshot, QuotaWindow
from primr.ai.provider_availability_collectors import LOCAL_OPENAI_COMPATIBLE_PROVIDER
from primr.ai.routing import Role
from primr.config.models import ModelRegistry

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def _cloud(
    backend_id: str,
    *,
    roles: tuple[Role, ...] = (Role.UTILITY,),
    input_cost: float = 1.0,
    output_cost: float = 2.0,
    reasoning: ReasoningDepth = ReasoningDepth.MEDIUM,
    trust: TrustSensitivity = TrustSensitivity.HIGH,
    context: int = 128_000,
    supports_web_search: bool = False,
    supports_deep_research: bool = False,
) -> BackendCapabilities:
    return BackendCapabilities(
        backend_id=backend_id,
        kind=BackendKind.CLOUD_API,
        roles=roles,
        reasoning_depth=reasoning,
        max_trust_sensitivity=trust,
        max_context_tokens=context,
        supports_web_search=supports_web_search,
        supports_deep_research=supports_deep_research,
        input_cost_per_million=input_cost,
        output_cost_per_million=output_cost,
    )


def _local(
    backend_id: str = "local-qwen",
    *,
    trust: TrustSensitivity = TrustSensitivity.MEDIUM,
    reasoning: ReasoningDepth = ReasoningDepth.MEDIUM,
) -> BackendCapabilities:
    return BackendCapabilities(
        backend_id=backend_id,
        kind=BackendKind.LOCAL,
        roles=(Role.UTILITY, Role.WRITING),
        reasoning_depth=reasoning,
        max_trust_sensitivity=trust,
        max_context_tokens=64_000,
    )


def _host(
    backend_id: str = "codex",
    *,
    official: bool = True,
    billing_mode: BillingMode = BillingMode.HOST_PLAN_USAGE,
) -> BackendCapabilities:
    return BackendCapabilities(
        backend_id=backend_id,
        kind=BackendKind.HOST_AGENT,
        roles=(Role.UTILITY, Role.WRITING),
        reasoning_depth=ReasoningDepth.MEDIUM,
        max_trust_sensitivity=TrustSensitivity.MEDIUM,
        max_context_tokens=200_000,
        official_host_runner=official,
        billing_mode=billing_mode,
    )


def test_cloud_profile_ranks_cheapest_capable_backend() -> None:
    requirements = StageRequirements(
        stage_id="write-summary",
        role=Role.WRITING,
        min_reasoning=ReasoningDepth.MEDIUM,
        min_context_tokens=16_000,
        expected_input_tokens=100_000,
        expected_output_tokens=20_000,
    )
    expensive = _cloud("expensive", roles=(Role.WRITING,), input_cost=5.0, output_cost=20.0)
    cheap = _cloud("cheap", roles=(Role.WRITING,), input_cost=0.25, output_cost=1.5)

    plan = route_stage(requirements, (expensive, cheap), RoutingPolicy())

    assert plan.is_routable is True
    assert plan.primary is not None
    assert plan.primary.backend.backend_id == "cheap"
    assert plan.primary.estimated_cost_usd == pytest.approx(0.055)
    assert plan.rejections == ()


def test_rejections_explain_every_failed_requirement() -> None:
    requirements = StageRequirements(
        stage_id="search",
        role=Role.REASONING,
        min_reasoning=ReasoningDepth.HIGH,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=200_000,
        requires_web_search=True,
        requires_structured_output=True,
    )
    backend = BackendCapabilities(
        backend_id="weak-local",
        kind=BackendKind.LOCAL,
        roles=(Role.UTILITY,),
        reasoning_depth=ReasoningDepth.LOW,
        max_trust_sensitivity=TrustSensitivity.LOW,
        max_context_tokens=8_000,
        supports_structured_output=False,
    )

    ok, reasons = backend_meets_requirements(backend, requirements, RoutingPolicy())

    assert ok is False
    assert reasons == (
        "role_not_supported",
        "reasoning_too_shallow",
        "trust_too_sensitive",
        "context_too_small",
        "web_search_required",
        "structured_output_required",
        "local_not_allowed_for_stage",
        "profile_disallows_backend",
    )


def test_host_agent_requires_stage_opt_in_and_official_runner() -> None:
    strict_stage = StageRequirements(stage_id="link-choice", role=Role.UTILITY)
    unofficial_stage = StageRequirements(
        stage_id="link-choice",
        role=Role.UTILITY,
        accepts_host_agent=True,
    )
    policy = RoutingPolicy(profile=InferenceProfile.AGENT)

    blocked_plan = route_stage(strict_stage, (_host(),), policy)
    unofficial_plan = route_stage(unofficial_stage, (_host(official=False),), policy)
    allowed_plan = route_stage(unofficial_stage, (_host(),), policy)

    assert blocked_plan.primary is None
    assert blocked_plan.rejections[0].reasons == ("host_agent_not_allowed_for_stage",)
    assert unofficial_plan.primary is None
    assert unofficial_plan.rejections[0].reasons == ("unofficial_host_runner",)
    assert allowed_plan.primary is not None
    assert allowed_plan.primary.backend.backend_id == "codex"
    assert "host_plan_usage" in allowed_plan.primary.reasons


def test_api_credit_handoff_requires_explicit_policy_approval() -> None:
    requirements = StageRequirements(
        stage_id="agent-write",
        role=Role.WRITING,
        accepts_host_agent=True,
    )
    backend = _host(billing_mode=BillingMode.API_CREDITS)

    denied = route_stage(
        requirements,
        (backend,),
        RoutingPolicy(profile=InferenceProfile.AGENT),
    )
    allowed = route_stage(
        requirements,
        (backend,),
        RoutingPolicy(
            profile=InferenceProfile.AGENT,
            allow_api_credit_handoff=True,
        ),
    )

    assert denied.primary is None
    assert denied.rejections[0].reasons == ("api_credit_handoff_not_approved",)
    assert allowed.primary is not None


def test_hybrid_prefers_zero_runtime_for_low_trust_but_cloud_for_high_trust() -> None:
    low_trust = StageRequirements(
        stage_id="summarize-page",
        role=Role.UTILITY,
        trust_sensitivity=TrustSensitivity.LOW,
        accepts_local=True,
    )
    high_trust = StageRequirements(
        stage_id="label-honesty",
        role=Role.UTILITY,
        trust_sensitivity=TrustSensitivity.HIGH,
        accepts_local=True,
    )
    local = _local(trust=TrustSensitivity.HIGH)
    cloud = _cloud("grok", roles=(Role.UTILITY,), input_cost=1.25, output_cost=2.5)
    policy = RoutingPolicy(profile=InferenceProfile.HYBRID)

    low_plan = route_stage(low_trust, (cloud, local), policy)
    high_plan = route_stage(high_trust, (cloud, local), policy)

    assert low_plan.primary is not None
    assert low_plan.primary.backend.kind is BackendKind.LOCAL
    assert high_plan.primary is not None
    assert high_plan.primary.backend.kind is BackendKind.CLOUD_API


def test_local_profile_does_not_silently_fallback_to_cloud() -> None:
    requirements = StageRequirements(
        stage_id="summary",
        role=Role.UTILITY,
        accepts_local=True,
    )
    backend = _cloud("gemini", roles=(Role.UTILITY,))

    strict_plan = route_stage(
        requirements,
        (backend,),
        RoutingPolicy(profile=InferenceProfile.LOCAL),
    )
    fallback_plan = route_stage(
        requirements,
        (backend,),
        RoutingPolicy(profile=InferenceProfile.LOCAL, allow_profile_fallback=True),
    )

    assert strict_plan.primary is None
    assert strict_plan.rejections[0].reasons == ("profile_disallows_backend",)
    assert fallback_plan.primary is not None
    assert fallback_plan.primary.reasons[-1] == "profile_fallback"


def test_deep_research_routes_only_to_capable_cloud_backend() -> None:
    requirements = StageRequirements(
        stage_id="premium-research",
        role=Role.REASONING,
        min_reasoning=ReasoningDepth.PREMIUM,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=500_000,
        requires_deep_research=True,
        acceptable_latency="long_running",
        accepts_host_agent=True,
        accepts_local=True,
    )
    host = _host()
    local = _local(trust=TrustSensitivity.HIGH, reasoning=ReasoningDepth.HIGH)
    deep = _cloud(
        "gemini-deep-research",
        roles=(Role.REASONING,),
        reasoning=ReasoningDepth.PREMIUM,
        context=1_000_000,
        supports_deep_research=True,
    )

    plan = route_stage(requirements, (host, local, deep), RoutingPolicy())

    assert plan.primary is not None
    assert plan.primary.backend.backend_id == "gemini-deep-research"
    rejected = {item.backend_id: item.reasons for item in plan.rejections}
    assert "deep_research_required" in rejected["codex"]
    assert "deep_research_required" in rejected["local-qwen"]


def test_from_model_config_maps_registry_metadata_without_probing() -> None:
    ollama = BackendCapabilities.from_model_config(
        ModelRegistry.OLLAMA_QWEN3_7B,
        roles=(Role.UTILITY,),
    )
    deprecated = BackendCapabilities.from_model_config(
        ModelRegistry.GEMINI_3_PRO,
        roles=("reasoning",),
    )

    assert ollama.kind is BackendKind.LOCAL
    assert ollama.billing_mode is BillingMode.ZERO_API_RUNTIME
    assert ollama.metadata["provider"] == "ollama"
    assert deprecated.available is False


def test_provider_availability_marks_missing_cloud_key_unavailable() -> None:
    backend = replace(
        _cloud("openai-writer", roles=(Role.WRITING,)), metadata={"provider": "openai"}
    )
    snapshot = ProviderQuotaSnapshot(
        provider="openai",
        ok=False,
        error="missing_api_key",
        metadata={
            "configured": False,
            "credential_source": None,
            "quota_source": "not_collected",
        },
    )

    annotated = backend_with_availability(backend, (snapshot,))
    requirements = StageRequirements(stage_id="writer", role=Role.WRITING)
    plan = route_stage(requirements, (annotated,), RoutingPolicy())

    assert annotated.available is False
    assert annotated.metadata["availability"] == {
        "available": False,
        "provider": "openai",
        "quota_source": "not_collected",
        "stale": False,
        "error": "missing_api_key",
        "configured": False,
        "credential_source": None,
    }
    assert plan.primary is None
    assert plan.rejections[0].reasons == ("unavailable",)


def test_provider_availability_matches_gemini_snapshot_to_google_model() -> None:
    backend = replace(_cloud("gemini-flash"), metadata={"provider": "google"})
    snapshot = ProviderQuotaSnapshot(
        provider="gemini",
        metadata={
            "configured": True,
            "credential_source": "env",
            "quota_source": "not_collected",
        },
    )

    annotated = backend_with_availability(backend, (snapshot,))

    assert annotated.available is True
    assert annotated.metadata["availability"]["provider"] == "gemini"
    assert annotated.metadata["availability"]["configured"] is True


def test_provider_availability_applies_generic_local_snapshot_to_local_backend() -> None:
    local = _local()
    snapshot = ProviderQuotaSnapshot(
        provider=LOCAL_OPENAI_COMPATIBLE_PROVIDER,
        windows=(QuotaWindow("local_service", used_percent=0),),
        metadata={
            "chat_model_available": True,
            "endpoint_source": "LOCAL_LLM_BASE_URL",
            "model_count": 2,
            "quota_source": "local_probe",
            "zero_incremental_api_cost": True,
        },
    )

    annotated = backend_with_availability(local, (snapshot,), require_snapshot=True)
    requirements = StageRequirements(
        stage_id="summarize",
        role=Role.UTILITY,
        accepts_local=True,
    )
    plan = route_stage(
        requirements,
        (annotated,),
        RoutingPolicy(profile=InferenceProfile.LOCAL),
    )

    assert annotated.available is True
    assert annotated.metadata["availability"]["provider"] == LOCAL_OPENAI_COMPATIBLE_PROVIDER
    assert annotated.metadata["availability"]["headroom_percent"] == pytest.approx(100.0)
    assert annotated.metadata["availability"]["model_count"] == 2
    assert plan.primary is not None
    assert plan.primary.backend.backend_id == "local-qwen"


def test_provider_availability_honors_injected_reset_time() -> None:
    backend = replace(
        _cloud("anthropic", roles=(Role.WRITING,)),
        metadata={"provider": "anthropic"},
    )
    snapshot = ProviderQuotaSnapshot(
        provider="anthropic",
        windows=(QuotaWindow("daily", used_percent=100, resets_at=NOW - timedelta(seconds=1)),),
    )

    annotated = backend_with_availability(backend, (snapshot,), now=NOW)

    assert annotated.available is True
    assert annotated.metadata["availability"]["headroom_percent"] == pytest.approx(100.0)


def test_provider_availability_sanitizes_error_metadata() -> None:
    backend = replace(
        _cloud("xai-reasoning", roles=(Role.REASONING,)), metadata={"provider": "xai"}
    )
    snapshot = ProviderQuotaSnapshot(
        provider="xai",
        ok=False,
        error="cannot reach http://operator-host.example.invalid:9999/quota",
        metadata={
            "quota_source": "http://operator-host.example.invalid:9999/quota",
            "raw_endpoint": "http://operator-host.example.invalid:9999/quota",
        },
    )

    annotated = backend_with_availability(backend, (snapshot,))

    assert annotated.available is False
    assert annotated.metadata["availability"]["error"] == "availability_error"
    assert annotated.metadata["availability"]["quota_source"] == "availability_error"
    assert "raw_endpoint" not in annotated.metadata["availability"]
    assert "operator-host" not in str(annotated.metadata)


def test_provider_availability_sanitizes_binding_window_label() -> None:
    # A quota collector controls QuotaWindow.label; a raw label could carry a
    # URL or account detail, so it must be sanitized before it becomes the
    # routing metadata's binding_window_label.
    backend = replace(
        _cloud("xai-reasoning", roles=(Role.REASONING,)), metadata={"provider": "xai"}
    )
    snapshot = ProviderQuotaSnapshot(
        provider="xai",
        windows=(
            QuotaWindow("quota at http://operator-host.example.invalid:9999/v1", used_percent=80),
        ),
    )

    annotated = backend_with_availability(backend, (snapshot,))

    assert annotated.metadata["availability"]["binding_window_label"] == "availability_error"
    assert "operator-host" not in str(annotated.metadata)


def test_provider_availability_sanitizes_allowlisted_snapshot_metadata() -> None:
    unsafe_provider = "operator-host.example.invalid"
    backend = replace(
        _cloud("unsafe-provider", roles=(Role.REASONING,)),
        metadata={"provider": unsafe_provider},
    )
    snapshot = ProviderQuotaSnapshot(
        provider=unsafe_provider,
        metadata={
            "chat_model_available": "yes",
            "configured": "yes",
            "credential_source": "secret://operator-host.example.invalid/key",
            "endpoint_source": "http://operator-host.example.invalid:9999/v1",
            "model_count": "not-a-number",
            "quota_source": "operator-host.example.invalid",
            "zero_incremental_api_cost": "yes",
        },
    )

    annotated = backend_with_availability(backend, (snapshot,))
    availability = annotated.metadata["availability"]

    assert availability["provider"] == "availability_error"
    assert availability["credential_source"] == "availability_error"
    assert availability["endpoint_source"] == "availability_error"
    assert availability["model_count"] == 0
    assert availability["chat_model_available"] is True
    assert availability["configured"] is True
    assert availability["zero_incremental_api_cost"] is True
    assert "operator-host" not in str(availability)


def test_require_snapshot_can_make_missing_availability_explicit() -> None:
    openai = replace(_cloud("openai", roles=(Role.UTILITY,)), metadata={"provider": "openai"})
    gemini = replace(_cloud("gemini", roles=(Role.UTILITY,)), metadata={"provider": "gemini"})
    snapshots = (ProviderQuotaSnapshot(provider="openai", windows=(QuotaWindow("daily", 10),)),)

    annotated = backends_with_availability(
        (openai, gemini),
        snapshots,
        require_snapshot=True,
    )
    by_id = {backend.backend_id: backend for backend in annotated}

    assert by_id["openai"].available is True
    assert by_id["gemini"].available is False
    assert by_id["gemini"].metadata["availability"]["error"] == "missing_availability_snapshot"


def test_stage_requirements_validate_and_coerce_values() -> None:
    requirements = StageRequirements(
        stage_id=" utility ",
        role="utility",
        min_reasoning="medium",
        trust_sensitivity="low",
        acceptable_latency="interactive",
        allowed_backend_ids=("a", " ", "b"),
        blocked_backend_ids=("c",),
    )

    assert requirements.role is Role.UTILITY
    assert requirements.min_reasoning is ReasoningDepth.MEDIUM
    assert requirements.allowed_backend_ids == frozenset({"a", "b"})
    assert requirements.blocked_backend_ids == frozenset({"c"})
    with pytest.raises(ValueError, match="stage_id"):
        StageRequirements(stage_id=" ", role=Role.UTILITY)
    with pytest.raises(ValueError, match="expected_input_tokens"):
        StageRequirements(stage_id="x", role=Role.UTILITY, expected_input_tokens=-1)
