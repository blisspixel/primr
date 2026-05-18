"""Property tests for SKILL.md AgentSkills compliance.

Property 3: SKILL.md AgentSkills Compliance
Validates: FR-2.2, FR-2.3
"""

from pathlib import Path
import re

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest
import yaml

SKILLS_DIR = Path(__file__).parent.parent.parent / "openclaw" / "skills"
SKILL_FILES = list(SKILLS_DIR.glob("*/SKILL.md"))


def parse_skill_file(path: Path) -> tuple[dict, str]:
    """Parse a SKILL.md file into frontmatter and body."""
    content = path.read_text(encoding="utf-8")

    # Split frontmatter from body
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()
            return frontmatter, body

    raise ValueError(f"Invalid SKILL.md format: {path}")


@pytest.fixture(params=SKILL_FILES, ids=lambda p: p.parent.name)
def skill_file(request) -> Path:
    """Parametrized fixture for all SKILL.md files."""
    return request.param


class TestSkillFrontmatterCompliance:
    """Test SKILL.md YAML frontmatter compliance."""

    def test_yaml_parses_without_errors(self, skill_file: Path) -> None:
        """FR-2.2: YAML frontmatter parses without errors."""
        frontmatter, _ = parse_skill_file(skill_file)
        assert isinstance(frontmatter, dict)

    def test_has_required_name_field(self, skill_file: Path) -> None:
        """FR-2.2: name field is present."""
        frontmatter, _ = parse_skill_file(skill_file)
        assert "name" in frontmatter
        assert isinstance(frontmatter["name"], str)
        assert len(frontmatter["name"]) > 0

    def test_has_required_version_field(self, skill_file: Path) -> None:
        """FR-2.2: version field is present."""
        frontmatter, _ = parse_skill_file(skill_file)
        assert "version" in frontmatter
        # Version should be semver-like
        version = frontmatter["version"]
        assert re.match(r"^\d+\.\d+\.\d+", str(version))

    def test_has_metadata_openclaw_requires_bins(self, skill_file: Path) -> None:
        """FR-2.2: metadata.openclaw.requires.bins contains primr-mcp."""
        frontmatter, _ = parse_skill_file(skill_file)

        assert "metadata" in frontmatter
        assert "openclaw" in frontmatter["metadata"]
        assert "requires" in frontmatter["metadata"]["openclaw"]
        assert "bins" in frontmatter["metadata"]["openclaw"]["requires"]

        bins = frontmatter["metadata"]["openclaw"]["requires"]["bins"]
        assert "primr-mcp" in bins

    def test_has_metadata_openclaw_requires_env(self, skill_file: Path) -> None:
        """FR-2.2: metadata.openclaw.requires.env lists required env vars."""
        frontmatter, _ = parse_skill_file(skill_file)

        env_vars = frontmatter["metadata"]["openclaw"]["requires"]["env"]
        assert isinstance(env_vars, list)
        assert len(env_vars) > 0

        assert "GEMINI_API_KEY" in env_vars
        assert "XAI_API_KEY" in env_vars

    def test_has_tools_array(self, skill_file: Path) -> None:
        """FR-2.2: tools array is present."""
        frontmatter, _ = parse_skill_file(skill_file)
        assert "tools" in frontmatter
        assert isinstance(frontmatter["tools"], list)
        assert len(frontmatter["tools"]) > 0


class TestSkillBodyCompliance:
    """Test SKILL.md markdown body compliance."""

    def test_has_conceptual_framework_section(self, skill_file: Path) -> None:
        """FR-2.3: Markdown body contains 'Conceptual Framework' section."""
        _, body = parse_skill_file(skill_file)
        assert "Conceptual Framework" in body or "conceptual framework" in body.lower()

    def test_has_operational_capabilities_section(self, skill_file: Path) -> None:
        """FR-2.3: Markdown body contains 'Operational Capabilities' section."""
        _, body = parse_skill_file(skill_file)
        assert "Operational Capabilities" in body or "operational capabilities" in body.lower()


class TestPrimrResearchSkillSpecific:
    """Tests specific to primr-research skill."""

    @pytest.fixture
    def research_skill(self) -> tuple[dict, str]:
        """Load primr-research SKILL.md."""
        path = SKILLS_DIR / "primr-research" / "SKILL.md"
        return parse_skill_file(path)

    def test_documents_async_job_model(self, research_skill: tuple[dict, str]) -> None:
        """FR-2.4: Documents async job model."""
        _, body = research_skill
        assert "async" in body.lower() or "job" in body.lower()

    def test_documents_status_monitoring(self, research_skill: tuple[dict, str]) -> None:
        """FR-2.4: Documents status monitoring via primr://research/status."""
        _, body = research_skill
        assert "primr://research/status" in body or "status" in body.lower()

    def test_documents_research_modes(self, research_skill: tuple[dict, str]) -> None:
        """FR-2.4: Documents the current research modes."""
        _, body = research_skill
        assert "scrape" in body.lower()
        assert "deep" in body.lower()
        assert "full" in body.lower()
        assert "premium" in body.lower()

    def test_has_error_handling_section(self, research_skill: tuple[dict, str]) -> None:
        """FR-2.3: Has Error Handling section."""
        _, body = research_skill
        assert "Error Handling" in body or "error handling" in body.lower()


# Property-based test for schema validation
class TestPropertyBasedCompliance:
    """Property-based tests for SKILL.md compliance."""

    @settings(max_examples=100)
    @given(st.sampled_from(SKILL_FILES) if SKILL_FILES else st.nothing())
    def test_all_skills_have_valid_structure(self, skill_path: Path) -> None:
        """Property 3: All SKILL.md files have valid structure."""
        frontmatter, body = parse_skill_file(skill_path)

        # Required frontmatter fields
        assert "name" in frontmatter
        assert "version" in frontmatter
        assert "metadata" in frontmatter
        assert "openclaw" in frontmatter["metadata"]
        assert "requires" in frontmatter["metadata"]["openclaw"]
        assert "bins" in frontmatter["metadata"]["openclaw"]["requires"]
        assert "primr-mcp" in frontmatter["metadata"]["openclaw"]["requires"]["bins"]

        # Required body sections
        body_lower = body.lower()
        assert "conceptual framework" in body_lower or "## conceptual" in body_lower
        assert "operational capabilities" in body_lower or "## operational" in body_lower
