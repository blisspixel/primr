"""Safe staged publication for generated skill-pack directories."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import stat
import time
import uuid
from pathlib import Path
from typing import Any

from primr.skill_pack.schema import SkillPackArtifacts
from primr.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

OUTPUT_MARKER_NAME = ".primr-skill-pack-output.json"
_OUTPUT_MARKER_FORMAT = "primr-skill-pack-output"
_OUTPUT_MARKER_VERSION = 1
_MAX_LEGACY_REPORT_BYTES = 8 * 1024 * 1024
_COLLISION_DIGEST_HEX_CHARS = 12


def _marker_payload(
    output_dir: Path,
    company_name: str,
    publication_warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "format": _OUTPUT_MARKER_FORMAT,
        "version": _OUTPUT_MARKER_VERSION,
        "company_name": company_name,
        "output_name": output_dir.name,
        "publication_warnings": list(publication_warnings or []),
    }


def write_output_marker(output_dir: Path, company_name: str) -> None:
    """Write ownership proof inside an isolated, not-yet-published tree."""
    (output_dir / OUTPUT_MARKER_NAME).write_text(
        json.dumps(_marker_payload(output_dir, company_name), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _is_reparse_point(path: Path) -> bool:
    """Return whether a path is a link, junction, or mounted boundary."""
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction()) or path.is_mount()


def _tree_contains_reparse_point(root: Path) -> bool:
    """Inspect an owned tree without following links, mounts, or junctions."""
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if _is_reparse_point(path):
                    return True
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
    return False


def _read_valid_output_marker(output_dir: Path) -> dict[str, object] | None:
    """Read a structurally valid ownership marker without trusting its owner."""
    marker_path = output_dir / OUTPUT_MARKER_NAME
    if not marker_path.is_file() or _is_reparse_point(marker_path):
        return None
    if marker_path.stat().st_size > 4096:
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(marker, dict):
        return None
    try:
        actual_output_name = output_dir.resolve(strict=True).name
    except (OSError, RuntimeError):
        return None
    warnings = marker.get("publication_warnings", [])
    valid = (
        marker.get("format") == _OUTPUT_MARKER_FORMAT
        and marker.get("version") == _OUTPUT_MARKER_VERSION
        and isinstance(marker.get("company_name"), str)
        and bool(marker.get("company_name"))
        and marker.get("output_name") == actual_output_name
        and isinstance(warnings, list)
        and all(isinstance(warning, str) for warning in warnings)
        and set(marker)
        <= {
            "format",
            "version",
            "company_name",
            "output_name",
            "publication_warnings",
        }
    )
    return marker if valid else None


def _has_valid_output_marker(output_dir: Path, company_name: str) -> bool:
    marker = _read_valid_output_marker(output_dir)
    return marker is not None and marker["company_name"] == company_name


def _read_legacy_output_owner(
    output_dir: Path,
    company_token: str,
) -> str | None:
    """Recognize pre-marker Primr output narrowly enough for one migration."""
    report = output_dir / f"{company_token}_Skills_Pack_Report.md"
    if not report.is_file() or _is_reparse_point(report):
        return None
    report_size = report.stat().st_size
    if report_size <= 0 or report_size > _MAX_LEGACY_REPORT_BYTES:
        return None
    try:
        with report.open("r", encoding="utf-8", errors="strict") as stream:
            first_line = stream.readline().rstrip("\r\n")
    except (OSError, UnicodeError):
        return None
    prefix = "# Skills Pack - "
    if not first_line.startswith(prefix) or not first_line.removeprefix(prefix):
        return None
    roles_dir = output_dir / "roles"
    cowork_zip = output_dir / f"{company_token}_Cowork_Pack.zip"
    if not (roles_dir.is_dir() or cowork_zip.is_file()):
        return None
    return first_line.removeprefix(prefix)


def _has_legacy_output_signature(
    output_dir: Path,
    company_name: str,
    company_token: str,
) -> bool:
    return _read_legacy_output_owner(output_dir, company_token) == company_name


def _validate_existing_output_shape(base_output_dir: Path, output_dir: Path) -> None:
    """Reject path substitution before reading or replacing an existing tree."""
    base_resolved = base_output_dir.resolve()
    if output_dir.parent.resolve() != base_resolved:
        raise ValueError("skill-pack output must be a direct child of its base directory")
    if _is_reparse_point(output_dir):
        raise ValueError("refusing to replace a symlink, junction, or mounted output directory")
    if not output_dir.exists():
        return
    if not output_dir.is_dir() or output_dir.resolve().parent != base_resolved:
        raise ValueError("refusing to replace a non-owned skill-pack output path")
    if _tree_contains_reparse_point(output_dir):
        raise ValueError("refusing to replace an output tree containing links or mount points")


def _existing_output_owner(output_dir: Path, company_token: str) -> str | None:
    marker = _read_valid_output_marker(output_dir)
    if marker is not None:
        owner = marker["company_name"]
        return owner if isinstance(owner, str) else None
    return _read_legacy_output_owner(output_dir, company_token)


def resolve_output_name(
    base_output_dir: Path,
    company_name: str,
    company_token: str,
    date_stamp: str,
) -> str:
    """Choose a stable dated name without conflating sanitized companies.

    The familiar unsuffixed name remains canonical. A deterministic digest is
    used only when that canonical path already carries valid Primr ownership
    for another exact company name. Unowned or structurally unsafe conflicts
    still fail closed rather than being silently bypassed.
    """
    canonical_name = f"{company_token}_Skills_Pack_{date_stamp}"
    canonical_dir = base_output_dir / canonical_name
    digest = hashlib.sha256(company_name.encode("utf-8")).hexdigest()[:_COLLISION_DIGEST_HEX_CHARS]
    disambiguated_name = f"{company_token}-{digest}_Skills_Pack_{date_stamp}"
    disambiguated_dir = base_output_dir / disambiguated_name

    _validate_existing_output_shape(base_output_dir, canonical_dir)
    if canonical_dir.exists():
        canonical_owner = _existing_output_owner(canonical_dir, company_token)
        if canonical_owner is None:
            raise ValueError(
                "refusing to replace an output directory without Primr ownership proof"
            )
        if canonical_owner == company_name:
            return canonical_name
        validate_replace_target(
            base_output_dir,
            disambiguated_dir,
            company_name,
            company_token,
        )
        return disambiguated_name

    # Preserve the stable disambiguated identity if the canonical owner was
    # later removed. An unrelated or malformed digest path is never replaced.
    _validate_existing_output_shape(base_output_dir, disambiguated_dir)
    if disambiguated_dir.exists():
        disambiguated_owner = _existing_output_owner(disambiguated_dir, company_token)
        if disambiguated_owner == company_name:
            return disambiguated_name
    return canonical_name


def validate_replace_target(
    base_output_dir: Path,
    output_dir: Path,
    company_name: str,
    company_token: str,
) -> None:
    """Prove an existing dated output is an owned real directory."""
    _validate_existing_output_shape(base_output_dir, output_dir)
    if not output_dir.exists():
        return
    if not (
        _has_valid_output_marker(output_dir, company_name)
        or _has_legacy_output_signature(output_dir, company_name, company_token)
    ):
        raise ValueError("refusing to replace an output directory without Primr ownership proof")


def _remove_readonly_path(function: Any, path: str, error: BaseException) -> None:
    """Let rmtree retry a read-only path without swallowing its failure."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        function(path)
    except OSError:
        raise error from None


