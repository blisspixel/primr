"""Minimal MCP server implementation for testing."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mcp.types import (
    CallToolRequest,
    CallToolResult,
    GetPromptRequest,
    GetPromptResult,
    ListPromptsRequest,
    ListPromptsResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
    ReadResourceContents,
    ReadResourceRequest,
    ReadResourceResult,
    TextContent,
)


@dataclass
class ServerResult:
    root: Any


@dataclass
class InitializationOptions:
    server_name: str


Handler = Callable[..., Awaitable[Any]]


class Server:
    """Decorator-based test server with request handler registry."""

    def __init__(self, name: str):
        self.name = name
        self.request_handlers: dict[type, Handler] = {}
        self._callbacks: dict[str, Callable[..., Awaitable[Any]]] = {}

    def list_tools(self) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._callbacks["list_tools"] = fn

            async def handler(_request: ListToolsRequest) -> ServerResult:
                tools = await fn()
                return ServerResult(ListToolsResult(tools=tools))

            self.request_handlers[ListToolsRequest] = handler
            return fn

        return decorator

    def call_tool(self) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._callbacks["call_tool"] = fn

            async def handler(request: CallToolRequest) -> ServerResult:
                try:
                    content = await fn(request.params.name, request.params.arguments or {})
                    return ServerResult(CallToolResult(content=content, isError=False))
                except Exception as exc:
                    return ServerResult(
                        CallToolResult(
                            content=[TextContent(type="text", text=str(exc))],
                            isError=True,
                        )
                    )

            self.request_handlers[CallToolRequest] = handler
            return fn

        return decorator

    def list_resources(self) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._callbacks["list_resources"] = fn

            async def handler(_request: ListResourcesRequest) -> ServerResult:
                resources = await fn()
                return ServerResult(ListResourcesResult(resources=resources))

            self.request_handlers[ListResourcesRequest] = handler
            return fn

        return decorator

    def read_resource(self) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._callbacks["read_resource"] = fn

            async def handler(request: ReadResourceRequest) -> ServerResult:
                raw_contents = await fn(request.params.uri)
                contents = [
                    ReadResourceContents(
                        text=item.content,
                        mimeType=getattr(item, "mime_type", "text/plain"),
                    )
                    for item in raw_contents
                ]
                return ServerResult(ReadResourceResult(contents=contents))

            self.request_handlers[ReadResourceRequest] = handler
            return fn

        return decorator

    def list_prompts(self) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._callbacks["list_prompts"] = fn

            async def handler(_request: ListPromptsRequest) -> ServerResult:
                prompts = await fn()
                return ServerResult(ListPromptsResult(prompts=prompts))

            self.request_handlers[ListPromptsRequest] = handler
            return fn

        return decorator

    def get_prompt(self) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._callbacks["get_prompt"] = fn

            async def handler(request: GetPromptRequest) -> ServerResult:
                messages = await fn(request.params.name, request.params.arguments)
                return ServerResult(GetPromptResult(messages=messages))

            self.request_handlers[GetPromptRequest] = handler
            return fn

        return decorator

    def create_initialization_options(self) -> InitializationOptions:
        return InitializationOptions(server_name=self.name)

    async def run(
        self, _read_stream: Any, _write_stream: Any, _options: InitializationOptions
    ) -> None:
        """No-op run loop for tests."""
        return None
