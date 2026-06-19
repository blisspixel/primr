"""Coverage tests for mcp_server/skill_pack_tools.py.

Targets the two MCP tool handlers end-to-end without running the real
pipeline: argument parsing/validation, the estimate vs generate paths,
the cost-cap gate, error handling, and the param mapping
(plan_only / from_plan_path / roles_override / roles_add / roles_skip /
allow_recon_only). The skill_pack pipeline (collect_evidence /
run_skill_pack_pipeline) is mocked so no real generation runs.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from primr.mcp_server import skill_pack_tools as spt
from primr.mcp_server.security import PathValidator
from primr.skill_pack.config import (
    DEFAULT_ROLES,
    DEFAULT_SKILLS_PER_ROLE,
    SkillPackConfig,
    SkillPackFormat,
)
from primr.skill_pack.schema import SkillPack, SkillPackArtifacts, ValidationReport

# Strict asyncio mode: coroutine tests are individually decorated with
# @pytest.mark.asyncio below.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mcp_server_for(arguments):
    """A mock MCP server whose path_validator is REAL.

    generate_skill_pack now contains report_path / destination through the
    server's PathValidator (the same containment every other path-taking MCP
    tool uses), so a bare MagicMock would make every path "valid" and defeat
    the test. The validator is scoped to the deliverable roots PLUS any
    report_path / destination argument that lives under the OS temp dir
    (pytest's tmp_path). Passing the EXACT tmp path as an allowed root matters
    on Linux: PathValidator rejects paths under a system dir (e.g. /tmp) unless
    the allowed root itself is under that system dir, in which case the check
    is skipped — so the root must be the tmp_path, not gettempdir(). Absolute
    paths NOT under the temp dir (e.g. /etc) are never auto-allowed, so the
    rejection tests still reject.
    """
    roots: list[str] = ["output", "logs", "working"]
    tmp_base = Path(tempfile.gettempdir()).resolve()
    for key in ("report_path", "destination", "from_jd_path"):
        val = arguments.get(key)
        if not val:
            continue
        try:
            rp = Path(str(val)).resolve()
        except OSError:
            continue
        if rp == tmp_base or tmp_base in rp.parents:
            roots.append(str(rp))
    server = MagicMock()
    server.path_validator = PathValidator(allowed_roots=roots)
    return server


async def _call(name, arguments, mcp_server=None):
    """Invoke the dispatcher and return the parsed JSON of the first block."""
    result = await spt.handle_skill_pack_tool(
        name, arguments, mcp_server=mcp_server or _mcp_server_for(arguments)
    )
    assert result is not None
    return json.loads(result[0].text)


def _make_pack_and_artifacts(report_md: str | None = "# Pack report"):
    pack = SkillPack(
        company_name="Acme Corp",
        company_url="https://acme.example",
        generated_at="2026-06-01T00:00:00Z",
        roles=[],
        validation=ValidationReport(),
        refinement_iterations_used={"role-a/skill-1": 2},
        dropped_roles=[("thin-role", "no evidence")],
    )
    artifacts = SkillPackArtifacts(
        output_dir="output/Acme_Pack",
        claude_tree_root="output/Acme_Pack/roles",
        cowork_zip_path="output/Acme_Pack/Acme_Cowork_Pack.zip",
        report_md_path=None,
    )
    return pack, artifacts, report_md


@pytest.fixture
def patched_pipeline(tmp_path):
    """Patch collect_evidence + run_skill_pack_pipeline at their import sites.

    The handler imports them lazily from primr.skill_pack.{evidence,pipeline},
    so patch there. collect_evidence reports both recon + hiring present so
    the evidence gate passes by default.
    """
    pack, artifacts, report_md = _make_pack_and_artifacts()

    if report_md is not None:
        report_file = tmp_path / "pack_report.md"
        report_file.write_text(report_md, encoding="utf-8")
        artifacts.report_md_path = str(report_file)

    collect = MagicMock(return_value={"recon": True, "hiring": True})
    run = MagicMock(return_value=(pack, artifacts))

    with (
        patch("primr.skill_pack.evidence.collect_evidence", collect),
        patch("primr.skill_pack.pipeline.run_skill_pack_pipeline", run),
    ):
        yield {"collect": collect, "run": run, "pack": pack, "artifacts": artifacts}


# ---------------------------------------------------------------------------
# Tool definitions / dispatcher
# ---------------------------------------------------------------------------


def test_register_returns_both_tools():
    tools = spt.register_skill_pack_tools(MagicMock(), MagicMock())
    names = {t.name for t in tools}
    assert names == {"estimate_skill_pack", "generate_skill_pack"}


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_none():
    assert await spt.handle_skill_pack_tool("not_ours", {}, MagicMock()) is None


# ---------------------------------------------------------------------------
# Cost estimator
# ---------------------------------------------------------------------------


def test_estimate_cost_standalone_more_expensive_than_reuse():
    with_report = spt._estimate_skill_pack_cost(5, 3, has_report_path=True)
    without = spt._estimate_skill_pack_cost(5, 3, has_report_path=False)
    assert without["cost_usd"] > with_report["cost_usd"]
    # standalone has a longer min time floor
    assert without["min_minutes"] > with_report["min_minutes"]
    assert without["max_minutes"] > with_report["max_minutes"]


def test_estimate_cost_scales_with_roles():
    few = spt._estimate_skill_pack_cost(2, 3, has_report_path=True)
    many = spt._estimate_skill_pack_cost(10, 3, has_report_path=True)
    assert many["cost_usd"] > few["cost_usd"]
    assert many["max_minutes"] > few["max_minutes"]


# ---------------------------------------------------------------------------
# estimate_skill_pack handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimate_requires_company_name():
    payload = await _call("estimate_skill_pack", {"company_name": "   "})
    assert payload["error"] is True
    assert "company_name" in payload["message"]


@pytest.mark.asyncio
async def test_estimate_defaults_applied():
    payload = await _call("estimate_skill_pack", {"company_name": "Acme Corp"})
    assert payload["company_name"] == "Acme Corp"
    assert payload["roles_count"] == DEFAULT_ROLES
    assert payload["skills_per_role"] == DEFAULT_SKILLS_PER_ROLE
    assert payload["uses_existing_report"] is False
    assert "cost_usd" in payload
    assert "notes" in payload


@pytest.mark.asyncio
async def test_estimate_with_report_path_flags_reuse():
    payload = await _call(
        "estimate_skill_pack",
        {"company_name": "Acme Corp", "report_path": "working/run-1", "roles_count": 7},
    )
    assert payload["uses_existing_report"] is True
    assert payload["roles_count"] == 7


@pytest.mark.asyncio
async def test_estimate_with_from_jd_path_flags_role_brief(tmp_path):
    jd = tmp_path / "role.md"
    jd.write_text("role brief", encoding="utf-8")

    payload = await _call(
        "estimate_skill_pack",
        {"company_name": "Acme Corp", "from_jd_path": str(jd), "roles_count": 1},
    )

    assert payload["uses_operator_role_brief"] is True
    assert payload["roles_count"] == 1


# ---------------------------------------------------------------------------
# generate_skill_pack: validation / early-exit branches (no pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_requires_company_name():
    payload = await _call("generate_skill_pack", {"company_name": ""})
    assert payload["error"] is True
    assert "company_name" in payload["message"]


@pytest.mark.asyncio
async def test_generate_requires_url_or_report_path():
    payload = await _call("generate_skill_pack", {"company_name": "Acme Corp"})
    assert payload["error"] is True
    assert "company_url" in payload["message"]


@pytest.mark.asyncio
async def test_generate_rejects_nonexistent_from_jd_path(tmp_path):
    missing = tmp_path / "missing.md"
    payload = await _call(
        "generate_skill_pack",
        {"company_name": "Acme Corp", "from_jd_path": str(missing)},
    )

    assert payload["error"] is True
    assert "from_jd_path does not exist" in payload["message"]


@pytest.mark.asyncio
async def test_generate_invalid_config_returns_error():
    # skills_per_role above MAX triggers SkillPackConfig.validate() ValueError.
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "skills_per_role": 99,
        },
    )
    assert payload["error"] is True
    assert "Invalid config" in payload["message"]


@pytest.mark.asyncio
async def test_generate_nonexistent_report_path_returns_error(tmp_path):
    missing = tmp_path / "does-not-exist"
    payload = await _call(
        "generate_skill_pack",
        {"company_name": "Acme Corp", "report_path": str(missing)},
    )
    assert payload["error"] is True
    assert "report_path does not exist" in payload["message"]


# ---------------------------------------------------------------------------
# Cost cap gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_cap_blocks_when_enforced(monkeypatch):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "max_estimated_cost_usd": 0.001,
        },
    )
    assert payload["error"] is True
    assert "exceeds cap" in payload["message"]


@pytest.mark.asyncio
async def test_cost_cap_ignored_when_not_enforced(monkeypatch, patched_pipeline):
    # Cap is tiny but enforcement env is off -> pipeline runs.
    monkeypatch.delenv("PRIMR_ENFORCE_MCP_COST_CAPS", raising=False)
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "max_estimated_cost_usd": 0.001,
        },
    )
    assert payload.get("error") is not True
    assert payload["company_name"] == "Acme Corp"
    patched_pipeline["run"].assert_called_once()


@pytest.mark.asyncio
async def test_cost_cap_passes_when_under_cap(monkeypatch, tmp_path, patched_pipeline):
    # Enforcement on but cap is generous -> gate passes, pipeline runs.
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "max_estimated_cost_usd": 100.0,
        },
    )
    assert payload.get("error") is not True
    assert payload["company_name"] == "Acme Corp"
    patched_pipeline["run"].assert_called_once()


@pytest.mark.parametrize(
    "value",
    ["1", "true", "YES", "On"],
)
def test_cost_cap_enforced_truthy_values(monkeypatch, value):
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", value)
    assert spt._is_cost_cap_enforced() is True


def test_cost_cap_not_enforced_by_default(monkeypatch):
    monkeypatch.delenv("PRIMR_ENFORCE_MCP_COST_CAPS", raising=False)
    assert spt._is_cost_cap_enforced() is False


# ---------------------------------------------------------------------------
# generate_skill_pack: success via report_path (skips evidence collection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_success_with_report_path(tmp_path, patched_pipeline):
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "formats": "claude",
        },
    )
    assert payload["company_name"] == "Acme Corp"
    assert payload["roles_count"] == 0
    assert payload["total_skills"] == 0
    assert payload["dropped_roles"] == [{"name": "thin-role", "reason": "no evidence"}]
    assert payload["refinement_iterations_used"] == {"role-a/skill-1": 2}
    assert payload["pack_report_md"] == "# Pack report"
    assert "sideload_instructions" in payload

    # Evidence collection skipped; working_dir resolves to the report path.
    patched_pipeline["collect"].assert_not_called()
    _, kwargs = patched_pipeline["run"].call_args
    assert kwargs["working_dir"] == Path(str(tmp_path)).resolve()
    cfg = kwargs["config"]
    assert isinstance(cfg, SkillPackConfig)
    assert cfg.reuse_existing_evidence is True
    assert cfg.formats is SkillPackFormat.CLAUDE


@pytest.mark.asyncio
async def test_generate_success_with_url_collects_evidence(patched_pipeline):
    payload = await _call(
        "generate_skill_pack",
        {"company_name": "Acme Corp", "company_url": "https://acme.example"},
    )
    assert payload["company_name"] == "Acme Corp"
    patched_pipeline["collect"].assert_called_once()
    _, kwargs = patched_pipeline["collect"].call_args
    assert kwargs["company_name"] == "Acme Corp"
    assert kwargs["company_url"] == "https://acme.example"
    # fresh temp working dir, evidence reuse off
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.reuse_existing_evidence is False


@pytest.mark.asyncio
async def test_generate_success_with_from_jd_path_only(tmp_path, patched_pipeline):
    jd = tmp_path / "role.md"
    jd.write_text("Licensing Operations Analyst role brief", encoding="utf-8")

    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "from_jd_path": str(jd),
            "roles_override": ["Licensing Operations Analyst"],
        },
    )

    assert payload["company_name"] == "Acme Corp"
    patched_pipeline["collect"].assert_not_called()
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.from_jd_path == str(jd.resolve())
    assert cfg.roles_override == ["Licensing Operations Analyst"]


@pytest.mark.asyncio
async def test_generate_evidence_collection_empty_returns_error():
    collect = MagicMock(return_value={"recon": False, "hiring": False})
    with patch("primr.skill_pack.evidence.collect_evidence", collect):
        payload = await _call(
            "generate_skill_pack",
            {"company_name": "Acme Corp", "company_url": "https://acme.example"},
        )
    assert payload["error"] is True
    assert "Could not collect any evidence" in payload["message"]


@pytest.mark.asyncio
async def test_generate_report_md_unreadable_yields_empty(tmp_path):
    pack, artifacts, _ = _make_pack_and_artifacts()
    # Point report_md_path at a directory so read_text raises OSError.
    artifacts.report_md_path = str(tmp_path)
    run = MagicMock(return_value=(pack, artifacts))
    with patch("primr.skill_pack.pipeline.run_skill_pack_pipeline", run):
        payload = await _call(
            "generate_skill_pack",
            {"company_name": "Acme Corp", "report_path": str(tmp_path)},
        )
    assert payload["pack_report_md"] == ""


@pytest.mark.asyncio
async def test_generate_no_report_md_path_yields_empty(tmp_path):
    pack, artifacts, _ = _make_pack_and_artifacts(report_md=None)
    artifacts.report_md_path = None
    run = MagicMock(return_value=(pack, artifacts))
    with patch("primr.skill_pack.pipeline.run_skill_pack_pipeline", run):
        payload = await _call(
            "generate_skill_pack",
            {"company_name": "Acme Corp", "report_path": str(tmp_path)},
        )
    assert payload["pack_report_md"] == ""


# ---------------------------------------------------------------------------
# Pipeline exception mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "needle"),
    [
        (FileNotFoundError("missing recon"), "Evidence missing"),
        (RuntimeError("authoring blew up"), "Pipeline failed"),
        (ValueError("weird"), "Invalid input"),
    ],
)
@pytest.mark.asyncio
async def test_generate_pipeline_exceptions_mapped(tmp_path, exc, needle):
    run = MagicMock(side_effect=exc)
    with patch("primr.skill_pack.pipeline.run_skill_pack_pipeline", run):
        payload = await _call(
            "generate_skill_pack",
            {"company_name": "Acme Corp", "report_path": str(tmp_path)},
        )
    assert payload["error"] is True
    assert needle in payload["message"]


# ---------------------------------------------------------------------------
# Param mapping: curation flags, plan_only, from_plan_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roles_override_sets_count_and_bypasses(tmp_path, patched_pipeline):
    await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "roles_count": 5,
            "roles_override": ["Account Executive", "Procurement Manager"],
        },
    )
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.roles_override == ["Account Executive", "Procurement Manager"]
    # roles_count is driven by the override length, not the explicit 5.
    assert cfg.roles_count == 2


@pytest.mark.asyncio
async def test_roles_add_and_skip_mapped(tmp_path, patched_pipeline):
    await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "roles_add": ["Cybersecurity Lead"],
            "roles_skip": ["Marketing Manager"],
        },
    )
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.roles_add == ["Cybersecurity Lead"]
    assert cfg.roles_skip == ["Marketing Manager"]


@pytest.mark.asyncio
async def test_unparseable_role_list_coerces_to_empty(tmp_path, patched_pipeline):
    # A non-str / non-list value (e.g. an int) falls through _coerce_list to [].
    await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "roles_add": 42,
        },
    )
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.roles_add == []


@pytest.mark.asyncio
async def test_non_numeric_cost_cap_is_rejected_when_enforced(monkeypatch, tmp_path):
    # Enforcement on + a non-numeric cap must FAIL CLOSED: the gate rejects the
    # bad value up front rather than swallowing the parse error and proceeding
    # with an effectively-absent cap (the previous, vulnerable behavior).
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "max_estimated_cost_usd": "not-a-number",
        },
    )
    assert payload["error"] is True
    assert "must be a number" in payload["message"]


@pytest.mark.asyncio
async def test_missing_cost_cap_is_rejected_when_enforced(monkeypatch, tmp_path):
    # Fail closed: enforcement on but NO cap supplied must be rejected, not run.
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    payload = await _call(
        "generate_skill_pack",
        {"company_name": "Acme Corp", "report_path": str(tmp_path)},
    )
    assert payload["error"] is True
    assert "max_estimated_cost_usd is required" in payload["message"]


@pytest.mark.asyncio
async def test_roles_override_estimate_uses_effective_count(monkeypatch, tmp_path):
    # roles_count=1 but 15 overrides must be estimated (and capped) on the
    # effective roster of 15, not 1 — otherwise a cap sized for one role lets
    # a 15-role run through.
    monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
    one_role = spt._estimate_skill_pack_cost(1, 3, has_report_path=True)["cost_usd"]
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "roles_count": 1,
            "roles_override": [f"Role {i}" for i in range(15)],
            "max_estimated_cost_usd": one_role,  # only covers a single role
        },
    )
    assert payload["error"] is True
    assert "exceeds cap" in payload["message"]


@pytest.mark.asyncio
async def test_path_outside_allowed_roots_is_rejected():
    # An absolute server path outside the allowed roots must be refused.
    payload = await _call(
        "generate_skill_pack",
        {"company_name": "Acme Corp", "report_path": "/etc"},
    )
    assert payload["error"] is True
    assert "report_path rejected" in payload["message"]


@pytest.mark.asyncio
async def test_destination_outside_allowed_roots_is_rejected(tmp_path):
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "destination": "/etc/primr-out",
        },
    )
    assert payload["error"] is True
    assert "destination rejected" in payload["message"]


@pytest.mark.asyncio
async def test_comma_string_role_lists_are_coerced(tmp_path, patched_pipeline):
    # The handler accepts comma-delimited strings as well as lists.
    await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "roles_add": "Cloud Architect, Data Engineer , ",
        },
    )
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.roles_add == ["Cloud Architect", "Data Engineer"]


@pytest.mark.asyncio
async def test_plan_only_and_from_plan_path_mapped(tmp_path, patched_pipeline):
    plan_json = tmp_path / "role_plan.json"
    plan_json.write_text("{}", encoding="utf-8")
    await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "plan_only": True,
            "from_plan_path": str(plan_json),
            "allow_recon_only": True,
            "emit_agent_metadata": True,
        },
    )
    cfg = patched_pipeline["run"].call_args.kwargs["config"]
    assert cfg.plan_only is True
    assert cfg.from_plan_path == str(plan_json)
    assert cfg.allow_recon_only is True
    assert cfg.emit_agent_metadata is True


@pytest.mark.asyncio
async def test_clashing_curation_flags_rejected(tmp_path):
    # roles_add and roles_skip sharing an entry is rejected by config.validate().
    payload = await _call(
        "generate_skill_pack",
        {
            "company_name": "Acme Corp",
            "report_path": str(tmp_path),
            "roles_add": ["Sales Lead"],
            "roles_skip": ["Sales Lead"],
        },
    )
    assert payload["error"] is True
    assert "Invalid config" in payload["message"]
