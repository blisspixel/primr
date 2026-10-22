"""Installer trust-store checks before the explicit self-update operation.

Source: https://discuss.python.org/t/109576. These checks do not change the
application's certificate bundle or silently modify another tool environment.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path


def _repaired_version(value: str, floor: tuple[int, int, int]) -> bool:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    return bool(match and tuple(int(part or 0) for part in match.groups()) >= floor)


def require_safe_update_installer(kind: str) -> None:
    """Reject an affected or unverified updater before dependency downloads."""
    if kind == "uv" or (kind == "pipx" and shutil.which("uv")):
        result = subprocess.run(
            ["uv", "--version"], capture_output=True, text=True, check=True, timeout=10
        )
        parts = result.stdout.split()
        if len(parts) < 2 or parts[0] != "uv" or not _repaired_version(parts[1], (0, 13, 4)):
            raise ValueError("Update UV to 0.13.4 or newer before retrying primr update.")
        if kind == "uv":
            return
    if kind == "pipx":
        receipt = Path(sys.prefix) / "pipx_metadata.json"
        if receipt.is_file() and json.loads(receipt.read_text()).get("backend") == "uv":
            if not shutil.which("uv"):
                raise ValueError("Restore patched UV to PATH before retrying primr update.")
            return
        result = subprocess.run(
            ["pipx", "environment", "--value", "PIPX_SHARED_LIBS"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        if not result.stdout.strip():
            raise ValueError("Cannot verify pipx shared pip; rerun the maintained Primr installer.")
        root = Path(result.stdout.strip())
        paths = [root / "Lib/site-packages", *root.glob("lib/python*/site-packages")]
        versions = [
            dist.version
            for path in paths
            for dist in metadata.distributions(path=[str(path)])
            if dist.metadata["Name"] and dist.metadata["Name"].lower() == "pip"
        ]
    elif kind == "pip":
        try:
            versions = [metadata.version("pip")]
        except metadata.PackageNotFoundError:
            versions = []
    else:
        raise ValueError(
            "Cannot verify the installation tool; rerun the maintained Primr installer."
        )
    if not versions or not all(_repaired_version(value, (26, 2, 2)) for value in versions):
        raise ValueError(
            "Update the selected installer's pip to 26.2.2 or newer before retrying. "
            "The maintained Primr installer provides a hash-verified bootstrap."
        )
