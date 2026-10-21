"""File-consuming tools must enforce artifact authority before any work."""

import asyncio
import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp.server.auth.provider import AccessToken

from primr.mcp_server.artifact_auth import (
    register_generated_artifacts,
    validate_artifact_destination,
    validate_artifact_input,
)
from primr.mcp_server.auth import AuthContext
from primr.mcp_server.resource_auth import TRUSTED_LOCAL_A2A_AUTH_CONTEXT
from primr.mcp_server.security import PathValidator
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage
from tests.mcp_server.sdk_compat import call_tool_handler


def context(client="owner", scopes=("read", "research", "report")):
    return AuthContext(AccessToken(token="synthetic-token", client_id=client, scopes=list(scopes)))


@pytest.fixture
def artifacts(tmp_path):
    server = create_mcp_server(
        journal_path=str(tmp_path / "journal.json"), skip_background_tasks=True
    )
    root = tmp_path / "output"
    root.mkdir()
    server.path_validator = PathValidator([str(root)])
    job = server.job_store.create("ExampleCo", "full", owner_client_id="owner")
    folder = root / job.job_id
    folder.mkdir()
    report = folder / "ExampleCo_Strategic_Overview.md"
    report.write_text("# ExampleCo\n\nResearch content.", encoding="utf-8")
    job.output_paths = [str(report)]
    job.advance_stage(ResearchStage.COMPLETED)
    server.job_store.update(job)
    server._auth_context = context()
    return server, report


@pytest.mark.parametrize("client", ["foreign", "stdio", "a2a", "anonymous"])
def test_remote_cannot_claim_another_clients_artifact(artifacts, client):
    server, report = artifacts
    server._auth_context = context(client)
    assert not validate_artifact_input(server, str(report)).valid
    assert not validate_artifact_input(server, str(report.parent), directory=True).valid
    assert not validate_artifact_destination(server, str(report.parent)).valid


def test_owned_artifact_still_requires_report_scope(artifacts):
    server, report = artifacts
    server._auth_context = context(scopes=("read", "research"))
    assert not validate_artifact_input(server, str(report)).valid
    server._auth_context = context()
    assert validate_artifact_input(server, str(report)).valid


def test_directory_authority_does_not_include_shared_root_or_unknown_files(artifacts):
    server, report = artifacts
    assert validate_artifact_input(server, str(report.parent), directory=True).valid
    assert not validate_artifact_input(server, str(report.parent.parent), directory=True).valid
    unknown = report.with_name("unregistered.md")
    unknown.write_text("private", encoding="utf-8")
    assert not validate_artifact_input(server, str(unknown)).valid
    assert not validate_artifact_destination(server, str(report.parent.parent)).valid


def test_replaced_job_does_not_authorize_retired_artifacts(artifacts):
    server, report = artifacts
    server.job_store.create("ExampleTwo", "full", owner_client_id="owner")
    assert not validate_artifact_input(server, str(report)).valid


def test_registration_cannot_admit_foreign_files_or_leave_partial_authority(artifacts):
    server, report = artifacts
    generated = report.with_name("generated.md")
    generated.write_text("generated", encoding="utf-8")
    foreign = report.parent.parent / "foreign.md"
    foreign.write_text("foreign", encoding="utf-8")
    with pytest.raises(ValueError, match="safely registered"):
        register_generated_artifacts(server, [generated, foreign])
    assert not validate_artifact_input(server, str(generated)).valid
    assert not validate_artifact_input(server, str(foreign)).valid
    register_generated_artifacts(server, [generated])
    assert validate_artifact_input(server, str(generated)).valid


@pytest.mark.parametrize("auth", [None, TRUSTED_LOCAL_A2A_AUTH_CONTEXT])
def test_trusted_local_reuse_remains_contained(artifacts, tmp_path, auth):
    server, report = artifacts
    server._auth_context = auth
    assert validate_artifact_input(server, str(report)).valid
    outside = tmp_path / "private.md"
    outside.write_text("private", encoding="utf-8")
    assert not validate_artifact_input(server, str(outside)).valid


