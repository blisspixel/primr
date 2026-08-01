"""Production stage capability inventory for backend-freedom routing.

This module is descriptive by design: it does not call providers, inspect
environment variables, or change runtime routing. It gives the backend router a
single typed source of truth for what each current production stage needs
before any stage is wired away from the legacy role router.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from primr.ai.capability_routing import (
    LatencyClass,
    ReasoningDepth,
    StageRequirements,
    TrustSensitivity,
)
from primr.ai.routing import Role


@dataclass(frozen=True)
class ProductionStage:
    """Capability declaration for one bounded production stage."""

    stage_id: str
    pipeline: str
    sequence: int
    title: str
    module: str
    entrypoint: str
    role: Role
    min_reasoning: ReasoningDepth = ReasoningDepth.LOW
    trust_sensitivity: TrustSensitivity = TrustSensitivity.MEDIUM
    min_context_tokens: int = 0
    expected_input_tokens: int = 0
    expected_output_tokens: int = 0
    requires_backend_web_search: bool = False
    requires_external_egress: bool = False
    requires_deep_research: bool = False
    requires_structured_output: bool = False
    accepts_host_agent: bool = False
    accepts_local: bool = False
    accepts_gateway: bool = True
    acceptable_latency: LatencyClass = LatencyClass.STANDARD
    optional: bool = False
    budget_checkpoint: bool = False
    current_backend: str = ""
    promotion_gate: str = ""
    notes: str = ""
    artifacts: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.stage_id.strip():
            raise ValueError("stage_id is required")
        if not self.pipeline.strip():
            raise ValueError("pipeline is required")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        for field_name in (
            "title",
            "module",
            "entrypoint",
            "current_backend",
            "promotion_gate",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")
        for field_name in (
            "min_context_tokens",
            "expected_input_tokens",
            "expected_output_tokens",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        object.__setattr__(self, "role", Role(self.role))
        object.__setattr__(self, "min_reasoning", ReasoningDepth(self.min_reasoning))
        object.__setattr__(
            self,
            "trust_sensitivity",
            TrustSensitivity(self.trust_sensitivity),
        )
        object.__setattr__(self, "acceptable_latency", LatencyClass(self.acceptable_latency))
        object.__setattr__(self, "artifacts", tuple(str(item) for item in self.artifacts))

    def to_requirements(self) -> StageRequirements:
        """Return the router-facing requirement row for this stage."""

        return StageRequirements(
            stage_id=self.stage_id,
            role=self.role,
            min_reasoning=self.min_reasoning,
            trust_sensitivity=self.trust_sensitivity,
            min_context_tokens=self.min_context_tokens,
            expected_input_tokens=self.expected_input_tokens,
            expected_output_tokens=self.expected_output_tokens,
            requires_web_search=self.requires_backend_web_search,
            requires_deep_research=self.requires_deep_research,
            requires_structured_output=self.requires_structured_output,
            accepts_host_agent=self.accepts_host_agent,
            accepts_local=self.accepts_local,
            accepts_gateway=self.accepts_gateway,
            acceptable_latency=self.acceptable_latency,
        )

    @property
    def accepted_backend_families(self) -> tuple[str, ...]:
        """Human-readable backend family allowlist for docs and inspections."""

        families = ["cloud_api"]
        if self.accepts_gateway:
            families.append("gateway")
        if self.accepts_host_agent:
            families.append("host_agent")
        if self.accepts_local:
            families.append("local")
        return tuple(families)


PRODUCTION_STAGES: Final[tuple[ProductionStage, ...]] = (
    ProductionStage(
        stage_id="fast.scrape_summary",
        pipeline="fast",
        sequence=10,
        title="Website scrape summarization",
        module="primr.core.fast_run_collection",
        entrypoint="collect_research_data",
        role=Role.UTILITY,
        min_reasoning=ReasoningDepth.LOW,
        trust_sensitivity=TrustSensitivity.MEDIUM,
        min_context_tokens=80_000,
        expected_input_tokens=70_000,
        expected_output_tokens=5_000,
        requires_external_egress=True,
        accepts_host_agent=True,
        accepts_local=True,
        current_backend="routed through ai.stage_routing with legacy scraping fallback",
        promotion_gate=(
            "Can route to local or host only after summary fidelity and source "
            "retention match the cloud baseline on the standing eval corpus."
        ),
        notes="Scraping/search egress stays in Primr; only the summarization call is routable.",
        artifacts=("insights.txt", "scraped_content.txt"),
    ),
    ProductionStage(
        stage_id="fast.source_relevance",
        pipeline="fast",
        sequence=20,
        title="External source relevance filtering",
        module="primr.core.fast_run_collection",
        entrypoint="_assess_source_relevance",
        role=Role.UTILITY,
        min_reasoning=ReasoningDepth.LOW,
        trust_sensitivity=TrustSensitivity.MEDIUM,
        min_context_tokens=32_000,
        expected_input_tokens=18_000,
        expected_output_tokens=2_000,
        requires_structured_output=True,
        requires_external_egress=True,
        accepts_host_agent=True,
        accepts_local=True,
        current_backend="routed through ai.stage_routing with legacy fast fallback",
        promotion_gate=(
            "Can route after accepted/rejected source decisions agree with the "
            "cloud baseline on the standing corpus "
            "(source_relevance_standing_v1 representative tags), live host "
            "route observations with billing provenance, and human review. "
            "Offline scorecards alone are not sufficient."
        ),
        notes=(
            "Bounded hybrid/local pilot. Offline standing corpus and backend "
            "comparison artifacts are scorecard input only "
            "(promotion_status=not_promoted)."
        ),
    ),
    ProductionStage(
        stage_id="fast.hiring_signals",
        pipeline="fast",
        sequence=30,
        title="Hiring signal triage and extraction",
        module="primr.core.fast_run_hiring",
        entrypoint="collect_hiring_block",
        role=Role.UTILITY,
        min_reasoning=ReasoningDepth.MEDIUM,
        trust_sensitivity=TrustSensitivity.MEDIUM,
        min_context_tokens=64_000,
        expected_input_tokens=45_000,
        expected_output_tokens=4_000,
        requires_structured_output=True,
        requires_external_egress=True,
        accepts_host_agent=True,
        accepts_local=True,
        current_backend="routed through ai.stage_routing with legacy fast fallback",
        promotion_gate=(
            "Can route after structured extraction preserves role, stack, and "
            "initiative signals against curated hiring fixtures."
        ),
        artifacts=("_hiring/",),
    ),
    ProductionStage(
        stage_id="fast.research_deepening",
        pipeline="fast",
        sequence=40,
        title="Research gap analysis and deepening",
        module="primr.core.fast_run_gaps",
        entrypoint="deepen_research",
        role=Role.REASONING,
        min_reasoning=ReasoningDepth.HIGH,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=160_000,
        expected_input_tokens=95_000,
        expected_output_tokens=5_000,
        requires_external_egress=True,
        budget_checkpoint=True,
        current_backend="routed through ai.stage_routing with reasoning failover",
        promotion_gate=(
            "Requires agreement-validated gap quality and no loss of diagnostic "
            "queries before any non-cloud backend can be promoted. Offline route "
            "records and fail-closed agent/local fallbacks are not promotion."
        ),
        notes=(
            "Cloud remains the validated baseline. Agent/local profiles without a "
            "qualifying adapter skip gap analysis and record a body-free route "
            "fallback rather than invoking cloud LLMs."
        ),
        artifacts=("gap_analysis.md",),
    ),
    ProductionStage(
        stage_id="fast.analysis_workbook",
        pipeline="fast",
        sequence=50,
        title="Analysis workbook generation",
        module="primr.core.fast_run_workbook",
        entrypoint="generate_analysis_workbook",
        role=Role.REASONING,
        min_reasoning=ReasoningDepth.HIGH,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=220_000,
        expected_input_tokens=180_000,
        expected_output_tokens=18_000,
        current_backend="routed through ai.stage_routing with reasoning failover",
        promotion_gate=(
            "Requires workbook quality within band of the calibrated cloud "
            "baseline because downstream sections inherit this reasoning. "
            "Route records alone are not promotion."
        ),
        notes=(
            "Cloud remains the validated baseline. Agent/local profiles without "
            "a qualifying adapter fall back to collected insights and record a "
            "body-free route fallback."
        ),
        artifacts=("analysis_workbook.md", "hypothesis_tree.md"),
    ),
    ProductionStage(
        stage_id="fast.report_sections",
        pipeline="fast",
        sequence=60,
        title="Report section writing and coherence pass",
        module="primr.core.fast_run_sections",
        entrypoint="write_report_sections",
        role=Role.WRITING,
        min_reasoning=ReasoningDepth.MEDIUM,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=180_000,
        expected_input_tokens=140_000,
        expected_output_tokens=32_000,
        current_backend="routed through ai.stage_routing with writing failover",
        promotion_gate=(
            "Requires report trust, section completeness, citation health, and "
            "utility scores within the accepted band on the standing corpus. "
            "Route records alone are not promotion."
        ),
        notes=(
            "Cloud remains the validated baseline. Agent/local profiles without "
            "a qualifying writing adapter fail closed with no report content."
        ),
        artifacts=("report.md",),
    ),
    ProductionStage(
        stage_id="fast.cross_validation",
        pipeline="fast",
        sequence=70,
        title="Cross-validation and evidence enrichment",
        module="primr.core.fast_run_validation",
        entrypoint="cross_validate_and_enrich",
        role=Role.REASONING,
        min_reasoning=ReasoningDepth.HIGH,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=180_000,
        expected_input_tokens=120_000,
        expected_output_tokens=10_000,
        requires_structured_output=True,
        requires_external_egress=True,
        budget_checkpoint=True,
        current_backend="Grok reasoning plus writing failover helpers",
        promotion_gate=(
            "Requires contradiction detection and weak-section enrichment to "
            "match the agreement-validated calibration baseline."
        ),
    ),
    ProductionStage(
        stage_id="fast.trust_polish",
        pipeline="fast",
        sequence=80,
        title="Trust polish, cleanup, and citation repair",
        module="primr.core.fast_run_trust",
        entrypoint="polish_and_gate_fast_report",
        role=Role.WRITING,
        min_reasoning=ReasoningDepth.MEDIUM,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=96_000,
        expected_input_tokens=65_000,
        expected_output_tokens=8_000,
        current_backend="grok_writing via trust polish and citation repair helpers",
        promotion_gate=(
            "Requires zero increase in scaffolding leaks, citation breakage, or "
            "confidence-label overstatement."
        ),
        artifacts=("_shipping_repair.json",),
    ),
    ProductionStage(
        stage_id="fast.label_honesty",
        pipeline="fast",
        sequence=90,
        title="Optional label-honesty audit",
        module="primr.core.fast_run_trust",
        entrypoint="_maybe_apply_label_honesty",
        role=Role.UTILITY,
        min_reasoning=ReasoningDepth.MEDIUM,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=32_000,
        expected_input_tokens=12_000,
        expected_output_tokens=2_000,
        requires_structured_output=True,
        requires_external_egress=True,
        optional=True,
        current_backend="calibration judge path, gated by PRIMR_LABEL_HONESTY",
        promotion_gate=(
            "Must stay report-only until the representative calibration baseline "
            "proves acceptable false positive and false negative behavior."
        ),
        artifacts=("_label_honesty.json",),
    ),
    ProductionStage(
        stage_id="fast.strategy_generation",
        pipeline="fast",
        sequence=100,
        title="Optional strategy document generation",
        module="primr.core.fast_run_strategy",
        entrypoint="run_strategy_phase",
        role=Role.WRITING,
        min_reasoning=ReasoningDepth.MEDIUM,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=220_000,
        expected_input_tokens=160_000,
        expected_output_tokens=32_000,
        requires_external_egress=True,
        optional=True,
        budget_checkpoint=True,
        current_backend="Grok writing with optional vendor Deep Research context",
        promotion_gate=(
            "Requires per-strategy QA, source health, and business utility within "
            "band before a non-cloud backend can generate strategy artifacts."
        ),
        artifacts=("AI_Strategy.md", "strategy modules"),
    ),
    ProductionStage(
        stage_id="premium.deep_research",
        pipeline="premium",
        sequence=10,
        title="Premium autonomous deep research",
        module="primr.core.research_orchestrator",
        entrypoint="_run_deep_research_with_context",
        role=Role.REASONING,
        min_reasoning=ReasoningDepth.PREMIUM,
        trust_sensitivity=TrustSensitivity.HIGH,
        min_context_tokens=1_000_000,
        expected_input_tokens=500_000,
        expected_output_tokens=40_000,
        requires_deep_research=True,
        acceptable_latency=LatencyClass.LONG_RUNNING,
        current_backend="Gemini Deep Research Agent",
        promotion_gate=(
            "Cannot route to local or generic host runners until they expose an "
            "official deep-research capability with comparable citations and provenance."
        ),
    ),
)


def production_stages(*, pipeline: str | None = None) -> tuple[ProductionStage, ...]:
    """Return production stage declarations, optionally filtered by pipeline."""

    if pipeline is None:
        return PRODUCTION_STAGES
    normalized = pipeline.strip().lower()
    return tuple(stage for stage in PRODUCTION_STAGES if stage.pipeline == normalized)


def get_production_stage(stage_id: str) -> ProductionStage:
    """Return one production stage declaration by id."""

    normalized = stage_id.strip()
    for stage in PRODUCTION_STAGES:
        if stage.stage_id == normalized:
            return stage
    raise KeyError(f"Unknown production stage: {stage_id}")


def stage_requirements(*, pipeline: str | None = None) -> tuple[StageRequirements, ...]:
    """Return router-facing requirement rows for declared production stages."""

    return tuple(stage.to_requirements() for stage in production_stages(pipeline=pipeline))


def utility_routing_candidate_stages() -> tuple[ProductionStage, ...]:
    """Return low-risk stages that can be evaluated first for local or host routing."""

    return tuple(
        stage
        for stage in PRODUCTION_STAGES
        if stage.role is Role.UTILITY
        and stage.trust_sensitivity is not TrustSensitivity.HIGH
        and (stage.accepts_local or stage.accepts_host_agent)
    )
