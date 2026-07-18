"""Bounded context and model resolution for lite AI Strategy generation."""

from __future__ import annotations

import os
from collections.abc import Sequence

from primr.config.models import LITE_AI_STRATEGY_MAX_INPUT_BYTES
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


def build_bounded_lite_strategy_prompt(
    strategy_prompt: str,
    context_files: Sequence[str],
) -> str:
    """Build one UTF-8 byte-bounded prompt with company context first."""
    header = b"Use the following context documents to inform your analysis:\n\n"
    suffix = f"\n\n---\n\n{strategy_prompt}".encode()
    if len(header) + len(suffix) > LITE_AI_STRATEGY_MAX_INPUT_BYTES:
        raise ValueError("AI Strategy instructions exceed the governed lite prompt limit")

    payload = bytearray(header)
    remaining = LITE_AI_STRATEGY_MAX_INPUT_BYTES - len(payload) - len(suffix)
    for context_file in context_files:
        separator = b"" if payload == header else b"\n\n"
        block_header = f"--- Context: {os.path.basename(context_file)} ---\n".encode()
        fixed_bytes = len(separator) + len(block_header)
        if fixed_bytes >= remaining:
            logger.info("Lite strategy context limit reached before remaining inputs")
            break
        content_limit = remaining - fixed_bytes
        try:
            with open(context_file, "rb") as handle:
                raw_content = handle.read(content_limit + 1)
        except OSError as exc:
            logger.warning(
                "Failed to read one lite strategy context file (%s)",
                type(exc).__name__,
            )
            continue
        truncated = len(raw_content) > content_limit
        content = raw_content[:content_limit].decode("utf-8", errors="ignore").strip()
        if not content:
            continue
        encoded_content = content.encode()
        payload.extend(separator)
        payload.extend(block_header)
        payload.extend(encoded_content)
        remaining -= fixed_bytes + len(encoded_content)
        if truncated:
            logger.info("Lite strategy context truncated at governed limit")
            break

    payload.extend(suffix)
    if len(payload) > LITE_AI_STRATEGY_MAX_INPUT_BYTES:
        raise AssertionError("Lite strategy prompt exceeded its enforced byte limit")
    return payload.decode("utf-8")


__all__ = ["build_bounded_lite_strategy_prompt"]
