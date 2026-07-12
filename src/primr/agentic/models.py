"""
Core data models for the agentic architecture.

This module defines the fundamental data structures used throughout
the agentic system. These models are designed to be:

- Immutable where possible (using frozen dataclasses)
- Serializable to JSON/YAML for persistence and MCP exposure
- Type-safe with comprehensive type hints
- Self-documenting with clear attribute descriptions

The models follow a layered design:
1. Primitive enums (ConfidenceLevel, VersionStatus, etc.)
2. Value objects (Hypothesis, Feature, etc.)
3. Aggregate roots (CompanyMemory, Version, etc.)

Example:
    from primr.agentic.models import Hypothesis, ConfidenceLevel

    hypothesis = Hypothesis(
        id="h_001",
        claim="Company uses microservices",
        confidence=ConfidenceLevel.UNTESTED
    )
    hypothesis.validate("CTO confirmed in interview")
    assert hypothesis.confidence == ConfidenceLevel.VALIDATED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# =============================================================================
# CONFIDENCE LEVELS
# =============================================================================


class ConfidenceLevel(Enum):
    """
    Confidence level for research hypotheses.

    Hypotheses progress through confidence levels as evidence is gathered:
    - UNTESTED: Initial state, no evidence gathered
    - VALIDATED: Evidence supports the hypothesis
    - INVALIDATED: Evidence contradicts the hypothesis
    - CONFIRMED: Strong evidence confirms the hypothesis

    The progression is not strictly linear - a validated hypothesis can
    be invalidated if contradicting evidence emerges.
    """

    UNTESTED = "untested"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    CONFIRMED = "confirmed"

    def __str__(self) -> str:
        """Return the value for display."""
        return self.value

    @property
    def is_positive(self) -> bool:
        """Check if this is a positive confidence level."""
        return self in (ConfidenceLevel.VALIDATED, ConfidenceLevel.CONFIRMED)

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal confidence level."""
        return self in (ConfidenceLevel.INVALIDATED, ConfidenceLevel.CONFIRMED)


# =============================================================================
# HYPOTHESIS
# =============================================================================


@dataclass
class Hypothesis:
    """
    A research claim with confidence tracking.

    Hypotheses are the core unit of research memory. They represent
    testable claims about a company that can be validated or invalidated
    through evidence gathering.

    Attributes:
        id: Unique identifier for the hypothesis
        claim: The testable claim (e.g., "Company uses microservices")
        confidence: Current confidence level
        evidence: List of evidence supporting/contradicting the claim
        created_at: When the hypothesis was created
        updated_at: When the hypothesis was last updated
        expires_at: When the hypothesis expires (None = never)
        topic: Topic category for filtering (e.g., "technology", "financials")

    Example:
        hypothesis = Hypothesis(
            id="h_001",
            claim="Revenue growth exceeds 20% YoY",
            confidence=ConfidenceLevel.UNTESTED,
            topic="financials",
            expires_at=datetime.now() + timedelta(days=90)
        )

        # Later, when evidence is found
        hypothesis.validate("Q3 earnings report shows 25% growth")
    """

    id: str
    claim: str
    confidence: ConfidenceLevel = ConfidenceLevel.UNTESTED
    evidence: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    topic: str = ""

    def validate(self, evidence: str) -> None:
        """
        Mark hypothesis as validated with supporting evidence.

        Args:
            evidence: Description of the supporting evidence
        """
        self.confidence = ConfidenceLevel.VALIDATED
        self.evidence.append(f"[VALIDATED] {evidence}")
        self.updated_at = datetime.now()

    def invalidate(self, evidence: str) -> None:
        """
        Mark hypothesis as invalidated with contradicting evidence.

        Args:
            evidence: Description of the contradicting evidence
        """
        self.confidence = ConfidenceLevel.INVALIDATED
        self.evidence.append(f"[INVALIDATED] {evidence}")
        self.updated_at = datetime.now()

    def confirm(self, evidence: str) -> None:
        """
        Mark hypothesis as confirmed with strong evidence.

        Args:
            evidence: Description of the confirming evidence
        """
        self.confidence = ConfidenceLevel.CONFIRMED
        self.evidence.append(f"[CONFIRMED] {evidence}")
        self.updated_at = datetime.now()

    def is_expired(self) -> bool:
        """
        Check if the hypothesis has expired.

        Returns:
            True if expires_at is set and in the past
        """
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary suitable for JSON serialization
        """
        return {
            "id": self.id,
            "claim": self.claim,
            "confidence": self.confidence.value,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "topic": self.topic,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hypothesis:
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary with hypothesis data

        Returns:
            Hypothesis instance
        """
        return cls(
            id=data["id"],
            claim=data["claim"],
            confidence=ConfidenceLevel(data["confidence"]),
            evidence=data.get("evidence", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=(
                datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
            ),
            topic=data.get("topic", ""),
        )

    def __hash__(self) -> int:
        """Hash by ID for set operations."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Compare by ID."""
        if not isinstance(other, Hypothesis):
            return NotImplemented
        return self.id == other.id


# =============================================================================
# VERSION STATUS (for Roadmap API)
# =============================================================================


class VersionStatus(Enum):
    """
    Status of a roadmap version.

    Versions progress through statuses as development proceeds:
    - COMPLETED: All features implemented and released
    - IN_PROGRESS: Currently being developed
    - PLANNED: Scheduled for future development
    - DEFERRED: Postponed indefinitely
    """

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    PLANNED = "planned"
    DEFERRED = "deferred"

    def __str__(self) -> str:
        """Return the value for display."""
        return self.value


# =============================================================================
# FEATURE (for Roadmap API)
# =============================================================================


@dataclass
class Feature:
    """
    A feature within a roadmap version.

    Attributes:
        name: Feature name
        description: Feature description
        status: Current status
        requirements: List of requirement IDs
        blockers: List of blocking issues
    """

    name: str
    description: str = ""
    status: VersionStatus = VersionStatus.PLANNED
    requirements: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "requirements": self.requirements,
            "blockers": self.blockers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Feature:
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            status=VersionStatus(data.get("status", "planned")),
            requirements=data.get("requirements", []),
            blockers=data.get("blockers", []),
        )


# =============================================================================
# VERSION (for Roadmap API)
# =============================================================================


@dataclass
class Version:
    """
    A version in the roadmap.

    Attributes:
        number: Version number or band (e.g., "1.x" or "2.0")
        title: Version title
        status: Current status
        features: List of features in this version
        dependencies: List of version numbers this depends on
        date: Release date (if known)
    """

    number: str
    title: str = ""
    status: VersionStatus = VersionStatus.PLANNED
    features: list[Feature] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "number": self.number,
            "title": self.title,
            "status": self.status.value,
            "features": [f.to_dict() for f in self.features],
            "dependencies": self.dependencies,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Version:
        """Deserialize from dictionary."""
        return cls(
            number=data["number"],
            title=data.get("title", ""),
            status=VersionStatus(data.get("status", "planned")),
            features=[Feature.from_dict(f) for f in data.get("features", [])],
            dependencies=data.get("dependencies", []),
            date=data.get("date"),
        )
