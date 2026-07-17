"""Local artifact fingerprint helpers for eval and calibration manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def artifact_bytes_fingerprint(content: bytes) -> dict[str, Any]:
    """Return the canonical fingerprint for an artifact already read as bytes."""

    return {
        "size_bytes": len(content),
        "content_hash": f"sha256:{hashlib.sha256(content).hexdigest()}",
    }


def artifact_fingerprint(path: Path) -> dict[str, Any]:
    """Return byte size and SHA-256 hash for a local file, or nulls if absent."""

    try:
        content = path.read_bytes()
    except OSError:
        return {"size_bytes": None, "content_hash": None}
    return artifact_bytes_fingerprint(content)