def test_remote_default_destination_is_server_selected_and_isolated(artifacts):
    server, report = artifacts
    server._auth_context = context("foreign")
    first = validate_artifact_destination(server, None, default=True)
    second = validate_artifact_destination(server, None, default=True)
    assert first.valid
    assert second.valid
    assert first.resolved_path.parent == report.parent.parent
    assert first.resolved_path != second.resolved_path
    assert first.resolved_path != report.parent


def test_source_checkout_report_roots_do_not_follow_launch_directory(tmp_path, monkeypatch):
    from primr.config.config import OUTPUT_DIR, WORKING_DIR

    monkeypatch.chdir(tmp_path)
    server = create_mcp_server(
        journal_path=str(tmp_path / "journal.json"), skip_background_tasks=True
    )
    assert Path(OUTPUT_DIR).resolve() in server.path_validator.allowed_roots
    assert Path(WORKING_DIR).resolve() in server.path_validator.allowed_roots


def test_path_aliases_are_checked_before_resolution(artifacts):
    server, report = artifacts
    alias = report.with_name("alias.md")
    try:
        alias.symlink_to(report)
    except OSError:
        pytest.skip("Host does not permit symbolic link creation")
    assert not server.path_validator.validate(str(alias)).valid


@pytest.mark.parametrize(
    "filename", ["ExampleCo.md", "ExampleCo.DOCX", "ExampleCo_Strategic_Overview_10-20-2026.md"]
)
def test_qa_display_name_removes_supported_file_extensions(filename):
    from primr.qa.report_loader import ReportLoader

    assert ReportLoader()._extract_company_name(filename) == "ExampleCo"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client,scopes,allowed",
    [
        ("foreign", ("research", "report"), False),
        ("owner", ("research",), False),
        ("owner", ("research", "report"), True),
    ],
)
async def test_mcp_qa_checks_authority_before_analysis(artifacts, client, scopes, allowed):
    server, report = artifacts
    server._auth_context = context(client, scopes)
    with patch("primr.mcp_server.qa_operations.run_qa_analysis", new_callable=AsyncMock) as analyze:
        analyze.return_value = {"overall_score": 91}
        result = await call_tool_handler(server, "run_qa", {"report_path": str(report)})
    data = json.loads(result.content[0].text)
    assert analyze.await_count == int(allowed)
    assert data == {"overall_score": 91} if allowed else data["error"] is True


@pytest.mark.asyncio
async def test_strategy_foreign_report_denied_even_with_approved_budget(artifacts):
    server, report = artifacts
    server._auth_context = context("foreign")
    estimate_result = await call_tool_handler(
        server, "estimate_strategy", {"strategy_type": "ai_strategy", "platform": "agnostic"}
    )
    estimate = json.loads(estimate_result.content[0].text)
    with patch(
        "primr.mcp_server.tools.run_strategy_generation", new_callable=AsyncMock
    ) as generate:
        result = await call_tool_handler(
            server,
            "generate_strategy",
            {
                "report_path": str(report),
                "strategy_type": "ai_strategy",
                "platform": "agnostic",
                "max_estimated_cost_usd": estimate["estimated_cost_usd"],
                "approval_token": estimate.get("approval_token"),
            },
        )
    assert json.loads(result.content[0].text)["error_type"] == "artifact_access_denied"
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_generated_strategy_retains_exact_current_job_ownership(artifacts):
    server, report = artifacts
    generated = report.with_name("ExampleCo_Customer_Experience.md")

    async def generate(**kwargs):
        generated.write_text("# Generated strategy", encoding="utf-8")
        return {"output_path": str(generated), "strategy_type": "customer_experience"}

    estimate_result = await call_tool_handler(
        server, "estimate_strategy", {"strategy_type": "customer_experience"}
    )
    estimate = json.loads(estimate_result.content[0].text)
    with patch("primr.mcp_server.tools.run_strategy_generation", side_effect=generate):
        result = await call_tool_handler(
            server,
            "generate_strategy",
            {
                "report_path": str(report),
                "strategy_type": "customer_experience",
                "max_estimated_cost_usd": estimate["estimated_cost_usd"],
                "approval_token": estimate.get("approval_token"),
            },
        )
    assert json.loads(result.content[0].text)["success"] is True
    assert validate_artifact_input(server, str(generated)).valid
    with patch("primr.mcp_server.qa_operations.run_qa_analysis", new_callable=AsyncMock) as qa:
        qa.return_value = {"overall_score": 91}
        result = await call_tool_handler(server, "run_qa", {"report_path": str(generated)})
    assert json.loads(result.content[0].text) == {"overall_score": 91}
    qa.assert_awaited_once()
    server._auth_context = context("foreign")
    assert not validate_artifact_input(server, str(generated)).valid


