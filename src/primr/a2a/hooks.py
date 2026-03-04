"""A2A-specific hooks for governance of external agent interactions.

A2AExternalAgentHook: PRE_TOOL_USE hook that validates external agent URLs
    via URLValidator (SSRF protection) and checks cost budget before delegation.

A2AContentSanitizationHook: POST_TOOL_USE hook that sanitizes responses from
    external agents using ContentSanitizer (prompt injection protection).
"""

from __future__ import annotations

import logging
from typing import Any

from primr.agentic.hooks import Hook, HookContext, HookResponse, HookResult, HookType
from primr.mcp_server.security import URLValidator

logger = logging.getLogger(__name__)

# Tool name used by the delegate_to_agent MCP tool
DELEGATE_TOOL_NAME = "delegate_to_agent"


class A2AExternalAgentHook(Hook):
    """PRE_TOOL_USE hook for external A2A agent delegation.

    Validates:
    1. Target agent URL passes SSRF checks (via URLValidator)
    2. Delegation cost stays within budget (if max_cost set)

    Args:
        max_cost_usd: Maximum total delegation budget. None = unlimited.
        priority: Execution priority (default 50, runs before general hooks).
    """

    def __init__(
        self,
        max_cost_usd: float | None = None,
        priority: int = 50,
    ):
        super().__init__(priority=priority, name="A2AExternalAgentHook")
        self.max_cost_usd = max_cost_usd
        self._spent: float = 0.0

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def remaining(self) -> float | None:
        if self.max_cost_usd is None:
            return None
        return max(0.0, self.max_cost_usd - self._spent)

    def record_cost(self, amount: float) -> None:
        """Record cost from a completed delegation."""
        self._spent += amount
        logger.debug("A2A delegation cost: $%.4f (total: $%.4f)", amount, self._spent)

    async def execute(self, context: HookContext) -> HookResponse:
        # Only apply to delegate_to_agent tool calls
        if context.tool_name != DELEGATE_TOOL_NAME:
            return HookResponse(result=HookResult.ALLOW)

        agent_url = context.arguments.get("agent_url", "")

        # 1. SSRF check on the agent URL
        validator = URLValidator()
        url_result = validator.validate(agent_url)
        if not url_result.valid:
            logger.warning(
                "A2A delegation blocked — SSRF: %s → %s",
                agent_url,
                url_result.error_message,
            )
            return HookResponse(
                result=HookResult.BLOCK,
                message=f"Agent URL blocked by security policy: {url_result.error_message}",
            )

        # 2. Cost budget check
        if self.max_cost_usd is not None and self._spent >= self.max_cost_usd:
            logger.warning(
                "A2A delegation blocked — budget exceeded: $%.2f / $%.2f",
                self._spent,
                self.max_cost_usd,
            )
            return HookResponse(
                result=HookResult.BLOCK,
                message=(
                    f"A2A delegation budget exceeded: "
                    f"${self._spent:.2f} spent of ${self.max_cost_usd:.2f} limit"
                ),
            )

        logger.debug("A2A delegation allowed: %s", agent_url)
        return HookResponse(result=HookResult.ALLOW)


class A2AContentSanitizationHook(Hook):
    """POST_TOOL_USE hook for sanitizing external agent responses.

    Runs ContentSanitizer on responses from external A2A agents to detect
    and neutralize prompt injection attempts.

    Args:
        mode: Sanitization mode — "block", "strip", or "warn".
        priority: Execution priority (default 50).
    """

    def __init__(
        self,
        mode: str = "strip",
        priority: int = 50,
    ):
        super().__init__(priority=priority, name="A2AContentSanitizationHook")
        self.mode = mode

    @property
    def hook_type(self) -> HookType:
        return HookType.POST_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        # Only apply to delegate_to_agent results
        if context.tool_name != DELEGATE_TOOL_NAME:
            return HookResponse(result=HookResult.ALLOW)

        result = context.result
        if not result or not isinstance(result, dict):
            return HookResponse(result=HookResult.ALLOW)

        # Extract text content from A2A response
        content = _extract_text_from_a2a_result(result)
        if not content:
            return HookResponse(result=HookResult.ALLOW)

        from primr.utils.content_sanitizer import ContentSanitizer, SanitizationMode

        mode_map = {
            "block": SanitizationMode.BLOCK,
            "strip": SanitizationMode.STRIP,
            "warn": SanitizationMode.WARN,
        }
        sanitizer = ContentSanitizer(mode=mode_map.get(self.mode, SanitizationMode.STRIP))
        sanitization_result = sanitizer.sanitize(content)

        if sanitization_result.blocked:
            logger.warning(
                "A2A response blocked by content sanitizer: %d issue(s)",
                len(sanitization_result.issues),
            )
            return HookResponse(
                result=HookResult.BLOCK,
                message="External agent response blocked: potential prompt injection detected",
            )

        if sanitization_result.was_modified:
            logger.info(
                "A2A response sanitized: %d issue(s) stripped",
                len(sanitization_result.issues),
            )
            # Store sanitized content in mutable_data for caller to use
            context.mutable_data["sanitized_response"] = sanitization_result.sanitized
            return HookResponse(
                result=HookResult.WARN,
                message=f"External agent response sanitized ({len(sanitization_result.issues)} issue(s))",
            )

        return HookResponse(result=HookResult.ALLOW)


def _extract_text_from_a2a_result(result: dict[str, Any]) -> str:
    """Extract text content from an A2A task result.

    A2A responses contain artifacts with parts. This extracts all text parts.
    """
    texts: list[str] = []

    # Check for artifacts in task result
    artifacts = result.get("artifacts", [])
    for artifact in artifacts:
        parts = artifact.get("parts", [])
        for part in parts:
            if part.get("kind") == "text" and "text" in part:
                texts.append(part["text"])

    # Check for status message
    status = result.get("status", {})
    message = status.get("message", {})
    if isinstance(message, dict):
        parts = message.get("parts", [])
        for part in parts:
            if part.get("kind") == "text" and "text" in part:
                texts.append(part["text"])

    return "\n".join(texts)
