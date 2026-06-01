"""UTC time helpers that avoid the deprecated ``datetime.utcnow()``.

``datetime.utcnow()`` is deprecated (Python 3.12+) and scheduled for removal —
it returns a *naive* datetime that misleadingly represents UTC. Two replacements
are provided so call sites pick the correct semantics explicitly:

- :func:`utcnow` — timezone-*aware* UTC. Preferred for new code (mirrors the
  ``datetime.now(timezone.utc)`` pattern already used in ``mcp_server``).
- :func:`utcnow_naive` — *naive* UTC, behaviour-identical to the old
  ``datetime.utcnow()``. Required where existing data persists offset-free
  ISO-8601 strings that are compared lexically (the SQLite-backed monitoring,
  tenancy, and knowledge-graph stores): making those aware would append
  ``+00:00`` and silently break ``WHERE ts >= ?`` string comparisons and
  ``fromisoformat`` round-trips against already-stored rows.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """Return the current UTC time as a naive datetime (no tzinfo).

    Drop-in replacement for the deprecated ``datetime.utcnow()`` that preserves
    its exact output (naive, UTC), so offset-free ISO-8601 serialization and
    lexical timestamp comparison keep working unchanged.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
