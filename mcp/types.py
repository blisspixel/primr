"""Minimal MCP types used by Primr tests."""

from dataclasses import dataclass, field, fields
from typing import Any


class ModelLike:
    """Simple pydantic-like API for tests."""

    def model_dump(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for f in fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if isinstance(value, list):
                data[f.name] = [v.model_dump() if hasattr(v, "model_dump") else v for v in value]
            elif hasattr(value, "model_dump"):
                data[f.name] = value.model_dump()
            else:
                data[f.name] = value
        return data


@dataclass
class TextContent(ModelLike):
    type: str
    text: str


@dataclass
class Tool(ModelLike):
    name: str
    description: str
    inputSchema: dict[str, Any]  # noqa: N815 - MCP field name


@dataclass
class Resource(ModelLike):
    uri: str
    name: str
    description: str | None = None
    mimeType: str | None = None  # noqa: N815 - MCP field name


@dataclass
class PromptArgument(ModelLike):
    name: str
    description: str | None = None
    required: bool = False


@dataclass
class PromptMessage(ModelLike):
    role: str
    content: TextContent


@dataclass
class Prompt(ModelLike):
    name: str
    description: str | None = None
    arguments: list[PromptArgument] = field(default_factory=list)


@dataclass
class CallToolRequestParams(ModelLike):
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadResourceRequestParams(ModelLike):
    uri: str


@dataclass
class GetPromptRequestParams(ModelLike):
    name: str
    arguments: dict[str, Any] | None = None


@dataclass
class ListToolsRequest(ModelLike):
    method: str


@dataclass
class ListResourcesRequest(ModelLike):
    method: str


@dataclass
class ListPromptsRequest(ModelLike):
    method: str


@dataclass
class CallToolRequest(ModelLike):
    method: str
    params: CallToolRequestParams


@dataclass
class ReadResourceRequest(ModelLike):
    method: str
    params: ReadResourceRequestParams


@dataclass
class GetPromptRequest(ModelLike):
    method: str
    params: GetPromptRequestParams


@dataclass
class ListToolsResult(ModelLike):
    tools: list[Tool]


@dataclass
class ListResourcesResult(ModelLike):
    resources: list[Resource]


@dataclass
class ListPromptsResult(ModelLike):
    prompts: list[Prompt]


@dataclass
class ReadResourceContents(ModelLike):
    text: str
    mimeType: str = "text/plain"  # noqa: N815 - MCP field name


@dataclass
class ReadResourceResult(ModelLike):
    contents: list[ReadResourceContents]


@dataclass
class CallToolResult(ModelLike):
    content: list[TextContent]
    isError: bool = False  # noqa: N815 - MCP field name


@dataclass
class GetPromptResult(ModelLike):
    messages: list[PromptMessage]
