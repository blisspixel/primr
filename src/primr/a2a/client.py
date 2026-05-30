"""A2A client for calling external A2A agents from Primr.

Uses httpx (already a dependency) for HTTP communication.
The a2a-sdk is NOT required for client-side operations — this module
implements the A2A JSON-RPC protocol directly over HTTP.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# A2A JSON-RPC method names
_METHOD_SEND = "message/send"
_METHOD_STREAM = "message/stream"
_METHOD_GET_TASK = "tasks/get"
_METHOD_CANCEL_TASK = "tasks/cancel"

# Well-known agent card path
_AGENT_CARD_PATH = "/.well-known/agent.json"


class A2AError(Exception):
    """Error from A2A protocol interaction."""

    def __init__(self, message: str, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class A2AClient:
    """Client for communicating with external A2A agents.

    Implements the A2A JSON-RPC protocol over HTTP using httpx.
    Does NOT require a2a-sdk — uses raw JSON-RPC.
    """

    def __init__(
        self,
        agent_url: str,
        auth_token: str | None = None,
        timeout: float = 60.0,
    ):
        self.agent_url = agent_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            # follow_redirects=False is deliberate: the MCP delegate_to_agent
            # tool only validates the originally-supplied agent_url. An
            # attacker-controlled public agent can return a 302/307 to a
            # loopback / RFC1918 / cloud metadata endpoint and httpx would
            # otherwise issue the JSON-RPC POST to that internal target.
            # Manual redirect handling with per-hop SSRF validation lives in
            # _follow_redirects_safely().
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=self.timeout,
                follow_redirects=False,
            )
        return self._client

    @staticmethod
    def _validate_url(url: str) -> None:
        """Raise A2AError if the URL fails the central SSRF check."""
        from primr.utils.security import is_safe_url

        safe, reason = is_safe_url(url)
        if not safe:
            raise A2AError(f"A2A request blocked by SSRF guard: {reason} ({url})")

    async def _follow_redirects_safely(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        max_redirects: int = 5,
    ) -> httpx.Response:
        """Issue ``method url`` and follow redirects manually, validating
        each Location target with the SSRF helper before re-requesting.

        Used for non-streaming requests. Streaming (SSE) requests reject any
        redirect outright; a streaming endpoint should not be relocating
        mid-handshake under normal A2A use.
        """
        client = await self._get_client()
        current_url = url
        for _ in range(max_redirects + 1):
            self._validate_url(current_url)
            if method.upper() == "GET":
                resp = await client.get(current_url)
            else:
                resp = await client.post(current_url, json=json_body)
            if resp.status_code not in (301, 302, 303, 307, 308):
                return resp
            location = resp.headers.get("location")
            if not location:
                return resp
            # Resolve relative redirects against the current URL.
            current_url = str(httpx.URL(current_url).join(location))
        raise A2AError(f"A2A request exceeded {max_redirects} redirects (last: {current_url})")

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> A2AClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _build_jsonrpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }

    async def _send_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result."""
        payload = self._build_jsonrpc(method, params)

        logger.debug("A2A RPC %s → %s", method, self.agent_url)
        response = await self._follow_redirects_safely("POST", self.agent_url, json_body=payload)
        response.raise_for_status()

        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            raise A2AError(f"Invalid JSON response from {self.agent_url}: {exc}") from exc
        if "error" in data:
            err = data["error"]
            raise A2AError(
                message=err.get("message", "Unknown A2A error"),
                code=err.get("code"),
                data=err.get("data"),
            )
        return data.get("result", {})

    async def discover(self) -> dict[str, Any]:
        """Fetch the agent card from /.well-known/agent.json.

        Returns:
            Agent card as a dictionary.
        """
        url = f"{self.agent_url}{_AGENT_CARD_PATH}"
        logger.info("Discovering agent at %s", url)
        response = await self._follow_redirects_safely("GET", url)
        response.raise_for_status()
        try:
            card = response.json()
        except (ValueError, TypeError) as exc:
            raise A2AError(f"Invalid JSON in agent card from {url}: {exc}") from exc
        logger.info("Discovered agent: %s (v%s)", card.get("name"), card.get("version"))
        return card

    async def send_message(
        self,
        message: str,
        skill_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to the agent and wait for response.

        Args:
            message: Text message to send.
            skill_id: Optional skill to target.
            context_id: Optional context/conversation ID.
            task_id: Optional existing task ID for follow-up.

        Returns:
            JSON-RPC result dict containing task state and response.
        """
        params: dict[str, Any] = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": str(uuid.uuid4()),
            },
        }
        if skill_id:
            params["message"]["metadata"] = {"skillId": skill_id}
        if context_id:
            params["configuration"] = {"contextId": context_id}
        if task_id:
            params["configuration"] = params.get("configuration", {})
            params["configuration"]["taskId"] = task_id

        return await self._send_rpc(_METHOD_SEND, params)

    async def send_message_streaming(
        self,
        message: str,
        skill_id: str | None = None,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a message and stream SSE events back.

        Yields:
            Parsed JSON event dicts from the SSE stream.
        """
        client = await self._get_client()
        params: dict[str, Any] = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": str(uuid.uuid4()),
            },
        }
        if skill_id:
            params["message"]["metadata"] = {"skillId": skill_id}
        if context_id:
            params["configuration"] = {"contextId": context_id}
        if task_id:
            params["configuration"] = params.get("configuration", {})
            params["configuration"]["taskId"] = task_id

        payload = self._build_jsonrpc(_METHOD_STREAM, params)

        # Streaming requests don't get a manual redirect chain — an SSE
        # handshake redirecting to a different host mid-stream is not part
        # of normal A2A flows, so we just SSRF-check the target and post.
        self._validate_url(self.agent_url)
        async with client.stream("POST", self.agent_url, json=payload) as response:
            response.raise_for_status()
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    for line in event_str.split("\n"):
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip():
                                try:
                                    yield json.loads(data)
                                except json.JSONDecodeError:
                                    logger.warning("Failed to parse SSE data: %s", data[:100])
            # Flush any remaining complete SSE lines in the buffer
            if buffer.strip():
                for line in buffer.split("\n"):
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip():
                            try:
                                yield json.loads(data)
                            except json.JSONDecodeError:
                                logger.warning("Failed to parse trailing SSE data: %s", data[:100])

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Get the current state of a task.

        Args:
            task_id: The A2A task ID.

        Returns:
            Task state dict.
        """
        return await self._send_rpc(_METHOD_GET_TASK, {"id": task_id})

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Cancel a running task.

        Args:
            task_id: The A2A task ID.

        Returns:
            Updated task state dict.
        """
        return await self._send_rpc(_METHOD_CANCEL_TASK, {"id": task_id})