@pytest.mark.asyncio
async def test_skill_plan_can_be_estimated_and_reused_by_its_current_job_owner(artifacts):
    from primr.mcp_server.skill_pack_tools import handle_skill_pack_tool
    from primr.skill_pack.saved_plan import load_plan
    from primr.skill_pack.schema import SkillPack, SkillPackArtifacts
    from tests.mcp_server.test_skill_pack_tools_more_coverage import _write_saved_plan

    server, report = artifacts
    plan_path = report.parent / "role_plan.json"

    def pipeline(**kwargs):
        _write_saved_plan(plan_path, 1)
        plan = load_plan(plan_path)
        plan.plan_json_path = str(plan_path)
        return (
            SkillPack("ExampleCo", "https://example.com", "2026-10-20", [], plan=plan),
            SkillPackArtifacts(output_dir=str(kwargs["output_dir"])),
        )

    arguments = {
        "company_name": "ExampleCo",
        "report_path": str(report.parent),
        "roles_count": 1,
        "skills_per_role": 1,
        "plan_only": True,
    }
    estimate_result = await handle_skill_pack_tool(
        "estimate_skill_pack", arguments, mcp_server=server
    )
    estimate = json.loads(estimate_result[0].text)
    arguments.update(
        max_estimated_cost_usd=estimate["cost_usd"], approval_token=estimate.get("approval_token")
    )
    with patch("primr.skill_pack.pipeline.run_skill_pack_pipeline", side_effect=pipeline):
        result = await handle_skill_pack_tool("generate_skill_pack", arguments, mcp_server=server)
    assert json.loads(result[0].text).get("error") is not True
    assert validate_artifact_input(server, str(plan_path)).valid
    arguments["from_plan_path"] = str(plan_path)
    estimate_result = await handle_skill_pack_tool(
        "estimate_skill_pack", arguments, mcp_server=server
    )
    estimate = json.loads(estimate_result[0].text)
    assert estimate["roles_count"] == 1
    arguments.update(
        max_estimated_cost_usd=estimate["cost_usd"], approval_token=estimate.get("approval_token")
    )
    with patch("primr.skill_pack.pipeline.run_skill_pack_pipeline", side_effect=pipeline):
        result = await handle_skill_pack_tool("generate_skill_pack", arguments, mcp_server=server)
    assert json.loads(result[0].text).get("error") is not True


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["report_path", "from_jd_path", "from_plan_path", "destination"])
async def test_skill_pack_foreign_input_or_destination_denied_before_work(artifacts, field):
    from primr.mcp_server.skill_pack_tools import handle_skill_pack_tool

    server, report = artifacts
    server._auth_context = context("foreign")
    target = report.parent if field in {"report_path", "destination"} else report
    arguments = {
        "company_name": "ExampleCo",
        "company_url": "https://example.com",
        field: str(target),
    }
    with (
        patch("primr.skill_pack.pipeline.run_skill_pack_pipeline") as generate,
        patch("primr.skill_pack.evidence.collect_evidence") as collect,
    ):
        result = await handle_skill_pack_tool("generate_skill_pack", arguments, mcp_server=server)
    assert json.loads(result[0].text)["error"] is True
    assert field in json.loads(result[0].text)["message"]
    collect.assert_not_called()
    generate.assert_not_called()


@given(
    client=st.sampled_from(["owner", "other", "stdio", "a2a"]),
    report_scope=st.booleans(),
    transport=st.sampled_from(["stdio", "streamable-http"]),
)
@settings(max_examples=32)
def test_authenticated_identity_never_becomes_a_local_operator(client, report_scope, transport):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        server = create_mcp_server(
            journal_path=str(root / "journal.json"), skip_background_tasks=True
        )
        server.transport = transport
        server.path_validator = PathValidator([str(root)])
        job = server.job_store.create("ExampleCo", "full", owner_client_id="owner")
        report = root / job.job_id / "report.md"
        job.output_paths = [str(report)]
        scopes = ("research", "report") if report_scope else ("research",)
        server._auth_context = context(client, scopes)
        assert validate_artifact_input(server, str(report)).valid == (
            client == "owner" and report_scope
        )


