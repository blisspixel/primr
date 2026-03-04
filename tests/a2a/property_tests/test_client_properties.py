"""Property-based tests for A2A client."""

import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.a2a.client import A2AClient


class TestJsonRpcProperties:
    """Property tests for JSON-RPC message construction."""

    @given(
        method=st.sampled_from(["message/send", "message/stream", "tasks/get", "tasks/cancel"]),
        params=st.fixed_dictionaries({"key": st.text(max_size=50)}),
    )
    @settings(max_examples=50)
    def test_jsonrpc_message_structure(self, method, params):
        """JSON-RPC messages always have required fields."""
        client = A2AClient(agent_url="http://example.com")
        msg = client._build_jsonrpc(method, params)

        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == method
        assert msg["params"] == params
        assert "id" in msg
        # ID should be valid UUID string
        uuid.UUID(msg["id"])

    @given(method=st.text(min_size=1, max_size=30))
    @settings(max_examples=30)
    def test_jsonrpc_always_has_id(self, method):
        """Every JSON-RPC message gets a unique ID."""
        client = A2AClient(agent_url="http://example.com")
        ids = {client._build_jsonrpc(method, {})["id"] for _ in range(5)}
        assert len(ids) == 5  # All unique
