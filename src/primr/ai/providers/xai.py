"""xAI provider.

The normal Grok chat path is OpenAI-compatible and inherits from
``OpenAICompatibleProvider``. xAI's Responses API with the ``web_search`` tool
is not a generic chat-completions feature, so it lives here instead of in the
legacy ``grok_client`` wrapper.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from primr.ai.providers.openai_compatible import OpenAICompatibleProvider
from primr.utils.logging_config import get_logger

logger = get_logger("ai.providers.xai")


@dataclass(frozen=True)
class BrowseSummary:
    """Normalized result for xAI browse/search synthesis."""

    text: str
    citations: tuple[str, ...]
    source_url: str
    tool_calls: int
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        """Return the backward-compatible ``grok_browse_and_summarize`` shape."""

        return {
            "text": self.text,
            "citations": list(self.citations),
            "source_url": self.source_url,
            "tool_calls": self.tool_calls,
        }


class XAIProvider(OpenAICompatibleProvider):
    """Provider for xAI Grok chat plus xAI-specific browse/search synthesis."""

    def __init__(
        self,
        *,
        name: str = "xai",
        base_url: str = "https://api.x.ai/v1",
        api_key_env: str = "XAI_API_KEY",
        billing_help_url: str = "https://console.x.ai/",
    ) -> None:
        super().__init__(
            name=name,
            base_url=base_url,
            api_key_env=api_key_env,
            billing_help_url=billing_help_url,
        )
        self._api_key_env = api_key_env
        self._responses_url = f"{base_url.rstrip('/')}/responses"

    def browse_and_summarize(
        self,
        url: str,
        context: str | None = None,
        *,
        model: str,
        max_tokens: int = 2000,
        timeout: float = 90.0,
    ) -> BrowseSummary | None:
        """Ask xAI Responses API to browse/search and summarize a URL."""

        api_key = os.getenv(self._api_key_env)
        if not api_key:
            logger.debug("xAI browse skipped: %s not set", self._api_key_env)
            return None

        try:
            response = httpx.post(
                self._responses_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": self._browse_prompt(url, context),
                    "tools": [{"type": "web_search"}],
                    "max_output_tokens": max_tokens,
                },
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("xAI browse: network error for %s: %s", url, exc)
            return None

        if response.status_code != 200:
            logger.warning(
                "xAI browse: status %s for %s: %s",
                response.status_code,
                url,
                (response.text or "")[:200],
            )
            return None

        try:
            data = response.json()
        except ValueError:
            logger.warning("xAI browse: non-JSON response for %s", url)
            return None

        summary = self._parse_browse_response(url, data)
        if summary is None:
            logger.info("xAI browse: empty body for %s", url)
            return None

        if summary.input_tokens or summary.output_tokens:
            self._record_usage(
                model,
                summary.input_tokens,
                summary.output_tokens,
                cached_input_tokens=summary.cached_input_tokens,
            )

        logger.info(
            "xAI browse: %s - %d chars, %d tool calls, %d citations",
            url,
            len(summary.text),
            summary.tool_calls,
            len(summary.citations),
        )
        return summary

    @staticmethod
    def _browse_prompt(url: str, context: str | None) -> str:
        context_block = f"\n\nAdditional context: {context}" if context else ""
        return (
            f"Use your web search and browse tools to gather content from this URL: {url}\n\n"
            "Summarize what the page says in 200-400 words. Focus on concrete facts: "
            "dates, products, services, leadership, customers, financials, strategy. "
            "If you cannot browse the page directly because it is behind bot protection, "
            "synthesize an equivalent summary from public sources about the same company "
            "or topic, and clearly cite where each fact came from. Do not invent details."
            f"{context_block}"
        )

    @classmethod
    def _parse_browse_response(cls, source_url: str, data: dict[str, Any]) -> BrowseSummary | None:
        text = ""
        citations: list[str] = []
        tool_calls = 0
        for item in data.get("output", []) or []:
            item_type = item.get("type")
            if item_type == "web_search_call":
                tool_calls += 1
                continue
            if item_type != "message":
                continue
            for block in item.get("content", []) or []:
                if block.get("type") not in ("output_text", "text"):
                    continue
                text += block.get("text", "")
                for annotation in block.get("annotations", []) or []:
                    if annotation.get("type") == "url_citation" and annotation.get("url"):
                        citations.append(str(annotation["url"]))

        text = text.strip()
        if not text:
            return None

        usage = data.get("usage") or {}
        return BrowseSummary(
            text=text,
            citations=cls._deduplicate(citations),
            source_url=source_url,
            tool_calls=tool_calls,
            input_tokens=int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
            cached_input_tokens=int(usage.get("cached_tokens") or 0),
        )

    @staticmethod
    def _deduplicate(values: list[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                unique.append(value)
        return tuple(unique)
