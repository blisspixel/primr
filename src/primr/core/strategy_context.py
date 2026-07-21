"""Bounded context and model resolution for lite AI Strategy generation."""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from primr.config.models import LITE_AI_STRATEGY_MAX_INPUT_BYTES
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)

VENDOR_CONTEXT_MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class VendorContextSnapshot:
    """One accepted source and its private, short-lived stable copy."""

    source_path: str
    snapshot_path: str


@contextmanager
def stable_vendor_context_snapshots(
    context_files: Sequence[str],
    *,
    max_bytes: int = VENDOR_CONTEXT_MAX_BYTES,
) -> Iterator[tuple[VendorContextSnapshot, ...]]:
    """Yield verified private snapshots for safe optional vendor inputs."""

    from primr.core.trusted_report import (
        ReportSnapshotError,
        stable_report_snapshot,
        validate_trusted_report,
    )
    from primr.utils.observability import log_structured

    accepted: list[VendorContextSnapshot] = []
    with TemporaryDirectory(prefix="primr-vendor-context-") as temp_dir, ExitStack() as stack:
        for source_value in dict.fromkeys(context_files):
            try:
                trusted = validate_trusted_report(source_value, max_bytes=max_bytes)
                snapshot = stack.enter_context(stable_report_snapshot(trusted, temp_dir))
            except (OSError, ReportSnapshotError) as exc:
                logger.warning(
                    "Optional vendor strategy context rejected: failure_type=%s",
                    type(exc).__name__,
                )
                log_structured(
                    "warning",
                    "Vendor strategy context rejected",
                    reason="unsafe_or_unstable",
                    failure_type=type(exc).__name__,
                )
                continue
            accepted.append(
                VendorContextSnapshot(
                    source_path=str(trusted.path),
                    snapshot_path=str(snapshot),
                )
            )
        yield tuple(accepted)


def read_stable_vendor_context_block(
    path_value: str | Path,
    *,
    header: str,
    context_kind: str,
    max_chars: int = 30_000,
) -> str | None:
    """Read bounded UTF-8 vendor context through the shared snapshot seam."""

    from primr.utils.observability import log_structured

    max_bytes = max(1, max_chars * 4 + 4)
    with stable_vendor_context_snapshots([str(path_value)], max_bytes=max_bytes) as snapshots:
        if not snapshots:
            return None
        try:
            content = Path(snapshots[0].snapshot_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            logger.warning(
                "Optional vendor strategy context unreadable: failure_type=%s",
                type(exc).__name__,
            )
            return None
    truncated = len(content) > max_chars
    content = content[:max_chars]
    if not content.strip():
        return None
    log_structured(
        "info",
        "Vendor strategy context included",
        context_kind=context_kind,
        characters=len(content),
        truncated=truncated,
    )
    return f"--- {header} ---\n{content}"


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


__all__ = [
    "VendorContextSnapshot",
    "build_bounded_lite_strategy_prompt",
    "read_stable_vendor_context_block",
    "stable_vendor_context_snapshots",
]
