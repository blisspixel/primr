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

        class MockResponse:
            def __init__(self, status_code, json_data):
                self.status_code = status_code
                self._json = json_data

            def json(self):
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
                    return MockResponse(r["status_code"], r.get("json"))
                return MockResponse(404, None)

            async def post(self, url, **kwargs):
                content = json.dumps(kwargs.get("json", {})).encode()
                mock_self._requests.append(httpx.Request("POST", url, content=content))
                # Match on base URL (ignore query params)
                key = url
                if key in mock_self._responses:
                    r = mock_self._responses[key]
                    return MockResponse(r["status_code"], r.get("json"))
                return MockResponse(404, None)

            async def aclose(self):
                self.is_closed = True

        self._monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    def add_response(self, url, json=None, status_code=200):
        self._responses[url] = {"json": json, "status_code": status_code}

    def get_request(self):
        return self._requests[-1] if self._requests else None
