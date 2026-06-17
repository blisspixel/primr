"""
Unit tests for skills_generator module.

Tests cover:
- slugify edge cases (special chars, unicode, path traversal attempts)
- parse_role_blocks with standard and messy LLM output
- generate_skill_md with quote escaping and missing fields
- write_skill_files end-to-end with path traversal defense
- Graceful degradation on parse failures
"""

from __future__ import annotations

from primr.output.skills_generator import (
    generate_skill_md,
    parse_role_blocks,
    slugify,
    write_skill_files,
)

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Test slugify function."""

    def test_basic(self):
        assert slugify("Cloud Security Engineer") == "cloud-security-engineer"

    def test_special_chars_stripped(self):
        assert slugify("ML/AI Engineer (Senior)") == "mlai-engineer-senior"

    def test_dots_stripped(self):
        assert slugify("Sr. Platform Engineer") == "sr-platform-engineer"

    def test_path_traversal_dots(self):
        assert slugify("../../etc/passwd") == "etcpasswd"

    def test_path_traversal_backslash(self):
        assert slugify("..\\..\\windows\\system32") == "windowssystem32"

    def test_empty_after_strip(self):
        assert slugify("...") == ""

    def test_only_special_chars(self):
        assert slugify("@#$%^&*()") == ""

    def test_unicode_stripped(self):
        # Non-ASCII chars are stripped by the regex
        assert slugify("Ingénieur DevOps") == "ingnieur-devops"

    def test_multiple_spaces_collapsed(self):
        assert slugify("Data   Platform   Engineer") == "data-platform-engineer"

    def test_leading_trailing_hyphens_stripped(self):
        assert slugify("-Engineer-") == "engineer"

    def test_underscores_become_hyphens(self):
        assert slugify("data_engineer") == "data-engineer"


# ---------------------------------------------------------------------------
# parse_role_blocks
# ---------------------------------------------------------------------------


class TestParseRoleBlocks:
    """Test parse_role_blocks function."""

    def test_standard_format(self):
        text = """## Top Roles and Skills

### Role: Cloud Security Engineer
**Confidence:** Confirmed
**Evidence:** 3 Greenhouse postings for Cloud Security Engineer

**Skills:**
1. AWS IAM — identity and access management
2. Kubernetes security — container runtime hardening
3. SIEM integration — Splunk/Datadog log correlation

### Role: Data Platform Engineer
**Confidence:** Inferred
**Evidence:** DNS-confirmed Snowflake + dbt mentions

**Skills:**
1. Snowflake administration — warehouse optimization
2. dbt modeling — transformation pipeline design
3. Airflow orchestration — DAG management

## Cross-Role Themes
Some themes here.
"""
        roles = parse_role_blocks(text)
        assert len(roles) == 2
        assert roles[0]["name"] == "Cloud Security Engineer"
        assert roles[0]["confidence"] == "Confirmed"
        assert "3 Greenhouse postings" in roles[0]["evidence"]
        assert "AWS IAM" in roles[0]["skills_text"]
        assert roles[1]["name"] == "Data Platform Engineer"
        assert roles[1]["confidence"] == "Inferred"

    def test_no_roles_returns_empty(self):
        text = "## Some heading\nNo role blocks here."
        roles = parse_role_blocks(text)
        assert roles == []

    def test_missing_confidence_defaults_to_inferred(self):
        text = """### Role: Mystery Role
Some content without confidence label.

**Skills:**
1. Skill one — description
"""
        roles = parse_role_blocks(text)
        assert len(roles) == 1
        assert roles[0]["confidence"] == "Inferred"

    def test_missing_evidence_returns_empty_string(self):
        text = """### Role: No Evidence Role
**Confidence:** Speculated

**Skills:**
1. Skill one — description
"""
        roles = parse_role_blocks(text)
        assert len(roles) == 1
        assert roles[0]["evidence"] == ""

    def test_missing_skills_returns_empty_string(self):
        text = """### Role: No Skills Role
**Confidence:** Confirmed
**Evidence:** Some evidence

No skills listed here.
"""
        roles = parse_role_blocks(text)
        assert len(roles) == 1
        assert roles[0]["skills_text"] == ""

    def test_single_role_at_end_of_document(self):
        text = """### Role: Solo Role
**Confidence:** Confirmed
**Evidence:** Direct evidence

