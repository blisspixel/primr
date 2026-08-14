"""Shared human and machine rendering for expected CLI command failures."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout

from primr.utils.console import console


def emit_json(obj: dict[str, object]) -> None:
    """Write exactly one formatted JSON object to stdout."""
    print(json.dumps(obj, indent=2, ensure_ascii=False))


@contextmanager
def suppress_json_command_stdout(enabled: bool) -> Iterator[None]:
    """Keep nested human output out of a command's one-object JSON response."""
    if not enabled:
        yield
        return
    with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
        yield


def report_command_error(
    *,
    json_output: bool,
    operation: str,
    error_type: str,
    message: str,
    hints: tuple[str, ...] = (),
    exit_code: int = 1,
) -> int:
    """Render one expected command failure in human or machine form."""
    if json_output:
        payload: dict[str, object] = {
            "schema_version": "primr.command-error.v1",
            "operation": operation,
            "error": True,
            "error_type": error_type,
            "message": message,
        }
        if hints:
            payload["hints"] = list(hints)
        emit_json(payload)
        return exit_code

    console.error(message)
    for hint in hints:
        console.info(hint)
    return exit_code


__all__ = ["emit_json", "report_command_error", "suppress_json_command_stdout"]
