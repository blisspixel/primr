#!/usr/bin/env python3
"""Verify that a PyPI release exactly matches locally built distributions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

PayloadFetcher = Callable[[str, str], Mapping[str, Any]]
Sleeper = Callable[[float], None]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def distribution_hashes(dist_dir: Path) -> dict[str, str]:
    """Return hashes for exactly one wheel and one source distribution."""
    files = sorted(path for path in dist_dir.iterdir() if path.is_file())
    wheels = [path for path in files if path.name.endswith(".whl")]
    sdists = [path for path in files if path.name.endswith(".tar.gz")]
    if len(files) != 2 or len(wheels) != 1 or len(sdists) != 1:
        names = ", ".join(path.name for path in files) or "none"
        raise ValueError(
            "Distribution directory must contain exactly one wheel and one source distribution; "
            f"found: {names}"
        )
    return {path.name: _sha256(path) for path in files}


def pypi_hashes(payload: Mapping[str, Any]) -> dict[str, str]:
    """Extract filename-to-SHA-256 mappings from a PyPI version response."""
    urls = payload.get("urls", [])
    if not isinstance(urls, list):
        raise ValueError("PyPI response field 'urls' must be a list")

    hashes: dict[str, str] = {}
    for entry in urls:
        if not isinstance(entry, Mapping):
            raise ValueError("PyPI artifact entry must be an object")
        filename = entry.get("filename")
        digests = entry.get("digests")
        sha256 = digests.get("sha256") if isinstance(digests, Mapping) else None
        if not isinstance(filename, str) or not isinstance(sha256, str):
            raise ValueError("PyPI artifact entry is missing filename or SHA-256")
        if filename in hashes:
            raise ValueError(f"PyPI response contains duplicate artifact: {filename}")
        hashes[filename] = sha256
    return dict(sorted(hashes.items()))


def _fetch_pypi_payload(package: str, version: str) -> Mapping[str, Any]:
    package_segment = urllib.parse.quote(package, safe="")
    version_segment = urllib.parse.quote(version, safe="")
    url = f"https://pypi.org/pypi/{package_segment}/{version_segment}/json"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise ValueError("PyPI response must be a JSON object")
    return payload


def check_existing_release(
    *,
    package: str,
    version: str,
    dist_dir: Path,
    fetch_payload: PayloadFetcher | None = None,
) -> str:
    """Require an existing PyPI version to match, while allowing a 404."""
    local_hashes = distribution_hashes(dist_dir)
    fetch = fetch_payload or _fetch_pypi_payload
    try:
        remote_hashes = pypi_hashes(fetch(package, version))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "absent"
        raise

    if remote_hashes != local_hashes:
        raise RuntimeError(
            "Existing PyPI release does not exactly match local distributions. "
            f"Local files: {sorted(local_hashes)}; PyPI files: {sorted(remote_hashes)}."
        )
    return "matching"


def verify_release_artifacts(
    *,
    package: str,
    version: str,
    dist_dir: Path,
    attempts: int = 6,
    delay_seconds: float = 10.0,
    fetch_payload: PayloadFetcher | None = None,
    sleep: Sleeper | None = None,
) -> dict[str, str]:
    """Wait for PyPI propagation, then require exact filename and hash equality."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    local_hashes = distribution_hashes(dist_dir)
    fetch = fetch_payload or _fetch_pypi_payload
    pause = sleep or time.sleep
    remote_hashes: dict[str, str] = {}
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            remote_hashes = pypi_hashes(fetch(package, version))
            last_error = None
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            remote_hashes = {}

        if remote_hashes == local_hashes:
            return local_hashes
        if attempt < attempts:
            pause(delay_seconds)

    detail = f" Last response error: {last_error}" if last_error else ""
    raise RuntimeError(
        "PyPI artifacts do not match local distributions. "
        f"Local files: {sorted(local_hashes)}; PyPI files: {sorted(remote_hashes)}.{detail}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify PyPI filenames and SHA-256 hashes against a local dist directory."
    )
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    parser.add_argument(
        "--allow-absent",
        action="store_true",
        help="Succeed when the version is absent, but reject any existing mismatch",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.allow_absent:
            state = check_existing_release(
                package=args.package,
                version=args.version,
                dist_dir=args.dist_dir,
            )
            print(f"PyPI pre-publication state for {args.package} {args.version}: {state}")
            return 0
        hashes = verify_release_artifacts(
            package=args.package,
            version=args.version,
            dist_dir=args.dist_dir,
            attempts=args.attempts,
            delay_seconds=args.delay_seconds,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Artifact verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Verified {args.package} {args.version} on PyPI:")
    for filename, sha256 in hashes.items():
        print(f"  {filename}  sha256:{sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
