"""Owned temporary-file helpers for research orchestration."""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress

from primr.utils.logging_config import get_logger
from primr.utils.validators import sanitize_for_filename

logger = get_logger(__name__)


def _cleanup_file_with_retry(filepath: str, max_retries: int = 3, delay: float = 0.5) -> bool:
    """Delete a file, retrying transient Windows lock failures."""
    for attempt in range(max_retries):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.debug("Cleaned up temp file: %s", filepath)
            return True
        except OSError as exc:
            if attempt < max_retries - 1:
                logger.debug(
                    "Cleanup attempt %d failed for %s: %s, retrying...",
                    attempt + 1,
                    filepath,
                    exc,
                )
                time.sleep(delay)
                continue
            logger.warning(
                "Failed to clean up temp file after %d attempts: %s - %s",
                max_retries,
                filepath,
                exc,
            )
            return False
    return False


@contextmanager
def temp_context_file(company_name: str, content: str) -> Generator[str, None, None]:
    """Write content to an owned temporary text file and always clean it up."""
    fd: int | None = None
    filepath: str | None = None
    try:
        safe_name = sanitize_for_filename(company_name.replace(" ", "_"))
        fd, filepath = tempfile.mkstemp(suffix=".txt", prefix=f"{safe_name}_step1_")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
        yield filepath
    finally:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)
        if filepath is not None:
            _cleanup_file_with_retry(filepath)


__all__ = ["temp_context_file"]
