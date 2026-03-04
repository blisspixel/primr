"""A2A type definitions for Primr integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ExternalAgentConfig:
    """Configuration for connecting to an external A2A agent."""

    url: str
    name: str
    auth_token: str | None = None
    skills: list[str] = field(default_factory=list)
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if not self.url or not self.url.strip():
            raise ValueError("Agent URL is required")
        if not self.name or not self.name.strip():
            raise ValueError("Agent name is required")


@dataclass
class A2ATaskMapping:
    """Maps an A2A task ID to a Primr job ID."""

    task_id: str
    job_id: str
    skill_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "job_id": self.job_id,
            "skill_id": self.skill_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> A2ATaskMapping:
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)
        return cls(
            task_id=data["task_id"],
            job_id=data["job_id"],
            skill_id=data["skill_id"],
            created_at=created_at,
        )
