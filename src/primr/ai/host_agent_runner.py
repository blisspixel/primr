"""Typed seam for official host-agent execution.

This module is deliberately transport-free. It defines the packet Primr can hand
to an official account-backed runner, such as Codex or Claude Code, without
giving that runner control of the research pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from primr.utils.content_sanitizer import fence_untrusted


class HostAgentUnavailableError(RuntimeError):
    """Raised when a requested host-agent runner is not available."""


class HostAgentKind(str, Enum):
    """Official host-agent families Primr may route bounded stages through."""

    CODEX = "codex"
    CLAUDE_CODE = "claude_code"


class HostAgentBillingMode(str, Enum):
    """How a host-agent stage should be represented in cost reporting."""

    HOST_PLAN_USAGE = "host_plan_usage"
    API_CREDITS = "api_credits"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HostAgentPolicy:
    """Budget and billing policy for a single host-agent stage."""

    billing_mode: HostAgentBillingMode = HostAgentBillingMode.HOST_PLAN_USAGE
    max_wall_seconds: int = 600
    max_output_chars: int = 100_000
    allow_api_credit_handoff: bool = False

    def __post_init__(self) -> None:
        billing_mode = HostAgentBillingMode(self.billing_mode)
        object.__setattr__(self, "billing_mode", billing_mode)
        if self.max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be positive")
        if self.max_output_chars <= 0:
            raise ValueError("max_output_chars must be positive")
        if billing_mode is HostAgentBillingMode.API_CREDITS and not self.allow_api_credit_handoff:
            raise ValueError("API credit handoff requires explicit approval")


@dataclass(frozen=True)
class HostAgentStagePacket:
    """Bounded unit of work Primr can give to an official host runner."""

    stage_id: str
    role: str
    instructions: str
    evidence: Mapping[str, str] = field(default_factory=dict)
    output_schema: Mapping[str, Any] | None = None
    policy: HostAgentPolicy = field(default_factory=HostAgentPolicy)

    def __post_init__(self) -> None:
        if not self.stage_id.strip():
            raise ValueError("stage_id is required")
        if not self.role.strip():
            raise ValueError("role is required")
        if not self.instructions.strip():
            raise ValueError("instructions are required")
        normalized_evidence = {
            str(label).strip(): str(text)
            for label, text in self.evidence.items()
            if str(label).strip() and str(text).strip()
        }
        object.__setattr__(self, "evidence", normalized_evidence)
        if self.output_schema is not None:
            object.__setattr__(self, "output_schema", dict(self.output_schema))


@dataclass(frozen=True)
class HostAgentResult:
    """Normalized result returned by a host-agent runner."""

    runner: HostAgentKind
    text: str
    billing_mode: HostAgentBillingMode
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "runner", HostAgentKind(self.runner))
        object.__setattr__(self, "billing_mode", HostAgentBillingMode(self.billing_mode))
        object.__setattr__(self, "metadata", dict(self.metadata))


@runtime_checkable
class HostAgentRunner(Protocol):
    """Protocol implemented by concrete Codex or Claude Code runners."""

    @property
    def kind(self) -> HostAgentKind:
        """Return the host-agent family this runner uses."""

    def is_available(self) -> bool:
        """Return True when the host runner is authenticated and callable."""

    def run(self, packet: HostAgentStagePacket) -> HostAgentResult:
        """Execute a bounded stage packet and return normalized text."""


def render_host_agent_prompt(packet: HostAgentStagePacket) -> str:
    """Render a stage packet into a prompt suitable for a host-agent runner."""

    lines = [
        "Run this Primr stage as a bounded host-agent task.",
        f"Stage: {packet.stage_id}",
        f"Role: {packet.role}",
        "",
        "Rules:",
        "- Use only the evidence included in this packet unless the packet explicitly asks otherwise.",
        "- Do not fetch URLs, run shell commands, or write files.",
        "- Return the requested output, then stop.",
        "",
        "Instructions:",
        packet.instructions.strip(),
    ]

    if packet.output_schema:
        lines.extend(
            [
                "",
                "Output schema:",
                repr(dict(packet.output_schema)),
            ]
        )

    if packet.evidence:
        lines.extend(["", "Evidence:"])
        for label, text in packet.evidence.items():
            fenced = fence_untrusted(label, text)
            if fenced:
                lines.append(fenced)

    lines.extend(
        [
            "",
            "Host billing policy:",
            f"- mode: {packet.policy.billing_mode.value}",
            f"- max_wall_seconds: {packet.policy.max_wall_seconds}",
            f"- max_output_chars: {packet.policy.max_output_chars}",
            f"- allow_api_credit_handoff: {packet.policy.allow_api_credit_handoff}",
        ]
    )
    return "\n".join(lines)
