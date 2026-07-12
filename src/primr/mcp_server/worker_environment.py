"""Least-privilege environment construction for supervised research workers."""

from __future__ import annotations

import os

from primr.config.env import is_supervised_worker_env_allowed


def worker_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Build the minimal runtime environment required by a research worker."""
    parent = os.environ if source is None else source
    environment: dict[str, str] = {}
    for name, value in parent.items():
        if is_supervised_worker_env_allowed(name):
            environment[name] = value
    environment["PRIMR_NO_BANNER"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


__all__ = ["worker_environment"]
