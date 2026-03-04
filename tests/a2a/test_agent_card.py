"""Tests for A2A agent card builder."""

import pytest

a2a = pytest.importorskip("a2a")

from primr.a2a.agent_card import build_agent_card


class TestBuildAgentCard:
    """Tests for build_agent_card function."""

    def test_returns_agent_card(self):
        card = build_agent_card(host="localhost", port=9000, version="1.0.0")
        assert card.name == "Primr Research Agent"
        assert card.version == "1.0.0"

    def test_url_format(self):
        card = build_agent_card(host="example.com", port=8080, version="1.0.0")
        assert card.url == "http://example.com:8080/"

    def test_skills_count(self):
        card = build_agent_card(version="1.0.0")
        assert len(card.skills) == 5

    def test_skill_ids(self):
        card = build_agent_card(version="1.0.0")
        skill_ids = {s.id for s in card.skills}
        assert "estimate_research" in skill_ids
        assert "research_company" in skill_ids
        assert "check_jobs" in skill_ids
        assert "run_qa" in skill_ids
        assert "system_health" in skill_ids

    def test_capabilities(self):
        card = build_agent_card(version="1.0.0")
        assert card.capabilities.streaming is True

    def test_input_output_modes(self):
        card = build_agent_card(version="1.0.0")
        assert "text" in card.defaultInputModes
        assert "text" in card.defaultOutputModes

    def test_authentication_scheme(self):
        card = build_agent_card(version="1.0.0")
        assert "bearer" in card.authentication.schemes

    def test_version_fallback(self):
        """When version is None, falls back to package version or 0.0.0."""
        card = build_agent_card(version=None)
        assert card.version  # Should not be None

    def test_each_skill_has_examples(self):
        card = build_agent_card(version="1.0.0")
        for skill in card.skills:
            assert len(skill.examples) > 0, f"Skill {skill.id} has no examples"

    def test_each_skill_has_tags(self):
        card = build_agent_card(version="1.0.0")
        for skill in card.skills:
            assert len(skill.tags) > 0, f"Skill {skill.id} has no tags"
