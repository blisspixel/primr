"""Authorize filesystem tool inputs independently of spending and root checks."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from primr.mcp_server.job_store import ResearchJobState
from primr.mcp_server.resource_auth import (
    caller_can_read_report,
    caller_client_id,
    caller_is_local_stdio,
    caller_owns_job_resource,
    is_trusted_local_a2a_context,
)
from primr.mcp_server.security import PathValidationResult
from primr.mcp_server.server_context import MCPServerContext
from primr.utils.fs_safety import path_is_linked_or_nonregular_file


def _local_operator(server: MCPServerContext) -> bool:
    return caller_is_local_stdio(server) or is_trusted_local_a2a_context(server._auth_context)


def _denied() -> PathValidationResult:
    return PathValidationResult(
        valid=False,
        error_type="artifact_access_denied",
        error_message="Artifact is not authorized for this caller",
    )


def _owned_artifacts(
    server: MCPServerContext,
) -> tuple[ResearchJobState | None, list[Path], list[Path]]:
    """Use the existing current-job authority; never infer ownership from paths."""
    job = server.job_store.get_active() or server.job_store.get_latest_terminal()
    if job is None or not caller_owns_job_resource(server, job, caller_client_id(server)):
        return None, [], []
    files = [Path(path).absolute() for path in job.output_paths or [] if isinstance(path, str)]
    roots: set[Path] = set()
    for artifact in files:
        # A UUID job directory is a dedicated boundary. A shared output root
        # or arbitrary parent containing one owned file grants no directory access.
        for parent in artifact.parents:
            if parent.name == job.job_id:
                roots.add(parent)
                break
    return job, files, sorted(roots)


def validate_artifact_input(
    server: MCPServerContext, path: str | None, *, directory: bool = False
) -> PathValidationResult:
    """Require remote report authority and exact owned files or owned job leaves.

    Local operators retain explicit contained artifact reuse. The job store has
    no historical authorization registry, so unknown/retired remote inputs fail
    closed rather than guessing an owner from a directory name.
    """
    if not _local_operator(server) and not caller_can_read_report(server):
        return _denied()
    result: PathValidationResult = server.path_validator.validate(path)
    if not result.valid or result.resolved_path is None or _local_operator(server):
        return result
    _, files, roots = _owned_artifacts(server)
    allowed = (
        any(result.resolved_path.is_relative_to(root) for root in roots)
        if directory
        else result.resolved_path in files
    )
    return result if allowed else _denied()


def validate_artifact_destination(
    server: MCPServerContext, path: str | None, *, default: bool = False
) -> PathValidationResult:
    """Keep remote output in an owned leaf or a fresh server-selected directory."""
    if default and not _local_operator(server):
        # A fresh random leaf cannot overwrite another client's known artifact.
        _, _, roots = _owned_artifacts(server)
        base = roots[0] if roots else server.path_validator.allowed_roots[0]
        path = str(base / str(uuid4()))
        return server.path_validator.validate(path)
    result: PathValidationResult = server.path_validator.validate(path)
    if not result.valid or result.resolved_path is None or _local_operator(server):
        return result
    _, _, roots = _owned_artifacts(server)
    return result if any(result.resolved_path.is_relative_to(root) for root in roots) else _denied()


def register_generated_artifacts(
    server: MCPServerContext, paths: Iterable[str | Path | None]
) -> None:
    """Retain exact ownership for newly produced files of the current job.

    Generation does not create a historical registry or grant access to sibling
    files. Only existing regular outputs inside the current owned UUID boundary
    can be added, including persisted plans that later become tool inputs.
    """
    if _local_operator(server):
        return
    job, existing, roots = _owned_artifacts(server)
    if job is None:
        return
    admitted: list[str] = []
    for path in paths:
        if path is None:
            continue
        result = server.path_validator.validate(str(path))
        candidate = result.resolved_path
        if (
            not result.valid
            or candidate is None
            or not any(candidate.is_relative_to(root) for root in roots)
            or not candidate.is_file()
            or path_is_linked_or_nonregular_file(candidate)
        ):
            raise ValueError("Generated artifact could not be safely registered")
        admitted.append(str(candidate))
    if admitted:
        job.output_paths = list(dict.fromkeys([*(str(path) for path in existing), *admitted]))
        server.job_store.update(job)
