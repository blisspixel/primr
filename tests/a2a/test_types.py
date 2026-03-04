"""Tests for A2A type definitions."""

from datetime import datetime, timezone

import pytest

from primr.a2a.types import A2ATaskMapping, ExternalAgentConfig


class TestExternalAgentConfig:
    """Tests for ExternalAgentConfig dataclass."""

    def test_basic_creation(self):
        config = ExternalAgentConfig(url="http://agent.example.com", name="TestAgent")
        assert config.url == "http://agent.example.com"
        assert config.name == "TestAgent"
        assert config.auth_token is None
        assert config.skills == []
        assert config.timeout == 60.0

    def test_full_creation(self):
        config = ExternalAgentConfig(
            url="http://agent.example.com",
            name="TestAgent",
            auth_token="secret",
            skills=["research", "analyze"],
            timeout=30.0,
        )
        assert config.auth_token == "secret"
        assert config.skills == ["research", "analyze"]
        assert config.timeout == 30.0

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="URL is required"):
            ExternalAgentConfig(url="", name="TestAgent")

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name is required"):
            ExternalAgentConfig(url="http://example.com", name="")


class TestA2ATaskMapping:
    """Tests for A2ATaskMapping dataclass."""

    def test_creation(self):
        mapping = A2ATaskMapping(
            task_id="t-123",
            job_id="j-456",
            skill_id="research_company",
        )
        assert mapping.task_id == "t-123"
        assert mapping.job_id == "j-456"
        assert mapping.skill_id == "research_company"
        assert isinstance(mapping.created_at, datetime)

    def test_to_dict(self):
        now = datetime(2026, 3, 1, tzinfo=timezone.utc)
        mapping = A2ATaskMapping(
            task_id="t-1",
            job_id="j-1",
            skill_id="estimate",
            created_at=now,
        )
        d = mapping.to_dict()
        assert d["task_id"] == "t-1"
        assert d["job_id"] == "j-1"
        assert d["skill_id"] == "estimate"
        assert "2026-03-01" in d["created_at"]

    def test_from_dict_roundtrip(self):
        original = A2ATaskMapping(
            task_id="t-1",
            job_id="j-1",
            skill_id="check",
        )
        d = original.to_dict()
        restored = A2ATaskMapping.from_dict(d)
        assert restored.task_id == original.task_id
        assert restored.job_id == original.job_id
        assert restored.skill_id == original.skill_id

    def test_from_dict_missing_created_at(self):
        mapping = A2ATaskMapping.from_dict({
            "task_id": "t-1",
            "job_id": "j-1",
            "skill_id": "check",
        })
        assert isinstance(mapping.created_at, datetime)
