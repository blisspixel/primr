"""
Coverage tests for tools.py handlers.

Targets currently-uncovered branches: estimate_strategy validation,
generate_strategy success + path/exists errors, run_qa success/errors,
check_jobs ownership + inline artifacts, wait_for_status_change,
clear_jobs, doctor cloud mode, show_usage cloud, delegate_to_agent,
and platform alias normalization.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams

from primr.mcp_server.platforms import normalize_platforms
from primr.mcp_server.research_policy import parse_max_duration
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.tools import _normalize_platform
from primr.mcp_server.types import ResearchStage


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
        s.rate_limiter.reset()
        yield s


@pytest.fixture
def output_report():
    """Create a report file under the project output/ dir (an allowed path
    root for the PathValidator) and clean it up afterward.

    Yields the bare filename: the PathValidator joins relative inputs onto
    the output root, so passing 'output/foo.md' would double-nest.
    """
    out = Path("output")
    out.mkdir(parents=True, exist_ok=True)
    report = out / "test_tools_cov_report.md"
    report.write_text("# report", encoding="utf-8")
    yield report.name
    report.unlink(missing_ok=True)


async def _call(server, name, arguments):
    handler = server.server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=name, arguments=arguments),
        )
    )
    return json.loads(result.root.content[0].text)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestPlatformHelpers:
    def test_normalize_single_alias(self):
        assert _normalize_platform("microsoft") == "azure"
        assert _normalize_platform("amazon") == "aws"
        assert _normalize_platform("google") == "gcp"
        assert _normalize_platform("nvidia") == "private"

    def test_normalize_unknown_passthrough(self):
        assert _normalize_platform("azure") == "azure"
        assert _normalize_platform("weird") == "weird"

    def test_normalize_list_expands_ms(self):
        result = normalize_platforms(["ms"])
        assert "azure" in result
        assert "private" in result

    def test_normalize_list_dedupes(self):
        result = normalize_platforms(["microsoft", "azure", "aws"])
        assert result.count("azure") == 1
        assert "aws" in result

    def test_parse_max_duration_range(self):
        assert parse_max_duration("5-10 min") == 10

    def test_parse_max_duration_single(self):
        assert parse_max_duration("30 min") == 30

    def test_parse_max_duration_fallback(self):
        assert parse_max_duration("garbage", default=42) == 42


# ---------------------------------------------------------------------------
# estimate_strategy
# ---------------------------------------------------------------------------
class TestEstimateStrategy:
    @pytest.mark.asyncio
    async def test_invalid_strategy_type_direct(self):
        """The handler's invalid_strategy_type branch is unreachable through the
        enum-validated MCP request layer, so exercise the handler directly."""
        from primr.mcp_server.tools import _handle_estimate_strategy

        result = await _handle_estimate_strategy({"strategy_type": "bogus"})
        data = json.loads(result[0].text)
        assert data["error"] is True
        assert data["error_type"] == "invalid_strategy_type"

    @pytest.mark.asyncio
    async def test_ai_with_platform_alias(self, server):
        data = await _call(
            server,
            "estimate_strategy",
            {"strategy_type": "ai_strategy", "platform": "microsoft"},
        )
        assert data["strategy_type"] == "ai_strategy"
        assert data["platform"] == "azure"


# ---------------------------------------------------------------------------
# estimate_run additional branches
# ---------------------------------------------------------------------------
class TestEstimateRun:
    @pytest.mark.asyncio
    async def test_no_ai_strategy_flag(self, server):
        data = await _call(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "full", "no_ai_strategy": True},
        )
        assert data["ai_strategy"] is False

    @pytest.mark.asyncio
    async def test_scrape_mode_no_strategy(self, server):
        data = await _call(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "scrape"},
        )
        assert data["mode"] == "scrape"
        assert data["ai_strategy"] is False

    @pytest.mark.asyncio
    async def test_single_platform_is_normalized_into_estimate(self, server):
        data = await _call(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "full", "platforms": ["microsoft"]},
        )
        assert data["ai_strategy"] is True
        assert data["platforms"] == ["azure"]
        assert data["strategy_type"] == "ai"
        assert data["approval_token"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "arguments,error_type",
        [
            ({"platforms": []}, "unsupported_platform_fanout"),
            ({"platforms": ["azure", "aws"]}, "unsupported_platform_fanout"),
            ({"platforms": ["ms"]}, "unsupported_platform_fanout"),
            ({"platform": "ms"}, "unsupported_platform_fanout"),
            (
                {"platform": "azure", "platforms": ["azure"]},
                "conflicting_platform_parameters",
            ),
            ({"strategy_type": "customer_experience"}, "unsupported_strategy_type"),
        ],
    )
    async def test_unsupported_estimate_shape_fails_before_approval(
        self, server, arguments, error_type
    ):
        from primr.mcp_server.tools import _handle_estimate_run

        data = json.loads(
            (
                await _handle_estimate_run(
                    server,
                    {"company_url": "https://example.com", "mode": "full", **arguments},
                )
            )[0].text
        )

        assert data["error"] is True
        assert data["error_type"] == error_type
        assert "approval_token" not in data


# ---------------------------------------------------------------------------
# generate_strategy
# ---------------------------------------------------------------------------
class TestGenerateStrategy:
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, server, tmp_path):
        # A path outside the allowed roots (output/, logs/) is rejected.
        outside = tmp_path / "nope.md"
        data = await _call(
            server,
            "generate_strategy",
            {"report_path": str(outside), "strategy_type": "customer_experience"},
        )
        assert data["error"] is True
        assert data["error_type"] == "path_traversal_blocked"

    @pytest.mark.asyncio
    async def test_report_not_found(self, server):
        data = await _call(
            server,
            "generate_strategy",
            {"report_path": "output/does_not_exist.md", "strategy_type": "customer_experience"},
        )
        assert data["error"] is True
        assert data["error_type"] == "report_not_found"

    @pytest.mark.asyncio
    async def test_success(self, server, output_report):
        with patch(
            "primr.mcp_server.tools.run_strategy_generation",
            new=AsyncMock(
                return_value={
                    "output_path": "output/strategy.md",
                    "strategy_type": "customer_experience",
                    "qa_score": None,
                }
            ),
        ):
            data = await _call(
                server,
                "generate_strategy",
                {"report_path": str(output_report), "strategy_type": "customer_experience"},
            )
        assert data["success"] is True
        assert data["output_path"].endswith("strategy.md")

    @pytest.mark.asyncio
    async def test_generation_exception(self, server, output_report):
        with patch(
            "primr.mcp_server.tools.run_strategy_generation",
            new=AsyncMock(side_effect=RuntimeError("strategy boom")),
        ):
            data = await _call(
                server,
                "generate_strategy",
                {"report_path": str(output_report), "strategy_type": "customer_experience"},
            )
        assert data["error"] is True
        assert data["error_type"] == "strategy_generation_failed"


# ---------------------------------------------------------------------------
# run_qa
# ---------------------------------------------------------------------------
class TestRunQA:
    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, server, tmp_path):
        data = await _call(server, "run_qa", {"report_path": str(tmp_path / "ghost.md")})
        assert data["error"] is True
        assert data["error_type"] == "path_traversal_blocked"

    @pytest.mark.asyncio
    async def test_report_not_found(self, server):
        data = await _call(server, "run_qa", {"report_path": "output/missing_qa_report.md"})
        assert data["error"] is True
        assert data["error_type"] == "report_not_found"

    @pytest.mark.asyncio
    async def test_success(self, server, output_report):
        with patch(
            "primr.mcp_server.qa_operations.run_qa_analysis",
            new=AsyncMock(return_value={"overall_score": 80}),
        ):
            data = await _call(server, "run_qa", {"report_path": str(output_report)})
        assert data["overall_score"] == 80

    @pytest.mark.asyncio
    async def test_analysis_exception(self, server, output_report):
        with patch(
            "primr.mcp_server.qa_operations.run_qa_analysis",
            new=AsyncMock(side_effect=RuntimeError("qa boom")),
        ):
            data = await _call(server, "run_qa", {"report_path": str(output_report)})
        assert data["error"] is True
        assert data["error_type"] == "qa_analysis_failed"


# ---------------------------------------------------------------------------
# check_jobs
# ---------------------------------------------------------------------------
class TestCheckJobs:
    @pytest.mark.asyncio
    async def test_specific_job_not_found(self, server):
        data = await _call(server, "check_jobs", {"job_id": "missing"})
        assert data["error"] is True
        assert data["error_type"] == "job_not_found"

    @pytest.mark.asyncio
    async def test_no_jobs_empty_list(self, server):
        data = await _call(server, "check_jobs", {})
        assert data["jobs"] == []

    @pytest.mark.asyncio
    async def test_specific_job_with_inline_artifacts(self, server, tmp_path):
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text("# overview body", encoding="utf-8")
        strategy = tmp_path / "Acme_AI_Strategy.md"
        strategy.write_text("# strategy body", encoding="utf-8")

        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        job.output_paths = [str(report), str(strategy)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _call(server, "check_jobs", {"job_id": job.job_id})
        j = data["jobs"][0]
        assert j["status"] == "completed"
        assert j["artifacts_content_included"] is True
        types = {a["type"] for a in j["artifacts"]}
        assert "strategic_overview" in types
        assert "ai_strategy" in types

    @pytest.mark.asyncio
    async def test_authenticated_read_scope_does_not_inline_report_artifacts(
        self, server, tmp_path
    ):
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text("# SECRET REPORT BODY", encoding="utf-8")

        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _call(server, "check_jobs", {"job_id": job.job_id, "include_artifacts": True})
        assert "SECRET REPORT BODY" not in json.dumps(data)
        j = data["jobs"][0]
        assert j["artifacts_content_included"] is False
        assert j["include_artifacts_requested"] is True
        assert j["report_read_required"] is True
        assert j["required_scopes"] == ["report"]
        assert j["report_read_uri"] == f"primr://output/report/by_job/{job.job_id}"

    @pytest.mark.asyncio
    async def test_authenticated_report_scope_must_still_opt_into_artifacts(self, server, tmp_path):
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text("# SECRET REPORT BODY", encoding="utf-8")

        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _call(server, "check_jobs", {"job_id": job.job_id})
        assert "SECRET REPORT BODY" not in json.dumps(data)
        j = data["jobs"][0]
        assert j["artifacts_content_included"] is False
        assert j["include_artifacts_requested"] is False
        assert "artifacts" not in j

    @pytest.mark.asyncio
    async def test_authenticated_report_scope_still_uses_explicit_report_resource(
        self, server, tmp_path
    ):
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text("# SECRET REPORT BODY", encoding="utf-8")

        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _call(server, "check_jobs", {"job_id": job.job_id, "include_artifacts": True})
        j = data["jobs"][0]
        assert "SECRET REPORT BODY" not in json.dumps(data)
        assert j["artifacts_content_included"] is False
        assert j["include_artifacts_requested"] is True
        assert j["report_read_required"] is True
        assert j["report_read_uri"] == f"primr://output/report/by_job/{job.job_id}"
        assert "required_scopes" not in j

    @pytest.mark.asyncio
    async def test_terminal_job_listed_when_no_active(self, server):
        # Single-job model: a completed (terminal) job with no active job is
        # surfaced via get_latest_terminal.
        t = server.job_store.create("Old Corp", "full", owner_client_id="stdio")
        t.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(t)

        data = await _call(server, "check_jobs", {})
        ids = {j["job_id"] for j in data["jobs"]}
        assert t.job_id in ids

    @pytest.mark.asyncio
    async def test_active_job_listed(self, server):
        a = server.job_store.create("New Corp", "full", owner_client_id="stdio")
        data = await _call(server, "check_jobs", {})
        ids = {j["job_id"] for j in data["jobs"]}
        assert a.job_id in ids


# ---------------------------------------------------------------------------
# wait_for_status_change
# ---------------------------------------------------------------------------
class TestWaitForStatusChange:
    @pytest.mark.asyncio
    async def test_job_not_found(self, server):
        data = await _call(
            server, "wait_for_status_change", {"job_id": "missing", "timeout_seconds": 1}
        )
        assert data["error"] is True
        assert data["error_type"] == "job_not_found"

    @pytest.mark.asyncio
    async def test_already_terminal(self, server):
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        data = await _call(
            server,
            "wait_for_status_change",
            {"job_id": job.job_id, "timeout_seconds": 1},
        )
        assert data["changed"] is False
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_change_detected(self, server):
        job = server.job_store.create("Acme Corp", "full", owner_client_id="stdio")

        async def fake_wait(job_id, current_status, timeout_seconds):
            return True, None

        server.job_store.wait_for_status_change = fake_wait
        data = await _call(
            server,
            "wait_for_status_change",
            {"job_id": job.job_id, "timeout_seconds": 1},
        )
        assert data["changed"] is True
        assert "current_stage" in data


# ---------------------------------------------------------------------------
# clear_jobs
# ---------------------------------------------------------------------------
class TestClearJobs:
    @pytest.mark.asyncio
    async def test_nothing_to_clear(self, server):
        data = await _call(server, "clear_jobs", {})
        assert data["success"] is True
        assert data["cleared_count"] == 0

    @pytest.mark.asyncio
    async def test_clears_old_terminal_job(self, server):
        from datetime import datetime, timedelta, timezone

        job = server.job_store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        job.completion_time = datetime.now(timezone.utc) - timedelta(hours=48)
        server.job_store.update(job)

        data = await _call(server, "clear_jobs", {"older_than_hours": 24})
        assert data["success"] is True
        assert data["cleared_count"] == 1


# ---------------------------------------------------------------------------
# doctor (cloud mode)
# ---------------------------------------------------------------------------
class TestDoctorCloud:
    @pytest.mark.asyncio
    async def test_cloud_mode_adds_diagnostics(self, server):
        with (
            patch("primr.mcp_server.cloud_detect.is_cloud_mode", return_value=True),
            patch(
                "primr.mcp_server.tools._get_cloud_diagnostics",
                new=AsyncMock(return_value={"cosmos_db": {"status": "ok"}}),
            ),
        ):
            data = await _call(server, "doctor", {})
        assert data["cloud_mode"] is True
        assert "cloud_diagnostics" in data


# ---------------------------------------------------------------------------
# show_usage (cloud mode)
# ---------------------------------------------------------------------------
class TestShowUsageCloud:
    @pytest.mark.asyncio
    async def test_cloud_usage_fetch_failure(self, server):
        with patch("primr.mcp_server.cloud_detect.is_cloud_mode", return_value=True):
            # No real HTTP server -> the httpx call fails -> usage_fetch_failed
            data = await _call(server, "show_usage", {})
        assert data["error"] is True
        assert data["error_type"] == "usage_fetch_failed"

    @pytest.mark.asyncio
    async def test_cloud_usage_success(self, server):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"daily_cost_usd": 1.23})

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("primr.mcp_server.cloud_detect.is_cloud_mode", return_value=True),
            patch("httpx.AsyncClient", return_value=mock_ctx),
        ):
            data = await _call(server, "show_usage", {})
        assert data["daily_cost_usd"] == 1.23


# ---------------------------------------------------------------------------
# delegate_to_agent
# ---------------------------------------------------------------------------
class TestDelegateToAgent:
    @pytest.mark.asyncio
    async def test_ssrf_blocked(self, server):
        # If a2a not installed this returns missing_dependency; otherwise the
        # internal metadata URL is SSRF-blocked. Accept either failure mode.
        data = await _call(
            server,
            "delegate_to_agent",
            {"agent_url": "http://169.254.169.254/", "message": "hi"},
        )
        assert data["error"] is True
        assert data["error_type"] in {"ssrf_blocked", "missing_dependency"}


# ---------------------------------------------------------------------------
# invalid company name validation in research_company
# ---------------------------------------------------------------------------
class TestResearchCompanyValidation:
    @pytest.mark.asyncio
    async def test_invalid_company_name(self, server):
        data = await _call(
            server,
            "research_company",
            {"company_name": "../../etc/passwd", "company_url": "https://example.com"},
        )
        assert data["error"] is True
        assert data["error_type"] == "invalid_company_name"

    @pytest.mark.asyncio
    async def test_invalid_url(self, server):
        data = await _call(
            server,
            "research_company",
            {"company_name": "Acme Corp", "company_url": "not-a-url"},
        )
        assert data["error"] is True
        assert data["error_type"] == "invalid_url"


# ---------------------------------------------------------------------------
# unknown tool
# ---------------------------------------------------------------------------
class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_is_error(self, server):
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="totally_unknown", arguments={}),
            )
        )
        # SDK wraps the ValueError into an error result
        assert result.root.isError is True
