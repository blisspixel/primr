"""Amazon Bedrock provider.

Uses the provider-agnostic boto3 ``bedrock-runtime`` ``converse`` API, which
normalizes the message schema across every Bedrock model family (Anthropic
Claude, Amazon Nova, Meta Llama, DeepSeek, Google Gemma, OpenAI). This avoids
per-family ``InvokeModel`` payload differences.

Auth uses the standard AWS credential chain (``AWS_ACCESS_KEY_ID`` /
``AWS_SECRET_ACCESS_KEY`` / ``AWS_REGION``, or ``AWS_PROFILE``) or a Bedrock API
key (``AWS_BEARER_TOKEN_BEDROCK``) — boto3 resolves both. The model id is the
Bedrock model or inference-profile id, e.g.
``us.anthropic.claude-sonnet-5`` or ``amazon.nova-2-lite-v1:0``.

``boto3`` is an optional dependency (``pip install 'primr[bedrock]'``); the
provider reports itself unavailable when it is missing so nothing else breaks.
"""

from __future__ import annotations

import os
import time
from typing import Any

from primr.ai.providers.base import (
    ChatResponse,
    CredentialCheck,
    Provider,
    ProviderUnavailableError,
    QuotaExhaustedError,
)
from primr.utils.logging_config import get_logger

logger = get_logger("ai.providers.bedrock")

DEFAULT_RETRIES = 4
BACKOFF_CAP_SECONDS = 60.0
_THROTTLE_MARKERS = ("throttl", "too many requests", "rate exceeded", "serviceunavailable")
_QUOTA_MARKERS = ("quota", "limit exceeded", "no capacity", "not authorized to access")


def _resolve_region() -> str | None:
    """Resolve the AWS region: explicit env first, then boto3's own resolution.

    Falling back to ``boto3.Session().region_name`` means a region set only in
    ``~/.aws/config`` (via ``aws configure``) or an active profile is honored,
    so the provider works with whatever standard AWS setup the user already has.
    """
    env_region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or os.getenv("AWS_BEDROCK_REGION")
    )
    if env_region:
        return env_region
    try:
        import boto3

        return boto3.Session().region_name or None
    except Exception:
        return None


def _has_aws_credentials() -> bool:
    """Best-effort check that some AWS credential is configured (no network)."""
    if os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        return True
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        return True
    if os.getenv("AWS_PROFILE") or os.getenv("AWS_ROLE_ARN"):
        return True
    # Fall back to boto3's own resolution (shared config file, SSO, IMDS).
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:
        return False


