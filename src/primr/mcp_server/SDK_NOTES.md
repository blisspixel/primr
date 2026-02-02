# MCP SDK Notes

Findings from the protocol spike (Task 0).

## SDK Version
- mcp >= 1.0.0 (tested with 1.23.3)

## Key API Patterns

### Server Creation
```python
from mcp.server import Server
server = Server("server-name")
```

### Tool Registration
```python
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [Tool(name="...", description="...", inputSchema={...})]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    return [TextContent(type="text", text="...")]
```

### Resource Registration
```python
from mcp.server.lowlevel.helper_types import ReadResourceContents

@server.list_resources()
async def list_resources() -> list[Resource]:
    return [Resource(uri="...", name="...", mimeType="...")]

@server.read_resource()
async def read_resource(uri: str) -> list[ReadResourceContents]:
    # URI comes in as AnyUrl - convert to string for comparison
    uri_str = str(uri)
    return [ReadResourceContents(content="...", mime_type="text/plain")]
```

### Stdio Transport
```python
from mcp.server.stdio import stdio_server

async with stdio_server() as (read_stream, write_stream):
    await server.run(read_stream, write_stream, server.create_initialization_options())
```

## Important Findings

1. **Result Wrapping**: Handler results are wrapped in `ServerResult`. Access via `.root`.

2. **URI Type**: URIs come in as `AnyUrl` type, not string. Convert with `str(uri)`.

3. **Unknown Tools**: SDK doesn't raise for unknown tools - logs warning and returns error result with `isError=True`.

4. **Resource Return Type**: Use `ReadResourceContents` from `mcp.server.lowlevel.helper_types`, NOT `TextResourceContents` from `mcp.types`.

5. **Stdout Purity**: Server creation and handler execution don't write to stdout - safe for stdio mode.

6. **Initialization Options**: Use `server.create_initialization_options()` - includes `server_name`.

## HTTP Transport (Task 0.4 - DONE)
The MCP SDK provides `StreamableHTTPServerTransport` for HTTP transport.

```python
from mcp.server.streamable_http import StreamableHTTPServerTransport

transport = StreamableHTTPServerTransport(
    mcp_session_id=None,  # Assigned per-connection
    is_json_response_enabled=False,
)
```

## Auth Hooks (Task 0.7 - DONE)
The MCP SDK provides built-in auth support:

```python
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware, BearerAuthBackend

class MyTokenVerifier:
    async def verify_token(self, token: str) -> Optional[AccessToken]:
        # Verify token and return AccessToken or None
        return AccessToken(
            token=token,
            client_id="user-123",
            scopes=["read", "write"],
            expires_at=None,
        )

backend = BearerAuthBackend(MyTokenVerifier())
middleware = RequireAuthMiddleware(backend)
```

AccessToken fields:
- `token`: The original token string
- `client_id`: Unique client identifier (from JWT `sub` claim)
- `scopes`: List of permission scopes
- `expires_at`: Optional expiration timestamp
