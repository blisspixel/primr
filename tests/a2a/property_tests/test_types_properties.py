"""Property-based tests for A2A types."""

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.a2a.types import A2ATaskMapping, ExternalAgentConfig


class TestA2ATaskMappingProperties:
    """Property tests for A2ATaskMapping serialization."""

    @given(
        task_id=st.text(min_size=1, max_size=50),
        job_id=st.text(min_size=1, max_size=50),
        skill_id=st.sampled_from(
            ["estimate_research", "research_company", "check_jobs", "run_qa", "system_health"]
        ),
    )
    @settings(max_examples=50)
    def test_roundtrip_serialization(self, task_id, job_id, skill_id):
        """Serialization round-trip preserves all fields."""
        original = A2ATaskMapping(
            task_id=task_id,
            job_id=job_id,
            skill_id=skill_id,
        )
        d = original.to_dict()
        restored = A2ATaskMapping.from_dict(d)

        assert restored.task_id == original.task_id
        assert restored.job_id == original.job_id
        assert restored.skill_id == original.skill_id

    @given(
        task_id=st.text(min_size=1, max_size=50),
        job_id=st.text(min_size=1, max_size=50),
        skill_id=st.text(min_size=1, max_size=20),
    )
    @settings(max_examples=50)
    def test_to_dict_keys(self, task_id, job_id, skill_id):
        """to_dict always contains the expected keys."""
        mapping = A2ATaskMapping(
            task_id=task_id,
            job_id=job_id,
            skill_id=skill_id,
        )
        d = mapping.to_dict()
        assert set(d.keys()) == {"task_id", "job_id", "skill_id", "created_at"}


class TestExternalAgentConfigProperties:
    """Property tests for ExternalAgentConfig."""

    @given(
        url=st.from_regex(r"https?://[a-z]+\.[a-z]{2,4}", fullmatch=True),
        name=st.text(min_size=1, max_size=50),
        timeout=st.floats(min_value=0.1, max_value=300.0),
    )
    @settings(max_examples=50)
    def test_valid_creation(self, url, name, timeout):
        """Valid inputs always create a config."""
        config = ExternalAgentConfig(url=url, name=name, timeout=timeout)
        assert config.url == url
        assert config.name == name
        assert config.timeout == timeout