class BedrockProvider(Provider):
    """Provider for Amazon Bedrock via the boto3 ``converse`` API."""

    def __init__(self, *, name: str = "bedrock") -> None:
        super().__init__(name)
        self._runtime: Any = None
        self._control: Any = None

    # -----------------------------------------------------------------
    # Availability + lazy clients
    # -----------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            import boto3  # noqa: F401
        except ImportError:
            return False
        if _resolve_region() is None:
            return False
        return _has_aws_credentials()

    def _runtime_client(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        try:
            import boto3
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'boto3' package is required for the Bedrock provider. "
                "Install it with: pip install 'primr[bedrock]'"
            ) from exc
        region = _resolve_region()
        if region is None:
            raise ProviderUnavailableError(
                "No AWS region configured. Set AWS_REGION for the Bedrock provider."
            )
        self._runtime = boto3.client("bedrock-runtime", region_name=region)
        return self._runtime

    def _control_client(self) -> Any:
        if self._control is not None:
            return self._control
        import boto3

        self._control = boto3.client("bedrock", region_name=_resolve_region())
        return self._control

    # -----------------------------------------------------------------
    # Message translation
    # -----------------------------------------------------------------

    @staticmethod
    def _split_messages(
        messages: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        """Split into Bedrock ``system`` blocks and ``converse`` messages."""
        system_blocks: list[dict[str, str]] = []
        converse_messages: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                if content:
                    system_blocks.append({"text": content})
                continue
            # Bedrock only accepts user/assistant roles in messages.
            norm_role = "assistant" if role == "assistant" else "user"
            converse_messages.append({"role": norm_role, "content": [{"text": content}]})
        return system_blocks, converse_messages

    # -----------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 16_000,
        retries: int = DEFAULT_RETRIES,
        **provider_kwargs: Any,
    ) -> ChatResponse:
        client = self._runtime_client()
        system_blocks, converse_messages = self._split_messages(messages)
        if not converse_messages:
            raise RuntimeError("Bedrock call requires at least one non-system message")

        inference_config: dict[str, Any] = {
            "maxTokens": max_tokens,
            "temperature": temperature,
        }
        request: dict[str, Any] = {
            "modelId": model,
            "messages": converse_messages,
            "inferenceConfig": inference_config,
        }
        if system_blocks:
            request["system"] = system_blocks

        last_error: Exception | None = None
        for attempt in range(1 + retries):
            try:
                response = client.converse(**request)
                text = self._extract_text(response)
                if not text:
                    raise RuntimeError("Bedrock returned an empty response")
                in_tok, out_tok, cached = self._extract_usage(response)
                if in_tok or out_tok:
                    self._record_usage(model, in_tok, out_tok, cached_input_tokens=cached)
                logger.info(
                    "bedrock call complete (model=%s): %d input, %d output tokens",
                    model,
                    in_tok,
                    out_tok,
                )
                return ChatResponse(
                    text=text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cached_input_tokens=cached,
                )
            except Exception as exc:
                last_error = exc
                text = str(exc).lower()
                if any(marker in text for marker in _QUOTA_MARKERS):
                    raise QuotaExhaustedError(
                        "Bedrock quota/authorization error. Check model access grants, "
                        "service quotas, or billing."
                    ) from exc
                if attempt < retries and any(marker in text for marker in _THROTTLE_MARKERS):
                    wait = min(BACKOFF_CAP_SECONDS, 5.0 * (2**attempt))
                    logger.warning(
                        "Bedrock throttled, waiting %.0fs before retry %d/%d",
                        wait,
                        attempt + 1,
                        retries + 1,
                    )
                    time.sleep(wait)
                    continue
                break

        raise RuntimeError(
            f"Bedrock API call failed after {retries + 1} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            blocks = response["output"]["message"]["content"]
            return "".join(b.get("text", "") for b in blocks).strip()
        except (KeyError, TypeError, IndexError):
            return ""

    @staticmethod
    def _extract_usage(response: Any) -> tuple[int, int, int]:
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        return (
            int(usage.get("inputTokens", 0) or 0),
            int(usage.get("outputTokens", 0) or 0),
            int(usage.get("cacheReadInputTokens", 0) or 0),
        )

    # -----------------------------------------------------------------
    # Credential validation
    # -----------------------------------------------------------------

    def validate_credentials(self) -> CredentialCheck:
        """Auth-only check via the free ``list_foundation_models`` call."""
        try:
            import boto3  # noqa: F401
        except ImportError:
            return CredentialCheck(
                provider=self.name,
                ok=False,
                detail="boto3 not installed (pip install 'primr[bedrock]')",
            )
        if _resolve_region() is None:
            return CredentialCheck(provider=self.name, ok=False, detail="AWS_REGION not set")
        if not _has_aws_credentials():
            return CredentialCheck(
                provider=self.name,
                ok=False,
                detail="no AWS credentials (set AWS keys/profile or AWS_BEARER_TOKEN_BEDROCK)",
            )
        start = time.monotonic()
        try:
            models = self._control_client().list_foundation_models()
            summaries = models.get("modelSummaries", []) if isinstance(models, dict) else []
            latency = int((time.monotonic() - start) * 1000)
            return CredentialCheck(
                provider=self.name,
                ok=True,
                detail=f"authenticated; {len(summaries)} foundation models visible",
                latency_ms=latency,
            )
        except Exception as exc:
            return CredentialCheck(
                provider=self.name,
                ok=False,
                detail=f"{type(exc).__name__}: {str(exc)[:120]}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
