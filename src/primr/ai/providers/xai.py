"""xAI provider.

The normal Grok text path uses xAI's recommended Responses API through the
shared OpenAI-compatible transport. xAI's ``web_search`` behavior remains here
because it is provider-specific rather than a generic text-generation feature.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from primr.ai.error_policy import extract_retry_after_seconds, is_billing_exhausted
from primr.ai.providers.base import QuotaExhaustedError
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider, _compute_backoff_delay
from primr.utils.logging_config import get_logger

logger = get_logger("ai.providers.xai")
_MAX_BROWSE_RETRIES = 4


def _safe_url_label(url: str) -> str:
    """Return a low-detail URL label for logs without path, query, or userinfo."""

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            return "<unparseable-url>"

        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"

        netloc = host
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is not None:
            netloc = f"{netloc}:{port}"

        return urlunparse((parsed.scheme.lower(), netloc, "", "", "", ""))
    except Exception:
        return "<unparseable-url>"


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
    actual_cost_usd: float | None = None
    response_status: str | None = None
    incomplete_reason: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """Return the backward-compatible ``grok_browse_and_summarize`` shape."""

        return {
            "text": self.text,
            "citations": list(self.citations),
            "source_url": self.source_url,
            "tool_calls": self.tool_calls,
        }


class XAIProvider(OpenAICompatibleProvider):
    """Provider for xAI Responses plus xAI-specific browse/search synthesis."""

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
            api_style="responses",
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
        retries: int = 2,
    ) -> BrowseSummary | None:
        """Ask xAI Responses API to browse/search and summarize a URL."""

        from primr.utils.model_policy import require_model_calls_allowed

        require_model_calls_allowed("xAI browse")
        api_key = os.getenv(self._api_key_env)
        if not api_key:
            logger.debug("xAI browse skipped: API key not configured")
            return None
        url_label = _safe_url_label(url)
        retries = min(max(0, retries), _MAX_BROWSE_RETRIES)
        deadline = time.monotonic() + max(0.0, timeout)
        response: httpx.Response | Any | None = None
        for attempt in range(retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("xAI browse: timeout budget exhausted for %s", url_label)
                return None
            request_timeout = timeout if attempt == 0 else remaining
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
                        "store": False,
                    },
                    timeout=request_timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= retries:
                    logger.warning(
                        "xAI browse: network error for %s after %d attempt(s): %s",
                        url_label,
                        attempt + 1,
                        type(exc).__name__,
                    )
                    return None
                wait = min(_compute_backoff_delay(attempt), max(0.0, deadline - time.monotonic()))
                if wait <= 0:
                    return None
                logger.warning(
                    "xAI browse: transient network error for %s; retrying in %.1fs",
                    url_label,
                    wait,
                )
                time.sleep(wait)
                continue

            response_text = str(getattr(response, "text", "") or "")
            if response.status_code != 200 and (
                response.status_code == 402 or is_billing_exhausted(response_text)
            ):
                raise QuotaExhaustedError(
                    "xai API credits exhausted or spending limit reached. "
                    f"Add credits at {self._billing_help_url} and re-run."
                )
            if response.status_code == 200:
                break
            if response.status_code not in {429, 500, 502, 503, 504} or attempt >= retries:
                logger.warning(
                    "xAI browse: status %s for %s",
                    response.status_code,
                    url_label,
                )
                return None

            retry_error = RuntimeError(f"xAI browse status {response.status_code}")
            retry_error.response = response  # type: ignore[attr-defined]
            retry_after = extract_retry_after_seconds(retry_error)
            wait = retry_after if retry_after is not None else _compute_backoff_delay(attempt)
            wait = min(wait, max(0.0, deadline - time.monotonic()))
            if wait <= 0:
                return None
            logger.warning(
                "xAI browse: transient status %s for %s; retrying in %.1fs",
                response.status_code,
                url_label,
                wait,
            )
            time.sleep(wait)

        if response is None:
            return None

        try:
            data = response.json()
        except ValueError:
            logger.warning("xAI browse: non-JSON response for %s", url_label)
            return None

        summary = self._parse_browse_response(url, data)
        if summary is None:
            logger.info("xAI browse: empty body for %s", url_label)
            return None

        if summary.input_tokens or summary.output_tokens or summary.actual_cost_usd is not None:
            self._record_usage(
                model,
                summary.input_tokens,
                summary.output_tokens,
                cached_input_tokens=summary.cached_input_tokens,
            )

        logger.info(
            "xAI browse: %s - %d chars, %d tool calls, %d citations",
            url_label,
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
        usage = data.get("usage") or {}
        billed_ticks = usage.get("cost_in_usd_ticks")
        input_details = usage.get("input_tokens_details") or {}
        response_status = data.get("status")
        incomplete_details = data.get("incomplete_details") or {}
        if not text and not usage and tool_calls == 0 and response_status is None:
            return None
        return BrowseSummary(
            text=text,
            citations=cls._deduplicate(citations),
            source_url=source_url,
            tool_calls=tool_calls,
            input_tokens=int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
            cached_input_tokens=int(
                input_details.get("cached_tokens") or usage.get("cached_tokens") or 0
            ),
            actual_cost_usd=(
                int(billed_ticks) / 10_000_000_000 if billed_ticks is not None else None
            ),
            response_status=str(response_status) if response_status is not None else None,
            incomplete_reason=(
                str(incomplete_details.get("reason"))
                if incomplete_details.get("reason") is not None
                else None
            ),
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
