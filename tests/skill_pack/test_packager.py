"""Tests for the Cowork packager.

Verifies: manifest.json shape, deterministic UUID v5, .zip structure
matches the M365 Cowork spec, and idempotent re-packaging.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from primr.skill_pack.config import SkillPackConfig, SkillPackFormat
from primr.skill_pack.packager import (
    MANIFEST_SCHEMA_URL,
    MAX_COWORK_AGENT_SKILLS,
    PACKAGE_VERSION,
    package_skill_pack,
)
from primr.skill_pack.schema import (
    BundledFile,
    IndustryClassification,
    Role,
    RoleEvidence,
    RolePlan,
    Skill,
    SkillPack,
    ValidationReport,
)


def _make_pack(company: str = "Acme Corp") -> SkillPack:
    skill = Skill(
        name="draft-dbt-models",
        display_name="Draft dbt models",
        description="Use when the user asks to draft a new dbt model.",
        body=(
            "## What This Skill Does\n\nAuthor a dbt model.\n\n"
            "## Workflow\n\n1. Read spec.\n2. Write SQL.\n\n"
            "## Output Format\n\n| f | v |\n|---|---|\n| ok | yes |\n"
        ),
    )
    role = Role(
        name="data-engineer",
        display_name="Data Engineer",
        confidence="Inferred",
        evidence=RoleEvidence(archetype="data-engineer"),
        skills=[skill],
    )
    return SkillPack(
        company_name=company,
        company_url="https://acme.example",
        generated_at="2026-05-28T00:00:00+00:00",
        roles=[role],
        validation=ValidationReport(),
    )


def _make_pack_with_bundled_files(company: str = "Acme Corp") -> SkillPack:
    pack = _make_pack(company)
    pack.roles[0].skills[0].bundled_files = [
        BundledFile(relpath="references/sku-map.md", content="# SKU map\n\n- A -> B\n"),
        BundledFile(relpath="scripts/calc.py", content="print('savings')\n"),
        # Unsafe path — must be dropped, not written.
        BundledFile(relpath="../escape.md", content="should not be written"),
    ]
    return pack


def test_bundled_files_written_to_claude_tree(tmp_path: Path):
    pack = _make_pack_with_bundled_files()
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)

    skill_dir = Path(artifacts.claude_tree_root) / "draft-dbt-models"
    assert (skill_dir / "references" / "sku-map.md").is_file()
    assert (skill_dir / "scripts" / "calc.py").is_file()
    # The unsafe path was dropped and never escaped the skill folder.
    assert not (skill_dir.parent / "escape.md").exists()
    assert not (tmp_path / "escape.md").exists()


def test_bundled_files_written_to_cowork_zip(tmp_path: Path):
    pack = _make_pack_with_bundled_files()
    config = SkillPackConfig(formats=SkillPackFormat.COWORK)
    artifacts = package_skill_pack(pack, config, tmp_path)

    with zipfile.ZipFile(artifacts.cowork_zip_path) as zf:
        names = zf.namelist()
    assert "skills/draft-dbt-models/references/sku-map.md" in names
    assert "skills/draft-dbt-models/scripts/calc.py" in names
    # No unsafe entry anywhere in the archive.
    assert not any("escape.md" in n for n in names)


def test_cowork_icons_use_local_generation_by_default(tmp_path: Path):
    pack = _make_pack()
    png = b"\x89PNG\r\n\x1a\nlocal"

    with patch("primr.skill_pack.packager.generate_icons", return_value=(png, png)) as generate:
        package_skill_pack(pack, SkillPackConfig(formats=SkillPackFormat.COWORK), tmp_path)

    assert generate.call_args.kwargs["disable_remote"] is True


def test_cowork_icons_allow_explicit_remote_generation(tmp_path: Path):
    pack = _make_pack()
    png = b"\x89PNG\r\n\x1a\nremote"

    config = SkillPackConfig(
        formats=SkillPackFormat.COWORK,
        remote_icon_generation=True,
    )
    with patch("primr.skill_pack.packager.generate_icons", return_value=(png, png)) as generate:
        package_skill_pack(pack, config, tmp_path)

    assert generate.call_args.kwargs["disable_remote"] is False


def test_unsafe_folder_slug_is_dropped_from_both_artifacts(tmp_path: Path):
    """A skill whose name is not a safe single path segment must not be
    written to the Claude tree or the Cowork zip (path-traversal guard)."""
    good = _make_pack().roles[0].skills[0]
    evil = Skill(
        name="../evil",
        display_name="Evil",
        description="Use when the user asks to do X, Y, or Z.",
        body=good.body,
    )
    role = Role(
        name="data-engineer",
        display_name="Data Engineer",
        confidence="Inferred",
        evidence=RoleEvidence(archetype="data-engineer"),
        skills=[good, evil],
    )
    pack = SkillPack(
        company_name="Acme Corp",
        company_url=None,
        generated_at="2026-01-01T00:00:00+00:00",
        roles=[role],
        validation=ValidationReport(),
    )
    artifacts = package_skill_pack(pack, SkillPackConfig(formats=SkillPackFormat.BOTH), tmp_path)
    # No traversal escaped the output dir.
    assert not (tmp_path.parent / "evil").exists()
    with zipfile.ZipFile(artifacts.cowork_zip_path) as zf:
        names = zf.namelist()
    assert not any("evil" in n for n in names)
    assert any("draft-dbt-models/SKILL.md" in n for n in names)  # good skill survived


def test_claude_tree_path_containment_rejects_sibling_prefix_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Defense-in-depth: containment is path-aware, not string-prefix based."""
    import primr.skill_pack.packager as packager

    good = _make_pack().roles[0].skills[0]
    evil = Skill(
        name="../roles_evil",
        display_name="Evil",
        description="Use when the user asks to do X, Y, or Z.",
        body=good.body,
    )
    role = Role(
        name="data-engineer",
        display_name="Data Engineer",
        confidence="Inferred",
        evidence=RoleEvidence(archetype="data-engineer"),
        skills=[evil],
    )
    pack = SkillPack(
        company_name="Acme Corp",
        company_url=None,
        generated_at="2026-01-01T00:00:00+00:00",
        roles=[role],
        validation=ValidationReport(),
    )

    monkeypatch.setattr(packager, "_is_safe_slug", lambda _slug: True)
    artifacts = package_skill_pack(pack, SkillPackConfig(formats=SkillPackFormat.CLAUDE), tmp_path)

    assert artifacts.claude_tree_root is not None
    assert not (Path(artifacts.claude_tree_root).parent / "roles_evil").exists()
    assert artifacts.skill_md_paths == []


