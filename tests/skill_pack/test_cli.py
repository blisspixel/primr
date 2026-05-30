"""Tests for the `primr skills` CLI subcommand argument handling.

Covers the pure / non-network paths only: command sniffing, parser
construction, the dry-run cost estimate, role-label splitting, and the
early-return error / warning branches. The full pipeline path (evidence
collection + authoring) is exercised by the pipeline tests and is not
re-run here.
"""

from __future__ import annotations

import json

import pytest

from primr.skill_pack.cli import (
    _create_parser,
    _estimate,
    _is_skills_command,
    run_skills_cli,
)
from primr.skill_pack.config import (
    DEFAULT_ROLES,
    DEFAULT_SKILLS_PER_ROLE,
    SkillPackConfig,
    SkillPackFormat,
)


class TestIsSkillsCommand:
    def test_true_when_first_arg_is_skills(self):
        assert _is_skills_command(["skills", "Acme", "https://acme.example"])

    def test_false_for_other_subcommand(self):
        assert not _is_skills_command(["recon", "acme.example"])

    def test_false_for_empty(self):
        assert not _is_skills_command([])


class TestParser:
    def test_defaults(self):
        parser = _create_parser()
        ns = parser.parse_args(["Acme", "https://acme.example"])
        assert ns.company_name == "Acme"
        assert ns.company_url == "https://acme.example"
        assert ns.roles == DEFAULT_ROLES
        assert ns.skills_per_role == DEFAULT_SKILLS_PER_ROLE
        assert ns.formats == SkillPackFormat.BOTH.value
        assert ns.dry_run is False

    def test_company_url_optional(self):
        parser = _create_parser()
        ns = parser.parse_args(["Acme"])
        assert ns.company_url is None

    def test_curation_flags_parse(self):
        parser = _create_parser()
        ns = parser.parse_args(
            [
                "Acme",
                "https://acme.example",
                "--roles-add",
                "Account Executive,Procurement Manager",
                "--roles-skip",
                "Marketing Manager",
                "--plan-only",
            ]
        )
        assert ns.roles_add == "Account Executive,Procurement Manager"
        assert ns.roles_skip == "Marketing Manager"
        assert ns.plan_only is True

    def test_invalid_format_rejected(self):
        parser = _create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["Acme", "https://acme.example", "--formats", "bogus"])


class TestEstimate:
    def test_standalone_run_includes_evidence_cost(self):
        config = SkillPackConfig(roles_count=5, skills_per_role=3)
        cost, minutes = _estimate(config, has_from_report=False)
        assert cost > 0
        assert minutes >= 1

    def test_from_report_cheaper_than_standalone(self):
        config = SkillPackConfig(roles_count=5, skills_per_role=3)
        standalone, _ = _estimate(config, has_from_report=False)
        from_report, _ = _estimate(config, has_from_report=True)
        assert from_report < standalone

    def test_more_roles_costs_more(self):
        small, _ = _estimate(SkillPackConfig(roles_count=2), has_from_report=True)
        big, _ = _estimate(SkillPackConfig(roles_count=10), has_from_report=True)
        assert big > small


class TestRunSkillsCliEarlyReturns:
    def test_missing_url_without_from_report_errors(self, capsys):
        rc = run_skills_cli(["skills", "Acme"])
        assert rc == 2
        assert "company_url is required" in capsys.readouterr().err

    def test_dry_run_exits_without_pipeline(self, capsys):
        rc = run_skills_cli(["skills", "Acme", "https://acme.example", "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Skill pack estimate for Acme" in out
        assert "Estimated cost" in out

    def test_override_with_curation_warns_and_clears(self, capsys):
        # --roles-override is mutually exclusive with --roles-add/--roles-skip;
        # the CLI warns and clears the curation flags, so config validation
        # does NOT raise on a clash and the dry-run completes.
        rc = run_skills_cli(
            [
                "skills",
                "Acme",
                "https://acme.example",
                "--roles-override",
                "Account Executive,Cloud Migration Consultant",
                "--roles-add",
                "Account Executive",
                "--dry-run",
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "mutually exclusive" in captured.err
        # roles_count follows the override label count (2), not the default.
        assert "Roles: 2" in captured.out

    def test_from_plan_nonexistent_path_errors(self, capsys):
        rc = run_skills_cli(
            [
                "skills",
                "Acme",
                "https://acme.example",
                "--from-plan",
                "does/not/exist/role_plan.json",
                "--dry-run",
            ]
        )
        assert rc == 2
        assert "--from-plan path does not exist" in capsys.readouterr().err

    def test_invalid_roles_count_errors(self, capsys):
        rc = run_skills_cli(
            ["skills", "Acme", "https://acme.example", "--roles", "999", "--dry-run"]
        )
        assert rc == 2
        assert "roles_count must be" in capsys.readouterr().err

    def test_from_plan_existing_path_passes_validation(self, capsys, tmp_path):
        plan_file = tmp_path / "role_plan.json"
        plan_file.write_text(json.dumps({"final_roster": []}), encoding="utf-8")
        rc = run_skills_cli(
            [
                "skills",
                "Acme",
                "https://acme.example",
                "--from-plan",
                str(plan_file),
                "--dry-run",
            ]
        )
        assert rc == 0
        assert "Skill pack estimate" in capsys.readouterr().out
