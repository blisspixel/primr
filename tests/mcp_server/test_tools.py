"""
Tests for tool handlers.

Task 9: Tool handlers
"""

import json
import tempfile
from pathlib import Path

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import MCPErrorCode


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
        assert data["mode"] == "full"
    
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
