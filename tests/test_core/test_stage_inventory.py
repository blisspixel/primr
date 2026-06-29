from __future__ import annotations

import pytest

from primr.ai.capability_routing import (
    BackendCapabilities,
    BackendKind,
    BillingMode,
    LatencyClass,
    ReasoningDepth,
    RoutingPolicy,
    TrustSensitivity,
    route_stage,
)
from primr.ai.routing import Role
from primr.core.stage_inventory import (
    PRODUCTION_STAGES,
    ProductionStage,
    get_production_stage,
    production_stages,
    stage_requirements,
    utility_routing_candidate_stages,
)


def _capable_backends() -> tuple[BackendCapabilities, ...]:
    return (
        BackendCapabilities(
            backend_id="cloud-utility",
            kind=BackendKind.CLOUD_API,
            roles=(Role.UTILITY,),
            reasoning_depth=ReasoningDepth.MEDIUM,
            max_trust_sensitivity=TrustSensitivity.HIGH,
            max_context_tokens=256_000,
            supports_structured_output=True,
            input_cost_per_million=0.25,
            output_cost_per_million=1.0,
        ),
        BackendCapabilities(
            backend_id="cloud-writing",
            kind=BackendKind.CLOUD_API,
            roles=(Role.WRITING,),
            reasoning_depth=ReasoningDepth.HIGH,
            max_trust_sensitivity=TrustSensitivity.HIGH,
            max_context_tokens=256_000,
            supports_structured_output=True,
            input_cost_per_million=0.5,
            output_cost_per_million=2.0,
        ),
        BackendCapabilities(
            backend_id="cloud-reasoning",
            kind=BackendKind.CLOUD_API,
            roles=(Role.REASONING,),
            reasoning_depth=ReasoningDepth.HIGH,
            max_trust_sensitivity=TrustSensitivity.HIGH,
            max_context_tokens=256_000,
            supports_structured_output=True,
            input_cost_per_million=3.0,
            output_cost_per_million=15.0,
        ),
        BackendCapabilities(
            backend_id="cloud-deep-research",
            kind=BackendKind.CLOUD_API,
            roles=(Role.REASONING,),
            reasoning_depth=ReasoningDepth.PREMIUM,
            max_trust_sensitivity=TrustSensitivity.HIGH,
            max_context_tokens=2_000_000,
            supports_structured_output=True,
            supports_deep_research=True,
            latency_class=LatencyClass.LONG_RUNNING,
            input_cost_per_million=3.0,
            output_cost_per_million=15.0,
        ),
    )


def test_production_stage_ids_are_unique_and_stably_ordered() -> None:
    stage_ids = [stage.stage_id for stage in PRODUCTION_STAGES]

    assert len(stage_ids) == len(set(stage_ids))
    assert stage_ids == [
        "fast.scrape_summary",
        "fast.source_relevance",
        "fast.hiring_signals",
        "fast.research_deepening",
        "fast.analysis_workbook",
        "fast.report_sections",
        "fast.cross_validation",
        "fast.trust_polish",
        "fast.label_honesty",
        "fast.strategy_generation",
        "premium.deep_research",
    ]


def test_production_stages_filter_by_pipeline() -> None:
    fast_stages = production_stages(pipeline="fast")
    premium_stages = production_stages(pipeline="premium")

    assert len(fast_stages) == 10
    assert [stage.pipeline for stage in fast_stages] == ["fast"] * 10
    assert [stage.stage_id for stage in premium_stages] == ["premium.deep_research"]


def test_get_production_stage_returns_exact_stage() -> None:
    stage = get_production_stage("fast.cross_validation")

    assert stage.title == "Cross-validation and evidence enrichment"
    assert stage.budget_checkpoint is True
    assert stage.requires_structured_output is True


def test_get_production_stage_rejects_unknown_stage() -> None:
    with pytest.raises(KeyError, match="Unknown production stage"):
        get_production_stage("missing.stage")


def test_every_declared_stage_is_router_ready() -> None:
    backends = _capable_backends()

    for requirements in stage_requirements():
        plan = route_stage(requirements, backends, RoutingPolicy())
        assert plan.primary is not None, requirements.stage_id
        assert plan.primary.estimated_cost_usd is not None, requirements.stage_id


def test_utility_candidate_stages_are_low_risk_local_or_host_pilots() -> None:
    candidate_ids = [stage.stage_id for stage in utility_routing_candidate_stages()]

    assert candidate_ids == [
        "fast.scrape_summary",
        "fast.source_relevance",
        "fast.hiring_signals",
    ]


def test_premium_deep_research_requires_deep_research_capability() -> None:
    stage = get_production_stage("premium.deep_research")
    requirements = stage.to_requirements()
    weak_reasoning = BackendCapabilities(
        backend_id="reasoning-only",
        kind=BackendKind.CLOUD_API,
        roles=(Role.REASONING,),
        reasoning_depth=ReasoningDepth.PREMIUM,
        max_trust_sensitivity=TrustSensitivity.HIGH,
        max_context_tokens=2_000_000,
        latency_class=LatencyClass.LONG_RUNNING,
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
    )
    deep_research = BackendCapabilities(
        backend_id="deep-research",
        kind=BackendKind.CLOUD_API,
        roles=(Role.REASONING,),
        reasoning_depth=ReasoningDepth.PREMIUM,
        max_trust_sensitivity=TrustSensitivity.HIGH,
        max_context_tokens=2_000_000,
        supports_deep_research=True,
        latency_class=LatencyClass.LONG_RUNNING,
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
    )

    plan = route_stage(requirements, (weak_reasoning, deep_research), RoutingPolicy())

    assert plan.primary is not None
    assert plan.primary.backend.backend_id == "deep-research"
    assert plan.rejections[0].backend_id == "reasoning-only"
    assert "deep_research_required" in plan.rejections[0].reasons


def test_stage_validation_rejects_empty_required_text() -> None:
    with pytest.raises(ValueError, match="title is required"):
        ProductionStage(
            stage_id="bad.stage",
            pipeline="fast",
            sequence=1,
            title="",
            module="primr.core.bad",
            entrypoint="run",
            role=Role.UTILITY,
            current_backend="legacy",
            promotion_gate="eval",
        )


def test_stage_requirements_preserve_backend_family_policy() -> None:
    local_candidate = get_production_stage("fast.source_relevance").to_requirements()
    cloud_only = get_production_stage("fast.analysis_workbook").to_requirements()
    local = BackendCapabilities(
        backend_id="local",
        kind=BackendKind.LOCAL,
        roles=(Role.UTILITY, Role.REASONING),
        reasoning_depth=ReasoningDepth.HIGH,
        max_trust_sensitivity=TrustSensitivity.HIGH,
        max_context_tokens=256_000,
        supports_structured_output=True,
        billing_mode=BillingMode.ZERO_API_RUNTIME,
    )

    local_plan = route_stage(
        local_candidate,
        (local,),
        RoutingPolicy(profile="local"),
    )
    blocked_plan = route_stage(
        cloud_only,
        (local,),
        RoutingPolicy(profile="local"),
    )

    assert local_plan.primary is not None
    assert blocked_plan.primary is None
    assert "local_not_allowed_for_stage" in blocked_plan.rejections[0].reasons