def test_package_emits_claude_tree_and_cowork_zip(tmp_path: Path):
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.BOTH)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is not None
    assert Path(artifacts.claude_tree_root).is_dir()
    assert artifacts.cowork_zip_path is not None
    assert Path(artifacts.cowork_zip_path).is_file()
    assert artifacts.report_md_path is not None
    assert Path(artifacts.report_md_path).is_file()

    # Claude tree has the SKILL.md file
    skill_path = Path(artifacts.claude_tree_root) / "draft-dbt-models" / "SKILL.md"
    assert skill_path.is_file()
    text = skill_path.read_text(encoding="utf-8")
    assert 'name: "draft-dbt-models"' in text
    assert "## Workflow" in text


def test_skill_md_has_clean_frontmatter_by_default(tmp_path: Path):
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is not None
    skill_path = Path(artifacts.claude_tree_root) / "draft-dbt-models" / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")

    # name/description preserved, branded metadata block omitted by default.
    assert 'name: "draft-dbt-models"' in text
    assert "metadata:" not in text
    assert "primr-role" not in text


def test_skill_md_metadata_can_be_enabled(tmp_path: Path):
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE, emit_agent_metadata=True)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is not None
    text = (Path(artifacts.claude_tree_root) / "draft-dbt-models" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert 'name: "draft-dbt-models"' in text
    assert "metadata:" in text
    assert 'primr-role: "Data Engineer"' in text
    assert 'primr-provenance: "posting"' in text  # RoleEvidence default provenance
    assert 'primr-confidence: "Inferred"' in text
    assert "primr-context-tokens:" in text
    assert "mcp:primr/generate_skill_pack" in text


def test_claude_and_cowork_skill_md_byte_identical(tmp_path: Path):
    # The pack invariant: the same SKILL.md bytes ship in both formats, metadata included.
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.BOTH)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is not None
    assert artifacts.cowork_zip_path is not None
    claude_bytes = (Path(artifacts.claude_tree_root) / "draft-dbt-models" / "SKILL.md").read_bytes()
    with zipfile.ZipFile(artifacts.cowork_zip_path) as zf:
        cowork_bytes = zf.read("skills/draft-dbt-models/SKILL.md")
    assert claude_bytes == cowork_bytes


def test_package_claude_only(tmp_path: Path):
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is not None
    assert artifacts.cowork_zip_path is None


