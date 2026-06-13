"""Tests for the --plan checkpoint (tradecraft Step 3).

Deterministic: recon and the tree LLM are mocked, the working folder is
redirected to tmp_path. Verifies the plan renders, writes its artifacts
(hypothesis_tree.{md,json} + plan.md), and exits 0 without a full run.
"""

from __future__ import annotations

from primr.core import cli_plan
from primr.core.cli import CLIConfig, Command, parse_args
from primr.core.cli_plan import run_plan

_TREE_JSON = '{"branches": [{"issue": "Posture", "hypotheses": [{"claim": "PLAN_TREE_TOKEN"}]}]}'


def _config(**overrides):
    return CLIConfig(command=Command.PLAN, **overrides)


def _mock_externals(monkeypatch, tmp_path, *, recon="Azure DNS", tree=_TREE_JSON):
    monkeypatch.setattr(cli_plan, "_safe_recon", lambda _d: recon)
    monkeypatch.setattr(
        "primr.core.research_agent.create_working_folder", lambda *a, **k: str(tmp_path)
    )
    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", lambda *a, **k: tree)


class TestPlanRouting:
    def test_plan_flag_routes_to_plan_command(self):
        config = parse_args(["Acme", "https://acme.example", "--plan"])
        assert config.command == Command.PLAN


class TestRunPlan:
    def test_requires_company_and_website(self):
        assert run_plan(_config(company_name=None, website=None)) == 1

    def test_happy_path_writes_artifacts(self, tmp_path, monkeypatch):
        _mock_externals(monkeypatch, tmp_path)
        config = _config(
            company_name="Acme Corp",
            website="https://acme.example",
            framing_question="near-term cloud budget?",
        )
        rc = run_plan(config)
        assert rc == 0

        tree_md = (tmp_path / "hypothesis_tree.md").read_text(encoding="utf-8")
        assert "PLAN_TREE_TOKEN" in tree_md
        assert (tmp_path / "hypothesis_tree.json").exists()

        plan_md = (tmp_path / "plan.md").read_text(encoding="utf-8")
        assert "Research Plan: Acme Corp" in plan_md
        assert "PLAN_TREE_TOKEN" in plan_md
        assert "Proposed Report Outline" in plan_md  # outline rendered

    def test_framing_block_included_when_specified(self, tmp_path, monkeypatch):
        _mock_externals(monkeypatch, tmp_path)
        config = _config(
            company_name="Acme",
            website="https://acme.example",
            framing_purpose="diligence",
        )
        run_plan(config)
        plan_md = (tmp_path / "plan.md").read_text(encoding="utf-8")
        assert "Framing" in plan_md

    def test_bad_discovery_notes_path_returns_1(self, tmp_path, monkeypatch):
        _mock_externals(monkeypatch, tmp_path)
        config = _config(
            company_name="Acme",
            website="https://acme.example",
            discovery_notes_path=str(tmp_path / "does_not_exist.md"),
        )
        assert run_plan(config) == 1

    def test_recon_failure_does_not_abort(self, tmp_path, monkeypatch):
        # _safe_recon already swallows errors; ensure an empty recon still plans.
        _mock_externals(monkeypatch, tmp_path, recon="")
        config = _config(company_name="Acme", website="https://acme.example")
        assert run_plan(config) == 0
        assert (tmp_path / "plan.md").exists()


class TestProposedOutline:
    def test_outline_loads_section_names(self):
        outline = cli_plan._proposed_outline()
        # The company-overview config defines the report sections; expect a
        # non-trivial ordered list of names.
        assert isinstance(outline, list)
        assert len(outline) > 5
        assert all(isinstance(n, str) and n for n in outline)
