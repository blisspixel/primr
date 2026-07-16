"""Immutable first-party verifier asset for generated skill packs.

The generated prose boundary may reference only this exact path, invocation,
and reviewed script body. Keeping the asset separate makes that registry
auditable without mixing its implementation into prose-safety parsing.
"""

from __future__ import annotations

from .markdown_safety import SECURITY_COMMONMARK, commonmark_security_text

VERIFY_ARTIFACT_SCRIPT_PATH = "scripts/verify-artifact.py"
VERIFY_ARTIFACT_INVOCATION = f"Run: python {VERIFY_ARTIFACT_SCRIPT_PATH} <artifact>"

VERIFY_ARTIFACT_SCRIPT = r'''#!/usr/bin/env python3
"""Deterministically verify that an artifact contains substantive UTF-8 text.

Run with a path to the generated artifact. The verifier accepts regular files
only and bounds both file size and text scanned.
"""
import os
import stat
import sys

MIN_PRINTABLE_NONSPACE_CHARS = 40
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_SCANNED_CHARS = 16 * 1024 * 1024
MAX_ARTIFACT_PATH_CHARS = 4096
READ_CHUNK_CHARS = 64 * 1024
WINDOWS_FILENAME_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_DEVICE_NAMES = {
    "aux", "con", "conin$", "conout$", "nul", "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def portable_path_component(component: str) -> bool:
    """Mirror Primr's cross-platform path-component contract."""
    if (
        not isinstance(component, str)
        or not component
        or not component.isascii()
        or len(component) > 255
    ):
        return False
    if component in {".", ".."} or component.endswith((" ", ".")):
        return False
    if any(separator in component for separator in ("/", "\\")):
        return False
    if any(ord(character) < 0x20 for character in component):
        return False
    if not WINDOWS_FILENAME_CHARACTERS.isdisjoint(component):
        return False
    windows_stem = component.split(".", 1)[0].rstrip(" ").casefold()
    return windows_stem not in WINDOWS_DEVICE_NAMES


def local_artifact_path(artifact_path: str) -> str | None:
    """Return a link-free path below a local working directory, or None."""
    if (
        not isinstance(artifact_path, str)
        or not artifact_path
        or len(artifact_path) > MAX_ARTIFACT_PATH_CHARS
    ):
        return None

    components = artifact_path.split("/")
    while components and components[0] == ".":
        components.pop(0)
    if not components:
        return None
    for component in components:
        if not portable_path_component(component):
            return None

    working_directory = os.getcwd()
    if working_directory.startswith(("//", "\\\\")):
        return None
    current = working_directory
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for component in components:
        current = os.path.join(current, component)
        path_status = os.lstat(current)
        if stat.S_ISLNK(path_status.st_mode) or (
            getattr(path_status, "st_file_attributes", 0) & reparse_point
        ):
            return None
    return current


def verify(artifact_path: str) -> bool:
    descriptor = None
    try:
        local_path = local_artifact_path(artifact_path)
        if local_path is None:
            print("Artifact path is not a safe local file.")
            return False
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOINHERIT", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(local_path, flags)
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode):
            print("Artifact is not a regular file.")
            return False
        if file_status.st_size > MAX_ARTIFACT_BYTES:
            print("Artifact exceeds the verification byte limit.")
            return False

        stream = os.fdopen(descriptor, "r", encoding="utf-8", errors="strict")
        descriptor = None
        printable_nonspace_chars = 0
        scanned_chars = 0
        with stream:
            while scanned_chars < MAX_SCANNED_CHARS:
                remaining_chars = MAX_SCANNED_CHARS - scanned_chars
                chunk = stream.read(min(READ_CHUNK_CHARS, remaining_chars))
                if not chunk:
                    break
                scanned_chars += len(chunk)
                printable_nonspace_chars += sum(
                    1 for char in chunk if char.isprintable() and not char.isspace()
                )

            if (
                scanned_chars == MAX_SCANNED_CHARS
                and stream.read(1)
            ):
                print("Artifact exceeds the verification text limit.")
                return False
            if os.fstat(stream.fileno()).st_size > MAX_ARTIFACT_BYTES:
                print("Artifact grew beyond the verification byte limit.")
                return False
    except (OSError, UnicodeError):
        # Exception representations from decoders can contain raw artifact
        # bytes. Keep diagnostics useful without reflecting file contents.
        print("Artifact is not readable bounded UTF-8 text.")
        return False
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                print("Artifact descriptor could not be closed.")

    if printable_nonspace_chars < MIN_PRINTABLE_NONSPACE_CHARS:
        print("Artifact is too small to verify.")
        return False
    print(
        "Artifact verified "
        f"({printable_nonspace_chars} printable non-space characters)."
    )
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify-artifact.py <artifact>")
        sys.exit(2)
    sys.exit(0 if verify(sys.argv[1]) else 1)
'''