def test_package_cowork_only(tmp_path: Path):
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.COWORK)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is None
    assert artifacts.cowork_zip_path is not None


def test_cowork_zip_matches_spec(tmp_path: Path):
    pack = _make_pack()
    config = SkillPackConfig(formats=SkillPackFormat.COWORK)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.cowork_zip_path is not None
    with zipfile.ZipFile(artifacts.cowork_zip_path) as zf:
        names = set(zf.namelist())
        # Required top-level entries
        assert "manifest.json" in names
        assert "color.png" in names
        assert "outline.png" in names
        # Skill in skills/ tree
        assert "skills/draft-dbt-models/SKILL.md" in names

        manifest = json.loads(zf.read("manifest.json"))

    assert manifest["$schema"] == MANIFEST_SCHEMA_URL
    assert manifest["manifestVersion"] == "1.28"
    assert manifest["version"] == PACKAGE_VERSION
    assert manifest["developer"]["name"] == "Custom Skill Pack"
    generated_label = "Generated " + "by primr"
    assert manifest["developer"]["name"] != generated_label
    assert generated_label not in json.dumps(manifest)
    # ASKILL-M001: agentSkills folder references must exist
    folders = [entry["folder"] for entry in manifest["agentSkills"]]
    assert "./skills/draft-dbt-models" in folders


def test_cowork_zip_caps_manifest_skill_count(tmp_path: Path):
    body = (
        "## What This Skill Does\n\nDo one scoped task.\n\n"
        "## Workflow\n\n1. Collect input.\n\n"
        "## Output Format\n\nReturn the artifact.\n"
    )
    role = Role(
        name="role-a",
        display_name="Role A",
        confidence="Inferred",
        evidence=RoleEvidence(),
        skills=[
            Skill(
                name=f"skill-{idx:02d}",
                display_name=f"Skill {idx:02d}",
                description="Use when the user asks for a scoped task.",
                body=body,
            )
            for idx in range(MAX_COWORK_AGENT_SKILLS + 5)
        ],
    )
    pack = SkillPack(
        company_name="Acme Corp",
        company_url=None,
        generated_at="2026-05-28T00:00:00+00:00",
        roles=[role],
        validation=ValidationReport(),
    )

    artifacts = package_skill_pack(pack, SkillPackConfig(formats=SkillPackFormat.BOTH), tmp_path)

    assert artifacts.cowork_zip_path is not None
    assert artifacts.claude_tree_root is not None
    with zipfile.ZipFile(artifacts.cowork_zip_path) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
    assert len(manifest["agentSkills"]) == MAX_COWORK_AGENT_SKILLS
    cowork_skill_mds = [
        name for name in names if name.startswith("skills/") and name.endswith("SKILL.md")
    ]
    assert len(cowork_skill_mds) == MAX_COWORK_AGENT_SKILLS
    assert (
        len(list(Path(artifacts.claude_tree_root).glob("*/SKILL.md")))
        == MAX_COWORK_AGENT_SKILLS + 5
    )

    assert artifacts.report_md_path is not None
    report = Path(artifacts.report_md_path).read_text(encoding="utf-8")
    assert "Cowork cap applied" in report


def test_cowork_companion_limits_filter_zip_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import primr.skill_pack.packager as packager

    monkeypatch.setattr(packager, "MAX_COWORK_COMPANION_FILES_PER_SKILL", 2)
    monkeypatch.setattr(packager, "MAX_COWORK_COMPANION_FILE_BYTES", 20)
    monkeypatch.setattr(packager, "MAX_COWORK_COMPANION_TOTAL_BYTES", 35)

    pack = _make_pack()
    pack.roles[0].skills[0].bundled_files = [
        BundledFile(relpath="references/a.md", content="a" * 10),
        BundledFile(relpath="references/b.md", content="b" * 10),
        BundledFile(relpath="references/c.md", content="c" * 10),
        BundledFile(relpath="references/too-large.md", content="x" * 21),
    ]

    artifacts = package_skill_pack(pack, SkillPackConfig(formats=SkillPackFormat.BOTH), tmp_path)

    assert artifacts.cowork_zip_path is not None
    with zipfile.ZipFile(artifacts.cowork_zip_path) as zf:
        names = set(zf.namelist())
    assert "skills/draft-dbt-models/references/a.md" in names
    assert "skills/draft-dbt-models/references/b.md" in names
    assert "skills/draft-dbt-models/references/c.md" not in names
    assert "skills/draft-dbt-models/references/too-large.md" not in names

    assert artifacts.claude_tree_root is not None
    tree_root = Path(artifacts.claude_tree_root) / "draft-dbt-models"
    assert (tree_root / "references/a.md").is_file()
    assert (tree_root / "references/b.md").is_file()
    assert (tree_root / "references/c.md").is_file()
    assert (tree_root / "references/too-large.md").is_file()