@pytest.mark.asyncio
async def test_a2a_explicit_path_cannot_bypass_confinement_or_ownership(artifacts, tmp_path):
    pytest.importorskip("a2a")
    from primr.a2a.executor import PrimrAgentExecutor

    server, report = artifacts
    executor = PrimrAgentExecutor(server, MagicMock())
    outside = tmp_path / "private.txt"
    outside.write_text("private", encoding="utf-8")
    with patch("primr.a2a.executor.run_qa_analysis", new_callable=AsyncMock) as analyze:
        for path in (outside, report):
            server._auth_context = context("foreign")
            result = await executor._handle_qa(json.dumps({"path": str(path)}), AsyncMock())
            assert result["error"] is True
        analyze.assert_not_awaited()
        server._auth_context = context()
        analyze.return_value = {"overall_score": 91}
        assert await executor._handle_qa(json.dumps({"path": str(report)}), AsyncMock()) == {
            "overall_score": 91
        }
        analyze.assert_awaited_once()


@pytest.mark.asyncio
async def test_qa_uses_stable_bytes_and_preserves_identity_without_blocking_loop(artifacts):
    from primr.mcp_server.qa_operations import run_qa_analysis
    from primr.qa.analyzer import QAAnalyzer

    _, report = artifacts
    started, release = threading.Event(), threading.Event()
    seen = []

    def analyze(self, loaded):
        seen.append(loaded)
        started.set()
        assert release.wait(5)
        return self._create_fallback_analysis(loaded)

    with (
        patch.object(QAAnalyzer, "_setup_ai_client"),
        patch.object(QAAnalyzer, "analyze_report", analyze),
    ):
        task = asyncio.create_task(run_qa_analysis(str(report)))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            report.write_text("replaced contents", encoding="utf-8")
            assert seen[0].company_name == "ExampleCo"
            assert "Research content" in seen[0].content
            assert seen[0].file_path == report
        finally:
            release.set()
        result = await task
    assert "completeness" in result["category_scores"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["hardlink", "symlink", "directory", "oversize"])
async def test_qa_rejects_unsafe_file_identity_before_analyzer(artifacts, tmp_path, kind):
    from primr.core.trusted_report import ReportSnapshotError
    from primr.mcp_server.qa_operations import run_qa_analysis

    _, report = artifacts
    private = tmp_path / "private.md"
    private.write_text("private", encoding="utf-8")
    report.unlink()
    if kind in {"hardlink", "symlink"}:
        try:
            os.link(private, report) if kind == "hardlink" else report.symlink_to(private)
        except OSError:
            pytest.skip("Host does not permit this link type")
    elif kind == "directory":
        report.mkdir()
    else:
        with report.open("wb") as handle:
            handle.truncate(8 * 1024 * 1024 + 1)
    with patch("primr.qa.analyzer.QAAnalyzer") as analyze:
        with pytest.raises(ReportSnapshotError):
            await run_qa_analysis(str(report), allowed_roots=[report.parent])
        analyze.assert_not_called()


@pytest.mark.parametrize("kind", ["hardlink", "symlink", "oversize"])
def test_nested_skill_evidence_cannot_redirect_or_expand_file_reads(artifacts, tmp_path, kind):
    from primr.skill_pack.discovery import load_full_evidence

    _, report = artifacts
    private = tmp_path / "private.txt"
    private.write_text("private", encoding="utf-8")
    nested = report.parent / "report.md"
    if kind in {"hardlink", "symlink"}:
        try:
            os.link(private, nested) if kind == "hardlink" else nested.symlink_to(private)
        except OSError:
            pytest.skip("Host does not permit this link type")
    else:
        with nested.open("wb") as handle:
            handle.truncate(2_000_001)
    with pytest.raises(ValueError, match="bounded, regular, non-linked"):
        load_full_evidence(report.parent)