_VERIFICATION_SKILL_NAME_MARKERS = ("validat", "review", "check", "verif")


def is_verification_skill_name(name: str) -> bool:
    """Return whether a skill name declares the verification role contract."""
    tokens = name.casefold().split("-")
    return any(
        token.startswith(marker) for token in tokens for marker in _VERIFICATION_SKILL_NAME_MARKERS
    )


def registered_verifier_path_count(text: str) -> int:
    """Count raw or CommonMark-decoded helper-path mentions.

    ``max`` avoids double-counting ordinary visible references while still
    detecting entity-encoded text and path mentions hidden in Markdown syntax.
    """
    raw_count = text.casefold().count(VERIFY_ARTIFACT_SCRIPT_PATH.casefold())
    decoded_count = (
        commonmark_security_text(text).casefold().count(VERIFY_ARTIFACT_SCRIPT_PATH.casefold())
    )
    return max(raw_count, decoded_count)


def _top_level_block_line_indices(
    text: str,
    *,
    token_type: str,
    raw_line: str,
    tag: str | None = None,
) -> list[int]:
    """Locate exact, visible CommonMark blocks at document level.

    Token levels distinguish ordinary top-level blocks from visually similar
    content nested in lists or block quotes. Requiring the exact source line
    also excludes alternate Markdown syntax and inline markup that happens to
    render to the same text.
    """
    lines = text.splitlines()
    indices: list[int] = []
    for token in SECURITY_COMMONMARK.parse(text):
        if token.type != token_type or token.level != 0 or token.map is None:
            continue
        if tag is not None and token.tag != tag:
            continue
        start, end = token.map
        if end != start + 1 or start >= len(lines) or lines[start].strip() != raw_line:
            continue
        indices.append(start)
    return indices


def has_registered_verifier_invocation(body: str) -> bool:
    """Return whether the exact invocation appears once in unfenced workflow prose."""
    lines = body.splitlines()
    if sum(line.strip() == VERIFY_ARTIFACT_INVOCATION for line in lines) != 1:
        return False
    if registered_verifier_path_count(body) != 1:
        return False
    workflow_indices = _top_level_block_line_indices(
        body,
        token_type="heading_open",
        tag="h2",
        raw_line="## Workflow",
    )
    invocation_indices = _top_level_block_line_indices(
        body,
        token_type="paragraph_open",
        raw_line=VERIFY_ARTIFACT_INVOCATION,
    )
    output_indices = _top_level_block_line_indices(
        body,
        token_type="heading_open",
        tag="h2",
        raw_line="## Output Format",
    )
    if not (len(workflow_indices) == len(invocation_indices) == len(output_indices) == 1):
        return False
    workflow_index = workflow_indices[0]
    invocation_index = invocation_indices[0]
    output_index = output_indices[0]
    return workflow_index < invocation_index < output_index


def insert_registered_verifier_invocation(body: str) -> str:
    """Insert the registered invocation before the unfenced output heading."""
    lines = [line for line in body.splitlines() if line.strip() != VERIFY_ARTIFACT_INVOCATION]
    body_without_invocation = "\n".join(lines)
    workflow_indices = _top_level_block_line_indices(
        body_without_invocation,
        token_type="heading_open",
        tag="h2",
        raw_line="## Workflow",
    )
    output_indices = _top_level_block_line_indices(
        body_without_invocation,
        token_type="heading_open",
        tag="h2",
        raw_line="## Output Format",
    )
    if len(workflow_indices) != 1 or len(output_indices) != 1:
        raise ValueError("verification body must have one unfenced workflow and output section")
    if workflow_indices[0] >= output_indices[0]:
        raise ValueError("verification body sections are out of order")
    output_index = output_indices[0]
    lines[output_index:output_index] = [VERIFY_ARTIFACT_INVOCATION, ""]
    result = "\n".join(lines)
    if not has_registered_verifier_invocation(result):
        raise ValueError("verification invocation could not be inserted safely")
    return result


def scan_python_script(relpath: str, content: str) -> str | None:
    """Reject every helper except an exact registered first-party artifact."""
    if relpath != VERIFY_ARTIFACT_SCRIPT_PATH:
        return "path is not registered as a first-party helper"
    if content != VERIFY_ARTIFACT_SCRIPT:
        return "content does not match the registered first-party helper"
    return None


__all__ = [
    "VERIFY_ARTIFACT_INVOCATION",
    "VERIFY_ARTIFACT_SCRIPT",
    "VERIFY_ARTIFACT_SCRIPT_PATH",
    "has_registered_verifier_invocation",
    "insert_registered_verifier_invocation",
    "is_verification_skill_name",
    "registered_verifier_path_count",
    "scan_python_script",
]