def cleanup_owned_tree(path: Path, *, context: str) -> str | None:
    """Retry owned-tree cleanup and return an explicit warning on exhaustion."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            shutil.rmtree(path, onexc=_remove_readonly_path)
            return None
        except Exception as exc:  # cleanup must not turn a committed publish into failure
            last_error = exc
            if attempt < 2:
                time.sleep(0.05 * (attempt + 1))
    error_type = type(last_error).__name__ if last_error is not None else "unknown error"
    return (
        f"{context} cleanup failed after 3 attempts ({error_type}). Quarantined path: {path.name}"
    )


def _rename_with_retry(source: Path, destination: Path) -> None:
    """Retry transient Windows sharing violations around directory renames."""
    for attempt in range(3):
        try:
            source.rename(destination)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))


def publish_staged_output(staged_output: Path, output_dir: Path) -> str | None:
    """Replace an owned dated output only after a complete staged build."""
    backup_dir: Path | None = None
    if output_dir.exists():
        backup_dir = output_dir.parent / f".primr-backup-{uuid.uuid4().hex}"
        _rename_with_retry(output_dir, backup_dir)
    try:
        _rename_with_retry(staged_output, output_dir)
    except Exception:
        if backup_dir is not None and not output_dir.exists():
            try:
                _rename_with_retry(backup_dir, output_dir)
            except Exception as restore_error:
                raise RuntimeError(
                    "skill-pack publication failed and the previous output could not be restored"
                ) from restore_error
        raise
    if backup_dir is not None:
        return cleanup_owned_tree(
            backup_dir,
            context="The new pack is published, but superseded output",
        )
    return None


def record_publication_warning(
    artifacts: SkillPackArtifacts,
    output_dir: Path,
    warning: str,
) -> None:
    """Persist a non-transactional cleanup warning in every handoff surface."""
    artifacts.publication_warnings.append(warning)
    logger.error("%s", warning)

    marker_path = output_dir / OUTPUT_MARKER_NAME
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["publication_warnings"] = list(artifacts.publication_warnings)
        atomic_write_text(marker_path, json.dumps(marker, indent=2, sort_keys=True) + "\n")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        logger.exception("Could not persist publication warning in output marker")

    if artifacts.report_md_path is not None:
        report_path = Path(artifacts.report_md_path)
        try:
            with report_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"\n## Publication Warning\n\n- {warning}\n")
        except OSError:
            logger.exception("Could not persist publication warning in pack report")


def rebase_artifact_paths(
    artifacts: SkillPackArtifacts,
    staged_output: Path,
    output_dir: Path,
) -> None:
    """Update returned paths after the staged directory is published."""

    def _rebase(path_text: str | None) -> str | None:
        if path_text is None:
            return None
        relative = Path(path_text).relative_to(staged_output)
        return str(output_dir / relative)

    artifacts.output_dir = str(output_dir)
    artifacts.claude_tree_root = _rebase(artifacts.claude_tree_root)
    artifacts.cowork_zip_path = _rebase(artifacts.cowork_zip_path)
    artifacts.report_md_path = _rebase(artifacts.report_md_path)
    artifacts.skill_md_paths = [
        str(output_dir / Path(path).relative_to(staged_output)) for path in artifacts.skill_md_paths
    ]


__all__ = [
    "cleanup_owned_tree",
    "publish_staged_output",
    "rebase_artifact_paths",
    "record_publication_warning",
    "resolve_output_name",
    "validate_replace_target",
    "write_output_marker",
]
