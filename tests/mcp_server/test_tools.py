"""
Tests for tool handlers.

Task 9: Tool handlers
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from primr.mcp_server.server import create_mcp_server


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
        handler = server.server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))

        tools = result.root.tools
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
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "https://example.com", "mode": "full"},
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert "estimated_cost_usd" in data
        assert "estimated_time_minutes" in data
        assert "planned_pages" in data
        assert "budget_enforcement" in data
        assert data["mode"] == "full"

    @pytest.mark.asyncio
    async def test_estimate_run_budget_policy_tracks_execution_profile(self, server, monkeypatch):
        handler = server.server.request_handlers[CallToolRequest]
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        premium_result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "https://example.com", "mode": "premium"},
                ),
            )
        )
        premium_data = json.loads(premium_result.root.content[0].text)
        assert premium_data["budget_enforcement"]["runtime_checkpoints"] is False
        assert "estimate-gated only" in premium_data["budget_enforcement"]["runtime"]

        monkeypatch.setenv("XAI_API_KEY", "x" * 30)
        full_result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "https://example.com", "mode": "full"},
                ),
            )
        )
        full_data = json.loads(full_result.root.content[0].text)
        assert full_data["budget_enforcement"]["runtime_checkpoints"] is True
        assert "strategy generation" in full_data["budget_enforcement"]["checkpointed_stages"]

    @pytest.mark.asyncio
    async def test_estimate_run_invalid_url(self, server):
        """estimate_run returns error for invalid URL."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "not-a-url"},
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "invalid_url"

    @pytest.mark.asyncio
    async def test_estimate_run_ssrf_blocked(self, server):
        """estimate_run blocks SSRF attempts."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "http://169.254.169.254/latest/meta-data/"},
                ),
            )
        )

        content = result.root.content[0]
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
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_strategy",
                    arguments={"strategy_type": "customer_experience"},
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert data["strategy_type"] == "customer_experience"
        assert "estimated_cost_usd" in data
        assert "estimated_time_minutes" in data

    @pytest.mark.asyncio
    async def test_estimate_strategy_requires_vendor_for_ai(self, server):
        """estimate_strategy requires platform for ai_strategy."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_strategy",
                    arguments={"strategy_type": "ai_strategy"},
                ),
            )
        )

        content = result.root.content[0]
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
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert "job_id" in data
        assert data["accepted"] is True
        assert data["status_uri"] == "primr://research/status"

    @pytest.mark.asyncio
    async def test_research_company_job_in_progress(self, server):
        """research_company returns error if job already in progress."""
        handler = server.server.request_handlers[CallToolRequest]

        # Create first job
        await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )

        # Try to create second job
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Other Corp",
                        "company_url": "https://other.com",
                    },
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "job_in_progress"
        assert "active_job_id" in data


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
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                        "mode": "full",
                        "max_estimated_cost_usd": 0.01,
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_generate_strategy_rejects_when_cap_exceeded(self, server):
        report = Path("output/test_cost_cap_report.md")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# report", encoding="utf-8")
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="generate_strategy",
                    arguments={
                        "report_path": str(report),
                        "strategy_type": "customer_experience",
                        "max_estimated_cost_usd": 0.01,
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_research_company_accepts_numeric_string_cap(self, server):
        """A numeric string cap (OpenClaw passes the estimate via quoted
        interpolation) is coerced to float and still enforced — previously this
        raised TypeError in the comparison."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                        "mode": "full",
                        "max_estimated_cost_usd": "0.01",
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_research_company_rejects_non_numeric_cap(self, server):
        """A non-numeric cap returns a structured invalid_cost_cap error rather
        than raising TypeError inside the comparison."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                        "mode": "full",
                        "max_estimated_cost_usd": "not-a-number",
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "invalid_cost_cap"

    @pytest.mark.asyncio
    async def test_research_company_requires_cap_when_enforced(self, server, monkeypatch):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "1")
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_required"

    @pytest.mark.asyncio
    async def test_generate_strategy_requires_cap_when_enforced(self, server, monkeypatch):
        monkeypatch.setenv("PRIMR_ENFORCE_MCP_COST_CAPS", "true")
        report = Path("output/test_required_cap_report.md")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# report", encoding="utf-8")
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="generate_strategy",
                    arguments={
                        "report_path": str(report),
                        "strategy_type": "customer_experience",
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "cost_cap_required"

    @pytest.mark.asyncio
    async def test_research_company_passes_approved_cap_to_runner(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = create_mcp_server(
                journal_path=str(Path(tmpdir) / "test_journal.json"),
                skip_background_tasks=False,
            )
            server.rate_limiter.reset()
            seen = {}
            done = asyncio.Event()

            class FakeRunner:
                def __init__(self, mcp_server):
                    self.mcp_server = mcp_server

                async def run_research(self, **kwargs):
                    seen.update(kwargs)
                    done.set()

            monkeypatch.setattr("primr.mcp_server.pipeline_runner.PipelineRunner", FakeRunner)
            handler = server.server.request_handlers[CallToolRequest]
            result = await handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="research_company",
                        arguments={
                            "company_name": "Acme Corp",
                            "company_url": "https://example.com",
                            "mode": "full",
                            "max_estimated_cost_usd": "100.00",
                        },
                    ),
                )
            )
            data = json.loads(result.root.content[0].text)

            assert data["accepted"] is True
            await asyncio.wait_for(done.wait(), timeout=1)
            assert seen["budget_usd"] == 100.0


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
        handler = server.server.request_handlers[CallToolRequest]

        # Create job
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_id = json.loads(result.root.content[0].text)["job_id"]

        # Cancel job
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="cancel_job",
                    arguments={"job_id": job_id},
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert data["success"] is True
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, server):
        """cancel_job returns error for nonexistent job."""
        handler = server.server.request_handlers[CallToolRequest]

        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="cancel_job",
                    arguments={"job_id": "nonexistent-id"},
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert data["error"] is True
        assert data["error_type"] == "job_not_found"


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
        handler = server.server.request_handlers[CallToolRequest]

        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="doctor",
                    arguments={},
                ),
            )
        )

        content = result.root.content[0]
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
        handler = server.server.request_handlers[CallToolRequest]

        # Exhaust rate limit for research_company (2/min)
        for _ in range(2):
            await handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="research_company",
                        arguments={
                            "company_name": "Test",
                            "company_url": "https://example.com",
                        },
                    ),
                )
            )
            # Cancel to allow next creation
            job = server.job_store.get_active()
            if job:
                job.advance_stage(server.job_store._job.current_stage.CANCELLED)
                server.job_store.update(job)

        # Third call should be rate limited
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Test",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )

        content = result.root.content[0]
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

        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="show_usage",
                    arguments={},
                ),
            )
        )

        content = result.root.content[0]
        data = json.loads(content.text)

        assert "message" in data
        assert "local" in data["message"].lower() or "Local" in data["message"]
        assert "not tracked" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_show_usage_listed_in_tools(self, server):
        """show_usage appears in the tool listing."""
        handler = server.server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))

        tools = result.root.tools
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
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                        "destination": "../../../etc/primr_evil",
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert "destination" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_absolute_outside_root_destination_rejected(self, server):
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Acme Corp",
                        "company_url": "https://example.com",
                        "destination": "/etc/primr_evil",
                    },
                ),
            )
        )
        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert "destination" in data["message"].lower()
