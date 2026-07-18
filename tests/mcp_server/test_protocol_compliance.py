"""
Protocol compliance tests.

Task 13: Property tests for protocol list responses and error codes.

These tests validate that the MCP server follows protocol requirements:
- Property 13: Protocol List Response Completeness
- Property 14: Protocol Error Codes
"""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    GetPromptRequest,
    GetPromptRequestParams,
    ListPromptsRequest,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import MCPErrorCode


class TestProtocolListResponseCompleteness:
    """
    Property 13: Protocol List Response Completeness

    Validates: Requirements 16.3, 16.4, 16.5
    - All list responses have required fields
    - Tool schemas are valid JSON Schema
    - Resource URIs are valid
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_list_tools_response_complete(self, server):
        """All tools have required fields: name, description, inputSchema."""
        handler = server.server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))

        tools = result.root.tools
        assert len(tools) > 0, "Server should have at least one tool"

        for tool in tools:
            # Required fields per MCP spec
            assert tool.name, "Tool missing name"
            assert tool.description, f"Tool {tool.name} missing description"
            assert tool.inputSchema, f"Tool {tool.name} missing inputSchema"

            # inputSchema must be valid JSON Schema object
            schema = tool.inputSchema
            assert isinstance(schema, dict), f"Tool {tool.name} inputSchema must be dict"
            assert "type" in schema, f"Tool {tool.name} inputSchema missing 'type'"
            assert schema["type"] == "object", f"Tool {tool.name} inputSchema type must be 'object'"

    @pytest.mark.asyncio
    async def test_list_tools_schemas_have_properties(self, server):
        """Tool schemas define their parameters in 'properties'."""
        handler = server.server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))

        for tool in result.root.tools:
            schema = tool.inputSchema
            # All tools should have properties (even if empty)
            assert "properties" in schema, f"Tool {tool.name} missing 'properties'"
            assert isinstance(schema["properties"], dict)

            # Required should be a list
            if "required" in schema:
                assert isinstance(schema["required"], list)

    @pytest.mark.asyncio
    async def test_list_resources_response_complete(self, server):
        """All resources have required fields: uri, name."""
        handler = server.server.request_handlers[ListResourcesRequest]
        result = await handler(ListResourcesRequest(method="resources/list"))

        resources = result.root.resources
        assert len(resources) > 0, "Server should have at least one resource"

        for resource in resources:
            # Required fields per MCP spec
            assert resource.uri, "Resource missing uri"
            assert resource.name, f"Resource {resource.uri} missing name"

            # URI should be valid primr:// URI
            uri_str = str(resource.uri)
            assert uri_str.startswith("primr://"), "Resource URI should start with primr://"

    @pytest.mark.asyncio
    async def test_list_resources_have_mime_types(self, server):
        """Resources should specify mimeType."""
        handler = server.server.request_handlers[ListResourcesRequest]
        result = await handler(ListResourcesRequest(method="resources/list"))

        for resource in result.root.resources:
            # mimeType is optional but recommended
            if resource.mimeType:
                assert "/" in resource.mimeType, f"Invalid mimeType: {resource.mimeType}"

    @pytest.mark.asyncio
    async def test_list_prompts_response_complete(self, server):
        """All prompts have required fields: name, description."""
        handler = server.server.request_handlers[ListPromptsRequest]
        result = await handler(ListPromptsRequest(method="prompts/list"))

        prompts = result.root.prompts
        assert len(prompts) > 0, "Server should have at least one prompt"

        for prompt in prompts:
            # Required fields per MCP spec
            assert prompt.name, "Prompt missing name"
            # description is optional but we require it for usability
            assert prompt.description, f"Prompt {prompt.name} missing description"

    @pytest.mark.asyncio
    async def test_list_prompts_arguments_valid(self, server):
        """Prompt arguments have required fields."""
        handler = server.server.request_handlers[ListPromptsRequest]
        result = await handler(ListPromptsRequest(method="prompts/list"))

        for prompt in result.root.prompts:
            if prompt.arguments:
                for arg in prompt.arguments:
                    assert arg.name, f"Prompt {prompt.name} has argument without name"
                    # description is optional but recommended

    @pytest.mark.asyncio
    async def test_governed_execution_prompt_listed(self, server):
        """Governed execution prompt is exposed to MCP clients."""
        handler = server.server.request_handlers[ListPromptsRequest]
        result = await handler(ListPromptsRequest(method="prompts/list"))
        names = [prompt.name for prompt in result.root.prompts]
        assert "governed_execution" in names

    @pytest.mark.asyncio
    async def test_governed_execution_prompt_get(self, server):
        """Governed execution prompt content is retrievable."""
        handler = server.server.request_handlers[GetPromptRequest]
        result = await handler(
            GetPromptRequest(
                method="prompts/get",
                params=GetPromptRequestParams(name="governed_execution", arguments={}),
            )
        )
        messages = result.root.messages
        assert len(messages) > 0
        assert "max_estimated_cost_usd" in messages[0].content.text


class TestProtocolErrorCodes:
    """
    Property 14: Protocol Error Codes

    Validates: Requirements 16.9, 16.10
    - Error responses use correct error codes
    - Error messages are informative
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_invalid_url_error_code(self, server):
        """Invalid URL returns correct error code."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "not-a-valid-url"},
                ),
            )
        )

        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "invalid_url"
        assert data["error_code"] == MCPErrorCode.INVALID_URL
        assert "message" in data

    @pytest.mark.asyncio
    async def test_ssrf_blocked_error_code(self, server):
        """SSRF attempt returns correct error code."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "http://169.254.169.254/"},
                ),
            )
        )

        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "ssrf_blocked"
        assert data["error_code"] == MCPErrorCode.SSRF_BLOCKED

    @pytest.mark.asyncio
    async def test_job_not_found_error_code(self, server):
        """Job not found returns correct error code."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="cancel_job",
                    arguments={"job_id": "nonexistent-job-id"},
                ),
            )
        )

        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "job_not_found"
        assert data["error_code"] == MCPErrorCode.JOB_NOT_FOUND

    @pytest.mark.asyncio
    async def test_job_in_progress_error_code(self, server):
        """Job in progress returns correct error code."""
        handler = server.server.request_handlers[CallToolRequest]

        # Create first job
        await handler(
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

        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "job_in_progress"
        assert data["error_code"] == MCPErrorCode.JOB_IN_PROGRESS
        assert "active_job_id" in data

    @pytest.mark.asyncio
    async def test_rate_limit_error_code(self, server):
        """Rate limit exceeded returns correct error code."""
        handler = server.server.request_handlers[CallToolRequest]

        # Exhaust rate limit for research_company (2/min)
        for _ in range(2):
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
            # Cancel to allow next creation
            job = server.job_store.get_active()
            if job:
                from primr.mcp_server.types import ResearchStage

                job.advance_stage(ResearchStage.CANCELLED)
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

        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert data["error_type"] == "rate_limit_exceeded"
        assert data["error_code"] == MCPErrorCode.RATE_LIMIT_EXCEEDED
        assert "retry_after_seconds" in data
        assert data["retry_after_seconds"] > 0

    @pytest.mark.asyncio
    async def test_unknown_resource_raises_exception(self, server):
        """Unknown resource raises ValueError."""
        handler = server.server.request_handlers[ReadResourceRequest]

        with pytest.raises(ValueError, match="Unknown resource"):
            await handler(
                ReadResourceRequest(
                    method="resources/read",
                    params=ReadResourceRequestParams(uri="primr://unknown/resource"),
                )
            )

    @pytest.mark.asyncio
    async def test_unknown_prompt_raises_exception(self, server):
        """Unknown prompt raises ValueError."""
        handler = server.server.request_handlers[GetPromptRequest]

        with pytest.raises(ValueError, match="Unknown prompt"):
            await handler(
                GetPromptRequest(
                    method="prompts/get",
                    params=GetPromptRequestParams(name="unknown_prompt"),
                )
            )


class TestToolParameterValidation:
    """
    Property 8: Tool Parameter Validation

    Validates: Requirements 5.2, 5.3, 5.4, 5.5, 6.2, 6.3, 6.4, 7.2, 7.3, 8.2
    - Tools validate their parameters correctly
    - Invalid parameters return appropriate errors
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @given(st.text(min_size=1, max_size=100).filter(lambda x: not x.startswith("http")))
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_estimate_run_rejects_invalid_urls(self, invalid_url):
        """estimate_run rejects non-URL strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            server = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

            handler = server.server.request_handlers[CallToolRequest]
            result = await handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="estimate_run",
                        arguments={"company_url": invalid_url},
                    ),
                )
            )

            data = json.loads(result.root.content[0].text)
            assert data["error"] is True
            assert data["error_type"] in ["invalid_url", "ssrf_blocked"]

    @pytest.mark.asyncio
    async def test_research_company_validates_mode(self, server):
        """research_company accepts valid modes."""
        handler = server.server.request_handlers[CallToolRequest]

        for mode in ["scrape", "deep", "full"]:
            # Reset rate limiter and job store for each test
            server.rate_limiter.reset()
            server.job_store.clear()

            result = await handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="research_company",
                        arguments={
                            "company_name": "Test Corp",
                            "company_url": "https://example.com",
                            "mode": mode,
                        },
                    ),
                )
            )

            data = json.loads(result.root.content[0].text)
            # Should succeed (not an error about mode)
            assert data.get("accepted") is True or data.get("error_type") != "invalid_mode"


class TestToolResultStructure:
    """
    Property 9: Tool Result Structure

    Validates: Requirements 5.6, 6.5, 7.4, 7.5, 7.6, 8.3, 8.6, 18.2, 18.5
    - Tool results have correct structure
    - Success results have expected fields
    - Error results have error_type and message
    """

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path, skip_background_tasks=True)

    @pytest.mark.asyncio
    async def test_estimate_run_result_structure(self, server):
        """estimate_run returns expected fields."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "https://example.com"},
                ),
            )
        )

        data = json.loads(result.root.content[0].text)

        # Success result structure
        assert "estimated_cost_usd" in data
        assert "estimated_time_minutes" in data
        assert "planned_pages" in data
        assert "mode" in data

        # Types
        assert isinstance(data["estimated_cost_usd"], (int, float))
        assert isinstance(data["estimated_time_minutes"], (int, float))
        assert isinstance(data["planned_pages"], int)

    @pytest.mark.asyncio
    async def test_estimate_strategy_result_structure(self, server):
        """estimate_strategy returns expected fields."""
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

        data = json.loads(result.root.content[0].text)

        assert "strategy_type" in data
        assert "estimated_cost_usd" in data
        assert "estimated_time_minutes" in data
        assert "cost_warning" in data

    @pytest.mark.asyncio
    async def test_cost_cap_errors_are_structured(self, server):
        """Cost-cap rejections return structured MCP-compatible errors."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="research_company",
                    arguments={
                        "company_name": "Test Corp",
                        "company_url": "https://example.com",
                        "max_estimated_cost_usd": 0.01,
                    },
                ),
            )
        )

        data = json.loads(result.root.content[0].text)
        assert data["error"] is True
        assert "error_code" in data
        assert data["error_type"] == "cost_cap_exceeded"

    @pytest.mark.asyncio
    async def test_research_company_result_structure(self, server):
        """research_company returns JobAcceptedResult structure."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
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

        data = json.loads(result.root.content[0].text)

        # JobAcceptedResult structure
        assert "job_id" in data
        assert "accepted" in data
        assert "status_uri" in data

        assert data["accepted"] is True
        assert data["status_uri"] == "primr://research/status"
        assert len(data["job_id"]) > 0

    @pytest.mark.asyncio
    async def test_doctor_result_structure(self, server):
        """doctor returns DoctorResult structure."""
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

        data = json.loads(result.root.content[0].text)

        # DoctorResult structure
        assert "orphaned_stores_count" in data
        assert "config_valid" in data
        assert "api_keys_configured" in data
        assert "warnings" in data
        assert data["status"] in {"healthy", "degraded", "unhealthy"}
        assert isinstance(data["checks"], list)
        assert any(check["component"] == "audit_log" for check in data["checks"])

        # Types
        assert isinstance(data["orphaned_stores_count"], int)
        assert isinstance(data["config_valid"], bool)
        assert isinstance(data["api_keys_configured"], bool)
        assert isinstance(data["warnings"], list)

    @pytest.mark.asyncio
    async def test_check_jobs_result_structure(self, server):
        """check_jobs returns jobs list structure."""
        handler = server.server.request_handlers[CallToolRequest]

        # Create a job first
        await handler(
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

        # Check jobs
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="check_jobs",
                    arguments={},
                ),
            )
        )

        data = json.loads(result.root.content[0].text)

        assert "jobs" in data
        assert isinstance(data["jobs"], list)
        assert len(data["jobs"]) > 0

        job = data["jobs"][0]
        assert "job_id" in job
        assert "status" in job
        assert "company_name" in job

    @pytest.mark.asyncio
    async def test_error_result_structure(self, server):
        """Error results have consistent structure."""
        handler = server.server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(
                    name="estimate_run",
                    arguments={"company_url": "invalid"},
                ),
            )
        )

        data = json.loads(result.root.content[0].text)

        # Error result structure
        assert data["error"] is True
        assert "error_type" in data
        assert "error_code" in data
        assert "message" in data

        # error_code should be an integer
        assert isinstance(data["error_code"], int)
