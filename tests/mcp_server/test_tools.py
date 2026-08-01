"""
Tests for tool handlers.

Task 9: Tool handlers
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.server import create_mcp_server
from tests.mcp_server.sdk_compat import call_tool_handler, list_tools_handler


class TestToolListing:
    """Tests for tool listing."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_list_tools(self, server):
        """All tools are listed."""
        result = await list_tools_handler(server)

        tools = result.tools
        tool_names = [t.name for t in tools]

        assert "estimate_run" in tool_names
        assert "estimate_strategy" in tool_names
        assert "research_company" in tool_names
        assert "generate_strategy" in tool_names
        assert "check_jobs" in tool_names
        assert "run_qa" in tool_names
        assert "doctor" in tool_names
        assert "clear_jobs" in tool_names
        assert "cancel_job" in tool_names

        estimate_run = next(tool for tool in tools if tool.name == "estimate_run")
        estimate_platforms = estimate_run.input_schema["properties"]["platforms"]
        assert estimate_platforms["minItems"] == 1
        assert estimate_platforms["maxItems"] == 1
        assert estimate_run.input_schema["properties"]["strategy_type"]["enum"] == ["ai"]

        research_company = next(tool for tool in tools if tool.name == "research_company")
        research_properties = research_company.input_schema["properties"]
        assert "platforms" not in research_properties
        assert "strategy_type" not in research_properties


