"""Shared sanitizers for provider-availability routing metadata and doctor output.

The availability bridge translates provider/quota state into two operator-facing
surfaces: capability-router metadata and `primr doctor` output. Both must obey
one invariant: no secret, raw endpoint URL, hostname/IP, account id, installed
model name, or control sequence may ever appear, regardless of what an upstream
collector wrote into a snapshot. These functions are the single seam that
enforces it (CLAUDE.md: one way to do each thing) -- previously the logic was
duplicated across `capability_routing.py` and `cli_doctor.py`, which let two
copies of the same Unicode/host-bypass drift apart.

Design: allowlist, not denylist. A value passes only if it is already a benign
code/label; anything else collapses to a fixed safe fallback. Code checks are
ASCII-only on purpose -- `str.isalnum()` is Unicode-wide and would pass homoglyph
or accented host detail.
"""

from __future__ import annotations

import re

_MAX_LABEL_LEN = 80
_ERROR_CODE = "availability_error"
# A model count is a small operational integer; clamp pathological values so a
# crafted snapshot cannot print a 50-digit number into routing metadata/output.
_COUNT_CEILING = 100_000
# A dotted host/IP token: an alphanumeric on both sides of a dot (e.g. "10.0.0.5",
# "example.com"). Matches anywhere, so embedding it among spaces does not hide it.
_DOTTED_HOST_RE = re.compile(r"[A-Za-z0-9]\.[A-Za-z0-9]")


def safe_code(value: str | None) -> str | None:
    """Normalize a short status/error/provider code, or collapse to a safe one.

    Returns ``None`` only for empty input. Otherwise lowercases, maps spaces to
    underscores, and accepts the result only if it is ASCII alphanumeric plus
    ``_`` / ``-`` and within the length bound; anything else (URLs, paths,
    homoglyphs, control chars, overlong text) becomes ``"availability_error"``.
    """
    if not value:
        return None
    code = value.strip().lower().replace(" ", "_")
    if len(code) > _MAX_LABEL_LEN:
        return _ERROR_CODE
    if all(
        character.isascii() and (character.isalnum() or character in {"_", "-"})
        for character in code
    ):
        return code
    return _ERROR_CODE


def safe_code_or(value: object, fallback: str) -> str:
    """``safe_code`` with a non-empty fallback for ``None``/empty/invalid input."""
    if value is None:
        return fallback
    return safe_code(str(value)) or fallback


def safe_count(value: object, *, ceiling: int = _COUNT_CEILING) -> int:
    """Coerce a metadata value to a non-negative, ceiling-clamped integer.

    ``bool`` and non-numeric types map to 0; ``inf``/``nan`` and overflow map to
    0; negatives clamp to 0; large values clamp to ``ceiling`` so output stays
    sane and bounded.
    """
    if isinstance(value, bool):
        return 0
    if not isinstance(value, (bytes, bytearray, float, int, str)):
        return 0
    try:
        count = int(value or 0)
    except (OverflowError, TypeError, ValueError):
        return 0
    return max(0, min(count, ceiling))


def safe_display_label(value: str | None, fallback: str) -> str:
    """Sanitize a human-facing provider display name for terminal output.

    Rejects URLs/paths/``@``, any dotted host/IP token (even when surrounded by
    spaces), non-printable/control sequences, and overlong text, falling back to
    a benign code. A plain name with a trailing period (e.g. ``"Acme Inc."``)
    survives -- it is not a dotted host.
    """
    if not value:
        return fallback
    label = value.strip()
    if not label or len(label) > _MAX_LABEL_LEN:
        return fallback
    if any(marker in label for marker in ("://", "@", "\\", "/")):
        return fallback
    if _DOTTED_HOST_RE.search(label):
        return fallback
    if not label.isprintable():
        return fallback
    return label


def safe_env_label(value: object, fallback: str = "provider key") -> str:
    """Sanitize an environment-variable name (e.g. ``OPENAI_API_KEY``).

    Accepts only ASCII upper-case letters, digits, and ``_`` (the env-var
    convention), requires at least one letter, and bounds length; anything else
    (URLs, lower-case, hostnames) collapses to the fallback.
    """
    if not isinstance(value, str):
        return fallback
    label = value.strip()
    if not label or len(label) > _MAX_LABEL_LEN:
        return fallback
    if not any(character.isalpha() for character in label):
        return fallback
    if all(
        character.isascii() and (character.isupper() or character.isdigit() or character == "_")
        for character in label
    ):
        return label
    return fallback
