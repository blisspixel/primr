# MCP SDK Notes

In-repo contract memo for how Primr uses the MCP Python SDK. Update this
whenever the SDK pin or a load-bearing integration pattern changes.

## SDK Version

- `mcp>=2.0.0,<3` (pyproject; uv.lock pins the exact version)
- SDK v2 speaks MCP spec revision **2026-07-28** natively and still answers
  the legacy `initialize` handshake, so one server serves both protocol eras.
  `server/discover` is served automatically by the SDK.

## Key API Patterns (v2)

### Server Creation

```python
from mcp.server import Server
from mcp.server.caching import CacheHint

server = Server(
    "primr",
    version=...,            # surfaces in serverInfo / server/discover
    title=..., description=..., instructions=..., website_url=...,
    cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="private"), ...},
)
```

Cache hints are the 2026-07-28 `ttlMs`/`cacheScope` result fields. The runner
stamps them onto list/read results for modern-era clients only; legacy-era
responses omit them.

### Handler Registration

Decorators are gone. Handlers are keyed by method string and take
`(ctx, params)`; they return typed result models directly (no `ServerResult`
wrapper). Primr keeps its internal `(name, arguments) -> list[TextContent]`
dispatcher shapes (audit decorators depend on them) and adapts at the
registration seam:

```python
async def _on_call_tool(_ctx, params: CallToolRequestParams) -> CallToolResult:
    return CallToolResult(content=list(await call_tool(params.name, params.arguments or {})))

server.add_request_handler("tools/call", CallToolRequestParams, _on_call_tool)
```

Registered methods: `tools/list`, `tools/call`, `resources/list`,
`resources/templates/list`, `resources/read`, `prompts/list`, `prompts/get`.
Parameterized `primr://.../by_job/{job_id}` resources are advertised both as
plain listings (back-compat) and as proper resource templates.

### Errors

Handler exceptions are no longer converted into `isError` tool results; they
surface as JSON-RPC errors. Raise deliberately:

```python
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS

raise MCPError(INVALID_PARAMS, f"Unknown tool: {name}")
```

Unknown tool/resource/prompt is `-32602` (Invalid Params) per 2026-07-28; the
old `-32002` resource-not-found code was retired. Primr's in-band application
error codes (`types.MCPErrorCode`, `-32001..-32017`) live inside TextContent
JSON payloads, never on the wire as JSON-RPC errors, and sit in the
implementation-defined range the spec now formally reserves (`-32000..-32019`).

### Types

- Python attribute access is snake_case (`input_schema`, `mime_type`,
  `is_error`, `next_cursor`); the wire stays camelCase via aliases
  (`model_dump(by_alias=True, mode="json")`).
- `Resource.uri` is a plain `str` (v1 used `AnyUrl`).
- `ReadResourceContents` (helper dataclass with `.content`) still exists and
  remains Primr's internal resource-reader return type; the registration
  adapter converts it to `TextResourceContents` (`.text`) inside a
  `ReadResourceResult`.

### Stdio Transport

Unchanged shape:

```python
async with stdio_server() as (read_stream, write_stream):
    await server.run(read_stream, write_stream, server.create_initialization_options())
```

`run()` drives a dual-era loop: the client's first message decides whether the
connection speaks the legacy handshake or the modern stateless envelope.

### Streamable HTTP Transport

`StreamableHTTPServerTransport(mcp_session_id=..., ...)` is gone. Compose:

```python
from mcp.server.streamable_http_manager import (
    StreamableHTTPASGIApp,
    StreamableHTTPSessionManager,
)

session_manager = StreamableHTTPSessionManager(app=server, json_response=False)
asgi_app = StreamableHTTPASGIApp(session_manager)
# The host Starlette app's lifespan MUST enter session_manager.run().
```

Primr wraps `asgi_app` with its own auth middleware and mounts it at `/mcp`
alongside `/healthz`, `/readyz`, and the co-hosted `/a2a` app (server.py).

### Auth Hooks

Unchanged from v1 in the parts Primr uses:

```python
from mcp.server.auth.provider import AccessToken           # + new optional
from mcp.server.auth.middleware.bearer_auth import (       #   resource/subject/claims
    BearerAuthBackend,        # BearerAuthBackend(token_verifier)
    RequireAuthMiddleware,    # RequireAuthMiddleware(app, required_scopes, resource_metadata_url=None)
)
```

`PrimrTokenVerifier` satisfies the `TokenVerifier` protocol structurally via
`async def verify_token(token) -> AccessToken | None`.

## Testing

`Server.request_handlers` (keyed by request class) no longer exists. Tests
invoke handlers through `tests/mcp_server/sdk_compat.py`
(`call_tool_handler`, `read_resource_handler`, ...), which resolves
`server.get_request_handler(method)` and passes `ctx=None` (Primr handlers
read auth from the server's own context variable). For full wire-level checks,
`mcp.client.Client(server)` runs an in-memory modern-era session and
`mcp.shared.memory.create_client_server_memory_streams` +
`ClientSession` exercises the legacy handshake era.
