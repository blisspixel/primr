"""Tests for A2A client."""

import json

import httpx
import pytest

from primr.a2a.client import A2AClient, A2AError


class TestA2AClientInit:
    """Tests for A2AClient initialization."""

    def test_strips_trailing_slash(self):
        client = A2AClient(agent_url="http://example.com/")
        assert client.agent_url == "http://example.com"

    def test_stores_auth_token(self):
        client = A2AClient(agent_url="http://example.com", auth_token="secret")
        assert client.auth_token == "secret"

    def test_default_timeout(self):
        client = A2AClient(agent_url="http://example.com")
        assert client.timeout == 60.0


class TestA2AClientJsonRpc:
    """Tests for JSON-RPC message building."""

    def test_build_jsonrpc(self):
        client = A2AClient(agent_url="http://example.com")
        msg = client._build_jsonrpc("test/method", {"key": "value"})
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "test/method"
        assert msg["params"] == {"key": "value"}
        assert "id" in msg


class TestA2AClientDiscover:
    """Tests for agent discovery."""

    @pytest.mark.asyncio
    async def test_discover_success(self, httpx_mock):
        """Discovery returns agent card."""
        card = {
            "name": "TestAgent",
            "version": "1.0.0",
            "url": "http://example.com",
            "skills": [],
        }
        httpx_mock.add_response(
            url="http://example.com/.well-known/agent.json",
            json=card,
        )

        async with A2AClient(agent_url="http://example.com") as client:
            result = await client.discover()

        assert result["name"] == "TestAgent"
        assert result["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_discover_404(self, httpx_mock):
        """Discovery raises on 404."""
        httpx_mock.add_response(
            url="http://example.com/.well-known/agent.json",
            status_code=404,
        )

        async with A2AClient(agent_url="http://example.com") as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.discover()


class TestA2AClientSendMessage:
    """Tests for message sending."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, httpx_mock):
        """Send message returns result."""
        httpx_mock.add_response(
            url="http://example.com",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"status": {"state": "completed"}},
            },
        )

        async with A2AClient(agent_url="http://example.com") as client:
            result = await client.send_message("Hello")

        assert result["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_send_message_with_skill_id(self, httpx_mock):
        """Send message includes skill_id in metadata."""
        httpx_mock.add_response(
            url="http://example.com",
            json={"jsonrpc": "2.0", "id": "1", "result": {}},
        )

        async with A2AClient(agent_url="http://example.com") as client:
            await client.send_message("Test", skill_id="research")

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["params"]["message"]["metadata"]["skillId"] == "research"

    @pytest.mark.asyncio
    async def test_send_message_rpc_error(self, httpx_mock):
        """RPC error raises A2AError."""
        httpx_mock.add_response(
            url="http://example.com",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "error": {"code": -32600, "message": "Invalid request"},
            },
        )

        async with A2AClient(agent_url="http://example.com") as client:
            with pytest.raises(A2AError, match="Invalid request"):
                await client.send_message("Test")


class TestA2AClientTaskManagement:
    """Tests for task management."""

    @pytest.mark.asyncio
    async def test_get_task(self, httpx_mock):
        httpx_mock.add_response(
            url="http://example.com",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"id": "task-1", "status": {"state": "working"}},
            },
        )

        async with A2AClient(agent_url="http://example.com") as client:
            result = await client.get_task("task-1")

        assert result["id"] == "task-1"

    @pytest.mark.asyncio
    async def test_cancel_task(self, httpx_mock):
        httpx_mock.add_response(
            url="http://example.com",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"id": "task-1", "status": {"state": "canceled"}},
            },
        )

        async with A2AClient(agent_url="http://example.com") as client:
            result = await client.cancel_task("task-1")

        assert result["status"]["state"] == "canceled"


class TestA2AClientClose:
    """Tests for client lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Context manager creates and closes client."""
        async with A2AClient(agent_url="http://example.com") as client:
            assert client._client is None  # Lazy init
        # After exit, client should be None or closed
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Closing twice doesn't raise."""
        client = A2AClient(agent_url="http://example.com")
        await client.close()
        await client.close()  # Should not raise


class TestA2AClientJsonDecodeError:
    """Tests for handling invalid JSON responses."""

    @pytest.mark.asyncio
    async def test_discover_invalid_json(self, httpx_mock):
        """Discovery raises A2AError on invalid JSON."""
        httpx_mock.add_response(
            url="http://example.com/.well-known/agent.json",
            raw_text="<html>Not JSON</html>",
        )

        async with A2AClient(agent_url="http://example.com") as client:
            with pytest.raises(A2AError, match="Invalid JSON"):
                await client.discover()

    @pytest.mark.asyncio
    async def test_send_message_invalid_json(self, httpx_mock):
        """RPC call raises A2AError on invalid JSON response."""
        httpx_mock.add_response(
            url="http://example.com",
            raw_text="Server Error",
        )

        async with A2AClient(agent_url="http://example.com") as client:
            with pytest.raises(A2AError, match="Invalid JSON"):
                await client.send_message("Test")

    @pytest.mark.asyncio
    async def test_send_message_empty_result(self, httpx_mock):
        """RPC call with no result key returns empty dict."""
        httpx_mock.add_response(
            url="http://example.com",
            json={"jsonrpc": "2.0", "id": "1"},
        )

        async with A2AClient(agent_url="http://example.com") as client:
            result = await client.send_message("Test")
        assert result == {}


class TestA2AClientContextAndTask:
    """Tests for context_id and task_id parameters."""

    @pytest.mark.asyncio
    async def test_send_message_with_context_id(self, httpx_mock):
        """context_id is included in configuration."""
        httpx_mock.add_response(
            url="http://example.com",
            json={"jsonrpc": "2.0", "id": "1", "result": {}},
        )

        async with A2AClient(agent_url="http://example.com") as client:
            await client.send_message("Test", context_id="ctx-123")

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["params"]["configuration"]["contextId"] == "ctx-123"

    @pytest.mark.asyncio
    async def test_send_message_with_task_id(self, httpx_mock):
        """task_id is included in configuration."""
        httpx_mock.add_response(
            url="http://example.com",
            json={"jsonrpc": "2.0", "id": "1", "result": {}},
        )

        async with A2AClient(agent_url="http://example.com") as client:
            await client.send_message("Test", task_id="task-456")

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["params"]["configuration"]["taskId"] == "task-456"

    @pytest.mark.asyncio
    async def test_auth_header_set(self, httpx_mock):
        """Auth token is set in client headers."""
        httpx_mock.add_response(
            url="http://example.com/.well-known/agent.json",
            json={"name": "Test"},
        )

        async with A2AClient(agent_url="http://example.com", auth_token="tok") as client:
            internal = await client._get_client()
            assert "Bearer tok" in internal._headers.get("Authorization", "")


class TestA2AClientGetClient:
    """Tests for lazy client initialization."""

    @pytest.mark.asyncio
    async def test_get_client_creates_once(self, httpx_mock):
        """_get_client returns same instance on repeated calls."""
        async with A2AClient(agent_url="http://example.com") as client:
            c1 = await client._get_client()
            c2 = await client._get_client()
            assert c1 is c2

    @pytest.mark.asyncio
    async def test_get_client_recreates_after_close(self, httpx_mock):
        """_get_client creates new instance after close."""
        client = A2AClient(agent_url="http://example.com")
        c1 = await client._get_client()
        await client.close()
        c2 = await client._get_client()
        assert c1 is not c2
        await client.close()


@pytest.fixture
def httpx_mock(monkeypatch):
    """Simple httpx mock fixture."""
    return HttpxMock(monkeypatch)


class HttpxMock:
    """Minimal httpx mock for testing."""

    def __init__(self, monkeypatch):
        self._monkeypatch = monkeypatch
        self._responses = {}
        self._requests = []
        self._setup()

    def _setup(self):
        mock_self = self
        from primr.utils.url_security import SafeUrlResolution

        def fake_resolve(url: str) -> SafeUrlResolution:
            return SafeUrlResolution(
                original_url=url,
                request_url=url,
                host_header="example.com",
                sni_hostname=None,
                resolved_ip="93.184.216.34",
            )

        self._monkeypatch.setattr(A2AClient, "_resolve_url", staticmethod(fake_resolve))

        class MockResponse:
            def __init__(self, status_code, json_data, raw_text=None):
                self.status_code = status_code
                self._json = json_data
                self._raw_text = raw_text

            def json(self):
                if self._raw_text is not None:
                    raise ValueError(f"Invalid JSON: {self._raw_text[:50]}")
                return self._json

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"HTTP {self.status_code}",
                        request=httpx.Request("GET", "http://test"),
                        response=httpx.Response(self.status_code),
                    )

        class MockAsyncClient:
            def __init__(self, **kwargs):
                self.is_closed = False
                self._headers = kwargs.get("headers", {})

            async def get(self, url, **kwargs):
                mock_self._requests.append(httpx.Request("GET", url))
                key = url
                if key in mock_self._responses:
                    r = mock_self._responses[key]
                    return MockResponse(r["status_code"], r.get("json"), r.get("raw_text"))
                return MockResponse(404, None)

            async def post(self, url, **kwargs):
                content = json.dumps(kwargs.get("json", {})).encode()
                mock_self._requests.append(httpx.Request("POST", url, content=content))
                key = url
                if key in mock_self._responses:
                    r = mock_self._responses[key]
                    return MockResponse(r["status_code"], r.get("json"), r.get("raw_text"))
                return MockResponse(404, None)

            async def aclose(self):
                self.is_closed = True

        self._monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    def add_response(self, url, json=None, status_code=200, raw_text=None):
        self._responses[url] = {"json": json, "status_code": status_code, "raw_text": raw_text}

    def get_request(self):
        return self._requests[-1] if self._requests else None
