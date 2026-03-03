"""
Protocol Spike Tests - Validate MCP SDK assumptions.

Task 0: Protocol spike validation
- 0.1: SDK installation, basic server creation
- 0.2: JSON-RPC framing, tool/resource listing
- 0.5: Resource subscription negotiation
- 0.6: Stdout purity in stdio mode
"""

import json
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)
from primr.mcp_server.spike import create_spike_server


class TestSpikeServerCreation:
    """Task 0.1: Validate SDK installation and basic server creation."""

    def test_server_creation(self):
        """Server can be created without errors."""
        server = create_spike_server()
        assert server is not None
        assert server.name == "primr-spike"

    def test_server_has_handlers(self):
        """Server has tool and resource handlers registered."""
        server = create_spike_server()
        # Check that handlers are registered
        assert ListToolsRequest in server.request_handlers
        assert ListResourcesRequest in server.request_handlers
        assert CallToolRequest in server.request_handlers
        assert ReadResourceRequest in server.request_handlers


class TestToolListing:
    """Task 0.2: Validate tool listing works correctly."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_ping(self):
        """list_tools returns the ping tool with correct schema."""
        server = create_spike_server()

        # Get the handler and call it
        handler = server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))

        # Result is wrapped in ServerResult, access .root
        tools = result.root.tools
        assert len(tools) == 1
        assert tools[0].name == "ping"
        assert tools[0].description == "Simple ping tool that returns pong with timestamp"
        assert "properties" in tools[0].inputSchema
        assert "message" in tools[0].inputSchema["properties"]

    @pytest.mark.asyncio
    async def test_call_ping_tool(self):
        """Calling ping tool returns pong with timestamp."""
        server = create_spike_server()

        handler = server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="ping", arguments={}),
            )
        )

        # Result is wrapped in ServerResult, access .root
        content = result.root.content
        assert len(content) == 1
        assert content[0].type == "text"
        assert "pong @" in content[0].text

    @pytest.mark.asyncio
    async def test_call_ping_tool_with_message(self):
        """Calling ping tool with message echoes it back."""
        server = create_spike_server()

        handler = server.request_handlers[CallToolRequest]
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="ping", arguments={"message": "hello"}),
            )
        )

        content = result.root.content
        assert len(content) == 1
        assert "echo: hello" in content[0].text

    @pytest.mark.asyncio
    async def test_call_unknown_tool_returns_error(self):
        """Calling unknown tool returns error result (SDK behavior)."""
        server = create_spike_server()

        handler = server.request_handlers[CallToolRequest]
        # SDK doesn't raise for unknown tools, it logs a warning
        # and returns an error result
        result = await handler(
            CallToolRequest(
                method="tools/call",
                params=CallToolRequestParams(name="unknown", arguments={}),
            )
        )

        # The result should indicate an error
        assert result.root.isError is True


class TestResourceListing:
    """Task 0.2: Validate resource listing works correctly."""

    @pytest.mark.asyncio
    async def test_list_resources_returns_test(self):
        """list_resources returns the test resource."""
        server = create_spike_server()

        handler = server.request_handlers[ListResourcesRequest]
        result = await handler(ListResourcesRequest(method="resources/list"))

        resources = result.root.resources
        assert len(resources) == 1
        assert str(resources[0].uri) == "primr://test"
        assert resources[0].name == "Test Resource"
        assert resources[0].mimeType == "text/plain"

    @pytest.mark.asyncio
    async def test_read_test_resource(self):
        """Reading test resource returns content with timestamp."""
        server = create_spike_server()

        handler = server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://test"),
            )
        )

        contents = result.root.contents
        assert len(contents) == 1
        assert "Test resource content @" in contents[0].text

    @pytest.mark.asyncio
    async def test_read_unknown_resource_raises(self):
        """Reading unknown resource raises ValueError."""
        server = create_spike_server()

        handler = server.request_handlers[ReadResourceRequest]
        with pytest.raises(ValueError, match="Unknown resource"):
            await handler(
                ReadResourceRequest(
                    method="resources/read",
                    params=ReadResourceRequestParams(uri="primr://unknown"),
                )
            )


class TestStdoutPurity:
    """Task 0.6: Validate stdout purity in stdio mode."""

    def test_server_creation_no_stdout(self):
        """Server creation does not write to stdout."""
        captured_stdout = StringIO()

        with patch.object(sys, 'stdout', captured_stdout):
            server = create_spike_server()
            assert server is not None

        # Nothing should be written to stdout during server creation
        assert captured_stdout.getvalue() == ""

    @pytest.mark.asyncio
    async def test_tool_call_no_stdout(self):
        """Tool calls do not write to stdout."""
        server = create_spike_server()
        captured_stdout = StringIO()

        handler = server.request_handlers[CallToolRequest]
        with patch.object(sys, 'stdout', captured_stdout):
            await handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(name="ping", arguments={"message": "test"}),
                )
            )

        # Nothing should be written to stdout during tool execution
        assert captured_stdout.getvalue() == ""

    @pytest.mark.asyncio
    async def test_resource_read_no_stdout(self):
        """Resource reads do not write to stdout."""
        server = create_spike_server()
        captured_stdout = StringIO()

        handler = server.request_handlers[ReadResourceRequest]
        with patch.object(sys, 'stdout', captured_stdout):
            await handler(
                ReadResourceRequest(
                    method="resources/read",
                    params=ReadResourceRequestParams(uri="primr://test"),
                )
            )

        # Nothing should be written to stdout during resource read
        assert captured_stdout.getvalue() == ""


class TestJSONRPCMessageValidity:
    """Property 1: JSON-RPC Message Validity tests."""

    def test_tool_result_is_serializable(self):
        """Tool results can be serialized to JSON."""
        from mcp.types import TextContent

        content = TextContent(type="text", text="test message")

        # Should not raise - use model_dump for Pydantic models
        json_str = json.dumps(content.model_dump())
        parsed = json.loads(json_str)

        assert parsed["type"] == "text"
        assert parsed["text"] == "test message"

    def test_resource_content_is_serializable(self):
        """Resource content can be serialized to JSON."""
        content = "Test resource content @ 2024-01-01T00:00:00"

        # Should not raise
        json_str = json.dumps({"content": content})
        parsed = json.loads(json_str)

        assert parsed["content"] == content


class TestCapabilityNegotiation:
    """Task 0.5: Validate capability negotiation."""

    def test_server_has_initialization_options(self):
        """Server can create initialization options."""
        server = create_spike_server()

        options = server.create_initialization_options()

        # Options should be created without error
        assert options is not None

    def test_server_name_in_options(self):
        """Server name is included in initialization options."""
        server = create_spike_server()

        options = server.create_initialization_options()

        # Server info should include name
        assert options.server_name == "primr-spike"
