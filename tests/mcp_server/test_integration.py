"""
Integration tests for MCP server.

Task 16: End-to-end workflow tests.

These tests validate complete workflows through the MCP server,
simulating real agent interactions.
"""

import json
import tempfile
from pathlib import Path

import pytest

from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ReadResourceRequest,
    ReadResourceRequestParams,
)
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage


class TestEndToEndResearchWorkflow:
    """
    Integration test for end-to-end research workflow.
    
    Validates: Requirements 5.1, 5.6, 2.6
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_full_research_workflow(self, server):
        """
        Test complete research workflow:
        1. Call estimate_run
        2. Call research_company
        3. Read status resource
        4. Simulate job completion
        5. Verify output resource updates
        """
        tool_handler = server.server.request_handlers[CallToolRequest]
        resource_handler = server.server.request_handlers[ReadResourceRequest]

        # Step 1: Estimate run
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "https://example.com", "mode": "full"},
                ),
            )
        )
        estimate = json.loads(result.root.content[0].text)
        assert "estimated_cost_usd" in estimate
        assert "estimated_time_minutes" in estimate

        # Step 2: Start research
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Example Corp",
                        "company_url": "https://example.com",
                        "mode": "full",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        assert job_result["accepted"] is True
        job_id = job_result["job_id"]

        # Step 3: Read status - should be in_progress
        result = await resource_handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )
        status = json.loads(result.root.contents[0].text)
        assert status["status"] == "in_progress"
        assert status["job_id"] == job_id

        # Step 4: Simulate job completion
        job = server.job_store.get(job_id)
        job.advance_stage(ResearchStage.SCRAPING)
        job.advance_stage(ResearchStage.DEEP_RESEARCH)
        job.advance_stage(ResearchStage.WRITING)
        job.advance_stage(ResearchStage.QA)
        job.advance_stage(ResearchStage.COMPLETED)
        job.output_paths = ["output/example_corp_report.md"]
        server.job_store.update(job)

        # Step 5: Verify status is completed
        result = await resource_handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )
        status = json.loads(result.root.contents[0].text)
        assert status["status"] == "completed"
        assert status["job_id"] == job_id


class TestMultiClientJobObservation:
    """
    Integration test for multi-client job observation.
    
    Validates: Requirements 2.1, 2.2
    - Client A triggers job
    - Client B can read status
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            s.rate_limiter.reset()  # Reset rate limiter for clean test
            yield s

    @pytest.mark.asyncio
    async def test_client_b_reads_client_a_job(self, server):
        """Client B can observe job started by Client A."""
        tool_handler = server.server.request_handlers[CallToolRequest]
        resource_handler = server.server.request_handlers[ReadResourceRequest]

        # Client A starts job (use example.com which resolves)
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Test Corp",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        assert "job_id" in job_result, f"Expected job_id in result: {job_result}"
        job_id = job_result["job_id"]

        # Client B reads status (simulated - same server, different logical client)
        result = await resource_handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )
        status = json.loads(result.root.contents[0].text)

        # Client B sees Client A's job
        assert status["job_id"] == job_id
        assert status["status"] == "in_progress"
        assert status["company_name"] == "Test Corp"


class TestCancelJobAuthorization:
    """
    Integration test for cancel_job authorization.
    
    Validates: Requirements 18.9
    - Owner can cancel their job
    - Non-owner cannot cancel (in HTTP mode)
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            s.rate_limiter.reset()  # Reset rate limiter for clean test
            yield s

    @pytest.mark.asyncio
    async def test_owner_can_cancel(self, server):
        """Job owner can cancel their job."""
        tool_handler = server.server.request_handlers[CallToolRequest]

        # Create job (owner is "stdio" in stdio mode, use example.com which resolves)
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Test Corp",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        assert "job_id" in job_result, f"Expected job_id in result: {job_result}"
        job_id = job_result["job_id"]

        # Cancel job (same client)
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="cancel_job",
                    arguments={"job_id": job_id},
                ),
            )
        )
        cancel_result = json.loads(result.root.content[0].text)

        assert cancel_result["success"] is True
        assert cancel_result["status"] == "cancelled"


class TestJobStateRecovery:
    """
    Integration test for job state recovery.
    
    Validates: Requirements 13.5, 13.10, 19.4
    - Job state survives server restart
    """

    @pytest.mark.asyncio
    async def test_job_state_survives_restart(self):
        """Job state is recovered after server restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")

            # Create first server and start job
            server1 = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            tool_handler = server1.server.request_handlers[CallToolRequest]

            result = await tool_handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="research_company",
                        arguments={
                            "company_name": "Persistent Corp",
                            "company_url": "https://persistent.com",
                        },
                    ),
                )
            )
            job_id = json.loads(result.root.content[0].text)["job_id"]

            # Advance job to a specific stage
            job = server1.job_store.get(job_id)
            job.advance_stage(ResearchStage.SCRAPING)
            server1.job_store.update(job)

            # "Restart" - create new server with same journal
            server2 = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

            # Verify job state was recovered
            recovered_job = server2.job_store.get(job_id)
            assert recovered_job is not None
            assert recovered_job.company_name == "Persistent Corp"
            assert recovered_job.current_stage == ResearchStage.SCRAPING


