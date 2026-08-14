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

from primr.config.models import PrimrModels
from primr.skill_pack.cli import (
    _create_parser,
    _estimate,
    _is_skills_command,
    run_skills_cli,
)
from primr.skill_pack.config import (
    DEFAULT_ROLES,
    DEFAULT_SKILLS_PER_ROLE,
    EVAL_CHARGEABLE_ATTEMPT_CAP,
    EVAL_MODEL_RETRIES,
    MAX_AUTO_RESOLVE_PAIRS,
    MAX_EVAL_CASES,
    SkillPackConfig,
    SkillPackFormat,
)


def _write_saved_plan(path, roles_count: int) -> None:
    roles = [
        {
            "name": f"role-{index}",
            "display_name": f"Role {index}",
            "confidence": "Confirmed",
            "summary": f"Role {index} summary",
            "evidence": {"provenance": "posting", "posting_count": 1},
        }
        for index in range(roles_count)
    ]
    path.write_text(
        json.dumps(
            {
                "observed": roles,
                "final_roster": roles,
                "industry": {},
                "evidence_summary": {},
            }
        ),
        encoding="utf-8",
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
        assert ns.remote_icons is False
        assert ns.dry_run is False
        assert ns.budget is None
        assert ns.skip_confirm is False

    def test_remote_icons_flag_parses(self):
        parser = _create_parser()
        ns = parser.parse_args(["Acme", "https://acme.example", "--remote-icons"])
        assert ns.remote_icons is True

    def test_from_jd_flag_parses(self):
        parser = _create_parser()
        ns = parser.parse_args(["Acme", "--from-jd", "role.md"])
        assert ns.company_url is None
        assert ns.from_jd == "role.md"

    def test_repeated_career_url_flags_parse(self):
        parser = _create_parser()
        ns = parser.parse_args(
            [
                "Acme",
                "--career-url",
                "https://jobs.acme.example/corporate",
                "--career-url",
                "https://boards.greenhouse.io/acmeco",
            ]
        )
        assert ns.company_url is None
        assert ns.career_url == [
            "https://jobs.acme.example/corporate",
            "https://boards.greenhouse.io/acmeco",
        ]

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
        cost, minutes = _estimate(config, will_collect_evidence=True)
        assert cost > 0
        assert minutes >= 1

    def test_from_report_cheaper_than_standalone(self):
        config = SkillPackConfig(roles_count=5, skills_per_role=3)
        standalone, _ = _estimate(config, will_collect_evidence=True)
        from_report, _ = _estimate(config, will_collect_evidence=False)
        assert from_report < standalone

    def test_more_roles_costs_more(self):
        small, _ = _estimate(SkillPackConfig(roles_count=2), will_collect_evidence=False)
        big, _ = _estimate(SkillPackConfig(roles_count=10), will_collect_evidence=False)
        assert big > small

    def test_fractional_runtime_is_rounded_up(self):
        _, minutes = _estimate(
            SkillPackConfig(roles_count=3),
            will_collect_evidence=False,
        )
        assert minutes == 2

    def test_remote_icons_add_explicit_allowance(self):
        local, _ = _estimate(SkillPackConfig(), will_collect_evidence=False)
        remote, _ = _estimate(
            SkillPackConfig(remote_icon_generation=True),
            will_collect_evidence=False,
        )
        assert remote > local

    def test_refinement_cost_scales_with_iteration_cap(self):
        low, _ = _estimate(
            SkillPackConfig(max_refine_iterations=1),
            will_collect_evidence=False,
        )
        high, _ = _estimate(
            SkillPackConfig(max_refine_iterations=5),
            will_collect_evidence=False,
        )
        assert high > low

    def test_refinement_estimate_reserves_every_reachable_call(self):
        config = SkillPackConfig(
            roles_count=15,
            skills_per_role=5,
            max_refine_iterations=5,
        )
        cost, _ = _estimate(config, will_collect_evidence=False)
        reachable_refinement_cost = 0.015 * (15 * 5 * 5 + MAX_AUTO_RESOLVE_PAIRS)
        assert cost >= reachable_refinement_cost

    def test_zero_per_skill_refinement_still_prices_auto_resolution(self):
        enabled, _ = _estimate(
            SkillPackConfig(max_refine_iterations=0),
            will_collect_evidence=False,
        )
        disabled, _ = _estimate(
            SkillPackConfig(
                max_refine_iterations=0,
                run_pack_coherence_pass=False,
            ),
            will_collect_evidence=False,
        )
        assert enabled - disabled >= 0.015 * MAX_AUTO_RESOLVE_PAIRS

    def test_behavioral_eval_estimate_matches_reachable_call_count(self):
        base = SkillPackConfig(
            roles_count=1,
            skills_per_role=1,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
        )
        enabled = SkillPackConfig(
            roles_count=1,
            skills_per_role=1,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
            with_evals=True,
            eval_cases_per_skill=3,
        )

        base_cost, _ = _estimate(base, will_collect_evidence=False)
        eval_cost, _ = _estimate(enabled, will_collect_evidence=False)

        max_output_tokens = 4_000 + 3 * (2 * 1_500 + 2 * 4_000)
        output_rate = PrimrModels.get_price(PrimrModels.GROK_MODEL)[1]
        assert eval_cost - base_cost >= (
            max_output_tokens * output_rate / 1_000_000 * EVAL_CHARGEABLE_ATTEMPT_CAP
        )

    def test_behavioral_eval_estimate_uses_execution_case_cap(self):
        base = SkillPackConfig(
            roles_count=1,
            skills_per_role=1,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
        )
        enabled = SkillPackConfig(
            roles_count=1,
            skills_per_role=1,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
            with_evals=True,
            eval_cases_per_skill=10_000,
        )

        base_cost, _ = _estimate(base, will_collect_evidence=False)
        eval_cost, _ = _estimate(enabled, will_collect_evidence=False)

        max_output_tokens = 4_000 + MAX_EVAL_CASES * (2 * 1_500 + 2 * 4_000)
        output_rate = PrimrModels.get_price(PrimrModels.GROK_MODEL)[1]
        assert eval_cost - base_cost >= (
            max_output_tokens * output_rate / 1_000_000 * EVAL_CHARGEABLE_ATTEMPT_CAP
        )

    def test_behavioral_eval_estimate_accounts_for_sequential_runtime(self):
        default = SkillPackConfig(with_evals=True)
        maximum = SkillPackConfig(
            roles_count=15,
            skills_per_role=5,
            with_evals=True,
            eval_cases_per_skill=MAX_EVAL_CASES,
        )

        assert _estimate(default, will_collect_evidence=False)[1] >= 423
        assert _estimate(maximum, will_collect_evidence=False)[1] >= 13_163

    def test_behavioral_eval_maximum_estimate_covers_output_ceiling(self):
        base = SkillPackConfig(
            roles_count=15,
            skills_per_role=5,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
        )
        enabled = SkillPackConfig(
            roles_count=15,
            skills_per_role=5,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
            with_evals=True,
            eval_cases_per_skill=MAX_EVAL_CASES,
        )

        base_cost, _ = _estimate(base, will_collect_evidence=False)
        eval_cost, _ = _estimate(enabled, will_collect_evidence=False)
        output_rate = PrimrModels.get_price(PrimrModels.GROK_MODEL)[1]
        output_ceiling = 75 * (4_000 + MAX_EVAL_CASES * 11_000) * output_rate / 1_000_000

        assert eval_cost - base_cost >= output_ceiling * EVAL_CHARGEABLE_ATTEMPT_CAP

    def test_behavioral_eval_retry_ceiling_matches_execution(self):
        assert EVAL_CHARGEABLE_ATTEMPT_CAP == EVAL_MODEL_RETRIES + 1

    def test_zero_behavioral_eval_cases_add_no_provider_cost(self):
        base = SkillPackConfig(
            roles_count=1,
            skills_per_role=1,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
        )
        enabled = SkillPackConfig(
            roles_count=1,
            skills_per_role=1,
            max_refine_iterations=0,
            run_pack_coherence_pass=False,
            with_evals=True,
            eval_cases_per_skill=0,
        )

        assert (
            _estimate(enabled, will_collect_evidence=False)[0]
            == _estimate(
                base,
                will_collect_evidence=False,
            )[0]
        )

    @pytest.mark.parametrize("n_cases", [-1, MAX_EVAL_CASES + 1, 1.5, True])
    def test_behavioral_eval_case_count_is_validated(self, n_cases: object):
        config = SkillPackConfig(eval_cases_per_skill=n_cases)

        with pytest.raises(ValueError, match="eval_cases_per_skill"):
            config.validate()


class TestRunSkillsCliEarlyReturns:
    def test_missing_url_without_from_report_errors(self, capsys):
        rc = run_skills_cli(["skills", "Acme"])
        assert rc == 2
        assert "company_url is required" in capsys.readouterr().err

    def test_from_jd_allows_no_company_url_for_dry_run(self, capsys, tmp_path):
        jd = tmp_path / "role.md"
        jd.write_text("Licensing Operations Analyst role brief", encoding="utf-8")

        rc = run_skills_cli(["skills", "Acme", "--from-jd", str(jd), "--dry-run"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "Skill pack estimate for Acme" in out

    def test_career_url_allows_no_company_url_for_dry_run(self, capsys):
        rc = run_skills_cli(
            [
                "skills",
                "Acme",
                "--career-url",
                "https://jobs.acme.example/corporate",
                "--dry-run",
            ]
        )

        assert rc == 0
        out = capsys.readouterr().out
        assert "Skill pack estimate for Acme" in out

    def test_invalid_career_url_errors(self, capsys):
        rc = run_skills_cli(["skills", "Acme", "--career-url", "jobs.acme.example"])

        assert rc == 2
        assert "career_urls entries must be absolute HTTP(S) URLs" in capsys.readouterr().err

    def test_from_jd_nonexistent_path_errors(self, capsys, tmp_path):
        missing = tmp_path / "missing.md"
        rc = run_skills_cli(["skills", "Acme", "--from-jd", str(missing), "--dry-run"])

        assert rc == 2
        assert "--from-jd path does not exist" in capsys.readouterr().err

    def test_dry_run_exits_without_pipeline(self, capsys):
        rc = run_skills_cli(["skills", "Acme", "https://acme.example", "--dry-run"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Skill pack estimate for Acme" in out
        assert "Estimated cost" in out

    def test_execution_decline_stops_before_collection(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda *a, **k: "n")
        monkeypatch.setattr(
            "primr.skill_pack.cli.collect_evidence",
            lambda **kwargs: pytest.fail("collection must not start before approval"),
        )

        rc = run_skills_cli(["skills", "Acme", "https://acme.example"])

        assert rc == 0
        assert "Estimated cost" in capsys.readouterr().out

    def test_budget_below_quote_stops_before_collection(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "primr.skill_pack.cli.collect_evidence",
            lambda **kwargs: pytest.fail("collection must not start over budget"),
        )

        rc = run_skills_cli(["skills", "Acme", "https://acme.example", "--budget", "0.01"])

        assert rc == 2
        assert "exceeds --budget" in capsys.readouterr().err

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

    def test_duplicate_overrides_use_deduplicated_count(self, capsys):
        rc = run_skills_cli(
            [
                "skills",
                "Acme",
                "https://acme.example",
                "--roles-override",
                "Account Executive,Account Executive",
                "--dry-run",
            ]
        )

        assert rc == 0
        assert "Roles: 1 x" in capsys.readouterr().out

    def test_automatic_roles_add_does_not_expand_final_count(self, capsys):
        rc = run_skills_cli(
            [
                "skills",
                "Acme",
                "https://acme.example",
                "--roles",
                "5",
                "--roles-add",
                "Account Executive,Procurement Manager",
                "--dry-run",
            ]
        )

        assert rc == 0
        assert "Roles: 5 x" in capsys.readouterr().out

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
        _write_saved_plan(plan_file, 4)
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
        output = capsys.readouterr().out
        assert "Skill pack estimate" in output
        assert "Roles: 4" in output

    def test_from_plan_dry_run_rejects_empty_roster(self, capsys, tmp_path):
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

        assert rc == 2
        assert "empty final_roster" in capsys.readouterr().err