class TestEstimateRun:
    """Tests for estimate_run tool."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_estimate_run_valid_url(self, server):
        """estimate_run returns estimates for valid URL."""
        result = await call_tool_handler(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "full"},
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert "estimated_cost_usd" in data
        assert "estimated_time_minutes" in data
        assert "planned_pages" in data
        assert "budget_enforcement" in data
        assert data["mode"] == "full"

    @pytest.mark.asyncio
    async def test_estimate_run_budget_policy_tracks_execution_profile(self, server, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        premium_result = await call_tool_handler(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "premium"},
        )
        premium_data = json.loads(premium_result.content[0].text)
        assert premium_data["budget_enforcement"]["runtime_checkpoints"] is True
        assert premium_data["budget_enforcement"]["checkpointed_stages"] == [
            "optional strategy generation"
        ]
        assert (
            "required Deep Research task cannot be stopped"
            in premium_data["budget_enforcement"]["runtime"]
        )

        monkeypatch.setenv("XAI_API_KEY", "x" * 30)
        full_result = await call_tool_handler(
            server,
            "estimate_run",
            {"company_url": "https://example.com", "mode": "full"},
        )
        full_data = json.loads(full_result.content[0].text)
        assert full_data["budget_enforcement"]["runtime_checkpoints"] is True
        assert "strategy generation" in full_data["budget_enforcement"]["checkpointed_stages"]

    @pytest.mark.asyncio
    async def test_estimate_run_invalid_url(self, server):
        """estimate_run returns error for invalid URL."""
        result = await call_tool_handler(
            server,
            "estimate_run",
            {"company_url": "not-a-url"},
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "invalid_url"

    @pytest.mark.asyncio
    async def test_estimate_run_ssrf_blocked(self, server):
        """estimate_run blocks SSRF attempts."""
        result = await call_tool_handler(
            server,
            "estimate_run",
            {"company_url": "http://169.254.169.254/latest/meta-data/"},
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "ssrf_blocked"


class TestEstimateStrategy:
    """Tests for estimate_strategy tool."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_estimate_strategy_valid(self, server):
        """estimate_strategy returns estimates for a valid strategy."""
        result = await call_tool_handler(
            server,
            "estimate_strategy",
            {"strategy_type": "customer_experience"},
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert data["strategy_type"] == "customer_experience"
        assert "estimated_cost_usd" in data
        assert "estimated_time_minutes" in data
        from primr.config.models import DEEP_RESEARCH_COST

        assert data["estimated_cost_usd"] == DEEP_RESEARCH_COST.standard_task_cost
        assert "actual token and tool usage varies" in data["cost_basis"]

    @pytest.mark.asyncio
    async def test_estimate_strategy_requires_vendor_for_ai(self, server):
        """estimate_strategy requires platform for ai_strategy."""
        result = await call_tool_handler(
            server,
            "estimate_strategy",
            {"strategy_type": "ai_strategy"},
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "missing_platform"


class TestResearchCompany:
    """Tests for research_company tool."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_research_company_creates_job(self, server):
        """research_company creates a job and returns job_id."""
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
            },
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert "job_id" in data
        assert data["accepted"] is True
        assert data["status_uri"] == "primr://research/status"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("field", "value", "error_type"),
        [
            ("mode", "turbo", "invalid_mode"),
            ("mode", 1, "invalid_mode"),
            ("platform", "unsupported", "invalid_platform"),
            ("platform", ["aws"], "invalid_platform"),
            ("no_ai_strategy", "false", "invalid_parameter"),
            ("skip_qa", 0, "invalid_parameter"),
            ("verify", None, "invalid_parameter"),
        ],
    )
    async def test_research_company_rejects_malformed_execution_shape_before_job_creation(
        self,
        server,
        field,
        value,
        error_type,
    ):
        from primr.mcp_server.tools import _handle_research_company

        result = await _handle_research_company(
            server,
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
                field: value,
            },
            "stdio",
        )

        data = json.loads(result[0].text)
        assert data["error"] is True
        assert data["error_type"] == error_type
        assert server.job_store.get_active() is None

    @pytest.mark.asyncio
    async def test_research_company_job_in_progress(self, server):
        """research_company returns error if job already in progress."""
        # Create first job
        await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
            },
        )

        # Try to create second job
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Other Corp",
                "company_url": "https://other.com",
            },
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "job_in_progress"
        assert "active_job_id" in data

    @pytest.mark.asyncio
    async def test_cross_tenant_job_in_progress_hides_active_id(self, server, monkeypatch):
        from mcp.server.auth.provider import AccessToken

        from primr.mcp_server.auth import AuthContext

        active = server.job_store.create("Acme Corp", "full", owner_client_id="owner-1")
        server.transport = "streamable-http"
        server._auth_context = AuthContext(
            AccessToken(token="test", client_id="other-1", scopes=["research"])
        )
        monkeypatch.setattr("primr.mcp_server.tools.enforce_approval_token", lambda **_kwargs: None)

        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Other Corp",
                "company_url": "https://example.com",
                "max_estimated_cost_usd": 100.0,
            },
        )

        data = json.loads(result.content[0].text)
        assert data["error_type"] == "job_in_progress"
        assert "active_job_id" not in data
        assert active.job_id not in data["message"]

    @pytest.mark.asyncio
    async def test_owner_job_in_progress_may_see_active_id(self, server, monkeypatch):
        from mcp.server.auth.provider import AccessToken

        from primr.mcp_server.auth import AuthContext

        active = server.job_store.create("Acme Corp", "full", owner_client_id="owner-1")
        server.transport = "streamable-http"
        server._auth_context = AuthContext(
            AccessToken(token="test", client_id="owner-1", scopes=["research"])
        )
        monkeypatch.setattr("primr.mcp_server.tools.enforce_approval_token", lambda **_kwargs: None)

        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Other Corp",
                "company_url": "https://example.com",
                "max_estimated_cost_usd": 100.0,
            },
        )

        data = json.loads(result.content[0].text)
        assert data["active_job_id"] == active.job_id


class TestCostCaps:
    """Tests for MCP cost-cap enforcement."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_research_company_rejects_when_cap_exceeded(self, server):
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
                "mode": "full",
                "max_estimated_cost_usd": 0.01,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_generate_strategy_rejects_when_cap_exceeded(self, server):
        report = Path("output/test_cost_cap_report.md")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# report", encoding="utf-8")
        result = await call_tool_handler(
            server,
            "generate_strategy",
            {
                "report_path": str(report),
                "strategy_type": "customer_experience",
                "max_estimated_cost_usd": 0.01,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_research_company_accepts_numeric_string_cap(self, server):
        """A numeric string cap (OpenClaw passes the estimate via quoted
        interpolation) is coerced to float and still enforced — previously this
        raised TypeError in the comparison."""
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
                "mode": "full",
                "max_estimated_cost_usd": "0.01",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_research_company_rejects_non_numeric_cap(self, server):
        """A non-numeric cap returns a structured invalid_cost_cap error rather
        than raising TypeError inside the comparison."""
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
                "mode": "full",
                "max_estimated_cost_usd": "not-a-number",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "invalid_cost_cap"

    @pytest.mark.asyncio
    async def test_research_company_requires_cap_when_enforced(self, server, monkeypatch):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_required"

    @pytest.mark.asyncio
    async def test_generate_strategy_requires_cap_when_enforced(self, server, monkeypatch):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "true")
        report = Path("output/test_required_cap_report.md")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# report", encoding="utf-8")
        result = await call_tool_handler(
            server,
            "generate_strategy",
            {
                "report_path": str(report),
                "strategy_type": "customer_experience",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_required"

    @pytest.mark.asyncio
    async def test_research_company_passes_approved_cap_to_supervisor(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = create_mcp_server(
                journal_path=str(Path(tmpdir) / "test_journal.json"),
                skip_background_tasks=False,
            )
            server.rate_limiter.reset()
            seen = {}
            done = asyncio.Event()

            async def fake_start(**kwargs):
                seen.update(kwargs)
                done.set()
                return asyncio.create_task(asyncio.sleep(0))

            monkeypatch.setattr(server.job_supervisor, "start", fake_start)
            result = await call_tool_handler(
                server,
                "research_company",
                {
                    "company_name": "Acme Corp",
                    "company_url": "https://example.com",
                    "mode": "full",
                    "max_estimated_cost_usd": "100.00",
                },
            )
            data = json.loads(result.content[0].text)

            assert data["accepted"] is True
            await asyncio.wait_for(done.wait(), timeout=1)
            assert seen["budget_usd"] == 100.0
            assert seen["platform"] == "agnostic"

    @pytest.mark.asyncio
    async def test_research_company_normalizes_single_platform_for_worker(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = create_mcp_server(
                journal_path=str(Path(tmpdir) / "test_journal.json"),
                skip_background_tasks=False,
            )
            server.rate_limiter.reset()
            seen = {}

            async def fake_start(**kwargs):
                seen.update(kwargs)
                return asyncio.create_task(asyncio.sleep(0))

            monkeypatch.setattr(server.job_supervisor, "start", fake_start)
            result = await call_tool_handler(
                server,
                "research_company",
                {
                    "company_name": "Acme Corp",
                    "company_url": "https://example.com",
                    "mode": "premium",
                    "platform": "microsoft",
                    "skip_qa": True,
                    "max_estimated_cost_usd": 100.0,
                },
            )

            data = json.loads(result.content[0].text)
            assert data["accepted"] is True
            assert seen["mode"] == "premium"
            assert seen["platform"] == "azure"
            assert seen["skip_qa"] is True


class TestCancelJob:
    """Tests for cancel_job tool."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, server):
        """cancel_job cancels an active job."""
        # Create job
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
            },
        )
        job_id = json.loads(result.content[0].text)["job_id"]

        # Cancel job
        result = await call_tool_handler(server, "cancel_job", {"job_id": job_id})

        content = result.content[0]
        data = json.loads(content.text)

        assert data["success"] is True
        assert data["status"] == "cancelled"

        repeated = await call_tool_handler(server, "cancel_job", {"job_id": job_id})
        repeated_data = json.loads(repeated.content[0].text)
        assert repeated_data["success"] is True
        assert repeated_data["status"] == "cancelled"
        assert repeated_data["termination_method"] == "already_exited"

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, server):
        """cancel_job returns error for nonexistent job."""
        result = await call_tool_handler(server, "cancel_job", {"job_id": "nonexistent-id"})

        content = result.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "job_not_found"

    @pytest.mark.asyncio
    async def test_admin_can_cancel_another_owners_unstarted_job(self, server):
        """The handler honors AuthContext's documented admin cancellation policy."""
        from mcp.server.auth.provider import AccessToken

        from primr.mcp_server.auth import AuthContext
        from primr.mcp_server.tools import _handle_cancel_job

        job = server.job_store.create("Acme", "full", owner_client_id="owner-1")
        server._auth_context = AuthContext(
            AccessToken(token="test", client_id="admin-1", scopes=["admin", "research"])
        )
        try:
            result = await _handle_cancel_job(server, {"job_id": job.job_id}, "admin-1")
        finally:
            server._auth_context = None

        data = json.loads(result[0].text)
        assert data["status"] == "cancelled"
        assert data["worker_exit_confirmed"] is True
        assert server.job_store.get(job.job_id).current_stage.value == "cancelled"

    @pytest.mark.asyncio
    async def test_non_owner_cancellation_hides_job_existence(self, server):
        """A cross-tenant caller gets the same response as a missing job."""
        from mcp.server.auth.provider import AccessToken

        from primr.mcp_server.auth import AuthContext
        from primr.mcp_server.tools import _handle_cancel_job

        job = server.job_store.create("Acme", "full", owner_client_id="owner-1")
        server._auth_context = AuthContext(
            AccessToken(token="test", client_id="other-1", scopes=["research"])
        )
        try:
            result = await _handle_cancel_job(server, {"job_id": job.job_id}, "other-1")
        finally:
            server._auth_context = None

        data = json.loads(result[0].text)
        assert data["error_type"] == "job_not_found"
        assert server.job_store.get(job.job_id).is_terminal() is False

    @pytest.mark.asyncio
    async def test_http_subject_named_stdio_cannot_cancel_or_enumerate_job(self, server):
        """Defense in depth holds even if an invalid reserved subject reaches dispatch."""
        from mcp.server.auth.provider import AccessToken

        from primr.mcp_server.auth import AuthContext
        from primr.mcp_server.tools import _handle_cancel_job

        server.transport = "streamable-http"
        job = server.job_store.create("Acme", "full", owner_client_id="owner-1")
        server._auth_context = AuthContext(
            AccessToken(token="test", client_id="stdio", scopes=["research"])
        )
        try:
            existing = await _handle_cancel_job(server, {"job_id": job.job_id}, "stdio")
            missing = await _handle_cancel_job(server, {"job_id": "missing-job"}, "stdio")
        finally:
            server._auth_context = None

        existing_data = json.loads(existing[0].text)
        missing_data = json.loads(missing[0].text)
        assert existing_data["error_type"] == missing_data["error_type"] == "job_not_found"
        assert existing_data["error_code"] == missing_data["error_code"]
        assert server.job_store.get(job.job_id).is_terminal() is False


class TestDoctor:
    """Tests for doctor tool."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_doctor_returns_health(self, server):
        """doctor returns system health status."""
        result = await call_tool_handler(server, "doctor", {})

        content = result.content[0]
        data = json.loads(content.text)

        assert "orphaned_stores_count" in data
        assert "config_valid" in data
        assert "api_keys_configured" in data
        assert "warnings" in data


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, server):
        """Rate limit is enforced."""
        # Exhaust rate limit for research_company (2/min)
        for _ in range(2):
            await call_tool_handler(
                server,
                "research_company",
                {
                    "company_name": "Test",
                    "company_url": "https://example.com",
                },
            )
            # Cancel to allow next creation
            job = server.job_store.get_active()
            if job:
                job.advance_stage(server.job_store._job.current_stage.CANCELLED)
                server.job_store.update(job)

        # Third call should be rate limited
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Test",
                "company_url": "https://example.com",
            },
        )

        content = result.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "rate_limit_exceeded"
        assert "retry_after_seconds" in data


class TestShowUsage:
    """Tests for show_usage tool."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_show_usage_local_mode(self, server, monkeypatch):
        """show_usage returns local-mode message when no cloud env vars are set."""
        # Ensure cloud env vars are not set
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("STORAGE_ACCOUNT_NAME", raising=False)

        result = await call_tool_handler(server, "show_usage", {})

        content = result.content[0]
        data = json.loads(content.text)

        assert "message" in data
        assert "local" in data["message"].lower() or "Local" in data["message"]
        assert "not tracked" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_show_usage_listed_in_tools(self, server):
        """show_usage appears in the tool listing."""
        result = await list_tools_handler(server)

        tools = result.tools
        tool_names = [t.name for t in tools]

        assert "show_usage" in tool_names

        # Verify description is agent-friendly
        show_usage_tool = next(t for t in tools if t.name == "show_usage")
        assert "spending" in show_usage_tool.description.lower()
        assert "budget" in show_usage_tool.description.lower()


class TestDestinationValidation:
    """research_company must path-validate the optional destination directory,
    so an authenticated client cannot write report artifacts outside the
    allowed output roots (report_path is validated; destination was not)."""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_traversal_destination_rejected(self, server):
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
                "destination": "../../../etc/primr_evil",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert "destination" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_absolute_outside_root_destination_rejected(self, server):
        result = await call_tool_handler(
            server,
            "research_company",
            {
                "company_name": "Acme Corp",
                "company_url": "https://example.com",
                "destination": "/etc/primr_evil",
            },
        )
        data = json.loads(result.content[0].text)
        assert data["error"] is True
        assert "destination" in data["message"].lower()