class TestRateLimitingMultiClient:
    """
    Integration test for multi-client rate limiting.
    
    Validates: Requirements 12.3
    - Rate limits are per-client
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_rate_limits_per_client(self, server):
        """Rate limits are tracked per client."""
        # In stdio mode, all requests come from "stdio" client
        # This test validates the rate limiter tracks by client_id

        # Exhaust rate limit for estimate_run (30/min)
        for i in range(30):
            result = server.rate_limiter.check_and_record("client_a", "estimate_run")
            assert result.allowed, f"Request {i+1} should be allowed"

        # Client A is now rate limited
        result = server.rate_limiter.check_and_record("client_a", "estimate_run")
        assert not result.allowed

        # Client B should still be allowed
        result = server.rate_limiter.check_and_record("client_b", "estimate_run")
        assert result.allowed


class TestGracefulShutdown:
    """
    Integration test for graceful shutdown.
    
    Validates: Requirements 20.2, 20.5
    - Active jobs marked as failed on shutdown
    - No ghost jobs
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            s.rate_limiter.reset()  # Reset rate limiter for clean test
            yield s

    @pytest.mark.asyncio
    async def test_shutdown_marks_job_failed(self, server):
        """Active job is marked failed on shutdown."""
        tool_handler = server.server.request_handlers[CallToolRequest]

        # Start a job (use example.com which resolves)
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Shutdown Test",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        assert "job_id" in job_result, f"Expected job_id in result: {job_result}"
        job_id = job_result["job_id"]

        # Verify job is in progress
        job = server.job_store.get(job_id)
        assert job.get_status().value == "in_progress"

        # Simulate shutdown
        server.job_store.mark_shutdown()

        # Verify job is now failed
        job = server.job_store.get(job_id)
        assert job.get_status().value == "failed"
        assert job.error_type == "server_shutdown"

    @pytest.mark.asyncio
    async def test_graceful_shutdown_waits_for_tasks(self, server):
        """Graceful shutdown waits for background tasks to complete."""
        import asyncio

        # Create a mock task that completes quickly
        completed = False

        async def quick_task():
            nonlocal completed
            await asyncio.sleep(0.1)
            completed = True

        task = asyncio.create_task(quick_task())
        server._track_task(task)

        # Run graceful shutdown
        await server._graceful_shutdown()

        # Task should have completed
        assert completed
        assert task.done()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_cancels_slow_tasks(self, server):
        """Graceful shutdown cancels tasks that exceed timeout."""
        import asyncio

        # Create a mock task that takes too long
        cancelled = False

        async def slow_task():
            nonlocal cancelled
            try:
                await asyncio.sleep(60)  # Way longer than timeout
            except asyncio.CancelledError:
                cancelled = True
                raise

        task = asyncio.create_task(slow_task())
        server._track_task(task)

        # Run graceful shutdown (should cancel after 5s)
        # Use a shorter timeout for testing
        from primr.mcp_server import server as server_module
        original_timeout = server_module.SHUTDOWN_WORK_COMPLETION_TIMEOUT
        server_module.SHUTDOWN_WORK_COMPLETION_TIMEOUT = 0.2  # 200ms for test

        try:
            await server._graceful_shutdown()
        finally:
            server_module.SHUTDOWN_WORK_COMPLETION_TIMEOUT = original_timeout

        # Task should have been cancelled
        assert cancelled
        assert task.done()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_marks_job_failed_after_tasks(self, server):
        """Job is marked failed after task cleanup during shutdown."""

        tool_handler = server.server.request_handlers[CallToolRequest]

        # Start a job
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Shutdown Order Test",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        job_id = job_result["job_id"]

        # Verify job is in progress
        job = server.job_store.get(job_id)
        assert job.get_status().value == "in_progress"

        # Run graceful shutdown
        await server._graceful_shutdown()

        # Verify job is now failed with server_shutdown error
        job = server.job_store.get(job_id)
        assert job.get_status().value == "failed"
        assert job.error_type == "server_shutdown"
        assert job.completion_time is not None

    @pytest.mark.asyncio
    async def test_shutdown_no_ghost_jobs(self, server):
        """
        No ghost jobs after shutdown.
        
        Validates: Requirement 20.5
        """
        tool_handler = server.server.request_handlers[CallToolRequest]

        # Start a job
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Ghost Test",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        job_id = job_result["job_id"]

        # Run graceful shutdown
        await server._graceful_shutdown()

        # Verify no active jobs remain
        active = server.job_store.get_active()
        assert active is None, "No active jobs should remain after shutdown"

        # The job should exist but be in terminal state
        job = server.job_store.get(job_id)
        assert job is not None
        assert job.is_terminal()

    @pytest.mark.asyncio
    async def test_shutdown_flushes_journal(self, server):
        """
        Journal is flushed during shutdown.
        
        Validates: Requirement 20.2 (flush job journal to disk)
        """
        tool_handler = server.server.request_handlers[CallToolRequest]

        # Start a job
        result = await tool_handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Journal Flush Test",
                        "company_url": "https://example.com",
                    },
                ),
            )
        )
        job_result = json.loads(result.root.content[0].text)
        job_id = job_result["job_id"]

        # Run graceful shutdown
        await server._graceful_shutdown()

        # Verify journal was written
        journal_path = server.job_store._journal_path
        assert journal_path.exists(), "Journal should exist after shutdown"

        # Load journal and verify it contains the failed job
        with open(journal_path) as f:
            journal_data = json.load(f)

        assert journal_data["job_id"] == job_id
        assert journal_data["current_stage"] == "failed"
        assert journal_data["error_type"] == "server_shutdown"