**Skills:**
1. Only skill — description
"""
        roles = parse_role_blocks(text)
        assert len(roles) == 1
        assert roles[0]["name"] == "Solo Role"


# ---------------------------------------------------------------------------
# generate_skill_md
# ---------------------------------------------------------------------------


class TestGenerateSkillMd:
    """Test generate_skill_md function."""

    def test_basic_output(self):
        role = {
            "name": "Data Engineer",
            "confidence": "Confirmed",
            "evidence": "5 postings on Greenhouse",
            "skills_text": "1. Snowflake — warehouse ops\n2. dbt — transforms",
            "body": "",
        }
        md = generate_skill_md(role)
        assert md.startswith("---\n")
        assert 'name: "Data Engineer"' in md
        assert 'description: "Data Engineer (Confirmed)' in md
        assert "# Data Engineer" in md
        assert "**Confidence:** Confirmed" in md
        assert "**Evidence:** 5 postings" in md
        assert "## Skills" in md
        assert "Snowflake" in md

    def test_quotes_escaped_in_frontmatter(self):
        role = {
            "name": 'Role "with" quotes',
            "confidence": "Inferred",
            "evidence": 'evidence "here"',
            "skills_text": "",
            "body": "",
        }
        md = generate_skill_md(role)
        assert 'name: "Role \\"with\\" quotes"' in md
        assert 'evidence \\"here\\"' in md

    def test_no_evidence_omits_line(self):
        role = {
            "name": "Simple Role",
            "confidence": "Speculated",
            "evidence": "",
            "skills_text": "",
            "body": "",
        }
        md = generate_skill_md(role)
        assert "**Evidence:**" not in md

    def test_no_skills_omits_section(self):
        role = {
            "name": "Empty Skills",
            "confidence": "Inferred",
            "evidence": "some evidence",
            "skills_text": "",
            "body": "",
        }
        md = generate_skill_md(role)
        assert "## Skills" not in md


# ---------------------------------------------------------------------------
# write_skill_files
# ---------------------------------------------------------------------------


class TestWriteSkillFiles:
    """Test write_skill_files end-to-end."""

    def test_writes_files_correctly(self, tmp_path):
        text = """### Role: Cloud Engineer
**Confidence:** Confirmed
**Evidence:** DNS + postings

**Skills:**
1. AWS — cloud infra
2. Terraform — IaC
3. K8s — orchestration

### Role: Data Scientist
**Confidence:** Inferred
**Evidence:** Industry baseline

**Skills:**
1. Python — analysis
2. PyTorch — ML
3. SQL — queries
"""
        written = write_skill_files(text, tmp_path)
        assert len(written) == 2

        # Check directory structure
        assert (tmp_path / "roles" / "cloud-engineer" / "SKILL.md").exists()
        assert (tmp_path / "roles" / "data-scientist" / "SKILL.md").exists()

        # Check content
        content = (tmp_path / "roles" / "cloud-engineer" / "SKILL.md").read_text()
        assert "---" in content
        assert 'name: "Cloud Engineer"' in content
        assert "AWS" in content

    def test_empty_text_returns_empty_list(self, tmp_path):
        written = write_skill_files("No roles here.", tmp_path)
        assert written == []

    def test_graceful_on_parse_error(self, tmp_path, monkeypatch):
        """If parsing raises, returns empty list without crashing."""
        import primr.output.skills_generator as sg

        def exploding_parse(text):
            raise RuntimeError("Simulated parse failure")

        monkeypatch.setattr(sg, "parse_role_blocks", exploding_parse)
        written = write_skill_files("anything", tmp_path)
        assert written == []

    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Roles with traversal-like names don't escape output_dir."""
        import primr.output.skills_generator as sg

        # Monkey-patch slugify to return a traversal attempt
        # (shouldn't happen with real slugify, but defense-in-depth)
        original_slugify = sg.slugify
        call_count = [0]

        def evil_slugify(text):
            call_count[0] += 1
            if call_count[0] == 1:
                return "..\\..\\evil"
            return original_slugify(text)

        monkeypatch.setattr(sg, "slugify", evil_slugify)

        text = """### Role: Evil Role
**Confidence:** Confirmed
**Evidence:** test

**Skills:**
1. Hack — traversal

### Role: Good Role
**Confidence:** Confirmed
**Evidence:** test

**Skills:**
1. Safe — normal
"""
        written = write_skill_files(text, tmp_path)
        # Evil role should be skipped, good role should succeed
        # (or both succeed if the slug resolves inside the dir)
        for path in written:
            resolved = path.resolve()
            resolved.relative_to(tmp_path.resolve())

    def test_path_prefix_sibling_escape_blocked(self, tmp_path, monkeypatch):
        """A sibling like roles_evil must not pass containment for roles."""
        import primr.output.skills_generator as sg

        def evil_slugify(_text):
            return "../roles_evil"

        monkeypatch.setattr(sg, "slugify", evil_slugify)

        text = """### Role: Evil Role
**Confidence:** Confirmed
**Evidence:** test

**Skills:**
1. Hack — traversal
"""
        written = write_skill_files(text, tmp_path)
        assert written == []
        assert not (tmp_path / "roles_evil").exists()

    def test_unsluggable_role_skipped(self, tmp_path):
        """Roles that slugify to empty string are skipped."""
        text = """### Role: ...
**Confidence:** Confirmed
**Evidence:** test

**Skills:**
1. Nothing — here
"""
        written = write_skill_files(text, tmp_path)
        assert written == []