def test_manifest_uuid_is_deterministic(tmp_path: Path):
    pack1 = _make_pack(company="Acme Corp")
    pack2 = _make_pack(company="Acme Corp")
    config = SkillPackConfig(formats=SkillPackFormat.COWORK)

    a1 = package_skill_pack(pack1, config, tmp_path / "run1")
    a2 = package_skill_pack(pack2, config, tmp_path / "run2")

    assert a1.manifest_uuid is not None
    assert a1.manifest_uuid == a2.manifest_uuid


def test_manifest_uuid_differs_per_company(tmp_path: Path):
    pack1 = _make_pack(company="Acme Corp")
    pack2 = _make_pack(company="Northwind Haulage")
    config = SkillPackConfig(formats=SkillPackFormat.COWORK)

    a1 = package_skill_pack(pack1, config, tmp_path / "run1")
    a2 = package_skill_pack(pack2, config, tmp_path / "run2")

    assert a1.manifest_uuid != a2.manifest_uuid


def test_skill_slug_collisions_disambiguated(tmp_path: Path):
    # Two roles with the same kebab-case skill name should not collide.
    body = "## What This Skill Does\n\nx\n\n## Workflow\n\n1. y\n\n## Output Format\n\nz"
    s1 = Skill(
        name="search",
        display_name="Search",
        description="Use when the user asks to search.",
        body=body,
    )
    s2 = Skill(
        name="search",
        display_name="Search",
        description="Use when the user asks to search.",
        body=body,
    )
    pack = SkillPack(
        company_name="Acme Corp",
        company_url=None,
        generated_at="2026-05-28T00:00:00+00:00",
        roles=[
            Role(
                name="role-a",
                display_name="Role A",
                confidence="Inferred",
                evidence=RoleEvidence(),
                skills=[s1],
            ),
            Role(
                name="role-b",
                display_name="Role B",
                confidence="Inferred",
                evidence=RoleEvidence(),
                skills=[s2],
            ),
        ],
    )
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.claude_tree_root is not None
    tree = Path(artifacts.claude_tree_root)
    written = sorted(p.name for p in tree.iterdir())
    # The second occurrence is disambiguated by the role slug prefix.
    assert "search" in written
    assert any(name.startswith("role-b--search") for name in written)


def test_report_md_lists_dropped_roles(tmp_path: Path):
    pack = _make_pack()
    pack.dropped_roles.append(("eng-manager", "SEC-INJECT"))
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)
    assert artifacts.report_md_path is not None
    text = Path(artifacts.report_md_path).read_text(encoding="utf-8")
    assert "Dropped Roles" in text
    assert "eng-manager" in text
    assert "by primr" not in text.lower()


def test_report_md_surfaces_posting_incomplete_warning(tmp_path: Path):
    pack = _make_pack()
    pack.plan = RolePlan(
        observed=list(pack.roles),
        final_roster=list(pack.roles),
        industry=IndustryClassification(
            business_model="Retail",
            industry_vertical="Multi-brand retailer",
            company_stage="Enterprise",
            employee_estimate="10,000+",
            confidence="Medium",
            source="llm",
        ),
        evidence_summary={
            "posting_coverage_warns": True,
            "posting_coverage_status": "posting-incomplete",
            "posting_coverage_reason": "9/10 postings cluster in `frontline-operations`.",
            "posting_coverage_recommendation": "Use --from-jd or --roles-add.",
        },
    )
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)

    assert artifacts.report_md_path is not None
    text = Path(artifacts.report_md_path).read_text(encoding="utf-8")
    assert "Posting coverage: **posting-incomplete**" in text
    assert "Use --from-jd or --roles-add" in text


@pytest.mark.parametrize(
    "company,token",
    [
        ("Acme Corp", "Acme_Corp"),
        ("Northwind Haulage, Inc.", "Northwind_Haulage_Inc"),
        ("Foo!Bar", "Foo_Bar"),
    ],
)
def test_company_name_safe_token(tmp_path: Path, company: str, token: str):
    pack = _make_pack(company=company)
    config = SkillPackConfig(formats=SkillPackFormat.CLAUDE)
    artifacts = package_skill_pack(pack, config, tmp_path)
    # The dated output dir uses the safe token form of the company name.
    assert token in Path(artifacts.output_dir).name
