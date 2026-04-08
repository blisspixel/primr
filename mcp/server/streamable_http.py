"""Minimal streamable HTTP transport shim."""

from typing import Any


class StreamableHTTPServerTransport:
    def __init__(self, mcp_session_id: str | None = None, is_json_response_enabled: bool = False):
        self.mcp_session_id = mcp_session_id
        self.is_json_response_enabled = is_json_response_enabled

    async def handle_request(self, scope: Any, receive: Any, send: Any) -> None:
        raise NotImplementedError("HTTP transport shim does not implement handle_request")
