"""Research framing: the typed "what is this research for" of a run.

Elite research teams frame the engagement before gathering evidence: the
purpose, the audience, the decision the work informs, and the core question
to answer. Primr historically threaded the operator's intent
(``--discovery-notes``) only into the final strategy stage, so the analytical
workbook and the section writing never saw it. This module promotes that
intent to a first-class, immutable object that is resolved once and threaded
through the analytical stages.

The object is deliberately operator-supplied and deterministic: it carries no
LLM inference. ``to_prompt_block`` renders a stable, clearly-delimited context
block, and returns an empty string when nothing is specified so a run without
framing produces byte-identical prompts to before (the backward-compatibility
invariant the cached-prefix section prompts rely on).

See ``docs/design/research-tradecraft.md`` (Step 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


class ResearchPurpose(Enum):
    """Why the research is being run.

    Drives how the analysis is oriented (what to surface first, which lens to
    apply). ``GENERAL`` is the neutral default and is treated as "unspecified"
    for the purpose of ``ResearchFraming.is_specified``.
    """

    GENERAL = "general"
    SALES_PURSUIT = "sales_pursuit"
    DILIGENCE = "diligence"
    COMPETITIVE_INTEL = "competitive_intel"
    PARTNERSHIP = "partnership"

    def __str__(self) -> str:
        return self.value

    @property
    def label(self) -> str:
        """Human-readable label for prompts and CLI output."""
        return {
            ResearchPurpose.GENERAL: "General research",
            ResearchPurpose.SALES_PURSUIT: "Sales pursuit",
            ResearchPurpose.DILIGENCE: "Investment / partnership diligence",
            ResearchPurpose.COMPETITIVE_INTEL: "Competitive intelligence",
            ResearchPurpose.PARTNERSHIP: "Partnership evaluation",
        }[self]

    @classmethod
    def from_str(cls, value: str | None) -> ResearchPurpose:
        """Parse a purpose string, tolerating case/spacing; default GENERAL.

        Unknown values fall back to ``GENERAL`` rather than raising, so a stray
        input degrades to neutral framing instead of failing a paid run.
        """
        if not value:
            return cls.GENERAL
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == normalized:
                return member
        return cls.GENERAL


@dataclass(frozen=True)
class ResearchFraming:
    """Operator intent for a research run, resolved once and threaded through.

    All fields are optional. An all-default instance is the historical
    "no framing" case and renders to an empty prompt block.

    Attributes:
        purpose: The kind of engagement the research supports.
        audience: Who will read the brief (e.g. "VP Sales, first meeting").
        decision: The decision the brief informs.
        core_question: The single most important question to answer.
        discovery_notes: Freeform operator notes (folds in ``--discovery-notes``).
    """

    purpose: ResearchPurpose = ResearchPurpose.GENERAL
    audience: str = ""
    decision: str = ""
    core_question: str = ""
    discovery_notes: str = ""

    @classmethod
    def from_inputs(
        cls,
        *,
        purpose: str | ResearchPurpose | None = None,
        audience: str | None = None,
        decision: str | None = None,
        core_question: str | None = None,
        discovery_notes: str | None = None,
    ) -> ResearchFraming:
        """Build a normalized framing from raw (possibly None) inputs.

        Strings are trimmed; ``purpose`` is parsed leniently. This is the
        single construction seam used by the CLI and the orchestrator so
        normalization lives in one place.
        """
        resolved_purpose = (
            purpose if isinstance(purpose, ResearchPurpose) else ResearchPurpose.from_str(purpose)
        )
        return cls(
            purpose=resolved_purpose,
            audience=(audience or "").strip(),
            decision=(decision or "").strip(),
            core_question=(core_question or "").strip(),
            discovery_notes=(discovery_notes or "").strip(),
        )

    @property
    def is_specified(self) -> bool:
        """True if the operator supplied any framing beyond the neutral default."""
        return bool(
            self.audience
            or self.decision
            or self.core_question
            or self.discovery_notes
            or self.purpose is not ResearchPurpose.GENERAL
        )

    def to_prompt_block(self) -> str:
        """Render framing as a stable, delimited prompt block.

        Returns an empty string when nothing is specified, so prompts for an
        unframed run are unchanged from the pre-framing behavior. Only the
        fields the operator set are emitted, each on its own labeled line, with
        discovery notes last (they are the largest block).
        """
        if not self.is_specified:
            return ""

        lines: list[str] = ["=== RESEARCH FRAMING (operator intent) ==="]
        if self.purpose is not ResearchPurpose.GENERAL:
            lines.append(f"Purpose: {self.purpose.label}")
        if self.audience:
            lines.append(f"Audience: {self.audience}")
        if self.decision:
            lines.append(f"Decision this informs: {self.decision}")
        if self.core_question:
            lines.append(f"Core question: {self.core_question}")
        if self.discovery_notes:
            lines.append("Operator discovery notes:")
            lines.append(self.discovery_notes)
        lines.append("=== END RESEARCH FRAMING ===")
        lines.append(
            "Orient the analysis to this purpose, audience, and decision. "
            "Lead with what matters for the core question, and call out where "
            "the evidence for it is thin rather than padding."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, str]:
        """Serialize for the plan artifact and MCP exposure (Step 3)."""
        return {
            "purpose": self.purpose.value,
            "audience": self.audience,
            "decision": self.decision,
            "core_question": self.core_question,
            "discovery_notes": self.discovery_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str] | None) -> ResearchFraming:
        """Reconstruct framing from a serialized dict (inverse of ``to_dict``)."""
        if not data:
            return cls()
        return cls.from_inputs(
            purpose=data.get("purpose"),
            audience=data.get("audience"),
            decision=data.get("decision"),
            core_question=data.get("core_question"),
            discovery_notes=data.get("discovery_notes"),
        )


# A shared neutral instance for the common "no framing supplied" path.
EMPTY_FRAMING: ResearchFraming = ResearchFraming()


def resolve_run_framing(
    *,
    discovery_notes_path: str | None = None,
    purpose: str | None = None,
    audience: str | None = None,
    decision: str | None = None,
    core_question: str | None = None,
) -> tuple[ResearchFraming | None, str | None, str | None]:
    """Load discovery notes (if any) and resolve operator framing for a run.

    This is the single seam that turns raw run inputs into a ``ResearchFraming``
    plus the discovery-notes content the strategy stage still consumes
    separately. It owns the discovery-notes file read so the orchestrator does
    not.

    Returns ``(framing, discovery_notes_content, error)``:
      - On success, ``error`` is None and ``framing`` is always built (neutral
        when nothing was supplied).
      - On a discovery-notes file error, ``framing`` and ``discovery_notes_content``
        are None and ``error`` is a user-facing message the caller surfaces
        before aborting the run.
    """
    discovery_notes_content: str | None = None
    if discovery_notes_path:
        try:
            with open(discovery_notes_path, encoding="utf-8") as f:
                discovery_notes_content = f.read().strip()
        except FileNotFoundError:
            return None, None, f"Discovery notes file not found: {discovery_notes_path}"
        except Exception as e:  # surface any read failure as an abortable run error
            return None, None, f"Failed to load discovery notes: {e}"
        if discovery_notes_content:
            logger.info("Loaded discovery notes from %s", discovery_notes_path)
        else:
            logger.warning("Discovery notes file is empty: %s", discovery_notes_path)
            discovery_notes_content = None

    framing = ResearchFraming.from_inputs(
        purpose=purpose,
        audience=audience,
        decision=decision,
        core_question=core_question,
        discovery_notes=discovery_notes_content,
    )
    return framing, discovery_notes_content, None
