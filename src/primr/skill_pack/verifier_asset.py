"""Immutable first-party verifier asset for generated skill packs.

The generated prose boundary may reference only this exact path, invocation,
and reviewed script body. Keeping the asset separate makes that registry
auditable without mixing its implementation into prose-safety parsing.
"""

from __future__ import annotations

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

__all__ = [
    "VERIFY_ARTIFACT_INVOCATION",
    "VERIFY_ARTIFACT_SCRIPT",
    "VERIFY_ARTIFACT_SCRIPT_PATH",
]
