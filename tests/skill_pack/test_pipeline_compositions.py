"""Pipeline composition tests for the new planning + curation surface.

Covers the flag combinations that weren't exercised by the original
end-to-end test:
  - --plan-only short-circuit (plan persisted, no authoring)
  - --from-plan happy path (load saved plan, author against it)
  - --from-plan + --roles-add (composition)
  - --from-plan + --roles-skip (composition)
  - --roles-override + --plan-only graceful handling (no plan to render)
  - hard-failure messages for empty evidence and bad from-plan paths
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from primr.skill_pack.config import SkillPackConfig, SkillPackFormat
from primr.skill_pack.pipeline import run_skill_pack_pipeline
from primr.skill_pack.saved_plan import load_plan

# Reuse the rich mock from test_pipeline.py so authoring + validation
# stay aligned with the canonical fixture.
from tests.skill_pack.test_pipeline import (
    _mock_grok_llm,
    _write_evidence,
)


@pytest.fixture
def working_dir(tmp_path: Path) -> Path:
    wd = tmp_path / "working"
    _write_evidence(wd)
    return wd


# =============================================================================
# --plan-only short-circuit
# =============================================================================


class TestPlanOnlyShortCircuit:
    def test_plan_only_persists_plan_and_skips_authoring(self, tmp_path: Path, working_dir: Path):
        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            formats=SkillPackFormat.BOTH,
            max_refine_iterations=1,
            plan_only=True,
        )

        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_grok_llm):
            pack, artifacts = run_skill_pack_pipeline(
                company_name="Acme Corp",
                company_url="https://acme.example",
                working_dir=working_dir,
                config=config,
                output_dir=tmp_path / "output",
            )

        # Pack is empty (no authoring) but plan is attached.
        assert pack.roles == []
        assert pack.plan is not None
        assert pack.plan.final_roster, "Plan should still have a roster"
        # Plan artifacts persisted to the working dir.
        assert pack.plan.plan_md_path is not None
        assert Path(pack.plan.plan_md_path).exists()
        assert pack.plan.plan_json_path is not None
        assert Path(pack.plan.plan_json_path).exists()
        # No skill pack artifacts (no authoring step).
        assert artifacts.claude_tree_root is None
        assert artifacts.cowork_zip_path is None


# =============================================================================
# --from-plan paths
# =============================================================================


class TestFromPlanPaths:
    def _generate_plan(self, tmp_path: Path, working_dir: Path) -> Path:
        """Run --plan-only first to produce a real role_plan.json on disk."""
        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            plan_only=True,
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_grok_llm):
            pack, _ = run_skill_pack_pipeline(
                company_name="Acme Corp",
                company_url="https://acme.example",
                working_dir=working_dir,
                config=config,
                output_dir=tmp_path / "output",
            )
        assert pack.plan is not None
        assert pack.plan.plan_json_path is not None
        return Path(pack.plan.plan_json_path)

    def test_from_plan_authors_saved_roster(self, tmp_path: Path, working_dir: Path):
        plan_path = self._generate_plan(tmp_path, working_dir)
        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            from_plan_path=str(plan_path),
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_grok_llm):
            pack, artifacts = run_skill_pack_pipeline(
                company_name="Acme Corp",
                company_url="https://acme.example",
                working_dir=working_dir,
                config=config,
                output_dir=tmp_path / "output",
            )
        # Authoring ran against the loaded plan.
        assert len(pack.roles) >= 1
        assert pack.total_skills >= 1
        # The plan was loaded from disk, not re-planned, so plan.plan_md_path
        # is whatever the original write produced.
        assert pack.plan is not None
        assert pack.plan.plan_json_path == str(plan_path)
        assert artifacts.claude_tree_root is not None

    def test_from_plan_with_roles_add_appends_operator_role(
        self, tmp_path: Path, working_dir: Path
    ):
        plan_path = self._generate_plan(tmp_path, working_dir)
        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            from_plan_path=str(plan_path),
            roles_add=["Cybersecurity Lead"],
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_grok_llm):
            pack, _ = run_skill_pack_pipeline(
                company_name="Acme Corp",
                company_url="https://acme.example",
                working_dir=working_dir,
                config=config,
                output_dir=tmp_path / "output",
            )
        role_names = {r.name for r in pack.roles}
        assert "cybersecurity-lead" in role_names
        assert pack.operator_added_role_count == 1

    def test_from_plan_with_roles_skip_drops_named_role(self, tmp_path: Path, working_dir: Path):
        plan_path = self._generate_plan(tmp_path, working_dir)
        # Find a role name from the plan to skip.
        with open(plan_path, encoding="utf-8") as f:
            data = json.load(f)
        target_name = data["final_roster"][0]["name"]

        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            from_plan_path=str(plan_path),
            roles_skip=[target_name],
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_grok_llm):
            pack, _ = run_skill_pack_pipeline(
                company_name="Acme Corp",
                company_url="https://acme.example",
                working_dir=working_dir,
                config=config,
                output_dir=tmp_path / "output",
            )
        role_names = {r.name for r in pack.roles}
        assert target_name not in role_names

    def test_from_plan_empty_roster_raises_runtime_error(self, tmp_path: Path, working_dir: Path):
        # Hand-craft an empty plan JSON.
        empty_plan = tmp_path / "empty_plan.json"
        empty_plan.write_text(
            json.dumps(
                {
                    "observed": [],
                    "plausible": [],
                    "gap_flagged": [],
                    "operator_added": [],
                    "operator_skipped": [],
                    "final_roster": [],
                    "industry": {},
                    "evidence_summary": {},
                }
            ),
            encoding="utf-8",
        )
        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            from_plan_path=str(empty_plan),
        )
        with pytest.raises(RuntimeError, match="empty final_roster"):
            run_skill_pack_pipeline(
                company_name="Acme Corp",
                company_url="https://acme.example",
                working_dir=working_dir,
                config=config,
                output_dir=tmp_path / "output",
            )

    def test_prepared_plan_is_the_single_execution_snapshot(
        self, tmp_path: Path, working_dir: Path
    ):
        plan_path = self._generate_plan(tmp_path, working_dir)
        prepared_plan = load_plan(plan_path)
        plan_path.unlink()
        config = SkillPackConfig(
            roles_count=len(prepared_plan.final_roster),
            skills_per_role=2,
            from_plan_path=str(plan_path),
            plan_only=True,
        )

        pack, _ = run_skill_pack_pipeline(
            company_name="Acme Corp",
            company_url="https://acme.example",
            working_dir=working_dir,
            config=config,
            output_dir=tmp_path / "output",
            prepared_plan=prepared_plan,
        )

        assert pack.plan is prepared_plan
        assert pack.roles == []


# =============================================================================
# --roles-override + --plan-only graceful handling
# =============================================================================


class TestRolesOverridePlanOnly:
    def test_override_with_plan_only_returns_empty_pack_no_plan(
        self, tmp_path: Path, working_dir: Path
    ):
        """Bug 11 regression: when --roles-override is set, planning is
        bypassed; combined with --plan-only there's no plan artifact to
        write. The pipeline must produce a clean (SkillPack, artifacts)
        tuple without crashing."""
        config = SkillPackConfig(
            roles_count=2,
            skills_per_role=2,
            roles_override=["Role A", "Role B"],
            plan_only=True,
        )
        pack, artifacts = run_skill_pack_pipeline(
            company_name="Acme Corp",
            company_url="https://acme.example",
            working_dir=working_dir,
            config=config,
            output_dir=tmp_path / "output",
        )
        assert pack.roles == []
        # No plan because --roles-override skipped planning.
        assert pack.plan is None
        assert artifacts.claude_tree_root is None
