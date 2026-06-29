"""Local artifact fingerprint helpers for eval and calibration manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def artifact_fingerprint(path: Path) -> dict[str, Any]:
    """Return byte size and SHA-256 hash for a local file, or nulls if absent."""

    try:
        size_bytes = path.stat().st_size
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError:
        return {"size_bytes": None, "content_hash": None}
    return {"size_bytes": size_bytes, "content_hash": f"sha256:{hasher.hexdigest()}"}
