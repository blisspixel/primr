"""Body-safe local readiness checks for the single MCP controller."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from primr.utils.fs_safety import (
    check_dir_atomic_writable,
    path_contains_link_or_reparse_point,
    path_is_linked_or_nonregular_file,
)

READINESS_COMPONENTS = ("controller", "journal", "audit", "output")


class PersistencePreflightError(RuntimeError):
    """Raised when one required local persistence boundary is unavailable."""

    def __init__(self, component: str) -> None:
        self.component = component
        super().__init__(f"{component} persistence preflight failed")


def validate_local_persistence_paths(
    *,
    journal_path: Path,
    audit_path: Path,
    output_root: Path,
    controller_lock_path: Path | None = None,
) -> None:
    """Reject redirected or nonregular persistence paths without mutating them."""
    state_paths = [("journal", journal_path), ("audit", audit_path)]
    if controller_lock_path is not None:
        state_paths.append(("journal", controller_lock_path))
    for component, state_path in state_paths:
        if path_is_linked_or_nonregular_file(state_path) or path_contains_link_or_reparse_point(
            state_path
        ):
            raise PersistencePreflightError(component)
    if path_contains_link_or_reparse_point(output_root):
        raise PersistencePreflightError("output")


def probe_local_persistence(
    *,
    journal_path: Path,
    audit_path: Path,
    output_root: Path,
    controller_lock_path: Path | None = None,
) -> dict[str, bool]:
    """Run bounded atomic-write probes once during controller activation."""
    validate_local_persistence_paths(
        journal_path=journal_path,
        audit_path=audit_path,
        output_root=output_root,
        controller_lock_path=controller_lock_path,
    )

    component_dirs = {
        "journal": journal_path.parent,
        "audit": audit_path.parent,
        "output": output_root,
    }
    probed: dict[Path, bool] = {}
    readiness: dict[str, bool] = {}
    for component, directory in component_dirs.items():
        identity = directory.resolve(strict=False)
        if identity not in probed:
            probed[identity], _ = check_dir_atomic_writable(directory)
        readiness[component] = probed[identity]
        if not readiness[component]:
            raise PersistencePreflightError(component)
    return readiness


def build_readiness_payload(
    *,
    phase: str,
    lease_acquired: bool,
    lifecycle_users: int,
    shutdown_requested: bool,
    admission_open: bool,
    persistence: Mapping[str, bool],
    audit_status: str,
) -> tuple[bool, dict[str, object]]:
    """Return an allowlisted readiness result without diagnostics or paths."""
    checks = {
        "controller": (
            phase == "ready"
            and lease_acquired
            and lifecycle_users > 0
            and not shutdown_requested
            and admission_open
        ),
        "journal": bool(persistence.get("journal", False)),
        "audit": bool(persistence.get("audit", False)) and audit_status == "ok",
        "output": bool(persistence.get("output", False)),
    }
    ready = all(checks.values())
    return ready, {
        "status": "ready" if ready else "not_ready",
        "checks": {
            component: "ready" if checks[component] else "not_ready"
            for component in READINESS_COMPONENTS
        },
    }


__all__ = [
    "PersistencePreflightError",
    "build_readiness_payload",
    "probe_local_persistence",
    "validate_local_persistence_paths",
]
